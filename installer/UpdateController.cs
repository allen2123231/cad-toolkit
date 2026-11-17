using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Windows.Threading;

namespace CadToolkit;

public sealed class UpdatePreferences {
    public bool Automatic {get;set;}=true;
    public bool Notifications {get;set;}=true;
    public bool Beta {get;set;}=true;
    public DateTimeOffset? LastAttempt {get;set;}
    public DateTimeOffset? LastSuccess {get;set;}
    public DateTimeOffset? RemindAfter {get;set;}
    public string? SkippedVersion {get;set;}
    public string? NotifiedVersion {get;set;}
}

public sealed class UpdateController : IDisposable {
    readonly string root,file;
    readonly ToolkitService service;
    readonly DispatcherTimer timer=new(){Interval=TimeSpan.FromHours(1)};
    readonly CancellationTokenSource stop=new();
    public UpdatePreferences Preferences {get;}
    public JsonElement? Available {get;private set;}
    public bool Busy {get;private set;}
    public string Message {get;private set;}="尚未檢查更新";
    public string? DownloadedInstaller {get;private set;}
    public event Action? Changed;
    public event Action<string>? Notify;
    public event Action<System.Diagnostics.ProcessStartInfo>? LaunchInstaller;
    public Func<string[],string?> ApplicationBlocker {get;set;}=CloseApplications;
    public string? Version=>Available is JsonElement value?ExperienceState.Text(value,"version"):null;
    public bool Visible=>Version!=null&&Version!=Preferences.SkippedVersion;
    public UpdateController(string root,HttpClient? client=null){
        this.root=root;file=Path.Combine(root,"updates.json");service=new ToolkitService(root,client);
        try{Preferences=JsonSerializer.Deserialize<UpdatePreferences>(File.ReadAllText(file))??new(){Beta=service.Version.Contains('-')};}catch(Exception ex) when(ex is IOException or JsonException){Preferences=new(){Beta=service.Version.Contains('-')};}
        service.Progress=_=>Changed?.Invoke();service.Report=text=>{Message=text;Changed?.Invoke();};
        timer.Tick+=async(_,_)=>await Check();
    }
    public void Start(){timer.Start();_=Check();}
    public void Save(){
        string temp=file+"."+Guid.NewGuid().ToString("N")+".tmp";
        try{
            Directory.CreateDirectory(root);File.WriteAllText(temp,JsonSerializer.Serialize(Preferences));
            for(int attempt=0;;attempt++)try{if(File.Exists(file))File.Replace(temp,file,null);else File.Move(temp,file);break;}
                catch(Exception ex) when(attempt<4&&ex is IOException or UnauthorizedAccessException){Thread.Sleep(40);}
        }catch(Exception ex) when(ex is IOException or UnauthorizedAccessException){Message="更新設定暫時無法儲存，請確認安裝資料夾可寫入。";}
        finally{try{if(File.Exists(temp))File.Delete(temp);}catch(IOException){}Changed?.Invoke();}
    }
    public bool Due(DateTimeOffset now)=>Preferences.Automatic&&(!Preferences.LastAttempt.HasValue||now-Preferences.LastAttempt.Value>=TimeSpan.FromDays(1));
    public async Task Check(bool manual=false){
        if(Busy||(!manual&&!Due(DateTimeOffset.UtcNow)))return;
        Busy=true;Message="正在檢查更新…";Preferences.LastAttempt=DateTimeOffset.UtcNow;Save();
        try{
            using var timeout=CancellationTokenSource.CreateLinkedTokenSource(stop.Token);timeout.CancelAfter(TimeSpan.FromSeconds(25));service.Token=timeout.Token;
            await service.CheckUpdate(Preferences.Beta);Available=service.Update;Preferences.LastSuccess=DateTimeOffset.UtcNow;
            if(manual&&Version!=null){Preferences.SkippedVersion=null;Preferences.RemindAfter=null;}
            Message=Version==null?"目前已是所選通道最新版本":"新版可用："+Version+(Available!.Value.GetProperty("beta").GetBoolean()?" · Beta 測試版":"");
            if(Visible&&Preferences.Notifications&&Preferences.NotifiedVersion!=Version&&(!Preferences.RemindAfter.HasValue||DateTimeOffset.UtcNow>=Preferences.RemindAfter)){
                Preferences.NotifiedVersion=Version;Notify?.Invoke(Version!);
            }
        }catch(Exception ex) when(ex is HttpRequestException or IOException or InvalidDataException or JsonException or InvalidOperationException or OperationCanceledException or KeyNotFoundException or FormatException){Message="暫時無法檢查更新，現有連線不受影響。可稍後按「檢查更新」重試。";}
        finally{Busy=false;Save();}
    }
    public void Later(){Preferences.RemindAfter=DateTimeOffset.UtcNow.AddDays(1);Preferences.NotifiedVersion=null;Save();}
    public void Skip(){Preferences.SkippedVersion=Version;Save();}
    public static string[] Components(string root){
        var state=ExperienceState.Read(root);var selected=new HashSet<string>();
        if(state.TryGetProperty("active",out var active))foreach(var p in active.EnumerateObject())selected.Add(p.Name);
        if(state.TryGetProperty("candidate",out var candidate)&&candidate.ValueKind==JsonValueKind.Object&&candidate.TryGetProperty("selected",out var list))foreach(var item in list.EnumerateArray())selected.Add(item.GetString()!);
        return selected.Where(ExperienceState.Names.ContainsKey).Order().ToArray();
    }
    public static string? CloseApplications(string[] selected){
        var names=new List<string>();foreach(string kind in selected){var processes=Process.GetProcessesByName(kind=="rhino"?"Rhino":kind=="autocad"?"acad":"Inventor");if(processes.Length>0)names.Add(ExperienceState.Names[kind]);foreach(var p in processes)p.Dispose();}
        return names.Count==0?null:"請先儲存並關閉 "+string.Join("、",names)+"，再按更新。CAD 文件不會自動關閉。";
    }
    public async Task Apply(){
        if(Busy||Available is not JsonElement release)return;
        var selected=Components(root);if(selected.Length==0){Message="請先完成 MCP 安裝。";Changed?.Invoke();return;}
        if(ApplicationBlocker(selected) is string reason){Message=reason;Changed?.Invoke();return;}
        Busy=true;Changed?.Invoke();
        try{
            service.Token=stop.Token;string version=release.GetProperty("version").GetString()!;
            if(!System.Text.RegularExpressions.Regex.IsMatch(version,@"^\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?$"))throw new InvalidDataException("版本格式不符");
            var spec=release.GetProperty("setup");string folder=Path.Combine(root,"updates",version+"-"+spec.GetProperty("sha256").GetString()![..12]);
            string exe=Path.Combine(folder,"McpToolkitSetup.exe");
            await service.Download(release.GetProperty("payload").GetProperty("url").GetString()!,Path.Combine(folder,"cad-toolkit-payload.zip"),release.GetProperty("payload").GetProperty("sha256").GetString()!);
            await service.Download(spec.GetProperty("url").GetString()!,exe,spec.GetProperty("sha256").GetString()!);
            var start=new ProcessStartInfo(exe){UseShellExecute=true};start.ArgumentList.Add("--apply-update");start.ArgumentList.Add("--root="+root);start.ArgumentList.Add("--expected-version="+version);
            DownloadedInstaller=exe;Message="下載驗證完成，正在更新並保留設定…";
            if(LaunchInstaller!=null)LaunchInstaller(start);else Process.Start(start);
        }catch(Exception ex) when(ex is IOException or InvalidDataException or HttpRequestException or OperationCanceledException or System.ComponentModel.Win32Exception or InvalidOperationException){Message="更新未完成，原版本與設定仍保留："+ex.Message;}
        finally{Busy=false;Changed?.Invoke();}
    }
    public void Dispose(){timer.Stop();stop.Cancel();stop.Dispose();}
}
