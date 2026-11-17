using System.IO;
using System.Text.Json;
using System.Diagnostics;
using Microsoft.Win32;

namespace CadToolkit;

public static class InstallLocation
{
    public static void PrepareUpgrade(params string[] roots){
        foreach(string root in roots.Distinct(StringComparer.OrdinalIgnoreCase)){
            string file=Path.Combine(root,"operation.lock");
            if(File.Exists(file))try{using var check=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.None);}catch(IOException){throw new InvalidOperationException("另一個安裝作業正在進行，請完成後再重試。");}
        }
        var candidates=new List<Process>();
        try{
            foreach(string name in new[]{"McpToolkit","McpToolkitSetup","CadToolkitSetup"})foreach(var process in Process.GetProcessesByName(name)){
                if(process.Id==Environment.ProcessId){process.Dispose();continue;}
                try{
                    var info=FileVersionInfo.GetVersionInfo(process.MainModule!.FileName!);
                    if(info.CompanyName!="allen2123231"||info.ProductName is not ("MCP Toolkit" or "CAD Toolkit")){process.Dispose();continue;}
                    candidates.Add(process);
                    if(process.MainWindowTitle.StartsWith("安裝 ",StringComparison.Ordinal))throw new InvalidOperationException("另一個安裝視窗已開啟，請先完成或關閉後再重試。");
                }catch(System.ComponentModel.Win32Exception){process.Dispose();}
            }
            // Only the Toolkit GUI is restarted. CAD and stdio MCP processes stay alive.
            foreach(var process in candidates)try{process.Kill();process.WaitForExit(5000);}catch(InvalidOperationException){}
        }finally{foreach(var process in candidates)process.Dispose();}
    }
    public static string DefaultPath=>Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"McpToolkit");
    public static string Resolve(string[] args){
        string? requested=args.FirstOrDefault(a=>a.StartsWith("--root="));
        if(requested!=null)return Path.GetFullPath(requested[7..]);
        if(args.Contains("--new-install"))return DefaultPath;
        string? own=Path.GetDirectoryName(Environment.ProcessPath);
        if(own!=null&&File.Exists(Path.Combine(own,"state.json"))&&string.Equals(Path.GetFileName(Environment.ProcessPath),"McpToolkit.exe",StringComparison.OrdinalIgnoreCase))return own;
        foreach(string keyName in new[]{"McpToolkit","CadToolkit"}){
            using var key=Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\"+keyName);
            if(key?.GetValue("InstallLocation") is string path&&File.Exists(Path.Combine(path,"state.json"))&&File.Exists(Path.Combine(path,"McpToolkit.exe")))return Path.GetFullPath(path);
        }
        foreach(string path in new[]{DefaultPath,Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CadToolkit")})
            if(File.Exists(Path.Combine(path,"state.json"))&&File.Exists(Path.Combine(path,"McpToolkit.exe")))return path;
        return DefaultPath;
    }
    public static string Validate(string path){
        path=path.Trim();
        if(!Path.IsPathFullyQualified(path))throw new InvalidOperationException("請輸入完整的安裝路徑，或按「瀏覽」選擇資料夾。");
        string full=Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));
        if(string.Equals(full,Path.TrimEndingDirectorySeparator(Path.GetPathRoot(full)!),StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("請選擇專用資料夾，例如 D:\\McpToolkit，不要直接使用磁碟根目錄。");
        if(File.Exists(full))throw new InvalidOperationException("這個位置是檔案，請選擇資料夾。");
        string state=Path.Combine(full,"state.json");
        if(File.Exists(state)){
            try{using var json=JsonDocument.Parse(File.ReadAllText(state));if(!json.RootElement.TryGetProperty("active",out var active)||active.ValueKind!=JsonValueKind.Object)throw new JsonException();}
            catch(JsonException){throw new InvalidOperationException("這個資料夾有其他程式的資料，請另選 MCP Toolkit 專用資料夾。");}
        }
        return full;
    }
}
