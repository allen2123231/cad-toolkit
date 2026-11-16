using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
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
    public ManagerWindow(RuntimeHost host,Action<string?,int?> setup) {
        this.host=host;this.setup=setup;
        Title="MCP Toolkit";Width=1050;Height=790;MinWidth=700;MinHeight=530;WindowStartupLocation=WindowStartupLocation.CenterScreen;
        Icon=((Image)Logo(32)).Source;
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
        host.Changed+=Render;Closed+=(_,_)=>host.Changed-=Render;Render();
    }
    public void Navigate(string target){page=target;Render();}
    void Header(string title,string subtitle) {body.Children.Add(Text(title,27,true));body.Children.Add(Text(subtitle,12,color:Muted));}
    StackPanel Card(string title,string? description=null) {
        var panel=new StackPanel();panel.Children.Add(Text(title,16,true));if(description!=null)panel.Children.Add(Text(description,12,color:Muted));
        body.Children.Add(new Border{Child=panel,BorderBrush=Line,BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(7),Padding=new Thickness(18),Margin=new Thickness(0,14,0,0)});return panel;
    }
    void Render() {
        body.Children.Clear();nav.Children.Clear();footer.Text=host.Message;
        foreach(var item in new[]{("overview","MCP 狀態"),("history","最近指令"),("install","安裝與版本"),("settings","設定")}){
            string target=item.Item1;var button=Button(item.Item2,()=>Navigate(target));button.HorizontalContentAlignment=HorizontalAlignment.Left;button.Padding=new Thickness(14,11,14,11);button.Margin=new Thickness(0,3,0,3);button.BorderThickness=new Thickness(0);button.Background=page==target?Color("#E3ECFF"):Brushes.Transparent;button.Foreground=page==target?Blue:Muted;nav.Children.Add(button);
        }
        if(page=="history"){Header("最近指令","只保存在這台電腦，保留最近 7 天；不記錄指令參數、提示詞或結果內容。");History(body,host);return;}
        if(page=="install"){Installations();return;}
        if(page=="settings"){Settings();return;}
        Header("MCP 狀態","開啟軟體後自動檢查連線；日常使用不需要輸入啟動指令。");
        var actions=new WrapPanel{Margin=new Thickness(0,12,0,0)};actions.Children.Add(Button("重新檢查",async()=>await host.Refresh()));actions.Children.Add(Button("安裝／加入 MCP",()=>setup(null,1),true));body.Children.Add(actions);
        if(!host.Rows.Any()){var empty=Card("先完成首次安裝",host.Message);empty.Children.Add(Button("開始設定",()=>setup(null,0),true));}
        foreach(var row in host.Rows)Server(row);
        var note=Text("關閉管理視窗後仍會在右下角監控。只有「可以使用」代表目前的連線已通過檢查。",11,color:Muted);note.Margin=new Thickness(0,20,0,0);body.Children.Add(note);
    }
    static string Get(JsonElement r,string key,string fallback="")=>ExperienceState.Text(r,key,fallback);
    public static string Label(JsonElement row)=>Get(row,"code") switch {
        "READY"=>"可以使用","NOT_INSTALLED"=>"需要安裝","CAD_NOT_RUNNING"=>"等待開啟","NO_DOCUMENT"=>"等待文件","NOT_ENABLED"=>"正在準備連線","SELECT_TARGET"=>"選擇視窗","VERSION_MISMATCH"=>"版本不符","BUSY"=>"指令進行中","STARTING"=>"啟動中","LICENSING_ERROR"=>"授權元件異常","CHECK_TIMEOUT"=>"等待回應",_=>"需要檢查連線"};
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
        var heading=new StackPanel{Orientation=Orientation.Horizontal};heading.Children.Add(NativeIcon(kind));var names=new StackPanel();names.Children.Add(Text(ExperienceState.Names.GetValueOrDefault(kind,kind),15,true));names.Children.Add(Text(Get(row,"cad_version",kind=="rhino"?"Rhino 8":""),11,color:Muted));heading.Children.Add(names);title.Children.Add(heading);panel.Children.Add(title);
        var grid=new Grid{Margin=new Thickness(0,17,0,12)};grid.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});grid.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});
        var left=new StackPanel();left.Children.Add(Text("目前文件",10,color:Muted));var file=new StackPanel{Orientation=Orientation.Horizontal};file.Children.Add(NativeIcon(kind,true,17));file.Children.Add(Text(Document(row),12));left.Children.Add(file);left.Children.Add(Text("MCP 服務",10,color:Muted));left.Children.Add(Text(Get(row,"version") is string ver&&ver.Length>0?"已安裝 "+ver:ExperienceState.Flag(row,"installed")?"已安裝 · 版本待確認":"尚未安裝",12));
        var right=new StackPanel();right.Children.Add(Text("連線方式／端口",10,color:Muted));right.Children.Add(Text(Get(row,"endpoint","尚未確認"),12));right.Children.Add(Text("版本狀態",10,color:Muted));right.Children.Add(Text(VersionLabel(row),12));Grid.SetColumn(right,1);grid.Children.Add(left);grid.Children.Add(right);panel.Children.Add(grid);
        var actions=new WrapPanel();actions.Children.Add(Button("開啟 "+ExperienceState.Names.GetValueOrDefault(kind,kind),()=>OpenCad(kind),true));actions.Children.Add(Button("重新檢查",async()=>await host.Refresh()));actions.Children.Add(Button(ExperienceState.Flag(row,"installed")?"設定／修復":"安裝 MCP",()=>setup(kind,ExperienceState.Flag(row,"installed")?4:3)));panel.Children.Add(actions);
        if(!ExperienceState.Flag(row,"managed"))panel.Children.Add(Text("既有 MCP 設定 · 可直接檢查；完成 Toolkit 安裝與啟用後會記錄最近指令。",11,color:Muted));
        if(code=="SELECT_TARGET"&&kind=="rhino"&&row.TryGetProperty("instances",out var instances)){
            panel.Children.Add(Text("選擇要連線的 Rhino（新 MCP 對話生效）：",12,true));
            foreach(var instance in instances.EnumerateArray()){
                int pid=instance.GetProperty("pid").GetInt32();string label=Get(instance,"document","未命名文件");if(label.Length==0)label="未命名文件";
                panel.Children.Add(Button($"{label} · 端口 {Get(instance,"port")} · PID {pid}",async()=>{try{await host.Run("select","--kind","rhino","--pid",pid.ToString());await host.Refresh();}catch(Exception ex){Error(ex);}}));
            }
        }
        if(code=="SELECT_TARGET"&&kind!="rhino")panel.Children.Add(Text("目前有多個軟體程序，請保留要操作的視窗再重新檢查。Toolkit 不會替你關閉文件。",11,color:Muted));
        var details=new StackPanel();
        details.Children.Add(Text("連線來源："+(ExperienceState.Flag(row,"managed")?"MCP Toolkit 管理":"既有獨立設定"),11,color:Muted));
        if(row.TryGetProperty("pids",out var pids))details.Children.Add(Text("程序 PID："+string.Join(", ",pids.EnumerateArray().Select(p=>p.ToString())),11,color:Muted));
        if(row.TryGetProperty("document",out var document)&&document.ValueKind==JsonValueKind.Object){details.Children.Add(Text("文件位置："+Get(document,"path","尚未儲存"),11,color:Muted));details.Children.Add(Text("單位："+Get(document,"units","尚未確認"),11,color:Muted));}
        if(Get(row,"plugin_version").Length>0)details.Children.Add(Text("外掛版本："+Get(row,"plugin_version"),11,color:Muted));
        if(row.TryGetProperty("message",out var message)&&message.ValueKind==JsonValueKind.String)details.Children.Add(Text(message.GetString()??"",11,color:Muted));
        panel.Children.Add(new Expander{Header="詳細資料",Content=details,Margin=new Thickness(0,8,0,0)});
        body.Children.Add(new Border{Child=panel,BorderBrush=Line,BorderThickness=new Thickness(0,0,0,1),Padding=new Thickness(0,22,0,20)});
    }
    void OpenCad(string kind) {
        try{
            footer.Text=host.OpenCad(kind);
        }catch(Exception ex){Error(ex);}
    }
    void Installations() {
        Header("安裝與版本","採用經 Toolkit 測試的固定組合，各套軟體可獨立安裝。");
        var own=Card("MCP Toolkit",host.Version+" · Windows x64 · 常駐管理程式");own.Children.Add(Button("查看 Toolkit 發布版本 ↗",()=>Process.Start(new ProcessStartInfo("https://github.com/allen2123231/cad-toolkit/releases"){UseShellExecute=true})));own.Children.Add(Button("安裝／加入 MCP",()=>setup(null,0)));
        foreach(var kind in new[]{"rhino","autocad","inventor"}){
            var row=host.Rows.FirstOrDefault(r=>Get(r,"id")==kind);var card=Card(ExperienceState.Names[kind],row.ValueKind==JsonValueKind.Object?VersionLabel(row):"尚未完成安裝");
            card.Children.Add(Text("目前版本："+(row.ValueKind==JsonValueKind.Object?Get(row,"version","尚未確認"):"尚未安裝"),12));
            var actions=new WrapPanel();actions.Children.Add(Button("安裝／修復 "+ExperienceState.Names[kind]+" MCP",()=>setup(kind,3),true));actions.Children.Add(Button("連線設定",()=>setup(kind,4)));card.Children.Add(actions);
        }
    }
    void Settings() {
        Header("設定","依你的習慣啟動與管理 MCP Toolkit。");
        var startup=Card("啟動與常駐","關閉管理視窗會縮到系統匣。從圖示的右鍵選單可完整結束程式。");
        using var key=Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run");bool enabled=key?.GetValue("McpToolkit")!=null;
        var toggle=new CheckBox{Content="登入 Windows 時啟動 MCP Toolkit",IsChecked=enabled,Margin=new Thickness(0,12,0,8)};
        toggle.Click+=(_,_)=>{try{using var run=Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run");if(toggle.IsChecked==true)run.SetValue("McpToolkit",$"\"{Environment.ProcessPath}\" --background \"--root={host.Root}\"");else run.DeleteValue("McpToolkit",false);}catch(Exception ex){Error(ex);}};startup.Children.Add(toggle);
        var privacy=Card("本機指令紀錄","只記錄 Toolkit 所管理 MCP 的新對話。保留最近 7 天、最多 2,000 筆；不會記錄參數、完整輸出或提示詞。");privacy.Children.Add(Button("清除最近指令",async()=>{if(MessageBox.Show(this,"清除這台電腦的 Toolkit 指令紀錄？","MCP Toolkit",MessageBoxButton.YesNo,MessageBoxImage.Question)!=MessageBoxResult.Yes)return;try{await host.Run("clear-history");await host.Refresh();}catch(Exception ex){Error(ex);}}));
        var config=Card("元件與問題處理","Rhino 首次安裝後需重新開啟軟體；AutoCAD 自動載入套件由安裝按鈕設定；Inventor 使用內建 COM 連線。");config.Children.Add(Button("安裝／修復 MCP",()=>setup(null,4)));
        config.Children.Add(Button("還原上一組設定",async()=>await Manage("rollback","還原上一組 MCP 設定？目前文件會保留，完成後需在 Codex 開啟新對話。")));
        config.Children.Add(Button("解除安裝 MCP 設定",async()=>await Manage("uninstall","解除安裝 Toolkit 的 MCP 設定並還原原有連線？CAD 軟體及工作文件會保留。")));
    }
    public static void History(Panel parent,RuntimeHost host,int limit=80) {
        var entries=host.History.Take(limit).ToArray();
        if(entries.Length==0){var note=Text("目前沒有指令紀錄。\n啟用 Toolkit 管理的 MCP，並在 Codex 開啟新對話後，實際執行的工具會顯示在這裡。",12,color:Muted);note.Margin=new Thickness(0,24,0,20);parent.Children.Add(note);return;}
        foreach(var item in entries){string kind=Get(item,"component");var row=new DockPanel();var state=Text(Get(item,"outcome") switch{"succeeded"=>"完成","failed"=>"失敗","interrupted"=>"已中斷","blocked"=>"未執行",_=>"執行中"},11,color:Get(item,"outcome")=="succeeded"?Color("#2F9461"):Muted);DockPanel.SetDock(state,Dock.Right);row.Children.Add(state);row.Children.Add(NativeIcon(kind,false,20));var detail=new StackPanel();detail.Children.Add(Text(Get(item,"tool"),12,true));string at=DateTimeOffset.TryParse(Get(item,"at"),out var date)?date.ToLocalTime().ToString("MM/dd HH:mm:ss"):"";detail.Children.Add(Text(ExperienceState.Names.GetValueOrDefault(kind,kind)+" · "+at+" · "+Get(item,"duration_ms","—")+" ms",10,color:Muted));row.Children.Add(detail);parent.Children.Add(new Border{Child=row,BorderBrush=Line,BorderThickness=new Thickness(0,0,0,1),Padding=new Thickness(0,13,0,13)});}
    }
    void Error(Exception ex){footer.Text="需要處理："+ex.Message;}
    async Task Manage(string action,string text){
        if(MessageBox.Show(this,text,"MCP Toolkit",MessageBoxButton.YesNo,MessageBoxImage.Question)!=MessageBoxResult.Yes)return;
        try{footer.Text="正在處理…";var service=new ToolkitService(host.Root);await service.Engine(action,ExperienceState.Names.Keys.ToArray());await host.Refresh();footer.Text="已完成。";}catch(Exception ex){Error(ex);}
    }
}
