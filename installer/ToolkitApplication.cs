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
    WindowPicker? picker;
    AutoCadRecoveryWindow? recovery;
    string? shownRecovery;
    readonly HashSet<string> shownRequests=new();
    bool exiting;
    readonly bool installer;
    public ToolkitApplication(Application app,string[] args,string root,string signal,bool installer=false) {
        this.app=app;this.args=args;this.installer=installer;host=new RuntimeHost(root,args,start:!installer);app.ShutdownMode=ShutdownMode.OnExplicitShutdown;
        activate=new EventWaitHandle(false,EventResetMode.AutoReset,signal);
        waiter=ThreadPool.RegisterWaitForSingleObject(activate,(_,_)=>app.Dispatcher.BeginInvoke(()=>{if(installer)ShowSetup(null,null);else ShowManager("overview");}),null,Timeout.Infinite,false);
        tray=new System.Windows.Forms.NotifyIcon{Text="MCP Toolkit · 正在檢查",Icon=ToolkitVisuals.TrayIcon(false),Visible=!installer};
        var menu=new System.Windows.Forms.ContextMenuStrip();menu.Items.Add("MCP 狀態",null,(_,_)=>TogglePopup());menu.Items.Add("MCP 管理",null,(_,_)=>ShowManager("mcps"));menu.Items.Add("完整管理",null,(_,_)=>ShowManager("overview"));menu.Items.Add("設定與更新",null,(_,_)=>ShowManager("settings"));menu.Items.Add(new System.Windows.Forms.ToolStripSeparator());menu.Items.Add("結束 MCP Toolkit",null,(_,_)=>Exit());tray.ContextMenuStrip=menu;
        tray.MouseClick+=(_,e)=>{if(e.Button==System.Windows.Forms.MouseButtons.Left)TogglePopup();};tray.DoubleClick+=(_,_)=>ShowManager("overview");
        tray.BalloonTipClicked+=(_,_)=>ShowManager("settings");
        host.Updates.Notify+=version=>app.Dispatcher.BeginInvoke(()=>{tray.BalloonTipTitle="MCP Toolkit 有新版本";tray.BalloonTipText=version+" 已推出，點此查看內容並更新。";tray.ShowBalloonTip(8000);});
        host.Changed+=()=>{var old=tray.Icon;tray.Icon=ToolkitVisuals.TrayIcon(host.Connected);old?.Dispose();tray.Text="MCP Toolkit · "+host.Rows.Count(r=>ExperienceState.Text(r,"code")=="READY")+" 套可以使用";};
        host.WindowsChanged+=()=>{
            if(host.WindowPanel.TryGetProperty("autocad_recovery",out var state)&&state.TryGetProperty("recovery",out var interrupted)&&interrupted.ValueKind==System.Text.Json.JsonValueKind.Object){
                string id=ExperienceState.Text(interrupted,"request_id");
                if(id!=shownRecovery){shownRecovery=id;recovery??=new AutoCadRecoveryWindow(host);recovery.Closed+=(_,_)=>recovery=null;recovery.Show();recovery.Activate();}
            }else shownRecovery=null;
            var ids=host.WindowPanel.GetProperty("requests").EnumerateArray().Select(r=>ExperienceState.Text(r,"id")).Concat(host.WindowPanel.GetProperty("confirmations").EnumerateArray().Select(r=>ExperienceState.Text(r,"id")+":"+r.GetProperty("context").GetProperty("document_epoch").ToString())).ToArray();
            shownRequests.RemoveWhere(id=>!ids.Contains(id));
            bool fresh=false;foreach(string id in ids)if(shownRequests.Add(id))fresh=true;
            if(fresh){picker??=CreatePicker();picker.Show();picker.Activate();}
        };
        if(args.Contains("--uninstall")){var removal=new UninstallWindow(root);removal.Closed+=(_,_)=>Exit();removal.Show();}
        else if(installer||args.Any(a=>a=="--setup"||a=="--update"||a.StartsWith("--components=")))ShowSetup(null,null);
        else if(!args.Contains("--background")){
            if(File.Exists(Path.Combine(root,"state.json")))ShowManager("overview");else ShowSetup(null,0);
        }
        if(!installer){_=host.Refresh();_=host.RefreshWindows();if(File.Exists(Path.Combine(root,"state.json")))app.Dispatcher.BeginInvoke(()=>host.Updates.Start());}
    }
    WindowPicker CreatePicker(){var view=new WindowPicker(host);view.Closed+=(_,_)=>picker=null;return view;}
    void TogglePopup(){if(popup?.IsVisible==true){popup.Hide();return;}popup??=new TrayPanel(host,ShowManager);popup.ShowNearTray();}
    void ShowManager(string page){
        if(exiting)return;
        if(manager==null){manager=new ManagerWindow(host,ShowSetup);manager.Closing+=HideManager;}
        manager.Navigate(page);manager.Show();if(manager.WindowState==WindowState.Minimized)manager.WindowState=WindowState.Normal;manager.Activate();
    }
    void HideManager(object? sender,System.ComponentModel.CancelEventArgs e){if(!exiting){e.Cancel=true;manager?.Hide();}}
    void ShowSetup(string? kind,int? step){
        if(wizard!=null){wizard.Show();wizard.Activate();return;}
        wizard=new InstallWindow(host,kind,args.Contains("--apply-update"));wizard.Closed+=async(_,_)=>{
            string? installed=wizard?.ResumeRoot;wizard=null;
            if(installed!=null&&(installer||!string.Equals(installed,host.Root,StringComparison.OrdinalIgnoreCase))){
                var start=new System.Diagnostics.ProcessStartInfo(Path.Combine(installed,"McpToolkit.exe")){UseShellExecute=true};start.ArgumentList.Add("--root="+installed);System.Diagnostics.Process.Start(start);Exit();return;
            }
            if(installer){Exit();return;}
            if(File.Exists(Path.Combine(host.Root,"state.json"))){await host.Refresh();ShowManager("overview");}else Exit();
        };wizard.Show();wizard.Activate();
    }
    async void Exit(){if(wizard!=null){var closing=wizard;closing.Close();if(closing.IsVisible)return;}if(!installer)try{await host.Run("clear-window-titles");}catch(Exception){}exiting=true;manager?.Close();popup?.Close();picker?.Close();recovery?.Close();app.Shutdown();}
    public void Dispose(){exiting=true;waiter.Unregister(null);activate.Dispose();tray.Visible=false;var icon=tray.Icon;tray.Dispose();icon?.Dispose();host.Dispose();}
    public static string Root(string[] args)=>InstallLocation.Resolve(args);
    public static string Identity(string root)=>Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(root.ToUpperInvariant())))[..20];
}
