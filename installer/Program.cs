using System.Windows;
namespace CadToolkit;
public static class Program {
    [STAThread] public static void Main(string[] args) {
        var app = new Application();
        if(args.Contains("--uninstall")&&!System.IO.Path.GetDirectoryName(Environment.ProcessPath)!.StartsWith(System.IO.Path.Combine(System.IO.Path.GetTempPath(),"McpToolkit-uninstall-"),StringComparison.OrdinalIgnoreCase)){try{UninstallCleanup.Launch(ToolkitApplication.Root(args));}catch(Exception ex){MessageBox.Show(ex.Message,"MCP Toolkit");}return;}
        bool installer=!args.Contains("--background")&&(args.Any(a=>a is "--setup" or "--update" or "--apply-update" or "--uninstall"||a.StartsWith("--components="))||string.Equals(System.IO.Path.GetFileNameWithoutExtension(Environment.ProcessPath),"McpToolkitSetup",StringComparison.OrdinalIgnoreCase));
        string root=ToolkitApplication.Root(args),id=ToolkitApplication.Identity(root),signal=installer?@"Local\McpToolkit.installer.activate":@"Local\McpToolkit.activate."+id;
        string? expected=args.FirstOrDefault(a=>a.StartsWith("--expected-version="));
        if(expected!=null&&new ToolkitService(root).Version!=expected[19..]){MessageBox.Show("下載的安裝程式版本不符，已保留目前版本。","MCP Toolkit");return;}
        using var single=new Mutex(true,installer?@"Local\McpToolkit.installer":@"Local\McpToolkit."+id,out bool first);
        if(!first){if(!args.Contains("--background"))try{using var existing=EventWaitHandle.OpenExisting(!installer&&args.Contains("--page=mcps")?@"Local\McpToolkit.activate.mcps."+id:signal);existing.Set();}catch(WaitHandleCannotBeOpenedException){try{using var fallback=EventWaitHandle.OpenExisting(signal);fallback.Set();}catch(WaitHandleCannotBeOpenedException){}}return;}
        using var toolkit=new ToolkitApplication(app,args,root,signal,installer);
        app.Run();
    }
}
