using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using static CadToolkit.ToolkitVisuals;

namespace CadToolkit;

public static class UninstallCleanup {
    public static string ValidateRoot(string root){
        root=InstallLocation.Validate(root);
        if(!File.Exists(Path.Combine(root,"state.json"))||!File.Exists(Path.Combine(root,"McpToolkit.exe")))throw new InvalidOperationException("找不到完整的 Toolkit 安裝資料，已停止清理。");
        for(var path=new DirectoryInfo(root);path!=null;path=path.Parent)if((path.Attributes&FileAttributes.ReparsePoint)!=0)throw new InvalidOperationException("安裝路徑含重新導向的資料夾，已保留檔案。");
        return root;
    }
    public static void Launch(string root){
        ValidateRoot(root);string folder=Path.Combine(Path.GetTempPath(),"McpToolkit-uninstall-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(folder);
        string exe=Path.Combine(folder,"McpToolkitSetup.exe");File.Copy(Environment.ProcessPath!,exe);
        var start=new ProcessStartInfo(exe){UseShellExecute=true};start.ArgumentList.Add("--uninstall");start.ArgumentList.Add("--root="+root);Process.Start(start);
    }
    public static void StopOwned(string root){
        string prefix=Path.GetFullPath(root)+Path.DirectorySeparatorChar;
        foreach(string name in new[]{"McpToolkit","McpToolkitSetup","CadToolkitSetup","python","pythonw","rhinomcp"})foreach(var process in Process.GetProcessesByName(name))using(process){
            if(process.Id==Environment.ProcessId)continue;
            try{if(process.MainModule?.FileName is string file&&file.StartsWith(prefix,StringComparison.OrdinalIgnoreCase)){process.Kill(true);if(!process.WaitForExit(5000))throw new IOException("背景連線尚未結束，請稍後重試。");}}
            catch(InvalidOperationException){}
        }
    }
    public static void DeleteTree(string root,string? backupBase=null){
        root=ValidateRoot(root);backupBase??=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"McpToolkitBackups");
        if(Path.GetFullPath(backupBase).StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||Path.GetFullPath(backupBase).Equals(root,StringComparison.OrdinalIgnoreCase))throw new IOException("備份位置位於安裝位置內，已停止清理。");
        PreserveUserFiles(root,backupBase);DeleteInside(root,root);
    }
    static void PreserveUserFiles(string root,string backupBase){
        var knownDirectories=new HashSet<string>(new[]{"versions","downloads","desktop","ipc","marketplace","backups","updates","application-launches"},StringComparer.OrdinalIgnoreCase);
        var knownFiles=new HashSet<string>(new[]{"state.json","ui-state.json","updates.json","McpToolkit.exe","CadToolkitSetup.exe","McpToolkitSetup.exe","history.sqlite3","history.sqlite3-wal","history.sqlite3-shm","windows.sqlite3","windows.sqlite3-wal","windows.sqlite3-shm","launches.json","operation.lock","targets.json","preserved-user-files.json"},StringComparer.OrdinalIgnoreCase);
        var documents=new HashSet<string>(new[]{".3dm",".dwg",".dxf",".ipt",".iam",".idw",".ipn",".step",".stp",".iges",".igs",".stl",".obj",".3mf",".sat",".ifc",".sldprt",".sldasm",".pdf",".docx",".xlsx"},StringComparer.OrdinalIgnoreCase);
        string backup=Path.Combine(backupBase,"user-files-"+Guid.NewGuid().ToString("N"));
        var saved=new List<string>();
        foreach(string file in Directory.EnumerateFiles(root,"*",new EnumerationOptions{RecurseSubdirectories=true,AttributesToSkip=FileAttributes.ReparsePoint})){
            string relative=Path.GetRelativePath(root,file),first=relative.Split(Path.DirectorySeparatorChar)[0];
            bool topFile=!relative.Contains(Path.DirectorySeparatorChar);
            if(!documents.Contains(Path.GetExtension(file))&&(topFile?knownFiles.Contains(relative)||relative.StartsWith("cancel-"):knownDirectories.Contains(first)))continue;
            string destination=Path.Combine(backup,relative);Directory.CreateDirectory(Path.GetDirectoryName(destination)!);File.Copy(file,destination);
            using var source=File.OpenRead(file);using var target=File.OpenRead(destination);
            if(!System.Security.Cryptography.SHA256.HashData(source).SequenceEqual(System.Security.Cryptography.SHA256.HashData(target)))throw new IOException("工作檔案備份未通過，已停止清除。");saved.Add(destination);
        }
        if(saved.Count>0)File.WriteAllText(Path.Combine(root,"preserved-user-files.json"),System.Text.Json.JsonSerializer.Serialize(saved));
    }
    static void DeleteInside(string path,string root){
        string full=Path.GetFullPath(path);
        if(!full.Equals(root,StringComparison.OrdinalIgnoreCase)&&!full.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("清理路徑超出安裝資料夾。");
        var item=new DirectoryInfo(full);
        if((item.Attributes&FileAttributes.ReparsePoint)!=0){item.Delete();return;}
        foreach(var file in item.GetFiles().Where(f=>f.Name is not ("state.json" or "McpToolkit.exe"))){if((file.Attributes&FileAttributes.ReparsePoint)==0)file.Attributes&=~FileAttributes.ReadOnly;file.Delete();}
        foreach(var folder in item.GetDirectories())DeleteInside(folder.FullName,root);
        foreach(var file in item.GetFiles()){file.Attributes&=~FileAttributes.ReadOnly;file.Delete();}
        item.Delete();
    }
}

public sealed class UninstallWindow : Window {
    readonly string root;
    readonly TextBlock status=Text("",12,color:Muted);
    readonly Button remove;
    bool busy,unregistered,finished,preserved;
    public UninstallWindow(string root){
        this.root=root;Title="解除安裝 MCP Toolkit";Width=650;Height=580;MinWidth=550;MinHeight=450;WindowStartupLocation=WindowStartupLocation.CenterScreen;
        Background=Brushes.White;FontFamily=new FontFamily("Microsoft JhengHei UI");Icon=AppIcon();Resources.Add(typeof(Button),ButtonStyle());
        var body=new StackPanel{Margin=new Thickness(28)};Content=new ScrollViewer{Content=body,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        body.Children.Add(Text("完整解除安裝 MCP Toolkit",24,true));
        body.Children.Add(Text("將移除這個位置的 Toolkit、已安裝的三套 MCP、自動連線外掛、Codex Plugin、捷徑與自動啟動設定。",13));
        body.Children.Add(Text(root,11,color:Muted));
        body.Children.Add(Text("CAD 軟體、工作文件、其他 MCP 與其他外掛會保留。設定與可驗證的 Rhino 外掛會先備份到 AppData\\Local\\McpToolkitBackups。",13));
        body.Children.Add(Text("請先儲存並關閉使用中的 CAD。解除安裝不會強制關閉 CAD 或工作文件。",13,true));
        body.Children.Add(status);var actions=new WrapPanel{Margin=new Thickness(0,20,0,0)};actions.Children.Add(Button("取消",Close));
        remove=Button("確認完整解除安裝",async()=>await Remove(),true);actions.Children.Add(remove);body.Children.Add(actions);
        Closing+=(_,e)=>{if(busy)e.Cancel=true;};
    }
    async Task Remove(){
        if(busy)return;if(finished){Close();return;}
        try{
            UninstallCleanup.ValidateRoot(root);
            if(UpdateController.CloseApplications(ExperienceState.Names.Keys.ToArray()) is string reason){status.Text=reason.Replace("再按更新","再按解除安裝");return;}
            busy=true;remove.IsEnabled=false;status.Text="正在備份設定並解除安裝，請稍候…";
            UninstallCleanup.StopOwned(root);
            if(!unregistered){var service=new ToolkitService(root);service.Report=text=>status.Text=text;var events=await service.Engine("uninstall",ExperienceState.Names.Keys.ToArray());preserved=events.Any(e=>ExperienceState.Text(e,"outcome")=="needs_action");unregistered=true;}
            await Task.Run(()=>{UninstallCleanup.StopOwned(root);UninstallCleanup.DeleteTree(root);});
            status.Text="解除安裝完成。CAD 軟體與工作文件已保留，請重新啟動 Codex 以卸載舊連線。"+(preserved?" 部分外掛檔案已被修改而保留，請查看備份紀錄。":"");remove.Content="完成";finished=true;
        }catch(Exception ex){status.Text="尚未完成："+ex.Message;remove.Content="重試解除安裝";}
        finally{busy=false;remove.IsEnabled=true;}
    }
}
