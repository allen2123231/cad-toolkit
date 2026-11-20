using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using Microsoft.Win32;
using static CadToolkit.ToolkitVisuals;

namespace CadToolkit;

public sealed class ManagerWindow : Window
{
    readonly RuntimeHost host;
    readonly Action<string?,int?> setup;
    readonly StackPanel body=new(),nav=new();
    readonly TextBlock footer=Text("",11,color:Muted);
    string page="overview";
    bool installedCategory=true;
    TextBlock? updateMessage,updateActivity;
    ProgressBar? updateProgress;
    bool renderedBusy,renderedVisible,renderedCancelable;
    string? renderedVersion;
    readonly DispatcherTimer updateClock=new(){Interval=TimeSpan.FromSeconds(1)};
    public ManagerWindow(RuntimeHost host,Action<string?,int?> setup) {
        this.host=host;this.setup=setup;
        System.Windows.Automation.AutomationProperties.SetAutomationId(this,"manager-"+ToolkitApplication.Identity(host.Root));
        Title="MCP Toolkit";Width=1050;Height=790;MinWidth=700;MinHeight=530;WindowStartupLocation=WindowStartupLocation.CenterScreen;
        Icon=AppIcon();
        FontFamily=new FontFamily("Microsoft JhengHei UI");Background=Brushes.White;Foreground=Ink;
        Resources.Add(typeof(Button),ButtonStyle());
        var shell=new Grid{Background=Brushes.White};shell.ColumnDefinitions.Add(new(){Width=new GridLength(196)});shell.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});Content=shell;
        var side=new DockPanel{Margin=new Thickness(17,25,13,18)};
        var brand=new StackPanel{Orientation=Orientation.Horizontal,Margin=new Thickness(4,0,0,30)};brand.Children.Add(Logo(27));brand.Children.Add(Text("MCP Toolkit",16,true));DockPanel.SetDock(brand,Dock.Top);side.Children.Add(brand);
        var bottom=new StackPanel();bottom.Children.Add(Text(host.Version,11,color:Muted));bottom.Children.Add(Text("Windows · 本機執行",11,color:Muted));DockPanel.SetDock(bottom,Dock.Bottom);side.Children.Add(bottom);side.Children.Add(nav);
        shell.Children.Add(new Border{Background=Soft,BorderBrush=Line,BorderThickness=new Thickness(0,0,1,0),Child=side});
        var workspace=new DockPanel();Grid.SetColumn(workspace,1);shell.Children.Add(workspace);
        footer.Margin=new Thickness(30,10,30,14);DockPanel.SetDock(footer,Dock.Bottom);workspace.Children.Add(footer);
        workspace.Children.Add(new ScrollViewer{Content=body,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,Padding=new Thickness(30,25,30,25)});
        host.Changed+=HostChanged;host.Updates.Changed+=UpdateFeedback;
        updateClock.Tick+=(_,_)=>{if(updateActivity!=null&&host.Updates.Applying)updateActivity.Text=host.Updates.Activity;};updateClock.Start();
        Closed+=(_,_)=>{host.Changed-=HostChanged;host.Updates.Changed-=UpdateFeedback;updateClock.Stop();};Render();
    }
    void HostChanged(){if(page=="settings")footer.Text=host.Message;else Render();}
    void UpdateFeedback(){
        if(!Dispatcher.CheckAccess()){Dispatcher.BeginInvoke(UpdateFeedback);return;}
        if(page!="settings")return;
        if(renderedBusy!=host.Updates.Busy||renderedVisible!=host.Updates.Visible||renderedVersion!=host.Updates.Version||renderedCancelable!=host.Updates.CanCancel){Render();return;}
        if(updateMessage!=null)updateMessage.Text=host.Updates.Message;
        if(updateActivity!=null)updateActivity.Text=host.Updates.Activity;
        if(updateProgress!=null){updateProgress.IsIndeterminate=!host.Updates.Percent.HasValue;updateProgress.Value=host.Updates.Percent??0;}
    }
    public void Navigate(string target){page=target=="install"?"settings":target;Render();}
    void Header(string title,string subtitle) {body.Children.Add(Text(title,27,true));body.Children.Add(Text(subtitle,12,color:Muted));}
    StackPanel Card(string title,string? description=null) {
        var panel=new StackPanel();if(title.Length>0)panel.Children.Add(Text(title,16,true));if(description!=null)panel.Children.Add(Text(description,12,color:Muted));
        body.Children.Add(new Border{Child=panel,BorderBrush=Line,BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(7),Padding=new Thickness(18),Margin=new Thickness(0,14,0,0)});return panel;
    }
    void Render() {
        updateMessage=null;updateActivity=null;updateProgress=null;renderedBusy=host.Updates.Busy;renderedVisible=host.Updates.Visible;renderedVersion=host.Updates.Version;renderedCancelable=host.Updates.CanCancel;
        body.Children.Clear();nav.Children.Clear();footer.Text=host.Message;
        foreach(var item in new[]{("overview","MCP 狀態"),("mcps","MCP 管理"),("history","最近指令"),("settings","設定與更新")}){
            string target=item.Item1;var button=Button(item.Item2,()=>Navigate(target));button.HorizontalContentAlignment=HorizontalAlignment.Left;button.Padding=new Thickness(14,11,14,11);button.Margin=new Thickness(0,3,0,3);button.BorderThickness=new Thickness(0);button.Background=page==target?Color("#E3ECFF"):Brushes.Transparent;button.Foreground=page==target?Blue:Muted;nav.Children.Add(button);
        }
        if(page=="history"){Header("最近指令","只保存在這台電腦，保留最近 7 天；不記錄指令參數、提示詞或結果內容。");History(body,host);return;}
        if(page=="mcps"){McpManagement();return;}
        if(page=="settings"){Settings();return;}
        Header("MCP 狀態","開啟軟體後自動檢查連線；日常使用不需要輸入啟動指令。");
        var actions=new WrapPanel{Margin=new Thickness(0,12,0,0)};actions.Children.Add(RecheckButton());actions.Children.Add(Button("管理 MCP",()=>Navigate("mcps")));body.Children.Add(actions);
        var installed=host.InstalledRows.ToArray();
        if(installed.Length==0){var empty=Card(host.IsChecking?"正在檢查已安裝的 MCP":"尚未安裝 MCP","到「MCP 管理」選擇要安裝的元件；已安裝但未開啟軟體的項目也會顯示在這裡。");empty.Children.Add(Button("前往 MCP 管理",()=>Navigate("mcps"),true));}
        foreach(var row in installed)Server(row);
        var note=Text("關閉管理視窗後仍會在右下角監控。只有「可以使用」代表目前的連線已通過檢查。",11,color:Muted);note.Margin=new Thickness(0,20,0,0);body.Children.Add(note);
    }
    static string Get(JsonElement r,string key,string fallback="")=>ExperienceState.Text(r,key,fallback);
    Button RecheckButton(string? kind=null){
        bool checking=host.IsChecking&&(kind==null||host.CheckingKind==null||host.CheckingKind==kind);
        var button=Button(checking?"檢查中…":"重新檢查",async()=>await host.Recheck(kind));button.IsEnabled=!host.IsChecking;
        System.Windows.Automation.AutomationProperties.SetAutomationId(button,"recheck-"+(kind??"all"));return button;
    }
    public static string Label(JsonElement row)=>Get(row,"code") switch {
        "CHECK_FAILED"=>"檢查失敗",
        "READY"=>"可以使用","NOT_INSTALLED"=>"需要安裝","CAD_NOT_RUNNING"=>"等待開啟","BACKGROUND_ONLY"=>"等待顯示視窗","CHECKING"=>"檢查中","TARGET_MISMATCH"=>"等待連線視窗","NO_DOCUMENT"=>"等待文件","NOT_ENABLED"=>"正在準備連線","SELECT_TARGET"=>"選擇視窗","VERSION_MISMATCH"=>"版本不符","BUSY"=>"指令進行中","STARTING"=>"啟動中","LICENSING_ERROR"=>"授權元件異常","CHECK_TIMEOUT"=>"等待回應",_=>"需要檢查連線"};
    public static Brush StatusColor(JsonElement row)=>Get(row,"code")=="READY"?Color("#2F9461"):Get(row,"code") is "CAD_NOT_RUNNING" or "NOT_INSTALLED"?Muted:Color("#B17A24");
    public static FrameworkElement Status(JsonElement row) => new Border{Background=Get(row,"code")=="READY"?Color("#EDF8F0"):Soft,CornerRadius=new CornerRadius(4),Padding=new Thickness(9,3,9,3),Child=Text(Label(row),11,color:StatusColor(row)),HorizontalAlignment=HorizontalAlignment.Right};
    public static string Document(JsonElement row) {
        if(row.TryGetProperty("document",out var doc)&&doc.ValueKind==JsonValueKind.Object)return Get(doc,"name","未命名文件") is string name&&name.Length>0?name:"未命名文件";
        return Get(row,"id")=="inventor"&&Get(row,"code")=="READY"?"首頁／無文件":"尚未讀取";
    }
    public static string VersionLabel(JsonElement row)=>Get(row,"update") switch {
        "compatible"=>"符合 Toolkit 相容版本","available"=>"可安裝相容新版 "+Get(row,"expected_version"),"different"=>"與測試組合版本不同",_=>"版本尚未確認"};
    void Server(JsonElement row) {
        string kind=Get(row,"id"),code=Get(row,"code");
        var panel=new StackPanel();var title=new DockPanel();var status=Status(row);DockPanel.SetDock(status,Dock.Right);title.Children.Add(status);
        var heading=new StackPanel{Orientation=Orientation.Horizontal};heading.Children.Add(NativeIcon(kind));var names=new StackPanel();names.Children.Add(Text(Get(row,"product",ExperienceState.Names.GetValueOrDefault(kind,kind)),15,true));names.Children.Add(Text(Get(row,"cad_version",kind=="rhino"?"Rhino 8":""),11,color:Muted));heading.Children.Add(names);title.Children.Add(heading);panel.Children.Add(title);
        var grid=new Grid{Margin=new Thickness(0,17,0,12)};grid.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});grid.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});
        var left=new StackPanel();int windowCount=host.Windows.Count(w=>Get(w,"kind")==kind);left.Children.Add(Text(windowCount>0?"已開啟視窗":"目前文件",10,color:Muted));var file=new StackPanel{Orientation=Orientation.Horizontal};file.Children.Add(NativeIcon(kind,windowCount==0,17));file.Children.Add(Text(windowCount>0?windowCount+" 個獨立視窗":Document(row),12));left.Children.Add(file);left.Children.Add(Text("MCP 服務",10,color:Muted));left.Children.Add(Text(Get(row,"version") is string ver&&ver.Length>0?"已安裝 "+ver:ExperienceState.Flag(row,"installed")?"已安裝 · 版本待確認":"尚未安裝",12));
        var right=new StackPanel();right.Children.Add(Text("連線方式／端口",10,color:Muted));right.Children.Add(Text(Get(row,"endpoint","尚未確認"),12));right.Children.Add(Text("版本狀態",10,color:Muted));right.Children.Add(Text(VersionLabel(row),12));Grid.SetColumn(right,1);grid.Children.Add(left);grid.Children.Add(right);panel.Children.Add(grid);
        var actions=new WrapPanel();
        if(ExperienceState.Names.ContainsKey(kind)){actions.Children.Add(Button("開啟 "+Get(row,"product",ExperienceState.Names.GetValueOrDefault(kind,kind)),()=>OpenCad(kind),true));actions.Children.Add(RecheckButton(kind));actions.Children.Add(Button("選擇程式",()=>ChooseApplication(kind)));actions.Children.Add(Button(ExperienceState.Flag(row,"installed")?"設定／修復":"安裝 MCP",()=>setup(kind,ExperienceState.Flag(row,"installed")?4:3)));}
        else actions.Children.Add(Button("查看 MCP 管理",()=>Navigate("mcps")));
        panel.Children.Add(actions);
        if(host.LastCheckedAt(kind) is DateTime checkedAt)panel.Children.Add(Text("上次檢查："+checkedAt.ToString("HH:mm:ss"),10,color:Muted));
        if(!ExperienceState.Flag(row,"managed"))panel.Children.Add(Text("既有 MCP 設定 · 可直接檢查；完成 Toolkit 安裝與啟用後會記錄最近指令。",11,color:Muted));
        if(kind=="rhino"){
            panel.Children.Add(Text("由每段對話各自要求連線，Toolkit 會彈出選窗面板；這裡的檢視不會切換任何對話的目標。",11,color:Muted));
            panel.Children.Add(Button("查看選窗與文件確認",()=>new WindowPicker(host){Owner=this}.Show()));
        }
        if(code=="SELECT_TARGET"&&kind!="rhino")panel.Children.Add(Text("目前可查看、命名與定位各個視窗。這套軟體的多視窗對話綁定尚未開放。",11,color:Muted));
        foreach(var window in host.Windows.Where(w=>Get(w,"kind")==kind))WindowCards.Add(panel,host,window,this);
        var details=new StackPanel();
        if(host.CheckError!=null)details.Children.Add(Text("檢查錯誤："+host.CheckError,11,color:Color("#B17A24")));
        details.Children.Add(Text("連線來源："+(ExperienceState.Flag(row,"managed")?"MCP Toolkit 管理":"既有獨立設定"),11,color:Muted));
        if(row.TryGetProperty("pids",out var pids))details.Children.Add(Text("程序 PID："+string.Join(", ",pids.EnumerateArray().Select(p=>p.ToString())),11,color:Muted));
        if(row.TryGetProperty("document",out var document)&&document.ValueKind==JsonValueKind.Object){details.Children.Add(Text("文件位置："+Get(document,"path","尚未儲存"),11,color:Muted));details.Children.Add(Text("單位："+Get(document,"units","尚未確認"),11,color:Muted));}
        if(Get(row,"plugin_version").Length>0)details.Children.Add(Text("外掛版本："+Get(row,"plugin_version"),11,color:Muted));
        if(row.TryGetProperty("message",out var message)&&message.ValueKind==JsonValueKind.String)details.Children.Add(Text(message.GetString()??"",11,color:Muted));
        panel.Children.Add(new Expander{Header="詳細資料",Content=details,Margin=new Thickness(0,8,0,0)});
        body.Children.Add(new Border{Child=panel,BorderBrush=Line,BorderThickness=new Thickness(0,0,0,1),Padding=new Thickness(0,22,0,20)});
    }
    async void OpenCad(string kind) {
        try{
            footer.Text=await host.OpenCad(kind);
        }catch(Exception ex){Error(ex);}
    }
    void ChooseApplication(string kind){
        var dialog=new OpenFileDialog{Title=kind=="autocad"?"選擇 AutoCAD 或 AutoCAD LT 主程式":"選擇 "+ExperienceState.Names[kind]+" 主程式",Filter="軟體主程式 (*.exe)|*.exe",CheckFileExists=true};
        if(dialog.ShowDialog(this)!=true)return;
        if(!ExperienceState.ExecutableNames(kind).Contains(Path.GetFileName(dialog.FileName),StringComparer.OrdinalIgnoreCase)){Error(new InvalidOperationException("請選擇 "+string.Join(" 或 ",ExperienceState.ExecutableNames(kind))+"。"));return;}
        try{var state=ExperienceState.Load(host.Root);state.Paths[kind]=dialog.FileName;state.Save(host.Root);footer.Text="已記住程式位置；按「開啟」即可使用，不需要輸入指令。";}
        catch(Exception ex){Error(ex);}
    }
    void ToolkitUpdates() {
        var updates=Card("MCP Toolkit",host.Version+(host.Version.Contains('-')?" · Beta 測試版":"")+" · Windows x64");updateMessage=Text(host.Updates.Message,12,color:Muted);updates.Children.Add(updateMessage);
        if(host.Updates.Applying){
            updateProgress=new ProgressBar{Height=6,Minimum=0,Maximum=100,IsIndeterminate=!host.Updates.Percent.HasValue,Value=host.Updates.Percent??0,Margin=new Thickness(0,12,0,8)};updates.Children.Add(updateProgress);
            updateActivity=Text(host.Updates.Activity,12,color:Muted);updates.Children.Add(updateActivity);
            updates.Children.Add(Text("下載完成後會開啟獨立更新視窗，繼續顯示解壓縮與元件更新進度。",11,color:Muted));
            if(host.Updates.CanCancel)updates.Children.Add(Button("取消下載",host.Updates.CancelDownload));
        }
        var toolkitActions=new WrapPanel();var check=Button("檢查更新",async()=>await host.Updates.Check(true));check.IsEnabled=!host.Updates.Busy;toolkitActions.Children.Add(check);
        toolkitActions.Children.Add(Button("管理 MCP",()=>Navigate("mcps")));toolkitActions.Children.Add(Button("查看發布版本 ↗",()=>Process.Start(new ProcessStartInfo("https://github.com/allen2123231/cad-toolkit/releases"){UseShellExecute=true})));updates.Children.Add(toolkitActions);
        if(host.Updates.Visible){
            var release=host.Updates.Available!.Value;updates.Children.Add(Text("可更新至 "+host.Updates.Version,16,true));
            updates.Children.Add(MarkdownNotes.View(ExperienceState.Text(release,"notes")));
            var update=Button(host.Updates.Busy?"正在下載更新…":"立即更新（保留設定）",async()=>await host.Updates.Apply(),true);update.IsEnabled=!host.Updates.Busy;updates.Children.Add(update);
            var actions=new WrapPanel();actions.Children.Add(Button("稍後提醒",host.Updates.Later));actions.Children.Add(Button("略過此版本",host.Updates.Skip));updates.Children.Add(actions);
        }
    }
    void McpManagement(){
        Header("MCP 管理","依需要安裝與管理 MCP。只有已安裝項目會出現在「MCP 狀態」。");
        var catalog=host.Catalog;int installed=catalog.Count(c=>c.Installed),available=catalog.Length-installed;
        var categories=new WrapPanel{Margin=new Thickness(0,14,0,6)};
        categories.Children.Add(Button("已安裝（"+installed+"）",()=>{installedCategory=true;Render();},installedCategory));
        categories.Children.Add(Button("加入新 MCP（"+available+"）",()=>{installedCategory=false;Render();},!installedCategory));body.Children.Add(categories);
        var entries=catalog.Where(c=>c.Installed==installedCategory).ToArray();
        if(entries.Length==0)Card(installedCategory?"尚未安裝 MCP":"目前沒有可加入的新 MCP",installedCategory?"切換到「加入新 MCP」，選擇你要使用的元件。":"目前目錄中的元件都已安裝，後續新增的 MCP 會出現在這裡。");
        var grid=new McpCardGrid();body.Children.Add(grid);
        foreach(var entry in entries){
            var card=new StackPanel();grid.Children.Add(new Border{Child=card,BorderBrush=Line,BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(7),Padding=new Thickness(18)});
            var row=entry.Row;var heading=new StackPanel{Orientation=Orientation.Horizontal};heading.Children.Add(NativeIcon(entry.Id,false,32));var label=new StackPanel();label.Children.Add(Text(entry.Name,16,true));label.Children.Add(Text(entry.Installed?VersionLabel(row):"尚未安裝",12,color:Muted));heading.Children.Add(label);card.Children.Add(heading);
            card.Children.Add(Text((entry.Installed?"目前版本：":"可安裝版本：")+(entry.Installed?Get(row,"version","版本待確認"):entry.ExpectedVersion.Length>0?entry.ExpectedVersion:"尚未提供"),12));
            if(entry.Installed)card.Children.Add(Text("連線狀態："+Label(row),12,color:Muted));
            var actions=new WrapPanel();
            if(entry.CanManage){
                actions.Children.Add(Button(entry.Installed?"修復":"安裝 "+entry.Name+" MCP",()=>setup(entry.Id,3),true));
                if(entry.Installed){actions.Children.Add(RecheckButton(entry.Id));actions.Children.Add(Button("解除安裝",()=>{var dialog=new ComponentUninstallWindow(host,entry.Id,entry.Name){Owner=this};dialog.ShowDialog();}));}
            }else card.Children.Add(Text(entry.Installed?"已偵測到既有安裝，請透過原提供者管理。":"此元件尚未提供 Toolkit 安裝整合。",11,color:Muted));
            card.Children.Add(actions);
        }
    }
    void Settings() {
        Header("設定與更新","管理 Toolkit 主程式更新、通知與啟動偏好。MCP 元件請到「MCP 管理」。");
        ToolkitUpdates();
        var updates=Card("更新與通知","啟動時及每天背景檢查；同一版本只通知一次，未更新時面板保留提示。");
        foreach(var item in new[]{("自動檢查更新",host.Updates.Preferences.Automatic,0),("顯示 Windows 更新通知",host.Updates.Preferences.Notifications,1),("接收 Beta 測試版更新",host.Updates.Preferences.Beta,2)}){
            var option=new CheckBox{Content=item.Item1,IsChecked=item.Item2,Margin=new Thickness(0,8,0,0)};
            option.Click+=(_,_)=>{bool value=option.IsChecked==true;if(item.Item3==0)host.Updates.Preferences.Automatic=value;else if(item.Item3==1)host.Updates.Preferences.Notifications=value;else host.Updates.Preferences.Beta=value;host.Updates.Save();};updates.Children.Add(option);
        }
        var startup=Card("啟動與常駐","關閉管理視窗會縮到系統匣。從圖示的右鍵選單可完整結束程式。");
        using var key=Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run");bool enabled=key?.GetValue("McpToolkit")!=null;
        var toggle=new CheckBox{Content="登入 Windows 時啟動 MCP Toolkit",IsChecked=enabled,Margin=new Thickness(0,12,0,8)};
        toggle.Click+=(_,_)=>{try{using var run=Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run");if(toggle.IsChecked==true)run.SetValue("McpToolkit",$"\"{Environment.ProcessPath}\" --background \"--root={host.Root}\"");else run.DeleteValue("McpToolkit",false);}catch(Exception ex){Error(ex);}};startup.Children.Add(toggle);
        var privacy=Card("本機指令紀錄","只記錄 Toolkit 所管理 MCP 的新對話。保留最近 7 天、最多 2,000 筆；不會記錄參數、完整輸出或提示詞。");privacy.Children.Add(Button("清除最近指令",async()=>{if(MessageBox.Show(this,"清除這台電腦的 Toolkit 指令紀錄？","MCP Toolkit",MessageBoxButton.YesNo,MessageBoxImage.Question)!=MessageBoxResult.Yes)return;try{await host.Run("clear-history");await host.Refresh();}catch(Exception ex){Error(ex);}}));
        var config=Card("元件與問題處理","Rhino 首次安裝後需重新開啟軟體；AutoCAD 自動載入套件由安裝按鈕設定；Inventor 使用內建 COM 連線。");config.Children.Add(Button("開啟 MCP 管理",()=>Navigate("mcps")));
        config.Children.Add(Button("還原上一組設定",async()=>await Manage("rollback","還原上一組 MCP 設定？目前文件會保留，完成後需在 Codex 開啟新對話。")));
        config.Children.Add(Button("完整解除安裝 MCP Toolkit",()=>{try{UninstallCleanup.Launch(host.Root);}catch(Exception ex){Error(ex);}}));
    }
    public static void History(Panel parent,RuntimeHost host,int limit=80) {
        var entries=host.History.Take(limit).ToArray();
        if(entries.Length==0){var note=Text("目前沒有指令紀錄。\n啟用 Toolkit 管理的 MCP，並在 Codex 開啟新對話後，實際執行的工具會顯示在這裡。",12,color:Muted);note.Margin=new Thickness(0,24,0,20);parent.Children.Add(note);return;}
        foreach(var item in entries){string kind=Get(item,"component");var row=new DockPanel();var state=Text(Get(item,"outcome") switch{"succeeded"=>"完成","failed"=>"失敗","interrupted"=>"已中斷","blocked"=>"未執行",_=>"執行中"},11,color:Get(item,"outcome")=="succeeded"?Color("#2F9461"):Muted);DockPanel.SetDock(state,Dock.Right);row.Children.Add(state);row.Children.Add(NativeIcon(kind,false,20));var detail=new StackPanel();detail.Children.Add(Text(Get(item,"tool"),12,true));string at=DateTimeOffset.TryParse(Get(item,"at"),out var date)?date.ToLocalTime().ToString("MM/dd HH:mm:ss"):"";detail.Children.Add(Text((Get(item,"window_name").Length>0?Get(item,"window_name")+" · "+Get(item,"connection_name"):ExperienceState.Names.GetValueOrDefault(kind,kind))+" · "+at+" · "+Get(item,"duration_ms","—")+" ms",10,color:Muted));row.Children.Add(detail);parent.Children.Add(new Border{Child=row,BorderBrush=Line,BorderThickness=new Thickness(0,0,0,1),Padding=new Thickness(0,13,0,13)});}
    }
    void Error(Exception ex){footer.Text="需要處理："+ex.Message;}
    async Task Manage(string action,string text){
        if(MessageBox.Show(this,text,"MCP Toolkit",MessageBoxButton.YesNo,MessageBoxImage.Question)!=MessageBoxResult.Yes)return;
        try{footer.Text="正在處理…";var service=new ToolkitService(host.Root);await service.Engine(action,ExperienceState.Names.Keys.ToArray());await host.Refresh();footer.Text="已完成。";}catch(Exception ex){Error(ex);}
    }
}
