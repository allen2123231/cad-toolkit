using System.Windows;
namespace CadToolkit;
public static class Program {
    [STAThread] public static void Main(string[] args) {
        var app = new Application();
        string root=ToolkitApplication.Root(args),id=ToolkitApplication.Identity(root),signal=@"Local\McpToolkit.activate."+id;
        using var single=new Mutex(true,@"Local\McpToolkit."+id,out bool first);
        if(!first){try{using var existing=EventWaitHandle.OpenExisting(signal);existing.Set();}catch(WaitHandleCannotBeOpenedException){}return;}
        using var toolkit=new ToolkitApplication(app,args,root,signal);
        app.Run();
    }
}
