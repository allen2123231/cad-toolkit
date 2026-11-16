using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Windows.Threading;

namespace CadToolkit;

public sealed class RuntimeHost : IDisposable
{
    public string Root { get; }
    public string Version { get; }
    public JsonElement Snapshot { get; private set; }=JsonDocument.Parse("{\"rows\":[],\"history\":[]}").RootElement.Clone();
    public string Message { get; private set; }="正在檢查本機連線…";
    public bool IsChecking { get; private set; }
    public event Action? Changed;
    readonly string helpers,manifest;
    readonly string? runtime;
    readonly DispatcherTimer timer;
    readonly CancellationTokenSource stop=new();
    readonly Dictionary<string,DateTime> activationAttempts=new();
    readonly Dictionary<string,DateTime> launches=new();
    public RuntimeHost(string root,string[] args,bool start=true) {
        Root=root;
        using var release=Assembly.GetExecutingAssembly().GetManifestResourceStream("CadToolkitSetup.release.json")!;
        Version=JsonDocument.Parse(release).RootElement.GetProperty("version").GetString()!;
        helpers=Path.Combine(root,"desktop",Version,"engine");Directory.CreateDirectory(helpers);
        var assembly=Assembly.GetExecutingAssembly();
        foreach(var name in assembly.GetManifestResourceNames().Where(n=>n.StartsWith("CadToolkitSetup.engine."))) {
            using var input=assembly.GetManifestResourceStream(name)!;string file=Path.Combine(helpers,name[23..]);
            using var output=File.Create(file);input.CopyTo(output);
        }
        manifest=Path.Combine(helpers,"sources.json");
        using(var input=assembly.GetManifestResourceStream("CadToolkitSetup.sources.json")!)using(var output=File.Create(manifest))input.CopyTo(output);
        runtime=args.FirstOrDefault(a=>a.StartsWith("--runtime="))?[10..];
        timer=new DispatcherTimer{Interval=TimeSpan.FromSeconds(10)};timer.Tick+=async(_,_)=>await Refresh();if(start)timer.Start();
    }
    public IEnumerable<JsonElement> Rows=>Snapshot.TryGetProperty("rows",out var rows)?rows.EnumerateArray():Enumerable.Empty<JsonElement>();
    public IEnumerable<JsonElement> History=>Snapshot.TryGetProperty("history",out var rows)?rows.EnumerateArray():Enumerable.Empty<JsonElement>();
    public bool Connected=>Rows.Any(r=>ExperienceState.Text(r,"code")=="READY");
    public string OpenCad(string kind) {
        if(launches.TryGetValue(kind,out var last)&&(DateTime.Now-last).TotalSeconds<15)return "剛才已發出啟動要求，請等待軟體回應。";
        var processes=Process.GetProcessesByName(kind=="autocad"?"acad":kind=="inventor"?"Inventor":"Rhino");
        bool running=processes.Length>0;foreach(var process in processes)process.Dispose();
        if(running)return ExperienceState.Names[kind]+" 已開啟。若剛安裝外掛，請自行儲存並重開。";
        string? file=ExperienceState.Load(Root).Paths.GetValueOrDefault(kind)??ExperienceState.Detect(kind);
        if(file==null)throw new InvalidOperationException("請先安裝 "+ExperienceState.Names[kind]+"。");
        var previous=ExperienceState.Read(Root,"launches.json");var data=new Dictionary<string,string>();if(previous.ValueKind==JsonValueKind.Object)foreach(var p in previous.EnumerateObject())data[p.Name]=p.Value.ToString();data[kind]=DateTimeOffset.Now.ToString("o");
        Directory.CreateDirectory(Root);File.WriteAllText(Path.Combine(Root,"launches.json"),JsonSerializer.Serialize(data));launches[kind]=DateTime.Now;
        using var started=Process.Start(new ProcessStartInfo(file){UseShellExecute=true});
        return "正在開啟 "+ExperienceState.Names[kind]+"，完成授權或登入後會自動檢查連線。";
    }
    string? Python() {
        if(runtime!=null&&File.Exists(runtime))return runtime;
        var state=ExperienceState.Read(Root);
        var targets=new List<string>();
        if(state.TryGetProperty("active",out var active))targets.AddRange(active.EnumerateObject().Select(p=>p.Value.GetString()!));
        if(state.TryGetProperty("candidate",out var candidate)&&candidate.ValueKind==JsonValueKind.Object)targets.Add(ExperienceState.Text(candidate,"path"));
        foreach(var target in targets){string file=Path.Combine(target,"payload/runtime/python.exe");if(File.Exists(file))return file;}
        var downloads=Path.Combine(Root,"downloads");
        if(Directory.Exists(downloads))foreach(var dir in Directory.EnumerateDirectories(downloads).OrderByDescending(Directory.GetLastWriteTimeUtc)){string file=Path.Combine(dir,"payload/runtime/python.exe");if(File.Exists(file))return file;}
        return null;
    }
    public async Task<JsonElement> Run(string action,params string[] arguments) {
        string python=Python()??throw new InvalidOperationException("請先完成 MCP 元件安裝，程式會自動準備所需環境。");
        var start=new ProcessStartInfo(python){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=System.Text.Encoding.UTF8,StandardErrorEncoding=System.Text.Encoding.UTF8};
        foreach(var arg in new[]{"-X","utf8",Path.Combine(helpers,"runtime.py"),action,"--root",Root,"--manifest",manifest}.Concat(arguments))start.ArgumentList.Add(arg);
        using var process=Process.Start(start)!;var output=process.StandardOutput.ReadToEndAsync();var errors=process.StandardError.ReadToEndAsync();
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(stop.Token);timeout.CancelAfter(TimeSpan.FromSeconds(32));
        try{await process.WaitForExitAsync(timeout.Token);}catch(OperationCanceledException){try{process.Kill(true);}catch(InvalidOperationException){}throw new TimeoutException("連線檢查逾時，稍後會自動重試。");}
        string text=await output;string error=await errors;
        if(process.ExitCode!=0)throw new InvalidOperationException(error.Length>0?error[^Math.Min(500,error.Length)..]:"連線檢查未完成。");
        return JsonDocument.Parse(text).RootElement.Clone();
    }
    public async Task Refresh() {
        if(IsChecking||stop.IsCancellationRequested)return;IsChecking=true;
        try {
            Snapshot=await Run("snapshot");Message="背景監控中 · "+DateTime.Now.ToString("HH:mm:ss");
            foreach(var row in Rows.Where(r=>ExperienceState.Flag(r,"pending")&&ExperienceState.Text(r,"code")=="NOT_ENABLED").ToArray()){
                string kind=ExperienceState.Text(row,"id");if(activationAttempts.TryGetValue(kind,out var last)&&(DateTime.Now-last).TotalMinutes<1)continue;
                activationAttempts[kind]=DateTime.Now;Message="正在完成 "+ExperienceState.Names[kind]+" 自動連線…";Changed?.Invoke();
                try{var service=new ToolkitService(Root){Token=stop.Token};await service.Engine("activate",[kind]);Message=ExperienceState.Names[kind]+" 已啟用，請在 Codex 開啟新對話。";}
                catch(Exception){Message=ExperienceState.Names[kind]+" 等待完成連線，可從安裝與版本頁修復。";}
            }
        }
        catch(Exception ex){Message=ex is InvalidOperationException?ex.Message:"暫時無法檢查，稍後自動重試。";Snapshot=JsonDocument.Parse("{\"rows\":[],\"history\":[]}").RootElement.Clone();}
        finally{IsChecking=false;Changed?.Invoke();}
    }
    public void Dispose(){timer.Stop();stop.Cancel();stop.Dispose();}
}
