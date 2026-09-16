using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
namespace CadToolkit;

public sealed partial class SetupWindow : Window
{
    readonly ToolkitService service;
    readonly ExperienceState state;
    readonly JsonElement guides;
    readonly Dictionary<string, JsonElement> checks = new();
    readonly Dictionary<string, DateTimeOffset> checkedAt = new();
    readonly Dictionary<string, string?> checkedTargets = new();
    readonly StackPanel body = new();
    readonly WrapPanel footer = new();
    readonly Dictionary<string,string> installProgress = new();
    readonly WrapPanel nav = new();
    readonly TextBlock heading = T("", 28), subtitle = T("", 14);
    readonly TextBlock status = T("準備好了，從下面的步驟開始。", 14);
    readonly TextBox log = new() { IsReadOnly=true, TextWrapping=TextWrapping.Wrap, VerticalScrollBarVisibility=ScrollBarVisibility.Auto, MinHeight=100, MaxHeight=200, FontSize=12 };
    readonly ProgressBar progress = new() { Height=5, Minimum=0, Maximum=100, Visibility=Visibility.Collapsed };
    readonly Button cancel = new() { Content="停止下載／安裝", Padding=new Thickness(12,8,12,8), Visibility=Visibility.Collapsed };
    readonly List<Control> controls = new();
    CancellationTokenSource? cancellation;
    bool busy, transaction, preview;
    string page = "wizard", guideId="autocad", lastError="";
    static readonly string[] steps = ["歡迎", "選擇軟體", "準備 AI 助手", "安裝連線工具", "設定 CAD", "確認可以使用", "第一次練習"];
    static readonly Brush Ink = new SolidColorBrush(Color.FromRgb(24,49,61));
    static readonly Brush Accent = new SolidColorBrush(Color.FromRgb(0,105,103));
    static readonly Brush Muted = new SolidColorBrush(Color.FromRgb(79,96,104));
    string Root => service.Root;
    string[] Selected => state.Selected;

    public SetupWindow(string[] args) {
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CadToolkit");
        string own = Path.GetDirectoryName(Environment.ProcessPath!)!;
        if(Path.GetFileName(own).Equals("CadToolkit", StringComparison.OrdinalIgnoreCase) && File.Exists(Path.Combine(own,"state.json"))) root=own;
        var rootArg=args.FirstOrDefault(a=>a.StartsWith("--root=")); if(rootArg!=null) root=Path.GetFullPath(rootArg[7..]);
        service=new(root); state=ExperienceState.Load(root);
        foreach(var id in ExperienceState.Names.Keys)if(!state.Paths.TryGetValue(id,out var path)||!File.Exists(path)){var found=ExperienceState.Detect(id);if(found!=null)state.Paths[id]=found;}
        using var source=GetType().Assembly.GetManifestResourceStream("CadToolkitSetup.guides.json")!;
        guides=JsonDocument.Parse(source).RootElement.Clone();
        Title="CAD Toolkit｜設定與使用"; Width=1060; Height=820; MinWidth=480; MinHeight=360;
        MaxHeight=SystemParameters.WorkArea.Height; MaxWidth=SystemParameters.WorkArea.Width;
        WindowStartupLocation=WindowStartupLocation.CenterScreen;
        FontFamily=new FontFamily("Microsoft JhengHei UI"); FontSize=15;
        Background=new SolidColorBrush(Color.FromRgb(244,247,249)); Foreground=Ink;
        var buttonStyle=new Style(typeof(Button));
        buttonStyle.Setters.Add(new Setter(Control.FontSizeProperty, 14.0));
        var focus=new Trigger { Property=UIElement.IsKeyboardFocusedProperty, Value=true };
        focus.Setters.Add(new Setter(Control.BorderBrushProperty, Accent)); focus.Setters.Add(new Setter(Control.BorderThicknessProperty,new Thickness(3)));
        buttonStyle.Triggers.Add(focus); Resources.Add(typeof(Button),buttonStyle);
        var shell=new Grid { Margin=new Thickness(24,18,24,16) };
        shell.RowDefinitions.Add(new(){Height=GridLength.Auto}); shell.RowDefinitions.Add(new(){Height=new GridLength(1,GridUnitType.Star)}); shell.RowDefinitions.Add(new(){Height=GridLength.Auto}); Content=shell;
        var header=new StackPanel(); shell.Children.Add(header);
        var brand=new DockPanel(); header.Children.Add(brand);
        var menu=new WrapPanel { HorizontalAlignment=HorizontalAlignment.Right }; DockPanel.SetDock(menu,Dock.Right); brand.Children.Add(menu);
        Button(menu,"首頁",()=>{page="home";Render();return Task.CompletedTask;});
        Button(menu,"教學",()=>{page="guides";Render();return Task.CompletedTask;});
        Button(menu,"設定",()=>{page="settings";Render();return Task.CompletedTask;});
        brand.Children.Add(T("CAD Toolkit",22,true));
        header.Children.Add(T("讓 AI 助手陪你使用 CAD  ·  "+service.Version,12));
        header.Children.Add(nav);
        var scroll=new ScrollViewer { Content=body, VerticalScrollBarVisibility=ScrollBarVisibility.Auto, HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled, Margin=new Thickness(0,12,0,10) };
        Grid.SetRow(scroll,1); shell.Children.Add(scroll);
        var bottom=new StackPanel(); Grid.SetRow(bottom,2); shell.Children.Add(bottom);
        bottom.Children.Add(progress); bottom.Children.Add(status);
        var detail=new Expander { Header="詳細資料與技術紀錄",Content=log, Margin=new Thickness(0,4,0,8) }; bottom.Children.Add(detail);
        var line=new DockPanel(); bottom.Children.Add(line); DockPanel.SetDock(cancel,Dock.Right);line.Children.Add(cancel);line.Children.Add(footer);
        cancel.Click+=(_,_)=>Stop();
        service.Log=s=>{log.AppendText(s+"\n");log.ScrollToEnd();};
        service.Report=s=>status.Text=s;
        service.Progress=p=>{progress.IsIndeterminate=!p.HasValue;if(p.HasValue)progress.Value=p.Value;};
        service.Event=e=>{
            if(e.TryGetProperty("cancellable",out var c)&&c.ValueKind==JsonValueKind.False){transaction=true;cancel.IsEnabled=false;}
            if(e.TryGetProperty("component",out var id)&&id.ValueKind==JsonValueKind.String&&e.TryGetProperty("result",out var result)&&result.ValueKind==JsonValueKind.Object){checks[id.GetString()!]=result.Clone();checkedAt[id.GetString()!]=DateTimeOffset.Now;}
            if(ExperienceState.Text(e,"step")=="install"&&ExperienceState.Text(e,"component") is string component&&component.Length>0){installProgress[component]=ExperienceState.Text(e,"message");if(page=="wizard"&&state.Step==3)Render();}
        };
        Closing+=(_,e)=>{if(busy){e.Cancel=true;Stop();}else Save();};
        var componentArg=args.FirstOrDefault(a=>a.StartsWith("--components="));
        if(componentArg!=null){state.Selected=componentArg[13..].Split(',').Where(ExperienceState.Names.ContainsKey).Distinct().ToArray();if(Selected.Length==0)state.Selected=ExperienceState.Names.Keys.ToArray();}
        if(state.Completed)page="home";
        // Saved UI progress never substitutes for installed files or current diagnostics.
        if(state.Step>3&&!Selected.Any(Installed))state.Step=3;
        if(state.Step>3&&Installation.TryGetProperty("candidate",out var candidate)&&candidate.ValueKind==JsonValueKind.Object&&ExperienceState.Text(candidate,"version")!=service.Version)state.Step=3;
        var render=args.FirstOrDefault(a=>a.StartsWith("--render-preview=")); preview=render!=null;
        var requested=args.FirstOrDefault(a=>a.StartsWith("--page="));
        if(requested!=null){var value=requested[7..];if(int.TryParse(value,out int s)){state.Step=Math.Clamp(s,0,6);page="wizard";}else page=value;}
        var size=args.FirstOrDefault(a=>a.StartsWith("--size="));if(size!=null){var v=size[7..].Split('x');Width=double.Parse(v[0]);Height=double.Parse(v[1]);}
        Render();
        var timer=new System.Windows.Threading.DispatcherTimer { Interval=TimeSpan.FromMinutes(1) };
        timer.Tick+=(_,_)=>{if(!busy&&checks.Count>0)Render();};timer.Start();Closed+=(_,_)=>timer.Stop();
        if(args.Contains("--update"))Loaded+=async(_,_)=>await Safe(async()=>{page="wizard";state.Step=3;Render();await Install();});
        if(args.Contains("--uninstall"))Loaded+=async(_,_)=>await Safe(()=>Confirm("uninstall","解除安裝會移除 Toolkit 的連線設定並還原舊設定。版本與備份會保留。繼續？"));
        if(render!=null)Loaded+=async(_,_)=>{
            await Task.Delay(250);UpdateLayout();
            var dpiArg=args.FirstOrDefault(a=>a.StartsWith("--dpi="));double dpi=dpiArg==null?96:double.Parse(dpiArg[6..]);
            var bitmap=new RenderTargetBitmap((int)(ActualWidth*dpi/96),(int)(ActualHeight*dpi/96),dpi,dpi,PixelFormats.Pbgra32);bitmap.Render(this);
            var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(bitmap));using(var f=File.Create(render[17..]))encoder.Save(f);Close();
        };
    }
    static TextBlock T(string text,int size=15,bool bold=false)=>new(){Text=text,FontSize=size,FontWeight=bold?FontWeights.SemiBold:FontWeights.Normal,TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,4,0,8),Foreground=Ink};
    Button Button(Panel panel,string text,Func<Task> action,bool primary=false){
        var b=new Button{Content=text,Padding=new Thickness(16,10,16,10),Margin=new Thickness(0,4,8,4),MinHeight=42,Background=primary?Accent:Brushes.White,Foreground=primary?Brushes.White:Ink,BorderBrush=primary?Accent:new SolidColorBrush(Color.FromRgb(180,195,201)),BorderThickness=new Thickness(1)};
        System.Windows.Automation.AutomationProperties.SetName(b,text);
        b.Click+=async(_,_)=>await Safe(action);controls.Add(b);panel.Children.Add(b);b.IsEnabled=!busy;return b;
    }
    StackPanel Card(Panel parent,string title,string? description=null){
        var panel=new StackPanel();var border=new Border{Background=Brushes.White,CornerRadius=new CornerRadius(12),Padding=new Thickness(20,16,20,16),Margin=new Thickness(0,8,0,8),BorderBrush=new SolidColorBrush(Color.FromRgb(222,230,234)),BorderThickness=new Thickness(1),Child=panel};parent.Children.Add(border);
        panel.Children.Add(T(title,19,true));if(description!=null)panel.Children.Add(T(description));return panel;
    }
    void Save(){if(!preview)state.Save(Root);}
    void Stop(){if(transaction){status.Text="正在完成設定切換，完成後就能關閉。";return;}cancellation?.Cancel();service.RequestStop();cancel.IsEnabled=false;status.Text="已要求停止，正在等候目前安全步驟結束。已完成項目會保留。";}
    async Task Safe(Func<Task> action){
        if(busy)return;busy=true;transaction=false;lastError="";cancellation=new();service.Token=cancellation.Token;
        status.Text="請依畫面指引繼續操作。";
        controls.ForEach(b=>b.IsEnabled=false);progress.Visibility=Visibility.Visible;progress.IsIndeterminate=true;cancel.Visibility=Visibility.Visible;cancel.IsEnabled=true;
        try{await action();}
        catch(OperationCanceledException){lastError="已停止。下載可重新開始，安裝會接續已完成的元件。";}
        catch(Exception ex){service.Log(ex.ToString());lastError=Friendly(ex);}
        finally{busy=false;transaction=false;cancel.Visibility=Visibility.Collapsed;progress.Visibility=Visibility.Collapsed;controls.ForEach(b=>b.IsEnabled=true);Save();Render();if(lastError.Length>0)status.Text=lastError;}
    }
    static string Friendly(Exception ex)=>ex switch {
        System.Net.Http.HttpRequestException=>"下載失敗。請確認網路後重試，或把同版本套件放在安裝程式旁。原有版本已保留。",
        IOException io when (io.HResult&0xffff)==112=>"磁碟空間不足。請釋放至少 3 GB 空間後重試。",
        InvalidDataException=>"下載檔案未通過驗證。請重新下載同一版本的安裝程式與套件。",
        InvalidOperationException=>"需要處理："+ex.Message,
        _=>"作業未完成。請再次嘗試；若仍失敗，展開詳細資料查看技術原因。" };
    static void Open(string path)=>Process.Start(new ProcessStartInfo(path){UseShellExecute=true});
    Task Go(int step){state.Step=step;page="wizard";Save();Render();return Task.CompletedTask;}
    void Render(){
        body.Children.Clear();footer.Children.Clear();nav.Children.Clear();
        // Drop detached page controls, retain the three global navigation buttons.
        if(controls.Count>3)controls.RemoveRange(3,controls.Count-3);
        if(page=="wizard"){
            nav.Children.Add(T($"首次設定  /  第 {state.Step+1} 步，共 7 步  ·  {steps[state.Step]}",14,true));
            body.Children.Add(T(steps[state.Step],28,true));
            body.Children.Add(T("只有第一次需要逐步設定；完成後從首頁開始日常使用。",14));
            Wizard();
            if(state.Step>0){var back=Button(footer,"上一步",()=>Go(state.Step-1));footer.Children.Remove(back);footer.Children.Insert(0,back);}
        }else if(page=="home")Home();else if(page=="guides")GuidePage();else Settings();
        if(lastError.Length>0){var box=Card(body,"需要你處理",lastError);box.Children.Add(T("可在下方展開詳細資料。處理後再次按原本的操作即可重試。",13));}
    }
    JsonElement Installation=>ExperienceState.Read(Root);
    bool HasActive(string id)=>Installation.TryGetProperty("active",out var map)&&map.TryGetProperty(id,out _);
    string? Target(string id,bool active=false){
        var data=Installation;
        if(active&&data.TryGetProperty("active",out var mapping)&&mapping.TryGetProperty(id,out var p))return p.GetString();
        if(data.TryGetProperty("candidate",out var c)&&c.ValueKind==JsonValueKind.Object&&c.GetProperty("selected").EnumerateArray().Any(v=>v.GetString()==id))return c.GetProperty("path").GetString();return null;
    }
    bool Installed(string id)=>Target(id) is string path&&File.Exists(Path.Combine(path,"envs",id,"Scripts/python.exe"));
    bool Fresh(string id)=>checkedAt.TryGetValue(id,out var at)&&(DateTimeOffset.Now-at).TotalMinutes<5;
    async Task Diagnose(string id,bool active=false){checks.Remove(id);checkedAt.Remove(id);checkedTargets[id]=Target(id,active);await service.Engine("diagnose",[id],active);status.Text="檢查已結束。請依各軟體卡片的狀態繼續。";}
    async Task Install(){
        if(Selected.Length==0)throw new InvalidOperationException("請至少勾選一套軟體。");
        if(ExperienceState.Codex()==null)throw new InvalidOperationException("尚未找到 Codex。請回到「準備 AI 助手」完成安裝後重新檢查。");
        if(new DriveInfo(Path.GetPathRoot(Root)!).AvailableFreeSpace<3L*1024*1024*1024)throw new InvalidOperationException("磁碟空間不足，請先釋放至少 3 GB。");
        await service.Engine("install",Selected);checks.Clear();checkedAt.Clear();state.Step=4;status.Text="連線工具已安裝。下一步：依圖解完成 CAD 內的設定。";
    }
    async Task Activate(string id){await service.Engine("activate",[id]);await Diagnose(id,true);status.Text="工具設定已切換。請在 Codex 新增對話，完成第一次唯讀練習。";}
    async Task Confirm(string action,string text){if(MessageBox.Show(this,text,"CAD Toolkit",MessageBoxButton.YesNo,MessageBoxImage.Question)==MessageBoxResult.Yes){await service.Engine(action,Selected);checks.Clear();checkedAt.Clear();if(action=="uninstall"){state.Completed=false;state.Step=0;}status.Text=action=="rollback"?"已還原，請重新檢查連線。":"已解除 Toolkit 設定，版本及備份保留。";}}
}
