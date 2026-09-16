using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
namespace CadToolkit;
public sealed class ToolkitService
{
    public string Root { get; }
    string root => Root;
    readonly HttpClient http;
    readonly JsonElement release;
    JsonElement? update;
    public string Version => release.GetProperty("version").GetString()!;
    public JsonElement? Update => update;
    public Action<string> Log = _ => {};
    public Action<string> Report = _ => {};
    public Action<double?> Progress = _ => {};
    public Action<JsonElement> Event = _ => {};
    public CancellationToken Token { get; set; }
    readonly string cancelId = Guid.NewGuid().ToString("N");
    public string CancelFile => Path.Combine(root, "cancel-" + cancelId + ".request");
    public ToolkitService(string root, HttpClient? client = null) {
        Root = root;
        http = client ?? new HttpClient { Timeout = TimeSpan.FromMinutes(20) };
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("CadToolkitSetup.release.json")!;
        release = JsonDocument.Parse(stream).RootElement.Clone();
        http.DefaultRequestHeaders.UserAgent.ParseAdd("CadToolkit/0.2");
    }
    public void RequestStop() { Directory.CreateDirectory(root); File.WriteAllText(CancelFile, "stop"); }
    public async Task Download(string url, string file, string expected)
    {
        if (!url.StartsWith("https://github.com/allen2123231/cad-toolkit/releases/download/", StringComparison.Ordinal))
            throw new InvalidDataException("下載網址不是 CAD Toolkit 發布來源。");
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        var temp = file + "." + Guid.NewGuid().ToString("N") + ".part";
        try
        {
            using var response = await http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, Token); response.EnsureSuccessStatusCode();
            var total = response.Content.Headers.ContentLength;
            using (var input = await response.Content.ReadAsStreamAsync())
            using (var target = File.Create(temp))
            {
                byte[] buffer = new byte[1024 * 1024]; long count = 0; int n;
                while ((n = await input.ReadAsync(buffer, Token)) > 0)
                {
                    await target.WriteAsync(buffer.AsMemory(0, n), Token); count += n; Progress(total.HasValue ? 100.0 * count / total.Value : null);
                    Report($"下載中：{count / 1048576} MB" + (total.HasValue ? $" / {total / 1048576} MB" : ""));
                }
            }
            var actual = await Hash(temp);
            if (!actual.Equals(expected, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("SHA-256 不符，已拒絕檔案。");
            File.Move(temp, file, true);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
    static async Task<string> Hash(string file)
    {
        using var stream = File.OpenRead(file);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream)).ToLowerInvariant();
    }

    public async Task<string> Payload()
    {
        string version = release.GetProperty("version").GetString()!;
        var spec = release.GetProperty("payload"); string hash = spec.GetProperty("sha256").GetString()!;
        var baseDir = Path.Combine(root, "downloads", version + "-" + hash[..12]);
        var destination = Path.Combine(baseDir, "payload");
        if (File.Exists(Path.Combine(destination, "extraction.complete"))) return destination;
        Directory.CreateDirectory(baseDir);
        var archive = Path.Combine(baseDir, "payload.zip");
        var adjacent = Path.Combine(AppContext.BaseDirectory, "cad-toolkit-payload.zip");
        if (!File.Exists(archive) || !string.Equals(await Hash(archive), hash, StringComparison.OrdinalIgnoreCase))
        {
            if (File.Exists(adjacent) && string.Equals(await Hash(adjacent), hash, StringComparison.OrdinalIgnoreCase)) File.Copy(adjacent, archive, true);
            else { Log("下載固定版本安裝套件（含 Python 與 CAD 元件）…"); await Download(spec.GetProperty("url").GetString()!, archive, hash); }
        }
        Report("正在解壓縮安裝環境…");
        var staging = destination + "." + Guid.NewGuid().ToString("N");
        try { await Task.Run(() =>
        {
            Directory.CreateDirectory(staging);
            using var zip = ZipFile.OpenRead(archive);
            foreach (var entry in zip.Entries)
            {
                string path = Path.GetFullPath(Path.Combine(staging, entry.FullName));
                if (!path.StartsWith(staging + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("不安全的壓縮路徑");
                if (string.IsNullOrEmpty(entry.Name)) { Directory.CreateDirectory(path); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(path)!); Token.ThrowIfCancellationRequested(); entry.ExtractToFile(path, true);
            }
            File.WriteAllText(Path.Combine(staging, "extraction.complete"), hash);
            if (Directory.Exists(destination)) Directory.Delete(destination, true);
            Directory.Move(staging, destination);
        }); }
        finally { if (Directory.Exists(staging) && Path.GetFullPath(staging).StartsWith(Path.GetFullPath(baseDir) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) Directory.Delete(staging, true); }
        return destination;
    }

    public async Task<List<JsonElement>> Engine(string action, string[] components, bool active = false)
    {
        string selected = string.Join(",", components);
        var events = new List<JsonElement>();
        if (selected.Length == 0) throw new InvalidOperationException("請至少選擇一套 CAD。");
        string payload = await Payload();
        var start = new ProcessStartInfo(Path.Combine(payload, "runtime", "python.exe")) {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8 };
        foreach(var arg in new[] { "-X", "utf8", Path.Combine(payload, "engine", "manager.py"), action,
                                  "--root", root, "--components", selected }) start.ArgumentList.Add(arg);
        if (action == "install")
        {
            start.ArgumentList.Add("--payload"); start.ArgumentList.Add(payload);
            start.ArgumentList.Add("--setup"); start.ArgumentList.Add(Environment.ProcessPath!);
            start.ArgumentList.Add("--defer-plugin");
        }
        if (active) start.ArgumentList.Add("--active");
        start.ArgumentList.Add("--cancel-file"); start.ArgumentList.Add(CancelFile);
        if (File.Exists(CancelFile)) File.Delete(CancelFile);
        Token.ThrowIfCancellationRequested();
        Log("開始：" + action);
        using var process = Process.Start(start)!;
        var stderr = process.StandardError.ReadToEndAsync();
        while (await process.StandardOutput.ReadLineAsync() is string line)
        {
            try {
                using var doc = JsonDocument.Parse(line); var item = doc.RootElement;
                events.Add(item.Clone()); Event(item.Clone());
                Log(item.ToString());
                Report(item.TryGetProperty("next_action", out var actionText) && actionText.ValueKind == JsonValueKind.String
                    ? actionText.GetString()! : item.GetProperty("message").GetString() ?? "");
                if(item.TryGetProperty("progress", out var progress) && progress.ValueKind == JsonValueKind.Number)
                    Progress(progress.GetDouble());
            }
            catch (JsonException) { Log(line); }
        }
        await process.WaitForExitAsync(); var error = await stderr;
        if (error.Length > 0) Log(error);
        if (process.ExitCode != 0) {
            if(Token.IsCancellationRequested) throw new OperationCanceledException();
            var failure = events.LastOrDefault(e => e.TryGetProperty("error", out var v) && v.ValueKind == JsonValueKind.True);
            throw new InvalidOperationException(failure.ValueKind == JsonValueKind.Undefined ? "作業未通過，請展開詳細資料。" : failure.GetProperty("message").GetString());
        }
        return events;
    }
    public static int CompareVersions(string left, string right)
    {
        var a = left.TrimStart('v').Split('-', 2); var b = right.TrimStart('v').Split('-', 2);
        int core = System.Version.Parse(a[0]).CompareTo(System.Version.Parse(b[0])); if (core != 0) return core;
        if (a.Length != b.Length) return a.Length == 1 ? 1 : -1;
        if (a.Length == 1) return 0;
        var ap = a[1].Split('.'); var bp = b[1].Split('.');
        for (int i = 0; i < Math.Min(ap.Length, bp.Length); i++)
        {
            bool an = int.TryParse(ap[i], out int av), bn = int.TryParse(bp[i], out int bv);
            int c = an && bn ? av.CompareTo(bv) : an != bn ? (an ? -1 : 1) : string.CompareOrdinal(ap[i], bp[i]);
            if (c != 0) return c;
        }
        return ap.Length.CompareTo(bp.Length);
    }
    public async Task CheckUpdate()
    {
        string current = release.GetProperty("version").GetString()!;
        using var data = JsonDocument.Parse(await http.GetStringAsync("https://api.github.com/repos/allen2123231/cad-toolkit/releases?per_page=30", Token));
        var candidates = data.RootElement.EnumerateArray().Where(r => !r.GetProperty("draft").GetBoolean()
            && (current.Contains('-') || !r.GetProperty("prerelease").GetBoolean())).ToList();
        candidates = candidates.Where(r => Regex.IsMatch(r.GetProperty("tag_name").GetString()!, @"^v\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?$")).ToList();
        candidates.Sort((a, b) => CompareVersions(b.GetProperty("tag_name").GetString()!, a.GetProperty("tag_name").GetString()!));
        if (candidates.Count == 0 || CompareVersions(candidates[0].GetProperty("tag_name").GetString()!, current) <= 0)
        { update = null; Log("目前已是此通道最新版本。"); return; }
        var latest = candidates[0];
        var asset = latest.GetProperty("assets").EnumerateArray().FirstOrDefault(a => a.GetProperty("name").GetString() == "release-manifest.json");
        if (asset.ValueKind == JsonValueKind.Undefined) throw new InvalidDataException("新版尚未提供完整安裝清單。");
        string manifestUrl = asset.GetProperty("browser_download_url").GetString()!;
        if (!manifestUrl.StartsWith("https://github.com/allen2123231/cad-toolkit/releases/download/")) throw new InvalidDataException("發布來源不符");
        using var descriptor = JsonDocument.Parse(await http.GetStringAsync(manifestUrl, Token));
        if ("v" + descriptor.RootElement.GetProperty("version").GetString() != latest.GetProperty("tag_name").GetString()) throw new InvalidDataException("版本清單不一致");
        update = descriptor.RootElement.Clone();
        Log("新版可用：" + update.Value.GetProperty("version").GetString() + "。按「一鍵更新」下載並安裝；現有版本會保留。\n" + latest.GetProperty("html_url").GetString());
    }

}
