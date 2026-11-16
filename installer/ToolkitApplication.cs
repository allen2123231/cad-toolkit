using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Windows;
using System.Windows.Threading;

namespace CadToolkit;

public sealed class ToolkitApplication : IDisposable
{
    readonly Application app;
    readonly string[] args;
    readonly RuntimeHost host;
    readonly System.Windows.Forms.NotifyIcon tray;
    readonly EventWaitHandle activate;
    readonly RegisteredWaitHandle waiter;
    ManagerWindow? manager;
    TrayPanel? popup;
    InstallWindow? wizard;
    bool exiting;
    public ToolkitApplication(Application app,string[] args,string root,string signal) {
        this.app=app;this.args=args;host=new RuntimeHost(root,args);app.ShutdownMode=ShutdownMode.OnExplicitShutdown;
        activate=new EventWaitHandle(false,EventResetMode.AutoReset,signal);
        waiter=ThreadPool.RegisterWaitForSingleObject(activate,(_,_)=>app.Dispatcher.BeginInvoke(()=>ShowManager("overview")),null,Timeout.Infinite,false);
        tray=new System.Windows.Forms.NotifyIcon{Text="MCP Toolkit · 正在檢查",Icon=ToolkitVisuals.TrayIcon(false),Visible=true};
        var menu=new System.Windows.Forms.ContextMenuStrip();menu.Items.Add("MCP 狀態",null,(_,_)=>TogglePopup());menu.Items.Add("完整管理",null,(_,_)=>ShowManager("overview"));menu.Items.Add("安裝與版本",null,(_,_)=>ShowManager("install"));menu.Items.Add(new System.Windows.Forms.ToolStripSeparator());menu.Items.Add("結束 MCP Toolkit",null,(_,_)=>Exit());tray.ContextMenuStrip=menu;
        tray.MouseClick+=(_,e)=>{if(e.Button==System.Windows.Forms.MouseButtons.Left)TogglePopup();};tray.DoubleClick+=(_,_)=>ShowManager("overview");
        host.Changed+=()=>{var old=tray.Icon;tray.Icon=ToolkitVisuals.TrayIcon(host.Connected);old?.Dispose();tray.Text="MCP Toolkit · "+host.Rows.Count(r=>ExperienceState.Text(r,"code")=="READY")+" 套可以使用";};
        if(args.Contains("--uninstall"))ShowManager("settings");
        else if(args.Any(a=>a=="--setup"||a=="--update"||a.StartsWith("--components=")))ShowSetup(null,null);
        else if(!args.Contains("--background")){
            if(File.Exists(Path.Combine(root,"state.json")))ShowManager("overview");else ShowSetup(null,0);
        }
        _=host.Refresh();
    }
    void TogglePopup(){if(popup?.IsVisible==true){popup.Hide();return;}popup??=new TrayPanel(host,ShowManager);popup.ShowNearTray();}
    void ShowManager(string page){
        if(exiting)return;
        if(manager==null){manager=new ManagerWindow(host,ShowSetup);manager.Closing+=HideManager;}
        manager.Navigate(page);manager.Show();if(manager.WindowState==WindowState.Minimized)manager.WindowState=WindowState.Normal;manager.Activate();
    }
    void HideManager(object? sender,System.ComponentModel.CancelEventArgs e){if(!exiting){e.Cancel=true;manager?.Hide();}}
    void ShowSetup(string? kind,int? step){
        if(wizard!=null){wizard.Show();wizard.Activate();return;}
        wizard=new InstallWindow(host,kind);wizard.Closed+=async(_,_)=>{wizard=null;if(File.Exists(Path.Combine(host.Root,"state.json"))){await host.Refresh();ShowManager("overview");}else Exit();};wizard.Show();wizard.Activate();
    }
    void Exit(){if(wizard!=null){wizard.Close();if(wizard.IsVisible)return;}exiting=true;manager?.Close();popup?.Close();app.Shutdown();}
    public void Dispose(){exiting=true;waiter.Unregister(null);activate.Dispose();tray.Visible=false;var icon=tray.Icon;tray.Dispose();icon?.Dispose();host.Dispose();}
    public static string Root(string[] args){var value=args.FirstOrDefault(a=>a.StartsWith("--root="));return Path.GetFullPath(value!=null?value[7..]:Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CadToolkit"));}
    public static string Identity(string root)=>Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(root.ToUpperInvariant())))[..20];
}
