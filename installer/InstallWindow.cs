using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using static CadToolkit.ToolkitVisuals;

namespace CadToolkit;

public sealed class InstallWindow : Window
{
    readonly RuntimeHost host;
    readonly ToolkitService service;
    readonly StackPanel body=new(),footer=new();
    readonly TextBlock status=Text("",12,color:Muted);
    readonly TextBox log=new(){IsReadOnly=true,TextWrapping=TextWrapping.Wrap,MinHeight=80,MaxHeight=130,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,FontSize=11};
    readonly ProgressBar progress=new(){Height=5,Minimum=0,Maximum=100,Margin=new Thickness(0,18,0,10)};
    readonly HashSet<string> selected=new();
    readonly List<string> needsAction=new();
    CancellationTokenSource? cancellation;
    bool busy,transaction,finished;
    public InstallWindow(RuntimeHost host,string? kind=null) {
        this.host=host;service=new ToolkitService(host.Root);foreach(string id in kind==null?new[]{"rhino","autocad","inventor"}:[kind])selected.Add(id);
        Title="安裝 MCP Toolkit";Width=730;Height=750;MinWidth=560;MinHeight=530;WindowStartupLocation=WindowStartupLocation.CenterScreen;Background=Brushes.White;Foreground=Ink;FontFamily=new FontFamily("Microsoft JhengHei UI");Resources.Add(typeof(Button),ButtonStyle());
        Icon=((Image)Logo(32)).Source;
        var shell=new DockPanel{Background=Brushes.White};Content=shell;
        var header=new StackPanel{Orientation=Orientation.Horizontal,Margin=new Thickness(28,24,28,14)};header.Children.Add(Logo(32));var brand=new StackPanel();brand.Children.Add(Text("MCP Toolkit",20,true));brand.Children.Add(Text(host.Version+" · Windows x64",11,color:Muted));header.Children.Add(brand);DockPanel.SetDock(header,Dock.Top);shell.Children.Add(header);
        footer.Margin=new Thickness(28,14,28,20);DockPanel.SetDock(footer,Dock.Bottom);shell.Children.Add(footer);
        shell.Children.Add(new ScrollViewer{Content=body,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,Padding=new Thickness(28,10,28,10)});
        service.Log=value=>{log.AppendText(value+"\n");log.ScrollToEnd();};service.Report=value=>status.Text=value;
        service.Progress=value=>{progress.IsIndeterminate=!value.HasValue;if(value.HasValue)progress.Value=value.Value;};
        service.Event=value=>{if(value.TryGetProperty("cancellable",out var flag)&&flag.ValueKind==JsonValueKind.False)transaction=true;if(ExperienceState.Text(value,"outcome")=="needs_action")needsAction.Add(ExperienceState.Text(value,"next_action"));};
        Closing+=(_,e)=>{if(busy){e.Cancel=true;status.Text=transaction?"正在完成設定，請等待完成。":"正在安裝，請使用「停止安裝」安全結束。";}};
        SelectPage();
    }
    void SelectPage(){
        body.Children.Clear();footer.Children.Clear();body.Children.Add(Text("安裝一次，開啟軟體就能連線",25,true));body.Children.Add(Text("選擇你要使用的 MCP。必要環境、自動連線外掛與 AI 工具設定會一起準備，不需要輸入啟動指令。",13,color:Muted));
        foreach(string kind in new[]{"rhino","autocad","inventor"}){
            var row=new DockPanel();var check=new CheckBox{IsChecked=selected.Contains(kind),VerticalAlignment=VerticalAlignment.Center,Margin=new Thickness(0,0,14,0)};check.Click+=(_,_)=>{if(check.IsChecked==true)selected.Add(kind);else selected.Remove(kind);};row.Children.Add(check);row.Children.Add(NativeIcon(kind,false,33));
            var text=new StackPanel();text.Children.Add(Text(ExperienceState.Names[kind]+" MCP",16,true));text.Children.Add(Text(kind switch{"rhino"=>"自動安裝完整 Rhino 外掛，開啟後自動連線","autocad"=>"自動安裝圖面連線套件，不需輸入 APPLOAD",_=>"使用內建 COM 自動連線，不需額外外掛"},12,color:Muted));
            string? path=ExperienceState.Detect(kind);text.Children.Add(Text(path!=null?"已找到 "+ExperienceState.Names[kind]:"尚未找到軟體，仍可先準備 MCP 元件",11,color:Muted));row.Children.Add(text);body.Children.Add(new Border{Child=row,BorderBrush=Line,BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(7),Padding=new Thickness(17),Margin=new Thickness(0,15,0,0)});
        }
        body.Children.Add(Text("安裝位置",11,true));body.Children.Add(Text(host.Root,11,color:Muted));body.Children.Add(Text("需要自己的軟體授權。正在使用的文件會保留；外掛安裝後可能需要自行儲存並重開軟體。",11,color:Muted));
        bool codex=ExperienceState.Codex()!=null;
        if(!codex){body.Children.Add(Text("請先安裝並登入 Codex，才能完成 AI 工具設定。",12,color:Color("#B17A24")));body.Children.Add(Button("前往 Codex 官方入門",()=>Process.Start(new ProcessStartInfo("https://learn.chatgpt.com/docs/windows/windows-app"){UseShellExecute=true})));}
        footer.Children.Add(status);var actions=new WrapPanel{HorizontalAlignment=HorizontalAlignment.Right};actions.Children.Add(Button("取消",Close));actions.Children.Add(Button("安裝所選 MCP",async()=>await Install(),true));footer.Children.Add(actions);
    }
    async Task Install(){
        if(busy)return;
        if(selected.Count==0){status.Text="請至少選擇一套 MCP。";return;}
        if(ExperienceState.Codex()==null){status.Text="請先安裝 Codex，再按安裝重試。";return;}
        if(new DriveInfo(Path.GetPathRoot(host.Root)!).AvailableFreeSpace<3L*1024*1024*1024){status.Text="可用空間不足，請至少預留 3 GB。";return;}
        busy=true;transaction=false;cancellation=new();service.Token=cancellation.Token;needsAction.Clear();body.Children.Clear();footer.Children.Clear();
        body.Children.Add(Text("正在安裝 MCP",26,true));body.Children.Add(Text("正在準備獨立環境、自動連線與 AI 工具設定。你不需要另外執行指令。",13,color:Muted));body.Children.Add(progress);body.Children.Add(status);body.Children.Add(new Expander{Header="安裝詳細資料",Content=log,Margin=new Thickness(0,18,0,0)});
        footer.Children.Add(Button("停止安裝",()=>{if(transaction){status.Text="正在完成設定，請等待完成。";return;}cancellation.Cancel();service.RequestStop();status.Text="正在安全停止，已完成的元件會保留。";}));
        string? failure=null;
        try{await service.Engine("setup",selected.ToArray());finished=true;}
        catch(Exception ex){failure=ex.Message;}
        finally{busy=false;transaction=false;progress.IsIndeterminate=false;cancellation.Dispose();}
        body.Children.Clear();footer.Children.Clear();
        body.Children.Add(Text(failure!=null?"安裝尚未完成":needsAction.Count>0?"元件已安裝，部分設定待完成":"安裝完成",26,true));
        body.Children.Add(Text(failure??"開啟要使用的軟體，MCP Toolkit 會自動檢查並啟用連線。到 Codex 開啟新對話後，就可以提出需求。",13,color:Muted));
        foreach(string kind in selected){var row=new StackPanel{Orientation=Orientation.Horizontal,Margin=new Thickness(0,12,0,0)};row.Children.Add(NativeIcon(kind));row.Children.Add(Text(ExperienceState.Names[kind]+" MCP",15,true));body.Children.Add(row);body.Children.Add(Button("開啟 "+ExperienceState.Names[kind],()=>{
            try{status.Text=host.OpenCad(kind);}catch(Exception ex){status.Text=ex.Message;}
        }));}
        foreach(string note in needsAction)body.Children.Add(Text(note,12,color:Color("#B17A24")));
        body.Children.Add(Text("Rhino／AutoCAD：若安裝時已開啟，請自行儲存並重新開啟一次。Inventor 可以停在首頁。",12,color:Muted));body.Children.Add(status);
        if(failure!=null)footer.Children.Add(Button("返回並重試",SelectPage));footer.Children.Add(Button(finished?"完成，查看 MCP 狀態":"關閉",async()=>{await host.Refresh();Close();},true));
    }
}
