using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows.Threading;

namespace CadToolkit;

public sealed class RuntimeHost : IDisposable
{
    public string Root { get; }
    public string Version { get; }
    public UpdateController Updates {get;}
    public JsonElement Snapshot { get; private set; }=JsonDocument.Parse("{\"rows\":[],\"history\":[]}").RootElement.Clone();
    public string Message { get; private set; }="正在檢查本機連線…";
    public bool IsChecking { get; private set; }
    public event Action? Changed;
    public event Action? WindowsChanged;
    public JsonElement WindowPanel { get; private set; }=JsonDocument.Parse("{\"windows\":[],\"requests\":[],\"confirmations\":[]}").RootElement.Clone();
    readonly string helpers,manifest;
    readonly Dispatcher dispatcher=Dispatcher.CurrentDispatcher;
    readonly string? runtime;
    readonly bool monitoring;
    readonly DispatcherTimer timer;
    readonly DispatcherTimer windowsTimer;
    bool checkingWindows;
    bool windowsChecked,refreshAgain;
    DateTime windowCheckAt;
    readonly CancellationTokenSource stop=new();
    readonly Dictionary<string,DateTime> activationAttempts=new();
    public RuntimeHost(string root,string[] args,bool start=true) {
        Root=root;monitoring=start;
        Updates=new UpdateController(root);Updates.Changed+=()=>{if(dispatcher.CheckAccess())Changed?.Invoke();else dispatcher.BeginInvoke(()=>Changed?.Invoke());};
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
        windowsTimer=new DispatcherTimer{Interval=TimeSpan.FromSeconds(2)};windowsTimer.Tick+=async(_,_)=>await RefreshWindows();if(start)windowsTimer.Start();
    }
    public IEnumerable<JsonElement> Rows=>Snapshot.TryGetProperty("rows",out var rows)?rows.EnumerateArray().Select(LiveRow):Enumerable.Empty<JsonElement>();
    public IEnumerable<JsonElement> History=>Snapshot.TryGetProperty("history",out var rows)?rows.EnumerateArray():Enumerable.Empty<JsonElement>();
    public bool HasFreshWindows=>windowsChecked&&(DateTime.UtcNow-windowCheckAt).TotalSeconds<8;
    public IEnumerable<JsonElement> Windows=>HasFreshWindows&&WindowPanel.TryGetProperty("windows",out var rows)?rows.EnumerateArray():Enumerable.Empty<JsonElement>();
    static string FrameKey(JsonElement w)=>string.Join("/",new[]{"pid","hwnd","processStart","instance_id"}.Select(k=>ExperienceState.Text(w,k)));
    JsonElement LiveRow(JsonElement row){
        if(!ExperienceState.Flag(row,"installed"))return row;
        string kind=ExperienceState.Text(row,"id"),code=ExperienceState.Text(row,"code");string? liveCode=null;
        if(!HasFreshWindows)liveCode="CHECKING";
        else{
            var frames=Windows.Where(w=>ExperienceState.Text(w,"kind")==kind).ToArray();
            if(frames.Length==0){
                var processes=Process.GetProcessesByName(kind=="rhino"?"Rhino":kind=="autocad"?"acad":"Inventor");bool background=processes.Length>0;foreach(var process in processes)process.Dispose();liveCode=background?"BACKGROUND_ONLY":"CAD_NOT_RUNNING";
            }
            else if(code=="READY"){
                var verified=row.TryGetProperty("verified_windows",out var proof)&&proof.ValueKind==JsonValueKind.Array?proof.EnumerateArray().Select(FrameKey).ToHashSet():new HashSet<string>();
                if(!frames.Any(w=>verified.Contains(FrameKey(w))))liveCode="CHECKING";
            }
            else if(code is "CAD_NOT_RUNNING" or "BACKGROUND_ONLY")liveCode="CHECKING";
        }
        if(liveCode==null)return row;
        var value=JsonNode.Parse(row.GetRawText())!.AsObject();value["code"]=liveCode;value["document"]=null;return JsonSerializer.SerializeToElement(value);
    }
    public void ApplyWindowSnapshot(JsonElement next){
        var before=Windows.Select(w=>ExperienceState.Text(w,"window_id")).Order().ToArray();bool wasFresh=HasFreshWindows;
        bool changed=next.GetRawText()!=WindowPanel.GetRawText();WindowPanel=next.Clone();windowsChecked=true;windowCheckAt=DateTime.UtcNow;
        var after=Windows.Select(w=>ExperienceState.Text(w,"window_id")).Order().ToArray();
        if(changed||!wasFresh){WindowsChanged?.Invoke();Changed?.Invoke();}
        if(monitoring&&!before.SequenceEqual(after)){if(IsChecking)refreshAgain=true;else _=Refresh();}
    }
    public async Task RefreshWindows() {
        if(checkingWindows||stop.IsCancellationRequested)return;checkingWindows=true;
        try{ApplyWindowSnapshot(await Run("windows"));}
        catch(Exception ex){windowsChecked=false;Message="視窗檢查："+ex.Message;Changed?.Invoke();}
        finally{checkingWindows=false;}
    }
    public async Task WindowAction(string action,params string[] arguments){await Run(action,arguments);await RefreshWindows();}
    public bool Connected=>Rows.Any(r=>ExperienceState.Text(r,"code")=="READY");
    public async Task<string> OpenCad(string kind) {
        var value=await Run("open-cad","--kind",kind);await RefreshWindows();return ExperienceState.Text(value,"message");
    }
    string? Python() {
        if(runtime!=null&&File.Exists(runtime))return runtime;
        var state=ExperienceState.Read(Root);
        var targets=new List<string>();
        if(state.TryGetProperty("active",out var active))targets.AddRange(active.EnumerateObject().Select(p=>p.Value.GetString()!));
        if(state.TryGetProperty("prepared",out var prepared))targets.AddRange(prepared.EnumerateObject().Select(p=>p.Value.GetString()!));
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
        if(process.ExitCode!=0){string message="無法完成這次要求，請重新檢查或到「安裝與版本」修復元件。";try{using var failure=JsonDocument.Parse(text);if(failure.RootElement.TryGetProperty("error",out var value)&&value.ValueKind==JsonValueKind.String)message=value.GetString()!;}catch(JsonException){}throw new InvalidOperationException(message);}
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
        finally{IsChecking=false;Changed?.Invoke();if(refreshAgain&&!stop.IsCancellationRequested){refreshAgain=false;_=Refresh();}}
    }
    public void Dispose(){timer.Stop();windowsTimer.Stop();Updates.Dispose();stop.Cancel();stop.Dispose();}
}
