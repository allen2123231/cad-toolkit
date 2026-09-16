using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
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
    readonly Dictionary<string,string> installProgress = new();
    readonly StackPanel body = new(), sidebar = new();
    readonly WrapPanel footer = new();
    readonly Grid shell = new();
    readonly ScrollViewer contentScroll;
    readonly Border sidebarBorder;
    readonly TextBlock breadcrumb = T("",12), status = T("準備好了，依照畫面開始設定。",13);
    readonly TextBox log = new() { IsReadOnly=true, TextWrapping=TextWrapping.Wrap, VerticalScrollBarVisibility=ScrollBarVisibility.Auto, MinHeight=90, MaxHeight=140, FontSize=12 };
    readonly ProgressBar progress = new() { Height=6, Minimum=0, Maximum=100, Visibility=Visibility.Collapsed, Margin=new Thickness(0,4,0,8) };
    readonly Button cancel = new() { Content="安全停止", Padding=new Thickness(12,8,12,8), Visibility=Visibility.Collapsed };
    readonly List<Control> controls = new();
    CancellationTokenSource? cancellation;
    bool busy, transaction, preview, updateChecked;
    string page="wizard", guideId="autocad", lastError="", operation="", receipt="";
    static readonly string[] steps = ["歡迎", "選擇軟體", "準備 AI 助手", "安裝連線工具", "設定 CAD", "安裝 Plugin", "確認可以使用", "第一次使用"];
    static readonly Brush Ink = Brush("#233C36"), Accent = Brush("#096C56"), Muted = Brush("#657A70"), Line = Brush("#DCE6DF"), Mint=Brush("#EAF5EE");
    static Brush Brush(string hex)=>new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex));
    string Root=>service.Root;
    string[] Selected=>state.Selected;
    string[] Managed=>ExperienceState.Names.Keys.Where(id=>Target(id,true)!=null||Target(id)!=null).ToArray();
    bool PluginReady=>ExperienceState.Flag(Installation,"plugin_registered") && ExperienceState.Text(Installation,"plugin_candidate_path")==ExperienceState.Text(Candidate,"path");
    JsonElement Installation=>ExperienceState.Read(Root);
    JsonElement Candidate=>Installation.TryGetProperty("candidate",out var c)&&c.ValueKind==JsonValueKind.Object?c:default;
    bool AnyReady=>checks.Any(p=>Fresh(p.Key)&&ExperienceState.Text(p.Value,"code")=="READY"&&checkedTargets.GetValueOrDefault(p.Key)==Target(p.Key,true));

    public SetupWindow(string[] args){
        var root=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CadToolkit");
        var own=Path.GetDirectoryName(Environment.ProcessPath!)!;
        if(Path.GetFileName(own).Equals("CadToolkit",StringComparison.OrdinalIgnoreCase)&&File.Exists(Path.Combine(own,"state.json")))root=own;
        var rootArg=args.FirstOrDefault(a=>a.StartsWith("--root="));if(rootArg!=null)root=Path.GetFullPath(rootArg[7..]);
        preview=args.Any(a=>a.StartsWith("--render-preview="));
        service=new(root);state=ExperienceState.Load(root);
        if(!preview)foreach(var id in ExperienceState.Names.Keys)if(!state.Paths.TryGetValue(id,out var path)||!File.Exists(path)){var found=ExperienceState.Detect(id);if(found!=null)state.Paths[id]=found;}
        using var source=GetType().Assembly.GetManifestResourceStream("CadToolkitSetup.guides.json")!;
        guides=JsonDocument.Parse(source).RootElement.Clone();
        Title="CAD Toolkit｜設定與使用";Width=1180;Height=860;MinWidth=480;MinHeight=420;
        MaxHeight=SystemParameters.WorkArea.Height;MaxWidth=SystemParameters.WorkArea.Width;
        WindowStartupLocation=WindowStartupLocation.CenterScreen;FontFamily=new FontFamily("Microsoft JhengHei UI");FontSize=15;
        Background=Brush("#F3F6F3");Foreground=Ink;
        var style=new Style(typeof(Button));style.Setters.Add(new Setter(Control.FontSizeProperty,14.0));
        var template=new ControlTemplate(typeof(Button));
        var border=new FrameworkElementFactory(typeof(Border));border.Name="surface";
        border.SetValue(Border.CornerRadiusProperty,new CornerRadius(8));
        border.SetValue(Border.BackgroundProperty,new TemplateBindingExtension(Control.BackgroundProperty));
        border.SetValue(Border.BorderBrushProperty,new TemplateBindingExtension(Control.BorderBrushProperty));
        border.SetValue(Border.BorderThicknessProperty,new TemplateBindingExtension(Control.BorderThicknessProperty));
        border.SetValue(Border.PaddingProperty,new TemplateBindingExtension(Control.PaddingProperty));
        var presenter=new FrameworkElementFactory(typeof(ContentPresenter));presenter.SetValue(FrameworkElement.HorizontalAlignmentProperty,HorizontalAlignment.Center);presenter.SetValue(FrameworkElement.VerticalAlignmentProperty,VerticalAlignment.Center);border.AppendChild(presenter);template.VisualTree=border;
        style.Setters.Add(new Setter(Control.TemplateProperty,template));
        var focus=new Trigger{Property=UIElement.IsKeyboardFocusedProperty,Value=true};focus.Setters.Add(new Setter(Control.BorderBrushProperty,Brush("#DA7B36")));focus.Setters.Add(new Setter(Control.BorderThicknessProperty,new Thickness(3)));style.Triggers.Add(focus);
        var disabled=new Trigger{Property=UIElement.IsEnabledProperty,Value=false};disabled.Setters.Add(new Setter(UIElement.OpacityProperty,0.45));style.Triggers.Add(disabled);Resources.Add(typeof(Button),style);
        shell.Background=Background;shell.ColumnDefinitions.Add(new(){Width=new GridLength(218)});shell.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});Content=shell;
        sidebarBorder=new Border{Background=Brushes.White,BorderBrush=Line,BorderThickness=new Thickness(0,0,1,0),Padding=new Thickness(16,24,12,12),Child=new ScrollViewer{Content=sidebar,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled}};shell.Children.Add(sidebarBorder);
        var workspace=new Grid();Grid.SetColumn(workspace,1);shell.Children.Add(workspace);
        workspace.RowDefinitions.Add(new(){Height=GridLength.Auto});workspace.RowDefinitions.Add(new(){Height=new GridLength(1,GridUnitType.Star)});workspace.RowDefinitions.Add(new(){Height=GridLength.Auto});
        var top=new DockPanel{Margin=new Thickness(24,16,24,12)};workspace.Children.Add(top);
        var menu=new WrapPanel{HorizontalAlignment=HorizontalAlignment.Right};DockPanel.SetDock(menu,Dock.Right);top.Children.Add(menu);
        // Top controls have their own handlers so page rebuilds do not retain detached controls.
        foreach(var entry in new[]{("首頁","home"),("教學","guides"),("設定","settings"),("？","help")}){
            var b=new Button{Content=entry.Item1,Padding=new Thickness(9,5,9,5),Margin=new Thickness(4),Background=Brushes.White,BorderBrush=Line,BorderThickness=new Thickness(1)};
            b.Click+=async(_,_)=>{if(!busy)await Navigate(entry.Item2);};menu.Children.Add(b);
        }
        top.Children.Add(breadcrumb);
        contentScroll=new ScrollViewer{Content=body,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,Margin=new Thickness(28,12,28,12)};Grid.SetRow(contentScroll,1);workspace.Children.Add(contentScroll);
        var bottom=new StackPanel{Margin=new Thickness(28,8,28,18)};Grid.SetRow(bottom,2);workspace.Children.Add(bottom);
        bottom.Children.Add(progress);bottom.Children.Add(status);bottom.Children.Add(new Expander{Header="詳細資料與技術紀錄",Content=log,Margin=new Thickness(0,4,0,8)});
        var actionLine=new DockPanel();bottom.Children.Add(actionLine);DockPanel.SetDock(cancel,Dock.Right);actionLine.Children.Add(cancel);actionLine.Children.Add(footer);cancel.Click+=(_,_)=>Stop();
        SizeChanged+=(_,_)=>{bool narrow=ActualWidth<900;sidebarBorder.Visibility=narrow?Visibility.Collapsed:Visibility.Visible;shell.ColumnDefinitions[0].Width=new GridLength(narrow?0:218);};
        service.Log=s=>{log.AppendText(s+"\n");log.ScrollToEnd();};service.Report=s=>status.Text=s;
        service.Progress=p=>{progress.IsIndeterminate=!p.HasValue;if(p.HasValue)progress.Value=p.Value;};
        service.Event=e=>{
            if(e.TryGetProperty("cancellable",out var c)&&c.ValueKind==JsonValueKind.False){transaction=true;cancel.IsEnabled=false;}
            if(ExperienceState.Text(e,"step")=="diagnose"&&e.TryGetProperty("component",out var id)&&id.ValueKind==JsonValueKind.String&&e.TryGetProperty("result",out var result)&&result.ValueKind==JsonValueKind.Object){checks[id.GetString()!]=result.Clone();checkedAt[id.GetString()!]=DateTimeOffset.Now;}
            if(ExperienceState.Text(e,"step")=="install"&&ExperienceState.Text(e,"component") is string component&&component.Length>0){installProgress[component]=ExperienceState.Text(e,"message");if(page=="wizard"&&state.Step==3)Render();}
        };
        Closing+=(_,e)=>{if(busy){e.Cancel=true;Stop();}else Save();};
        var componentArg=args.FirstOrDefault(a=>a.StartsWith("--components="));if(componentArg!=null)state.Selected=componentArg[13..].Split(',').Where(ExperienceState.Names.ContainsKey).Distinct().ToArray();
        if(state.Completed)page="home";
        if(state.Step>3&&!Selected.Any(Installed))state.Step=3;
        if(state.Step>3&&Candidate.ValueKind==JsonValueKind.Object&&ExperienceState.Text(Candidate,"version")!=service.Version)state.Step=3;
        var requested=args.FirstOrDefault(a=>a.StartsWith("--page="));if(requested!=null){var value=requested[7..];if(int.TryParse(value,out int s)){state.Step=Math.Clamp(s,0,7);page="wizard";}else page=value;}
        var guideArg=args.FirstOrDefault(a=>a.StartsWith("--guide="));if(guideArg!=null)guideId=guideArg[8..];
        var size=args.FirstOrDefault(a=>a.StartsWith("--size="));if(size!=null){var v=size[7..].Split('x');Width=double.Parse(v[0]);Height=double.Parse(v[1]);}
        Render();
        var timer=new System.Windows.Threading.DispatcherTimer{Interval=TimeSpan.FromMinutes(1)};timer.Tick+=(_,_)=>{if(!busy&&checks.Count>0)Render();};timer.Start();Closed+=(_,_)=>timer.Stop();
        if(args.Contains("--update"))Loaded+=async(_,_)=>await Safe(async()=>{page="wizard";state.Step=3;Render();await Install();});
        if(args.Contains("--uninstall")){page="uninstall";Render();}
        if(state.Interrupted)status.Text="上次作業中斷。已完成元件保留，請在原步驟重試；連線狀態需要重新檢查。";
        var render=args.FirstOrDefault(a=>a.StartsWith("--render-preview="));
        if(render!=null)Loaded+=async(_,_)=>{await Task.Delay(250);UpdateLayout();var dpiArg=args.FirstOrDefault(a=>a.StartsWith("--dpi="));double dpi=dpiArg==null?96:double.Parse(dpiArg[6..]);var surface=(FrameworkElement)Content;var bitmap=new RenderTargetBitmap((int)(surface.ActualWidth*dpi/96),(int)(surface.ActualHeight*dpi/96),dpi,dpi,PixelFormats.Pbgra32);bitmap.Render(surface);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(bitmap));using(var f=File.Create(render[17..]))encoder.Save(f);Close();};
    }
    static TextBlock T(string text,int size=15,bool bold=false)=>new(){Text=text,FontSize=size,FontWeight=bold?FontWeights.SemiBold:FontWeights.Normal,TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,4,0,8),Foreground=Ink};
    Button Button(Panel parent,string text,Func<Task> action,bool primary=false){
        var b=new Button{Content=new TextBlock{Text=text,TextWrapping=TextWrapping.Wrap},Padding=new Thickness(15,10,15,10),Margin=new Thickness(0,4,8,4),MinHeight=42,MaxWidth=420,Background=primary?Accent:Brushes.White,Foreground=primary?Brushes.White:Ink,BorderBrush=primary?Accent:Line,BorderThickness=new Thickness(1)};
        System.Windows.Automation.AutomationProperties.SetName(b,text);b.Click+=async(_,_)=>await Safe(action);controls.Add(b);parent.Children.Add(b);b.IsEnabled=!busy;return b;
    }
    StackPanel Card(Panel parent,string title,string? text=null){var p=new StackPanel();parent.Children.Add(new Border{Background=Brushes.White,CornerRadius=new CornerRadius(13),Padding=new Thickness(22,18,22,18),Margin=new Thickness(0,8,0,8),BorderBrush=Line,BorderThickness=new Thickness(1),Child=p});if(title.Length>0)p.Children.Add(T(title,19,true));if(text!=null)p.Children.Add(T(text));return p;}
    void Header(string over,string text,string sub){body.Children.Add(T(over,12,true));body.Children.Add(T(text,28,true));var t=T(sub,14);t.Foreground=Muted;body.Children.Add(t);}
    void Notice(Panel parent,string title,string text,bool warning=false){var p=new StackPanel();p.Children.Add(T(title,15,true));p.Children.Add(T(text,14));parent.Children.Add(new Border{Background=warning?Brush("#FFF4DC"):Mint,BorderBrush=warning?Brush("#E7D4A8"):Line,BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(9),Padding=new Thickness(16,10,16,10),Margin=new Thickness(0,10,0,10),Child=p});}
    void Save(){if(!preview)state.Save(Root);}
    void Stop(){if(transaction){status.Text="正在完成設定切換，請等待完成。";return;}cancellation?.Cancel();service.RequestStop();cancel.IsEnabled=false;status.Text="已要求安全停止，正在等待目前步驟結束。";}
    async Task Safe(Func<Task> action){
        if(busy||preview)return;busy=true;transaction=false;lastError="";cancellation=new();service.Token=cancellation.Token;controls.ForEach(c=>c.IsEnabled=false);
        try{await action();}catch(OperationCanceledException){lastError="已安全停止。已完成的元件會保留，可以在這一步重試。";}
        catch(Exception ex){service.Log(ex.ToString());lastError=Friendly(ex);}
        finally{busy=false;transaction=false;cancel.Visibility=Visibility.Collapsed;progress.Visibility=Visibility.Collapsed;if(operation.Length>0)state.Interrupted=lastError.Length>0;operation="";Save();Render();if(lastError.Length>0)status.Text=lastError;}
    }
    async Task Work(string label,Func<Task> work){operation=label;state.LastOperation=label;state.Interrupted=true;Save();status.Text=label;progress.Visibility=Visibility.Visible;progress.IsIndeterminate=true;cancel.Visibility=Visibility.Visible;cancel.IsEnabled=true;await work();state.Interrupted=false;state.LastOperation="";Save();}
    static string Friendly(Exception ex)=>ex switch{
        System.Net.Http.HttpRequestException=>"下載失敗。確認網路後重試，或將同版本套件放在安裝程式旁。原有版本已保留。",
        IOException io when(io.HResult&0xffff)==112=>"磁碟空間不足。請釋放至少 3 GB 再重試。",
        InvalidDataException=>"檔案驗證未通過。請重新下載同版本的 EXE 與安裝套件。",
        InvalidOperationException=>"需要處理："+ex.Message,_=>"作業未完成。處理後重試；原始錯誤可在詳細資料查看。"};
    static void Open(string path)=>Process.Start(new ProcessStartInfo(path){UseShellExecute=true});
    Task Navigate(string name){page=name;contentScroll.ScrollToTop();Save();Render();return Task.CompletedTask;}
    Task Go(int step){state.Step=Math.Clamp(step,0,7);return Navigate("wizard");}
    void Navigation(){
        sidebar.Children.Clear();sidebar.Children.Add(T("C  CAD Toolkit",22,true));sidebar.Children.Add(T("把 AI 和你的 CAD 接起來",12));sidebar.Children.Add(T("首次設定",12));
        for(int i=0;i<steps.Length;i++){int s=i;NavButton($"{i+1}  {steps[i]}",()=>Go(s),page=="wizard"&&state.Step==s);}
        sidebar.Children.Add(T("每天使用",12));foreach(var entry in new[]{("⌂  日常首頁","home"),("↑  檢查新版","updates"),("⚙  設定","settings"),("？  問題處理","help")})NavButton(entry.Item1,()=>Navigate(entry.Item2),page==entry.Item2);
        sidebar.Children.Add(T(service.Version+"\nWindows x64 · 本機執行",11));
    }
    void NavButton(string text,Func<Task> action,bool selected){var b=Button(sidebar,text,action);b.Background=selected?Mint:Brushes.Transparent;b.Foreground=selected?Accent:Muted;b.BorderBrush=Brushes.Transparent;b.Padding=new Thickness(10,8,10,8);}
    void Render(){
        body.Children.Clear();footer.Children.Clear();controls.Clear();Navigation();breadcrumb.Text="CAD Toolkit / "+(page=="wizard"?steps[state.Step]:page switch{"home"=>"日常首頁","updates"=>"版本更新","guides"=>"圖解教學","help"=>"問題處理","restore"=>"還原版本","uninstall"=>"解除安裝","complete"=>"設定完成",_=>"設定"});
        if(page=="wizard"){Header($"首次設定 · {state.Step+1} / 8",steps[state.Step],"只有第一次需要逐步設定；下次從首頁開始使用。");Wizard();if(state.Step>0){var back=Button(footer,"← 上一步",()=>Go(state.Step-1));footer.Children.Remove(back);footer.Children.Insert(0,back);}}
        else switch(page){case "home":Home();break;case "guides":GuidePage();break;case "updates":Updates();break;case "help":Help();break;case "restore":RestorePage();break;case "uninstall":UninstallPage();break;case "complete":Complete();break;default:Settings();break;}
        if(lastError.Length>0)Notice(body,"需要你處理",lastError+"\n處理後按原操作重試。詳細資料保留完整技術原因。",true);
    }
    bool HasActive(string id)=>Installation.TryGetProperty("active",out var map)&&map.TryGetProperty(id,out _);
    string? Target(string id,bool active=false){var data=Installation;if(active&&data.TryGetProperty("active",out var m)&&m.TryGetProperty(id,out var p))return p.GetString();if(Candidate.ValueKind==JsonValueKind.Object&&Candidate.GetProperty("selected").EnumerateArray().Any(v=>v.GetString()==id))return Candidate.GetProperty("path").GetString();return null;}
    bool Installed(string id)=>Target(id) is string path&&File.Exists(Path.Combine(path,"envs",id,"Scripts/python.exe"));
    bool Fresh(string id)=>checkedAt.TryGetValue(id,out var at)&&(DateTimeOffset.Now-at).TotalMinutes<5;
    async Task Diagnose(string id,bool active=false){checks.Remove(id);checkedAt.Remove(id);checkedTargets[id]=Target(id,active);await Work("正在唯讀檢查 "+ExperienceState.Names[id],async()=>await service.Engine("diagnose",[id],active));status.Text="檢查結束，請依各卡片的實際結果繼續。";}
    async Task CheckAll(bool active){foreach(var id in (active?Managed:Selected))await Diagnose(id,active&&HasActive(id));}
    async Task Install(){
        if(Selected.Length==0)throw new InvalidOperationException("請至少勾選一套軟體。");
        if(ExperienceState.Codex()==null)throw new InvalidOperationException("尚未找到 Codex。請先完成「準備 AI 助手」。");
        if(new DriveInfo(Path.GetPathRoot(Root)!).AvailableFreeSpace<3L*1024*1024*1024)throw new InvalidOperationException("磁碟空間不足，請先釋放至少 3 GB。");
        await Work("正在準備連線工具",async()=>await service.Engine("install",Selected));checks.Clear();checkedAt.Clear();state.Step=4;state.Completed=false;state.ReadonlyAcknowledged=false;status.Text="元件已準備好，接著完成 CAD 端設定。";
    }
    async Task Activate(string id){state.ReadonlyAcknowledged=false;await Work("正在驗證與啟用 "+ExperienceState.Names[id],async()=>await service.Engine("activate",[id]));await Diagnose(id,true);status.Text=AnyReady?"已有工具可使用。請在 Codex 新增對話做唯讀確認。":"設定已切換，但最新診斷尚未通過。請查看狀態卡片。";}
    Task Copy(string text){Clipboard.SetText(text);status.Text="已複製。切換到指定應用程式貼上。";return Task.CompletedTask;}
}
