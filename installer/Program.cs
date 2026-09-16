using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace CadToolkit;

public static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        var app = new Application();
        app.Run(new SetupWindow(args));
    }
}

public sealed class SetupWindow : Window
{
    readonly string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CadToolkit");
    readonly HttpClient http = new() { Timeout = TimeSpan.FromMinutes(20) };
    readonly JsonElement release;
    readonly TextBox output = new() { IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap,
        VerticalScrollBarVisibility = ScrollBarVisibility.Auto, FontFamily = new FontFamily("Consolas"), FontSize = 13,
        Background = new SolidColorBrush(Color.FromRgb(242, 246, 249)), BorderThickness = new Thickness(0), Padding = new Thickness(14) };
    readonly TextBlock status = new() { Text = "先檢查環境，再安裝所需元件。", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 10) };
    readonly Dictionary<string, CheckBox> choices = new();
    readonly List<Button> buttons = new();
    JsonElement? update;
    bool busy;

    public SetupWindow(string[] args)
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("CadToolkitSetup.release.json")!;
        release = JsonDocument.Parse(stream).RootElement.Clone();
        http.DefaultRequestHeaders.UserAgent.ParseAdd("CadToolkit/0.1");
        Title = "CAD Toolkit — 安裝與連線管理"; Width = 1000; Height = 790; MinWidth = 840; MinHeight = 650;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        FontFamily = new FontFamily("Microsoft JhengHei UI"); FontSize = 14;
        Background = Brushes.White;
        var layout = new Grid { Margin = new Thickness(30, 24, 30, 24) };
        layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        layout.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        Content = layout;
        var top = new StackPanel(); layout.Children.Add(top);
        top.Children.Add(new TextBlock { Text = "CAD Toolkit", FontSize = 30, FontWeight = FontWeights.SemiBold, Foreground = new SolidColorBrush(Color.FromRgb(19, 63, 87)) });
        top.Children.Add(new TextBlock { Text = "AutoCAD · Inventor · Rhino   /   " + release.GetProperty("version").GetString(), Foreground = Brushes.DimGray, Margin = new Thickness(0, 6, 0, 18) });
        top.Children.Add(new TextBlock { Text = "環境檢查  →  安裝元件  →  CAD 端設定  →  連線診斷  →  切換 Plugin", FontWeight = FontWeights.SemiBold });
        var select = new WrapPanel { Margin = new Thickness(0, 18, 0, 16) };
        foreach (var (id, label) in new[] { ("autocad", "AutoCAD"), ("inventor", "Inventor"), ("rhino", "Rhino 8") })
        {
            var checkbox = new CheckBox { Content = label, IsChecked = true, Margin = new Thickness(0, 0, 30, 0) };
            choices[id] = checkbox; select.Children.Add(checkbox);
        }
        top.Children.Add(select);
        var actions = new WrapPanel(); top.Children.Add(actions);
        AddButton(actions, "1  環境檢查", EnvironmentCheck);
        AddButton(actions, "2  安裝所選元件", () => Engine("install"));
        AddButton(actions, "3  CAD 端設定", ShowCadSetup);
        AddButton(actions, "4  連線診斷", () => Engine("diagnose"));
        AddButton(actions, "5  切換 Plugin", () => Engine("activate"));
        var maintenance = new WrapPanel(); top.Children.Add(maintenance);
        AddButton(maintenance, "檢查新版", CheckUpdate);
        AddButton(maintenance, "一鍵更新", ApplyUpdate);
        AddButton(maintenance, "還原上一版", () => ConfirmAction("rollback", "還原上一組 MCP 設定？目前文件不會被關閉或儲存。"));
        AddButton(maintenance, "解除安裝", () => ConfirmAction("uninstall", "解除 Toolkit Plugin 並還原舊設定？將保留版本檔案與備份。"));
        AddButton(maintenance, "開啟安裝目錄", () => { Directory.CreateDirectory(root); Open(root); return Task.CompletedTask; });
        top.Children.Add(status);
        Grid.SetRow(output, 1); layout.Children.Add(output);
        Log("首次安裝：自動下載固定版本環境。現有 MCP 設定會保留，直到連線驗證通過並切換。\n" +
            "每次使用：開啟 CAD；Rhino 執行 mcpstart；AutoCAD 載入 dispatcher。\n" +
            "首版為預覽版。尚未經乾淨 Windows 與完整 CAD 組合驗收的項目，請見 GitHub 發布說明。\n");
        Closing += (_, e) => { if (busy) { e.Cancel = true; Log("作業進行中，請等候完成後關閉。"); } };
        var statePath = Path.Combine(root, "state.json");
        if (File.Exists(statePath))
        {
            try {
                using var saved = JsonDocument.Parse(File.ReadAllText(statePath));
                var selected = saved.RootElement.GetProperty("candidate").GetProperty("selected").EnumerateArray().Select(c => c.GetString()).ToArray();
                foreach(var c in choices) c.Value.IsChecked = selected.Contains(c.Key);
            } catch (Exception ex) when (ex is JsonException or InvalidOperationException or KeyNotFoundException) { Log("無法讀取先前元件選擇，請重新勾選。"); }
        }
        var componentArg = args.FirstOrDefault(a => a.StartsWith("--components="));
        if (componentArg is not null)
            foreach(var c in choices) c.Value.IsChecked = componentArg[13..].Split(',').Contains(c.Key);
        if (args.Contains("--uninstall")) Loaded += async (_, _) => await Safe(() => ConfirmAction("uninstall", "解除 Toolkit Plugin 並還原舊設定？"));
        if (args.Contains("--update")) Loaded += async (_, _) => await Safe(async () => { await Engine("install"); await Engine("activate"); });
        var render = args.FirstOrDefault(a => a.StartsWith("--render-preview="));
        if (render is not null) Loaded += async (_, _) => {
            await Task.Delay(300); UpdateLayout();
            var bitmap = new RenderTargetBitmap((int)ActualWidth, (int)ActualHeight, 96, 96, PixelFormats.Pbgra32);
            bitmap.Render(this); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            using(var file = File.Create(render[17..])) encoder.Save(file); Close();
        };
        var verify = args.FirstOrDefault(a => a.StartsWith("--verify-payload-report="));
        if (verify is not null) Loaded += async (_, _) => {
            int exit = 0;
            try {
                var path = await Payload();
                var start = new ProcessStartInfo(Path.Combine(path, "runtime", "python.exe")) { UseShellExecute = false,
                    CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
                start.ArgumentList.Add("--version");
                using var p = Process.Start(start)!;
                string stdout = await p.StandardOutput.ReadToEndAsync(); await p.WaitForExitAsync();
                if(p.ExitCode != 0) throw new Exception(await p.StandardError.ReadToEndAsync());
                File.WriteAllText(verify[24..], JsonSerializer.Serialize(new { passed = true, payload = path, python = stdout.Trim() }));
            } catch(Exception ex) { exit = 1; File.WriteAllText(verify[24..], JsonSerializer.Serialize(new { passed = false, error = ex.Message })); }
            Application.Current.Shutdown(exit);
        };
    }

    void AddButton(Panel panel, string label, Func<Task> handler)
    {
        var button = new Button { Content = label, Padding = new Thickness(12, 9, 12, 9), Margin = new Thickness(0, 0, 8, 8), MinHeight = 36 };
        button.Click += async (_, _) => await Safe(handler);
        buttons.Add(button); panel.Children.Add(button);
    }
    async Task Safe(Func<Task> handler)
    {
        if (busy) return;
        busy = true; buttons.ForEach(b => b.IsEnabled = false); foreach(var c in choices.Values) c.IsEnabled = false;
        try { await handler(); status.Text = "作業完成；詳細狀態請查看下方紀錄。"; }
        catch (Exception ex) { Log("未完成：" + ex.Message); status.Text = "需要處理：" + ex.Message; }
        finally { busy = false; buttons.ForEach(b => b.IsEnabled = true); foreach(var c in choices.Values) c.IsEnabled = true; }
    }
    void Log(string message) { output.AppendText(message + "\n"); output.ScrollToEnd(); }
    static void Open(string path) => Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });

    Task EnvironmentCheck()
    {
        Log("Windows x64：" + Environment.Is64BitOperatingSystem);
        Log("安裝位置：" + root);
        var drive = new DriveInfo(Path.GetPathRoot(root)!);
        Log($"可用空間：{drive.AvailableFreeSpace / 1073741824.0:F1} GB（建議至少 3 GB）");
        foreach(var name in new[] { "acad", "Inventor", "Rhino" })
        {
            var processes = Process.GetProcessesByName(name);
            Log(name + "：" + processes.Length + " 個執行中的程序" + (processes.Length > 1 ? "，診斷前請確認唯一目標。" : ""));
            foreach(var process in processes) process.Dispose();
        }
        var cliDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OpenAI", "Codex", "bin");
        bool found = Directory.Exists(cliDirectory) && Directory.EnumerateFiles(cliDirectory, "codex.exe", SearchOption.AllDirectories).Any();
        if (!found) found = (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator)
            .Any(p => File.Exists(Path.Combine(p, "codex.exe")) || File.Exists(Path.Combine(p, "codex.cmd")));
        Log(found ? "已找到 Codex CLI。" : "尚未找到 Codex CLI，請先安裝或更新 Codex。");
        Log("此步驟未下載或修改環境；MCP 的完整設定檢查會在切換前執行。");
        return Task.CompletedTask;
    }

    async Task Download(string url, string file, string expected)
    {
        if (!url.StartsWith("https://github.com/allen2123231/cad-toolkit/releases/download/", StringComparison.Ordinal))
            throw new InvalidDataException("下載網址不是 CAD Toolkit 發布來源。");
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        var temp = file + "." + Guid.NewGuid().ToString("N") + ".part";
        try
        {
            using var response = await http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead); response.EnsureSuccessStatusCode();
            var total = response.Content.Headers.ContentLength;
            using (var input = await response.Content.ReadAsStreamAsync())
            using (var target = File.Create(temp))
            {
                byte[] buffer = new byte[1024 * 1024]; long count = 0; int n;
                while ((n = await input.ReadAsync(buffer)) > 0)
                {
                    await target.WriteAsync(buffer.AsMemory(0, n)); count += n;
                    status.Text = $"下載中：{count / 1048576} MB" + (total.HasValue ? $" / {total / 1048576} MB" : "");
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

    async Task<string> Payload()
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
        status.Text = "正在解壓縮安裝環境…";
        var staging = destination + "." + Guid.NewGuid().ToString("N");
        await Task.Run(() =>
        {
            Directory.CreateDirectory(staging);
            using var zip = ZipFile.OpenRead(archive);
            foreach (var entry in zip.Entries)
            {
                string path = Path.GetFullPath(Path.Combine(staging, entry.FullName));
                if (!path.StartsWith(staging + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("不安全的壓縮路徑");
                if (string.IsNullOrEmpty(entry.Name)) { Directory.CreateDirectory(path); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(path)!); entry.ExtractToFile(path, true);
            }
            File.WriteAllText(Path.Combine(staging, "extraction.complete"), hash);
            if (Directory.Exists(destination)) Directory.Delete(destination, true);
            Directory.Move(staging, destination);
        });
        return destination;
    }

    async Task Engine(string action)
    {
        string selected = string.Join(",", choices.Where(p => p.Value.IsChecked == true).Select(p => p.Key));
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
        }
        Log("開始：" + action);
        using var process = Process.Start(start)!;
        var stderr = process.StandardError.ReadToEndAsync();
        while (await process.StandardOutput.ReadLineAsync() is string line)
        {
            try {
                using var doc = JsonDocument.Parse(line); var item = doc.RootElement;
                Log(item.GetProperty("message").GetString() ?? "");
                if (item.TryGetProperty("result", out var result))
                {
                    if (result.TryGetProperty("installed", out var installed))
                        Log($"元件已安裝：{installed}　MCP 可啟動：{result.GetProperty("mcp")}　CAD 已啟動：{result.GetProperty("cad")}　橋接已連線：{result.GetProperty("bridge")}");
                    if (result.TryGetProperty("document", out var document) && document.ValueKind != JsonValueKind.Null)
                        Log("目前文件：" + document.ToString());
                    if (result.TryGetProperty("cad", out var cad) && cad.ValueKind == JsonValueKind.Object)
                        foreach(var c in cad.EnumerateObject()) Log(c.Name + "：" + c.Value.GetArrayLength() + " 個執行中的程序");
                    if (result.TryGetProperty("codex", out var codex)) Log("Codex：" + codex.GetString());
                }
                foreach(var key in new[] {"autocad_lisp", "rhino_plugin"})
                    if (item.TryGetProperty(key, out var path)) Log(path.GetString() ?? "");
            }
            catch (JsonException) { Log(line); }
        }
        await process.WaitForExitAsync(); var error = await stderr;
        if (error.Length > 0) Log(error);
        if (process.ExitCode != 0) throw new InvalidOperationException("作業未通過，請依紀錄處理後重試。");
    }

    Task ShowCadSetup()
    {
        string stateFile = Path.Combine(root, "state.json");
        if (!File.Exists(stateFile)) throw new InvalidOperationException("請先安裝元件。");
        using var state = JsonDocument.Parse(File.ReadAllText(stateFile));
        string target = state.RootElement.GetProperty("candidate").GetProperty("path").GetString()!;
        Log("AutoCAD（首次）：APPLOAD 載入以下檔案；可信任位置請依 AutoCAD 提示設定，不停用安全機制。\n" + Path.Combine(target, "autocad", "mcp_dispatch.lsp"));
        Log("Rhino（首次）：保留整個外掛資料夾，將下列 .rhp 拖入 Rhino 註冊。若已有其他版本，請先自行儲存、關閉 Rhino，再切換註冊。\n" + Path.Combine(target, "payload", "cad", "rhino", "rhinomcp.rhp"));
        Log("Rhino（每次）：執行 mcpstart。Inventor：開啟軟體及欲使用的文件。完成後執行連線診斷。\n多程序會要求確認唯一目標，不自動關閉任何 CAD。");
        Open(target); return Task.CompletedTask;
    }
    async Task ConfirmAction(string action, string message)
    {
        if (MessageBox.Show(this, message, "CAD Toolkit", MessageBoxButton.YesNo, MessageBoxImage.Question) == MessageBoxResult.Yes) await Engine(action);
    }

    public static int CompareVersions(string left, string right)
    {
        var a = left.TrimStart('v').Split('-', 2); var b = right.TrimStart('v').Split('-', 2);
        int core = Version.Parse(a[0]).CompareTo(Version.Parse(b[0])); if (core != 0) return core;
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
    async Task CheckUpdate()
    {
        string current = release.GetProperty("version").GetString()!;
        using var data = JsonDocument.Parse(await http.GetStringAsync("https://api.github.com/repos/allen2123231/cad-toolkit/releases?per_page=30"));
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
        using var descriptor = JsonDocument.Parse(await http.GetStringAsync(manifestUrl));
        if ("v" + descriptor.RootElement.GetProperty("version").GetString() != latest.GetProperty("tag_name").GetString()) throw new InvalidDataException("版本清單不一致");
        update = descriptor.RootElement.Clone();
        Log("新版可用：" + update.Value.GetProperty("version").GetString() + "。按「一鍵更新」下載並安裝；現有版本會保留。\n" + latest.GetProperty("html_url").GetString());
    }
    async Task ApplyUpdate()
    {
        if (update is null) await CheckUpdate();
        if (update is null) return;
        var setup = update.Value.GetProperty("setup");
        string filename = Path.Combine(root, "updates", update.Value.GetProperty("version").GetString()!, "CadToolkitSetup.exe");
        await Download(setup.GetProperty("url").GetString()!, filename, setup.GetProperty("sha256").GetString()!);
        // New manager starts after this one exits; loaded CAD plugins remain untouched until explicit activation.
        var launch = new ProcessStartInfo(filename) { UseShellExecute = true };
        launch.ArgumentList.Add("--update");
        launch.ArgumentList.Add("--components=" + string.Join(",", choices.Where(p => p.Value.IsChecked == true).Select(p => p.Key)));
        Process.Start(launch);
        busy = false; Close();
    }
}
