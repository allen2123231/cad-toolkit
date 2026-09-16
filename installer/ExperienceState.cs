using System.Diagnostics;
using System.IO;
using System.Text.Json;
using Microsoft.Win32;
namespace CadToolkit;

public sealed class ExperienceState
{
    public int Schema { get; set; } = 2;
    public int Step { get; set; }
    public bool Completed { get; set; }
    public string[] Selected { get; set; } = ["autocad", "inventor", "rhino"];
    public Dictionary<string, string> Paths { get; set; } = new();
    public Dictionary<string, int> GuideSteps { get; set; } = new();
    public bool AiReady { get; set; }
    public bool ReadonlyAcknowledged { get; set; }
    public string LastOperation { get; set; } = "";
    public bool Interrupted { get; set; }
    public static ExperienceState Load(string root) {
        try {
            var path = Path.Combine(root, "ui-state.json");
            if(File.Exists(path)) {
                var value = JsonSerializer.Deserialize<ExperienceState>(File.ReadAllText(path)) ?? new();
                using var json = JsonDocument.Parse(File.ReadAllText(path));
                int schema = json.RootElement.TryGetProperty("Schema", out var schemaValue) ? schemaValue.GetInt32() : 1;
                if(schema < 2 && value.Step >= 5) value.Step++;
                value.Schema = 2;
                value.Step = Math.Clamp(value.Step, 0, 7);
                value.Selected = value.Selected.Where(Names.ContainsKey).Distinct().ToArray();
                if(value.Selected.Length == 0) value.Selected = Names.Keys.ToArray();
                return value;
            }
            var state = Read(root);
            var result = new ExperienceState();
            if(state.TryGetProperty("candidate", out var candidate) && candidate.ValueKind == JsonValueKind.Object) {
                result.Selected = candidate.GetProperty("selected").EnumerateArray().Select(x => x.GetString()!).ToArray();
                result.Step = 4;
            }
            result.Completed = state.TryGetProperty("active", out var active) && active.EnumerateObject().Any();
            return result;
        } catch { return new(); }
    }
    public void Save(string root) {
        Directory.CreateDirectory(root);
        string file = Path.Combine(root, "ui-state.json");
        File.WriteAllText(file + ".tmp", JsonSerializer.Serialize(this)); File.Move(file + ".tmp", file, true);
    }
    public static JsonElement Read(string root, string name = "state.json") {
        try { return JsonDocument.Parse(File.ReadAllText(Path.Combine(root, name))).RootElement.Clone(); }
        catch { return JsonDocument.Parse("{}").RootElement.Clone(); }
    }
    public static Dictionary<string, string> Names = new() { ["autocad"]="AutoCAD", ["inventor"]="Inventor", ["rhino"]="Rhino" };
    public static string Text(JsonElement value, string key, string fallback="") => value.ValueKind == JsonValueKind.Object && value.TryGetProperty(key, out var p) && p.ValueKind != JsonValueKind.Null ? p.ToString() : fallback;
    public static bool Flag(JsonElement value, string key) => value.ValueKind == JsonValueKind.Object && value.TryGetProperty(key, out var p) && p.ValueKind == JsonValueKind.True;
    public static string? Codex() {
        var paths = (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator);
        foreach(var dir in paths) if(File.Exists(Path.Combine(dir, "codex.exe"))) return Path.Combine(dir, "codex.exe");
        var local = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OpenAI/Codex/bin");
        try { return Directory.Exists(local) ? Directory.EnumerateFiles(local, "codex.exe", SearchOption.AllDirectories).FirstOrDefault() : null; } catch { return null; }
    }
    public static string? Detect(string id) {
        string exe = id switch { "autocad"=>"acad.exe", "inventor"=>"Inventor.exe", _=>"Rhino.exe" };
        foreach(var process in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(exe))) {
            using(process) { try { if(process.MainModule?.FileName is string p) return p; } catch { } }
        }
        foreach(var hive in new[] { Registry.LocalMachine, Registry.CurrentUser }) {
            using var key = hive.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\" + exe);
            if(key?.GetValue(null) is string path && File.Exists(path.Trim('"'))) return path.Trim('"');
        }
        string program = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        var candidates = id switch {
            "autocad" => Enumerable.Range(2022, 8).Reverse().Select(v => Path.Combine(program, $"Autodesk/AutoCAD {v}/acad.exe")),
            "inventor" => Enumerable.Range(2022, 8).Reverse().Select(v => Path.Combine(program, $"Autodesk/Inventor {v}/Bin/Inventor.exe")),
            _ => new[] { Path.Combine(program, "Rhino 8/System/Rhino.exe") }.AsEnumerable()
        };
        return candidates.FirstOrDefault(File.Exists);
    }
}
