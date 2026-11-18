using CadToolkit;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;

sealed class Fixture : HttpMessageHandler {
    public bool Corrupt,Offline;
    public string Version="99.0.0-beta.2";
    public int Requests;
    public bool StallDownloads;
    public static byte[] Setup="verified setup"u8.ToArray(),Payload="verified payload"u8.ToArray();
    static string Hash(byte[] bytes)=>Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token){
        Requests++;if(Offline)throw new HttpRequestException("offline");
        string url=request.RequestUri!.ToString(),prefix="https://github.com/allen2123231/cad-toolkit/releases/download/v"+Version+"/";
        if(StallDownloads&&!url.Contains("api.github.com")&&!url.EndsWith("release-manifest.json"))return WaitForCancellation(token);
        object spec=new{version=Version,setup=new{url=prefix+"McpToolkitSetup.exe",sha256=Hash(Setup)},payload=new{url=prefix+"cad-toolkit-payload.zip",sha256=Hash(Payload)}};
        var content=url.Contains("api.github.com")?JsonSerializer.Serialize(new[]{new{tag_name="v"+Version,prerelease=true,draft=false,body="Beta release notes",html_url="https://github.com/allen2123231/cad-toolkit/releases/tag/v"+Version,assets=new[]{new{name="release-manifest.json",browser_download_url=prefix+"release-manifest.json"}}}}):url.EndsWith("release-manifest.json")?JsonSerializer.Serialize(spec):null;
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK){Content=content!=null?new StringContent(content):new ByteArrayContent(Corrupt?"corrupt"u8.ToArray():url.EndsWith(".exe")?Setup:Payload)});
    }
    static async Task<HttpResponseMessage> WaitForCancellation(CancellationToken token){await Task.Delay(Timeout.Infinite,token);throw new Exception("Unexpected completion");}
}
class Program {
    static int checks;
    static void Assert(bool value,string name){checks++;if(!value)throw new Exception(name);}
    [STAThread] static void Main(string[] args){
        if(args.Length==2&&args[0]=="--finish-e2e-cleanup"){FinishE2E(args[1]).GetAwaiter().GetResult();return;}
        if(args.Contains("--repro-update-feedback")){Feedback().GetAwaiter().GetResult();return;}
        Run().GetAwaiter().GetResult();
    }
    static async Task Feedback(){
        string root=Path.Combine(Path.GetTempPath(),"McpToolkit-feedback-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
        File.WriteAllText(Path.Combine(root,"state.json"),"""{"active":{"rhino":"fixture"}}""");
        Fixture.Payload=new byte[64*1024*1024];Fixture.Setup=new byte[32*1024*1024];
        using var client=new HttpClient(new Fixture());using var controller=new UpdateController(root,client);controller.ApplicationBlocker=_=>null;controller.LaunchInstaller+=_=>{};
        await controller.Check(true);int changes=0;var messages=new List<string>();controller.Changed+=()=>{changes++;messages.Add(controller.Message);};await controller.Apply();
        var failures=new List<string>();if(changes>35)failures.Add($"Each download chunk rebuilds the manager: {changes} UI events for 96 MB");
        if(!messages.Any(m=>m.Contains("安裝套件"))||!messages.Any(m=>m.Contains("安裝程式")))failures.Add("Download feedback cannot distinguish payload and installer");
        if(failures.Count>0)throw new Exception(string.Join("; ",failures));
        Console.WriteLine(JsonSerializer.Serialize(new{passed=true,changes,scope="Real verified downloads with fast synchronous fixture stream and installer handoff"}));
    }
    static async Task FinishE2E(string file){
        var report=System.Text.Json.Nodes.JsonNode.Parse(File.ReadAllText(file))!.AsObject();
        string root=Path.GetFullPath(report["root"]!.GetValue<string>()),baseDir=Path.GetFullPath(report["base"]!.GetValue<string>());
        bool owned=baseDir.StartsWith(@"D:\McpToolkit-Beta-E2E-",StringComparison.OrdinalIgnoreCase)||baseDir.StartsWith(@"D:\McpToolkit-Repair-E2E-",StringComparison.OrdinalIgnoreCase);
        if(!report["passed"]!.GetValue<bool>()||!owned||!root.StartsWith(baseDir+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new Exception("Not the owned E2E installation");
        string global=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),".codex","config.toml");byte[] before=File.ReadAllBytes(global);
        Environment.SetEnvironmentVariable("CODEX_HOME",Path.Combine(baseDir,"private-codex"));Environment.SetEnvironmentVariable("APPDATA",Path.Combine(baseDir,"private-roaming"));Environment.SetEnvironmentVariable("LOCALAPPDATA",Path.Combine(baseDir,"private-local"));
        var service=new ToolkitService(root);await service.Engine("uninstall",["inventor"]);
        File.Copy(Environment.ProcessPath!,Path.Combine(root,"McpToolkit.exe"),true);
        UninstallCleanup.DeleteTree(root);
        if(Directory.Exists(root)||!File.ReadAllBytes(global).SequenceEqual(before))throw new Exception("Cleanup did not preserve production configuration");
        report["offline_embedded_uninstaller_passed"]=true;report["installation_files_removed"]=true;
        File.WriteAllText(file,report.ToJsonString(new JsonSerializerOptions{WriteIndented=true}));Console.WriteLine("Real isolated update, offline uninstall and full installation-directory removal passed.");
    }
    static async Task Run(){
        string baseDir=Path.Combine(Path.GetTempPath(),"McpToolkit-update-checks-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(baseDir);
        string root=Path.Combine(baseDir,"中文 自訂位置");Directory.CreateDirectory(root);
        File.WriteAllText(Path.Combine(root,"state.json"),"""{"active":{"rhino":"old-target"},"candidate":{"selected":["rhino"]}}""");
        File.WriteAllText(Path.Combine(root,"ui-state.json"),"custom settings");File.WriteAllText(Path.Combine(root,"windows.sqlite3"),"existing names");
        foreach(string kind in new[]{"autocad","inventor"}){
            string target=Path.Combine(root,"versions","legacy-"+kind),python=Path.Combine(target,"envs",kind,"Scripts","python.exe");Directory.CreateDirectory(Path.GetDirectoryName(python)!);File.WriteAllText(python,"fixture");File.WriteAllText(Path.Combine(target,"ready.json"),JsonSerializer.Serialize(new{selected=new[]{kind}}));
        }
        Assert(UpdateController.Components(root).SequenceEqual(new[]{"autocad","inventor","rhino"}),"update recovers installed components omitted by old single-component state");
        var handler=new Fixture();using var client=new HttpClient(handler);using var updates=new UpdateController(root,client);
        int notifications=0;updates.Notify+=_=>notifications++;
        Assert(updates.Due(DateTimeOffset.UtcNow),"initial automatic check due");await updates.Check();
        Assert(updates.Visible&&updates.Version==handler.Version,"Beta release discovered");Assert(notifications==1,"initial notification");
        int requests=handler.Requests;await updates.Check();Assert(requests==handler.Requests,"daily checks throttled");
        await updates.Check(true);Assert(notifications==1,"same release is not announced repeatedly");
        updates.Skip();Assert(!updates.Visible,"skip hides current release");
        await updates.Check(true);Assert(updates.Visible,"manual check can unskip");
        updates.Later();handler.Version="99.0.0-beta.3";await updates.Check(true);Assert(notifications==2,"manual new version notifies once");
        updates.Preferences.Notifications=false;handler.Version="99.0.0-beta.4";await updates.Check(true);Assert(notifications==2&&updates.Visible,"notification opt-out retains panel update");
        updates.Preferences.Beta=false;await updates.Check(true);Assert(updates.Available==null,"stable channel excludes beta");
        updates.Preferences.Beta=true;await updates.Check(true);
        System.Diagnostics.ProcessStartInfo? launched=null;updates.LaunchInstaller+=start=>launched=start;
        updates.ApplicationBlocker=_=>"save CAD first";await updates.Apply();Assert(launched==null&&updates.Message=="save CAD first","open CAD blocks handoff without forced close");
        updates.ApplicationBlocker=_=>null;handler.Corrupt=true;await updates.Apply();Assert(launched==null,"checksum failure never launches installer");
        Assert(!Directory.EnumerateFiles(root,"*.part",SearchOption.AllDirectories).Any(),"failed downloads clean staging files");
        handler.Corrupt=false;await updates.Apply();Assert(launched!=null,"verified installer handed off");
        Assert(launched!.ArgumentList.Contains("--root="+root)&&launched.ArgumentList.Contains("--apply-update")&&launched.ArgumentList.Contains("--expected-version="+handler.Version),"handoff preserves root and validates version");
        Assert(File.ReadAllBytes(launched.FileName).SequenceEqual(Fixture.Setup),"installer bytes verified");
        Assert(File.ReadAllText(Path.Combine(root,"ui-state.json"))=="custom settings"&&File.ReadAllText(Path.Combine(root,"windows.sqlite3"))=="existing names","download stage preserves settings and names");
        launched=null;handler.StallDownloads=true;
        var pending=updates.Apply();await Task.Delay(30);Assert(updates.CanCancel&&updates.Applying,"slow download visibly stays cancellable");updates.CancelDownload();await pending;
        Assert(launched==null&&!updates.Busy&&updates.Message.Contains("已取消"),"cancelled download preserves installation and unlocks UI");
        var stalled=new ToolkitService(root,client){DownloadIdleTimeout=TimeSpan.FromMilliseconds(50)};
        try{await stalled.Download("https://github.com/allen2123231/cad-toolkit/releases/download/v99.0.0/test.zip",Path.Combine(root,"stall.zip"),new string('0',64));throw new Exception("stalled download did not time out");}
        catch(IOException ex){Assert(ex.Message.Contains("長時間"),"no-data timeout explains stalled network");}
        Assert(!Directory.EnumerateFiles(root,"*.part",SearchOption.AllDirectories).Any(),"cancel and timeout remove partial downloads");handler.StallDownloads=false;
        handler.Offline=true;await updates.Check(true);Assert(updates.Message.Contains("不受影響"),"offline check does not disable CAD");
        updates.Save();using var reloaded=new UpdateController(root,client);Assert(!reloaded.Preferences.Notifications&&reloaded.Preferences.LastSuccess.HasValue,"preferences persist across Toolkit restart");
        Assert(ToolkitService.CompareVersions("0.5.0-beta.10","0.5.0-beta.2")>0&&ToolkitService.CompareVersions("0.5.0","0.5.0-beta.10")>0,"semantic version order");
        string outside=Path.Combine(baseDir,"documents");Directory.CreateDirectory(outside);File.WriteAllText(Path.Combine(outside,"work.3dm"),"preserve");
        try{UninstallCleanup.DeleteTree(outside);throw new Exception("non-Toolkit path accepted");}catch(InvalidOperationException){checks++;}
        File.WriteAllText(Path.Combine(root,"McpToolkit.exe"),"owned fixture");File.WriteAllText(Path.Combine(root,"work.3dm"),"user work in install folder");
        string preserved=Path.Combine(baseDir,"preserved");UninstallCleanup.DeleteTree(root,preserved);
        Assert(!Directory.Exists(root)&&File.Exists(Path.Combine(outside,"work.3dm")),"full removal leaves neighboring CAD files intact");
        Assert(Directory.EnumerateFiles(preserved,"work.3dm",SearchOption.AllDirectories).Any(p=>File.ReadAllText(p)=="user work in install folder"),"CAD files inside install folder are backed up before removal");
        Console.WriteLine(JsonSerializer.Serialize(new{passed=true,checks,scope="Mock GitHub network with real downloads/hashes/handoff; actual owned-directory cleanup; no production installation changed",test_directory=baseDir}));
    }
}
