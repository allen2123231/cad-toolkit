using CadToolkit;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Automation;
using System.Net.Http;

sealed class HeldDownload : HttpMessageHandler {
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token){await Task.Delay(Timeout.Infinite,token);throw new Exception("Unexpected download completion");}
}

class DesktopChecks
{
    [System.Runtime.InteropServices.DllImport("user32.dll")] static extern IntPtr SendMessageW(IntPtr hwnd,int msg,IntPtr w,IntPtr l);
    static (int width,int height,int fill) NativeIconSize(Window window){
        return NativeIconSize(new System.Windows.Interop.WindowInteropHelper(window).Handle,1);
    }
    static (int width,int height,int fill) NativeIconSize(IntPtr window,int kind){
        var handle=SendMessageW(window,0x7F,new IntPtr(kind),IntPtr.Zero);
        if(handle==IntPtr.Zero)return (0,0,0);
        using var icon=System.Drawing.Icon.FromHandle(handle);using var bitmap=icon.ToBitmap();int minX=bitmap.Width,maxX=-1;
        for(int y=0;y<bitmap.Height;y++)for(int x=0;x<bitmap.Width;x++){var c=bitmap.GetPixel(x,y);if(c.A>100&&c.B>c.R+35){minX=Math.Min(minX,x);maxX=Math.Max(maxX,x);}}
        return(bitmap.Width,bitmap.Height,maxX-minX+1);
    }
    static int count;
    static void Assert(bool value,string label){count++;if(!value)throw new Exception(label);}
    static IEnumerable<T> Find<T>(DependencyObject root) where T:DependencyObject {
        for(int i=0;i<VisualTreeHelper.GetChildrenCount(root);i++){var child=VisualTreeHelper.GetChild(root,i);if(child is T value)yield return value;foreach(var nested in Find<T>(child))yield return nested;}
    }
    static void Capture(Window window,string file,double dpi=96){window.UpdateLayout();var surface=(FrameworkElement)window.Content;var bitmap=new RenderTargetBitmap((int)Math.Ceiling(surface.ActualWidth*dpi/96),(int)Math.Ceiling(surface.ActualHeight*dpi/96),dpi,dpi,PixelFormats.Pbgra32);bitmap.Render(surface);var png=new PngBitmapEncoder();png.Frames.Add(BitmapFrame.Create(bitmap));using var output=File.Create(file);png.Save(output);}
    [STAThread] static void Main(string[] args){
        if(args.Length==2&&args[0]=="--inspect-process-icon"){
            using var process=System.Diagnostics.Process.GetProcessById(int.Parse(args[1]));
            var big=NativeIconSize(process.MainWindowHandle,1);var small=NativeIconSize(process.MainWindowHandle,2);
            bool passed=big.width>0&&big.fill>=big.width*.8&&small.width>0&&small.fill>=small.width*.8;
            Console.WriteLine(JsonSerializer.Serialize(new{passed,pid=process.Id,big=new{big.width,big.height,big.fill},small=new{small.width,small.height,small.fill}}));
            Environment.ExitCode=passed?0:1;return;
        }
        if(args.Length==2&&args[0]=="--write-brand-icon"){File.WriteAllBytes(args[1],ToolkitVisuals.IconBytes());Console.WriteLine("Wrote multiresolution brand icon");return;}
        if(args.Length==2&&args[0]=="--inspect-installer"){
            var setup=AutomationElement.RootElement.FindFirst(TreeScope.Children,new AndCondition(new PropertyCondition(AutomationElement.ProcessIdProperty,int.Parse(args[1])),new PropertyCondition(AutomationElement.NameProperty,"安裝 MCP Toolkit")))??throw new Exception("New installer did not open while old manager was running");
            var edit=setup.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)).Cast<AutomationElement>().First(e=>e.TryGetCurrentPattern(ValuePattern.Pattern,out var pattern)&&!((ValuePattern)pattern).Current.IsReadOnly);
            var value=(ValuePattern)edit.GetCurrentPattern(ValuePattern.Pattern);string selected=value.Current.Value;
            if(Path.GetFileName(selected)!="McpToolkit")throw new Exception("New installer did not default to McpToolkit");
            var version=setup.FindFirst(TreeScope.Descendants,new PropertyCondition(AutomationElement.NameProperty,new ToolkitService(InstallLocation.DefaultPath).Version+" · Windows x64"))??throw new Exception("Old installer version was activated");
            value.SetValue(@"D:\McpToolkit UI check");if(value.Current.Value!=@"D:\McpToolkit UI check")throw new Exception("Install path cannot be changed");
            var cancel=setup.FindFirst(TreeScope.Descendants,new AndCondition(new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),new PropertyCondition(AutomationElement.NameProperty,"取消")))!;
            ((InvokePattern)cancel.GetCurrentPattern(InvokePattern.Pattern)).Invoke();
            Console.WriteLine(JsonSerializer.Serialize(new{passed=true,new_installer_opened=true,version="0.4.1-preview.1",default_path=selected,path_editable=true,cancelled_without_installing=true}));return;
        }
        if(args.Length==2&&args[0]=="--read-ready-count"){
            var manager=AutomationElement.RootElement.FindFirst(TreeScope.Children,new AndCondition(new PropertyCondition(AutomationElement.ProcessIdProperty,int.Parse(args[1])),new PropertyCondition(AutomationElement.NameProperty,"MCP Toolkit")))??throw new Exception("Manager window not found");
            Console.WriteLine(manager.FindAll(TreeScope.Descendants,new AndCondition(new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Text),new PropertyCondition(AutomationElement.NameProperty,"可以使用"))).Count);return;
        }
        if(args.Length==3&&args[0]=="--select-live-window"){
            int pid=int.Parse(args[1]);string identity=args[2];
            var target=AutomationElement.RootElement.FindFirst(TreeScope.Children,new PropertyCondition(AutomationElement.ProcessIdProperty,pid))??throw new Exception("Toolkit window not found");
            var button=target.FindFirst(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,"bind-window-"+identity))??throw new Exception("Exact window selection action not found");
            ((InvokePattern)button.GetCurrentPattern(InvokePattern.Pattern)).Invoke();Console.WriteLine("Invoked exact window selection in isolated Toolkit process");return;
        }
        string output=Path.GetFullPath(args.Length>0?args[0]:"test-results/desktop");Directory.CreateDirectory(output);var app=new Application{ShutdownMode=ShutdownMode.OnExplicitShutdown};
        app.Startup+=async(_,_)=>{try{
            if(args.Contains("--repro-autocad-recovery")){
                string panel="""{"windows":[],"requests":[],"confirmations":[],"autocad_recovery":{"recovery":{"request_id":"native-interruption-test","command":"execute-lisp"},"can_confirm":false,"target_token":"new-document-token","current_document":null}}""";
                string? action=null;string[]? received=null;
                using var recoveryHost=new RuntimeHost(Path.Combine(output,"root"),[],false,(name,arguments)=>{action=name;received=arguments;return Task.FromResult(JsonDocument.Parse(name=="windows"?panel:"{\"ok\":true}").RootElement.Clone());});
                recoveryHost.ApplyWindowSnapshot(JsonDocument.Parse(panel).RootElement);
                var view=new AutoCadRecoveryWindow(recoveryHost);view.Show();view.UpdateLayout();
                var confirm=Find<Button>(view).Single(b=>b.Content?.ToString()=="確認圖面並解除暫停");
                Assert(!confirm.IsEnabled,"Closed CAD must not be confirmable");
                Assert(!Find<CheckBox>(view).Single().IsEnabled,"Closed CAD checkbox disabled");
                Capture(view,Path.Combine(output,"cad-closed.png"),144);
                panel="""{"windows":[],"requests":[],"confirmations":[],"autocad_recovery":{"recovery":{"request_id":"native-interruption-test","command":"execute-lisp","closed_observed":true},"can_confirm":true,"target_token":"new-document-token","current_document":{"id":"fresh","name":"recovery-test.dwg","path":"C:/Test/recovery-test.dwg","units":4}}}""";
                recoveryHost.ApplyWindowSnapshot(JsonDocument.Parse(panel).RootElement);view.UpdateLayout();
                confirm=Find<Button>(view).Single(b=>b.Content?.ToString()=="確認圖面並解除暫停");var check=Find<CheckBox>(view).Single();
                Assert(check.IsEnabled&&!confirm.IsEnabled,"Reopened CAD still needs human checkbox");
                check.IsChecked=true;Assert(confirm.IsEnabled,"Inspection enables confirmation");
                recoveryHost.ApplyWindowSnapshot(JsonDocument.Parse(panel).RootElement);
                Assert(ReferenceEquals(check,Find<CheckBox>(view).Single())&&check.IsChecked==true,"Identical poll preserves inspection selection");
                Capture(view,Path.Combine(output,"cad-reopened-confirm.png"),144);
                var changed=panel.Replace("new-document-token","changed-document-token").Replace("recovery-test.dwg","another.dwg");
                recoveryHost.ApplyWindowSnapshot(JsonDocument.Parse(changed).RootElement);view.UpdateLayout();
                Assert(Find<CheckBox>(view).Single().IsChecked!=true,"Document switch resets confirmation");
                Assert(Find<TextBlock>(view).Any(t=>t.Text.Contains("不會自動重送")),"No replay warning visible");
                // Exercise a backend action without accepting the human check.
                await recoveryHost.WindowAction("confirm-autocad-recovery","--request-id","native-interruption-test","--target-token","changed-document-token");
                Assert(action=="windows","Action refreshes native state afterwards");
                view.Close();File.WriteAllText(Path.Combine(output,"report.json"),JsonSerializer.Serialize(new{passed=true,checks=count}));Console.WriteLine($"AutoCAD recovery UI: {count} checks passed");app.Shutdown();return;
            }
            if(args.Contains("--repro-mcp-management")){
                using var catalogHost=new RuntimeHost(Path.Combine(output,"catalog-root"),[],false);
                typeof(RuntimeHost).GetProperty("Snapshot")!.SetValue(catalogHost,JsonDocument.Parse("""{"rows":[{"id":"rhino","installed":true,"managed":true,"version":"0.5.3","code":"CAD_NOT_RUNNING","update":"compatible"},{"id":"autocad","installed":false,"code":"NOT_INSTALLED"},{"id":"inventor","installed":true,"managed":true,"version":"0.1.0","code":"CAD_NOT_RUNNING","update":"compatible"}],"history":[]}""").RootElement.Clone());
                catalogHost.ApplyWindowSnapshot(JsonDocument.Parse("""{"windows":[],"requests":[],"confirmations":[]}""").RootElement);
                typeof(UpdateController).GetProperty("Available")!.SetValue(catalogHost.Updates,JsonDocument.Parse("""{"version":"0.5.0-beta.7","beta":true,"notes":"# MCP Toolkit 更新\n\n## 修正\n\n- **保留設定**，支援 `acadlt.exe`。\n- [發布頁](https://github.com/allen2123231/cad-toolkit/releases)\n\n```text\nC:/Toolkit\n```"}""").RootElement.Clone());
                string? requestedComponent=null;int? requestedStep=null;var view=new ManagerWindow(catalogHost,(kind,step)=>{requestedComponent=kind;requestedStep=step;});view.Show();view.UpdateLayout();var failures=new List<string>();
                if(Find<TextBlock>(view).Any(t=>t.Text=="AutoCAD"))failures.Add("Status includes uninstalled AutoCAD");
                var tray=new TrayPanel(catalogHost,_=>{});tray.Show();tray.UpdateLayout();if(Find<TextBlock>(tray).Any(t=>t.Text=="AutoCAD"))failures.Add("Tray includes uninstalled AutoCAD");tray.Close();
                view.Navigate("install");view.UpdateLayout();if(Find<TextBlock>(view).Any(t=>t.Text=="Rhino"))failures.Add("Update page still includes per-MCP installation cards");
                if(Find<TextBlock>(view).Any(t=>t.Text.Contains("## 修正")||t.Text.Contains("**保留設定**")))failures.Add("Release notes expose raw Markdown");
                var notes=Find<System.Windows.Controls.FlowDocumentScrollViewer>(view).SingleOrDefault();
                if(notes==null)failures.Add("No native Markdown document");else{
                    var text=new System.Windows.Documents.TextRange(notes.Document.ContentStart,notes.Document.ContentEnd).Text;
                    if(text.Contains("##")||text.Contains("**")||text.Contains("`acadlt.exe`"))failures.Add("Markdown punctuation remains visible");
                    if(!notes.Document.Blocks.OfType<System.Windows.Documents.List>().Any())failures.Add("Bullet list not rendered");
                }
                if(!Find<TextBlock>(view).Any(t=>t.Text=="設定與更新"))failures.Add("Settings and updates are not combined");
                Capture(view,Path.Combine(output,"settings-updates-144.png"),144);
                view.Navigate("overview");Capture(view,Path.Combine(output,"installed-status-144.png"),144);
                view.Navigate("mcps");view.UpdateLayout();
                if(!Find<Button>(view).Any(b=>b.Content?.ToString()=="加入新 MCP（1）"))failures.Add("MCP management has no installed/uninstalled categories");
                if(Find<TextBlock>(view).Any(t=>t.Text=="AutoCAD"))failures.Add("Installed category includes an uninstalled MCP");
                if(Find<Button>(view).Any(b=>b.Content?.ToString()=="連線設定"))failures.Add("Duplicate connection settings action remains");
                if(Find<Button>(view).Count(b=>b.Content?.ToString()=="解除安裝")!=2)failures.Add("Installed cards lack individual uninstall");
                var cards=Find<McpCardGrid>(view).Single();
                if(cards.Children.Count!=2||cards.Children[0].RenderSize.Width>=cards.RenderSize.Width*.9)failures.Add("Installed cards do not use multiple grid columns");
                using(var unused=new RuntimeHost(Path.Combine(output,"removal-root"),[],false)){
                    var componentRemoval=new ComponentUninstallWindow(unused,"rhino","Rhino");componentRemoval.Show();componentRemoval.UpdateLayout();
                    if(!Find<Button>(componentRemoval).Any(b=>b.Content?.ToString()=="確認解除安裝"))failures.Add("Single MCP removal lacks scope confirmation");
                    Capture(componentRemoval,Path.Combine(output,"component-uninstall-144.png"),144);componentRemoval.Close();
                }
                Capture(view,Path.Combine(output,"mcps-installed-144.png"),144);
                view.Width=720;view.UpdateLayout();
                if(cards.Children[0].RenderSize.Width<cards.RenderSize.Width*.9)failures.Add("Narrow grid does not collapse to one column");
                Capture(view,Path.Combine(output,"mcps-installed-narrow-144.png"),144);view.Width=1050;view.UpdateLayout();
                var uninstalled=Find<Button>(view).Single(b=>b.Content?.ToString()=="加入新 MCP（1）");uninstalled.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));view.UpdateLayout();
                if(!Find<TextBlock>(view).Any(t=>t.Text=="AutoCAD")||Find<TextBlock>(view).Any(t=>t.Text=="Rhino"||t.Text=="Inventor"))failures.Add("Uninstalled category is incorrect");
                if(!Find<Button>(view).Any(b=>b.Content?.ToString()=="安裝 AutoCAD MCP"))failures.Add("Uninstalled MCP lacks its install action");
                if(Find<McpCardGrid>(view).Count()!=1)failures.Add("New MCP category does not use the shared grid");
                Capture(view,Path.Combine(output,"mcps-uninstalled-144.png"),144);
                Find<Button>(view).Single(b=>b.Content?.ToString()=="安裝 AutoCAD MCP").RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                if(requestedComponent!="autocad"||requestedStep!=3)failures.Add("Install action targets the wrong MCP");
                var future=JsonDocument.Parse("""{"components":{"rhino":{},"autocad":{},"inventor":{},"sketchup":{"display_name":"SketchUp","package_version":"1.0"}}}""").RootElement;
                if(!McpCatalog.Entries(future,catalogHost.Rows).Any(c=>c.Id=="sketchup"&&c.Name=="SketchUp"&&!c.Installed))failures.Add("Catalog is hardcoded to three MCPs");
                var unsafeNotes=MarkdownNotes.Document("[unsafe](javascript:alert(1)) ![remote](https://example.invalid/image.png)\n\n| A | B |\n|---|---|\n| 1 | 2 |");
                if(!unsafeNotes.Blocks.OfType<System.Windows.Documents.Table>().Any())failures.Add("Markdown table not rendered");
                foreach(var paragraph in unsafeNotes.Blocks.OfType<System.Windows.Documents.Paragraph>())if(paragraph.Inlines.OfType<System.Windows.Documents.Hyperlink>().Any())failures.Add("Unsafe URL is clickable");
                typeof(RuntimeHost).GetProperty("Snapshot")!.SetValue(catalogHost,JsonDocument.Parse("""{"rows":[{"id":"rhino","installed":false},{"id":"autocad","installed":false},{"id":"inventor","installed":false}],"history":[]}""").RootElement.Clone());
                view.Navigate("overview");view.UpdateLayout();if(!Find<TextBlock>(view).Any(t=>t.Text=="尚未安裝 MCP"))failures.Add("Zero installed MCPs have no empty state");
                if(Find<TextBlock>(view).Any(t=>t.Text=="Rhino"||t.Text=="AutoCAD"||t.Text=="Inventor"))failures.Add("Empty status shows uninstalled MCPs");
                view.Close();if(failures.Count>0)throw new Exception(string.Join("; ",failures));Console.WriteLine("MCP management and Markdown checks passed");app.Shutdown(0);return;
            }
            if(args.Contains("--repro-lt-ui")){
                using var ltHost=new RuntimeHost(Path.Combine(output,"lt-root"),[],false);
                typeof(RuntimeHost).GetProperty("Snapshot")!.SetValue(ltHost,JsonDocument.Parse("""{"rows":[{"id":"autocad","product":"AutoCAD LT","installed":true,"managed":true,"version":"3.2.0","code":"CAD_NOT_RUNNING","update":"compatible"}],"history":[]}""").RootElement.Clone());
                ltHost.ApplyWindowSnapshot(JsonDocument.Parse("""{"windows":[],"requests":[],"confirmations":[]}""").RootElement);
                var ltView=new ManagerWindow(ltHost,(_,_)=>{});ltView.Show();ltView.UpdateLayout();
                Assert(Find<TextBlock>(ltView).Any(t=>t.Text=="AutoCAD LT"),"LT product name is shown");Assert(Find<Button>(ltView).Any(b=>b.Content?.ToString()=="開啟 AutoCAD LT"),"LT launch has the correct product name");Assert(Find<Button>(ltView).Any(b=>b.Content?.ToString()=="選擇程式"),"Nondefault installation has a button-driven path selection");
                Capture(ltView,Path.Combine(output,"autocad-lt-144.png"),144);ltView.Close();Console.WriteLine("LT interface checks passed: "+count);app.Shutdown(0);return;
            }
            if(args.Contains("--repro-update-responsive")){
                string root=Path.Combine(output,"update-root");Directory.CreateDirectory(root);File.WriteAllText(Path.Combine(root,"state.json"),"""{"active":{"rhino":"fixture"}}""");
                using var client=new HttpClient(new HeldDownload());using var updateHost=new RuntimeHost(root,[],false,updateClient:client);
                var service=(ToolkitService)typeof(UpdateController).GetField("service",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(updateHost.Updates)!;
                typeof(UpdateController).GetProperty("Available")!.SetValue(updateHost.Updates,JsonDocument.Parse("""{"version":"99.0.0-beta.1","setup":{"url":"https://github.com/allen2123231/cad-toolkit/releases/download/v99.0.0-beta.1/McpToolkitSetup.exe","sha256":"0000000000000000000000000000000000000000000000000000000000000000"},"payload":{"url":"https://github.com/allen2123231/cad-toolkit/releases/download/v99.0.0-beta.1/cad-toolkit-payload.zip","sha256":"0000000000000000000000000000000000000000000000000000000000000000"}}""").RootElement.Clone());
                updateHost.Updates.ApplicationBlocker=_=>null;bool launched=false;updateHost.Updates.LaunchInstaller+=_=>launched=true;
                var view=new ManagerWindow(updateHost,(_,_)=>{});view.Show();view.Navigate("install");
                updateHost.Updates.ApplicationBlocker=_=>"請先儲存並關閉 AutoCAD，再按更新。CAD 文件不會自動關閉。";
                await updateHost.Updates.Apply();view.UpdateLayout();
                var warning=Find<Border>(view).Single(b=>System.Windows.Automation.AutomationProperties.GetAutomationId(b)=="update-required-action");
                Assert(warning.IsVisible&&warning.Background!=null,"Blocked update displays a prominent notice panel");
                Assert(Find<TextBlock>(warning).Any(t=>t.FontSize>=18&&t.FontWeight==FontWeights.Bold),"Required action has a large bold heading");
                Assert(Find<TextBlock>(warning).Any(t=>t.Text.Contains("AutoCAD")&&t.FontSize>=15),"Notice clearly names the application to close");
                Assert(!launched&&!updateHost.Updates.Busy,"Blocked update never starts installation");
                Capture(view,Path.Combine(output,"update-required-action-144.png"),144);
                view.Width=720;view.UpdateLayout();Capture(view,Path.Combine(output,"update-required-action-narrow-144.png"),144);view.Width=1050;view.UpdateLayout();
                updateHost.Updates.ApplicationBlocker=_=>null;
                var pending=updateHost.Updates.Apply();await Task.Delay(100);
                Assert(!Find<Border>(view).Any(b=>b.IsVisible&&System.Windows.Automation.AutomationProperties.GetAutomationId(b)=="update-required-action"),"Successful retry hides the resolved required action");
                Assert(Find<ProgressBar>(view).Any(p=>p.IsIndeterminate),"Unknown progress is visibly animated");Assert(Find<Button>(view).Any(b=>b.Content?.ToString()=="取消下載"),"Download cancel action is available");
                var title=Find<TextBlock>(view).First(t=>t.Text=="MCP Toolkit");for(int i=0;i<100;i++)service.Report("下載安裝套件 · "+i+" MB");
                Assert(Find<TextBlock>(view).Contains(title),"Download feedback keeps the existing visual tree");
                await Task.Delay(2200);Assert(Find<TextBlock>(view).Any(t=>t.Text.Contains("已耗時")&&!t.Text.Contains("00:00")),"Dispatcher and elapsed feedback remain live during stalled download");
                Capture(view,Path.Combine(output,"update-progress-144.png"),144);updateHost.Updates.CancelDownload();await pending;Assert(!launched&&!updateHost.Updates.Busy,"Cancelling stalled download never starts installation");view.Close();
                Console.WriteLine("Responsive update UI checks passed: "+count);app.Shutdown(0);return;
            }
            if(args.Contains("--repro-management-refresh")){
                var faults=new List<string>();
                var snapshot=JsonDocument.Parse("""{"rows":[{"id":"autocad","installed":true,"version":"3.2.0","update":"compatible","code":"CAD_NOT_RUNNING"},{"id":"inventor","installed":true,"version":"0.1.0","update":"compatible","code":"CAD_NOT_RUNNING"},{"id":"rhino","installed":true,"version":"0.5.3","update":"compatible","code":"CAD_NOT_RUNNING"}]}""").RootElement.Clone();
                TaskCompletionSource<JsonElement>? response=null;
                Task<JsonElement> ProbeManagement(string action,string[] arguments)=>action=="snapshot"?response!.Task:Task.FromResult(JsonDocument.Parse("""{"windows":[],"requests":[],"confirmations":[]}""").RootElement.Clone());
                using var quietHost=new RuntimeHost(Path.Combine(output,"management-refresh-root"),[],false,ProbeManagement);
                typeof(RuntimeHost).GetProperty("Snapshot")!.SetValue(quietHost,snapshot);
                quietHost.ApplyWindowSnapshot(JsonDocument.Parse("""{"windows":[],"requests":[],"confirmations":[]}""").RootElement);
                var management=new ManagerWindow(quietHost,(_,_)=>{}){Width=720,Height=530};management.Show();management.Navigate("mcps");management.UpdateLayout();
                var original=Find<Button>(management).Single(b=>System.Windows.Automation.AutomationProperties.GetAutomationId(b)=="recheck-autocad");
                var grid=Find<McpCardGrid>(management).Single();
                var scroller=Find<ScrollViewer>(management).First(v=>v.ScrollableHeight>0);scroller.ScrollToVerticalOffset(90);management.UpdateLayout();double scroll=scroller.VerticalOffset;
                var point=original.TranslatePoint(new Point(),management);
                for(int cycle=0;cycle<3;cycle++){
                    response=new(TaskCreationOptions.RunContinuationsAsynchronously);var background=quietHost.Refresh();management.UpdateLayout();
                    var button=Find<Button>(management).Single(b=>System.Windows.Automation.AutomationProperties.GetAutomationId(b)=="recheck-autocad");
                    if(button.Content?.ToString()!="重新檢查"||!button.IsEnabled)faults.Add("Background refresh changes or disables the manual recheck button");
                    if(!ReferenceEquals(button,original)||!Find<McpCardGrid>(management).Contains(grid))faults.Add("Background refresh rebuilds MCP management cards");
                    if(cycle==0)Capture(management,Path.Combine(output,"background-refresh-144.png"),144);
                    response.SetResult(snapshot);await background;management.UpdateLayout();
                    if(Math.Abs(scroller.VerticalOffset-scroll)>.5||Math.Abs(original.TranslatePoint(new Point(),management).Y-point.Y)>.5)faults.Add("Background refresh changes scroll or button position");
                }
                response=new(TaskCreationOptions.RunContinuationsAsynchronously);var manual=quietHost.Recheck("autocad");await Task.Yield();management.UpdateLayout();
                if(!Find<Button>(management).Any(b=>System.Windows.Automation.AutomationProperties.GetAutomationId(b)=="recheck-autocad"&&b.Content?.ToString()=="檢查中…"&&!b.IsEnabled))faults.Add("Manual recheck has no progress feedback");
                if(Find<Button>(management).Any(b=>System.Windows.Automation.AutomationProperties.GetAutomationId(b)=="recheck-rhino"&&b.Content?.ToString()=="檢查中…"))faults.Add("Manual recheck changes unrelated software labels");
                response.SetResult(snapshot);await manual;management.UpdateLayout();
                Capture(management,Path.Combine(output,"management-stable-144.png"),144);
                response=new(TaskCreationOptions.RunContinuationsAsynchronously);var failing=quietHost.Refresh();response.SetException(new IOException("fixture background failure"));await failing;management.UpdateLayout();
                if(!Find<TextBlock>(management).Any(t=>t.Text=="連線狀態：檢查失敗")||!Find<Button>(management).Contains(original))faults.Add("In-place refresh hides failure or rebuilds cards");
                response=new(TaskCreationOptions.RunContinuationsAsynchronously);var recovered=quietHost.Refresh();response.SetResult(snapshot);await recovered;management.UpdateLayout();
                if(Find<TextBlock>(management).Any(t=>t.Text=="連線狀態：檢查失敗"))faults.Add("Recovered status remains stale");
                response=new(TaskCreationOptions.RunContinuationsAsynchronously);var removed=quietHost.Refresh();
                response.SetResult(JsonDocument.Parse("""{"rows":[{"id":"autocad","installed":true,"version":"3.2.0","code":"CAD_NOT_RUNNING"},{"id":"inventor","installed":true,"version":"0.1.0","code":"CAD_NOT_RUNNING"},{"id":"rhino","installed":false,"code":"NOT_INSTALLED"}]}""").RootElement.Clone());await removed;management.UpdateLayout();
                if(!Find<Button>(management).Any(b=>b.Content?.ToString()=="已安裝（2）")||Find<Button>(management).Any(b=>System.Windows.Automation.AutomationProperties.GetAutomationId(b)=="recheck-rhino"))faults.Add("Installation changes no longer update the catalog");
                management.Close();
                if(faults.Count>0)throw new Exception(string.Join("; ",faults.Distinct()));
                Console.WriteLine("Quiet management background refresh checks passed");app.Shutdown(0);return;
            }
            if(args.Contains("--repro-refresh-cards")){
                var delayed=new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);var second=new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);var secondStarted=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);int requests=0;
                Task<JsonElement> Probe(string action,string[] arguments){if(action!="snapshot")return Task.FromResult(JsonDocument.Parse("""{"windows":[],"requests":[],"confirmations":[]}""").RootElement.Clone());requests++;if(requests==1)return delayed.Task;if(requests==2){secondStarted.SetResult(true);return second.Task;}return Task.FromException<JsonElement>(new InvalidOperationException("fixture diagnostic failure"));}
                using var checking=new RuntimeHost(Path.Combine(output,"checking-root"),[],false,Probe);
                int changes=0;checking.Changed+=()=>changes++;
                var view=new ManagerWindow(checking,(_,_)=>{});view.ShowActivated=false;view.Show();view.Navigate("install");view.UpdateLayout();
                var faults=new List<string>();if(Find<TextBlock>(view).Any(t=>t.Text=="Toolkit 更新")&&Find<TextBlock>(view).Any(t=>t.Text=="MCP Toolkit"))faults.Add("Toolkit version and update cards are duplicated");
                var refresh=checking.Refresh();if(changes==0||!checking.Message.Contains("檢查"))faults.Add("Refresh has no immediate visible progress event");
                var queued=checking.Recheck("rhino");if(queued.IsCompleted||!checking.Message.Contains("排入"))faults.Add("Busy refresh drops the user's manual request");
                var result=JsonDocument.Parse("""{"rows":[{"id":"rhino","installed":true,"managed":true,"pending":false,"code":"CAD_NOT_RUNNING","document":null}],"history":[]}""").RootElement.Clone();
                delayed.SetResult(result);await refresh;await secondStarted.Task;view.Navigate("overview");view.UpdateLayout();
                if(!checking.IsManualCheck||!Find<Button>(view).Any(b=>System.Windows.Automation.AutomationProperties.GetAutomationId(b)=="recheck-rhino"&&!b.IsEnabled&&b.Content?.ToString()=="檢查中…"))faults.Add("Manual MCP check does not show a disabled progress button");
                second.SetResult(result);await queued;
                if(checking.LastCheckedAt("rhino")==null||!checking.Message.Contains("完成"))faults.Add("Refresh completion has no timestamp or result");
                await checking.Recheck("rhino");
                if(!checking.Rows.Any(r=>ExperienceState.Flag(r,"installed")&&ExperienceState.Text(r,"code")=="CHECK_FAILED")||!checking.Message.Contains("fixture diagnostic failure"))faults.Add("A failed check hides installed MCPs or loses the error");
                view.Close();
                if(faults.Count>0)throw new Exception(string.Join("; ",faults));
                Console.WriteLine("Merged card and refresh feedback checks passed");app.Shutdown(0);return;
            }
            using var host=new RuntimeHost(Path.Combine(output,"isolated-root"),[],false);
            if(args.Contains("--repro-desktop-issues")){
                var faults=new List<string>();
                if(Path.GetFileName(ToolkitApplication.Root(["--new-install"]))!="McpToolkit")faults.Add("Default folder is still CadToolkit");
                var setup=new InstallWindow(host);setup.ShowActivated=false;setup.Show();setup.UpdateLayout();
                var actualIcon=NativeIconSize(setup);Console.WriteLine("Native taskbar icon (width,height,blue fill): "+actualIcon);
                if(actualIcon.fill<actualIcon.width*.8)faults.Add("Native taskbar icon has excessive empty space");
                if(!Find<TextBox>(setup).Any(t=>!t.IsReadOnly))faults.Add("Installation path cannot be edited");
                var pathBox=Find<TextBox>(setup).FirstOrDefault(t=>!t.IsReadOnly);
                if(pathBox!=null){string custom=Path.Combine(output,"自訂安裝位置");pathBox.Text=custom;typeof(InstallWindow).GetMethod("SelectPage",BindingFlags.Instance|BindingFlags.NonPublic)!.Invoke(setup,null);if(pathBox.Text!=custom||InstallLocation.Validate(pathBox.Text)!=custom)faults.Add("Custom path is lost on retry");}
                if(setup.Icon is not BitmapFrame)faults.Add("Window icon uses natural-size vector instead of a multiresolution icon");
                setup.Close();
                typeof(RuntimeHost).GetProperty("Snapshot")!.SetValue(host,JsonDocument.Parse("""{"rows":[{"id":"rhino","installed":true,"code":"READY","document":{"name":"closed model"}},{"id":"inventor","installed":true,"code":"READY","document":{"name":"closed part"}}]}""").RootElement.Clone());
                host.ApplyWindowSnapshot(JsonDocument.Parse("""{"windows":[],"requests":[],"confirmations":[]}""").RootElement);
                if(host.Rows.Any(r=>ExperienceState.Text(r,"code")=="READY"||r.GetProperty("document").ValueKind!=JsonValueKind.Null))faults.Add("Cached readiness survives visible-window close");
                if(faults.Count>0)throw new Exception(string.Join("; ",faults));
                Console.WriteLine("Desktop issue reproduction passed");app.Shutdown(0);return;
            }
            var fixture=JsonDocument.Parse("""
            {"at":"2026-11-16T10:00:00Z","rows":[
            {"id":"rhino","code":"READY","installed":true,"managed":true,"version":"0.5.3","update":"compatible","endpoint":"127.0.0.1:1999","verified_windows":[{"pid":501,"hwnd":1501,"processStart":1,"instance_id":"rhino-one"}],"document":{"name":"練習模型.3dm"}},
            {"id":"autocad","code":"CAD_NOT_RUNNING","installed":true,"managed":true,"version":"3.2.0","update":"compatible","endpoint":"檔案 IPC · 無網路端口","document":null},
            {"id":"inventor","code":"READY","installed":true,"managed":true,"version":"0.1.0","update":"compatible","endpoint":"COM · 無網路端口","verified_windows":[{"pid":502,"hwnd":1502,"processStart":1,"instance_id":null}],"document":null}],
            "history":[{"component":"rhino","tool":"create_object","outcome":"succeeded","at":"2026-11-16T10:00:00Z","duration_ms":142}]}
            """);
            typeof(RuntimeHost).GetProperty("Snapshot")!.SetValue(host,fixture.RootElement.Clone());
            host.ApplyWindowSnapshot(JsonDocument.Parse("""{"requests":[],"confirmations":[],"windows":[{"kind":"rhino","window_id":"initial-rhino","pid":501,"hwnd":1501,"processStart":1,"instance_id":"rhino-one","display_name":"Rhino 01","binding":null},{"kind":"inventor","window_id":"initial-inventor","pid":502,"hwnd":1502,"processStart":1,"instance_id":null,"display_name":"Inventor 01","binding":null}]}""").RootElement);
            var window=new ManagerWindow(host,(_,_)=>{});window.ShowActivated=false;window.Show();
            foreach(string page in new[]{"overview","history","install","settings"}){
                host.ApplyWindowSnapshot(host.WindowPanel);
                window.Navigate(page);window.UpdateLayout();Assert(Find<Button>(window).All(b=>b.Focusable),"Keyboard focus "+page);
                Assert(!Find<TextBlock>(window).Any(t=>t.Text.Contains("最新版本")),"Compatibility is not an online latest assertion");
                if(page=="overview"){
                    foreach(string name in new[]{"Rhino","AutoCAD","Inventor"})Assert(Find<Button>(window).Any(b=>b.Content?.ToString()=="開啟 "+name),"Correct application action "+name);
                    Assert(Find<TextBlock>(window).Any(t=>t.Text=="Inventor 01"),"Inventor home frame remains named without a document");
                    Assert(Find<Image>(window).Count()>=6,"Native application and document icons");
                }
                foreach(int dpi in new[]{96,144,192})Capture(window,Path.Combine(output,page+"-"+dpi+".png"),dpi);
            }
            window.Close();
            typeof(UpdateController).GetProperty("Available")!.SetValue(host.Updates,JsonDocument.Parse("""{"version":"0.5.1-beta.1","beta":true,"notes":"Beta 測試版：更新會保留原安裝位置、視窗名稱與 MCP 啟用設定。"}""").RootElement.Clone());
            var updateView=new ManagerWindow(host,(_,_)=>{});updateView.ShowActivated=false;updateView.Show();updateView.Navigate("install");updateView.UpdateLayout();
            Assert(Find<Button>(updateView).Any(b=>b.Content?.ToString()=="立即更新（保留設定）"),"Available update exposes a single retained-settings action");
            Assert(Find<Button>(updateView).Any(b=>b.Content?.ToString()=="稍後提醒")&&Find<Button>(updateView).Any(b=>b.Content?.ToString()=="略過此版本"),"Update reminder choices remain available");
            Capture(updateView,Path.Combine(output,"beta-update-144.png"),144);updateView.Navigate("settings");updateView.UpdateLayout();
            Assert(Find<Button>(updateView).Any(b=>b.Content?.ToString()=="完整解除安裝 MCP Toolkit"),"Complete uninstaller is accessible in settings");updateView.Close();
            var removal=new UninstallWindow(host.Root);removal.ShowActivated=false;removal.Show();removal.UpdateLayout();
            Assert(Find<Button>(removal).Any(b=>b.Content?.ToString()=="確認完整解除安裝"),"Removal requires explicit scope confirmation");
            Capture(removal,Path.Combine(output,"uninstall-144.png"),144);removal.Close();
            var windowsFixture=JsonDocument.Parse("""
            {"requests":[{"id":"request-a","label":"連線 01","code":"ABC123"},{"id":"request-b","label":"連線 02","code":"DEF456"}],
             "confirmations":[{"id":"binding-b","label":"連線 03","window_name":"Rhino 02 · 零件測試","context":{"document_serial":22,"document_epoch":3,"document":"新文件.3dm"}}],
             "windows":[
              {"kind":"rhino","window_id":"one","display_name":"Rhino 01 · 造型工作台","guard_protocol":1,"pid":101,"hwnd":1001,"port":1999,"version":"0.5.3","document":"同名文件.3dm","binding":null},
              {"kind":"rhino","window_id":"two","display_name":"Rhino 02 · 零件測試","guard_protocol":1,"pid":102,"hwnd":1002,"port":2000,"version":"0.5.3","document":"同名文件.3dm","binding":{"id":"binding-b","label":"連線 03","busy":0}},
              {"kind":"autocad","window_id":"three","display_name":"AutoCAD 01","pid":103,"hwnd":1003,"binding":null},
              {"kind":"autocad","window_id":"four","display_name":"AutoCAD 02","pid":104,"hwnd":1004,"binding":null},
              {"kind":"inventor","window_id":"five","display_name":"Inventor 01","pid":105,"hwnd":1005,"binding":null}]}
            """);
            host.ApplyWindowSnapshot(windowsFixture.RootElement);
            var picker=new WindowPicker(host);picker.ShowActivated=false;picker.Show();picker.UpdateLayout();
            Assert(Find<ComboBox>(picker).Single().Items.Count==2,"Multiple pending conversations are distinguishable");
            Assert(Find<Button>(picker).Any(b=>b.Content?.ToString()=="連線")&&Find<Button>(picker).Any(b=>b.Content?.ToString()=="轉交並連線"),"Free and occupied windows have explicit actions");
            Assert(Find<TextBlock>(picker).Any(t=>t.Text=="Rhino 01 · 造型工作台")&&Find<TextBlock>(picker).Any(t=>t.Text=="Rhino 02 · 零件測試"),"Window identity is independent of same-name files");
            Assert(Find<Button>(picker).Any(b=>b.Content?.ToString()=="確認使用目前文件"),"Document switch needs confirmation");
            foreach(int dpi in new[]{96,144,192})Capture(picker,Path.Combine(output,"window-picker-"+dpi+".png"),dpi);picker.Close();
            var multi=new ManagerWindow(host,(_,_)=>{});multi.ShowActivated=false;multi.Show();multi.UpdateLayout();
            foreach(string name in new[]{"AutoCAD 01","AutoCAD 02","Inventor 01"})Assert(Find<TextBlock>(multi).Any(t=>t.Text==name),"Named native frames "+name);
            Assert(Find<TextBlock>(multi).Any(t=>t.Text.Contains("對話綁定尚未開放")),"Other CAD routing is not falsely advertised");
            Capture(multi,Path.Combine(output,"multi-window-overview-144.png"),144);multi.Close();
            var install=new InstallWindow(host,"rhino");install.ShowActivated=false;install.Show();install.UpdateLayout();
            Assert(Find<TextBlock>(install).Any(t=>t.Text=="安裝一次，開啟軟體就能連線"),"New installer entry point");
            Assert(!Find<TextBlock>(install).Any(t=>t.Text.Contains("首次設定 ·")||t.Text.Contains("1 / 8")),"Old wizard is not presented");
            Assert(Find<CheckBox>(install).Count()==3,"Three independently selectable MCPs");
            Assert(ExperienceState.ExecutableNames("autocad").SequenceEqual(new[]{"acad.exe","acadlt.exe"}),"AutoCAD and LT are included in detection and update process guards");
            var installPath=Find<TextBox>(install).First(t=>!t.IsReadOnly);installPath.Text=@"C:\Users\Demo\AppData\Local\McpToolkit";
            Capture(install,Path.Combine(output,"install-selection-144.png"),144);install.Close();
            var popup=new TrayPanel(host,_=>{});popup.ShowActivated=false;popup.Show();popup.UpdateLayout();
            Assert(popup.ShowInTaskbar==false&&popup.Width==390,"Compact notification-area panel");
            Assert(Find<TextBlock>(popup).Any(t=>t.Text=="Rhino 01 · 造型工作台")&&Find<TextBlock>(popup).Any(t=>t.Text=="Rhino 02 · 零件測試"),"Tray names each window independently of the health-probe document");
            Capture(popup,Path.Combine(output,"tray-192.png"),192);popup.Close();
            using var plain=ToolkitVisuals.TrayIcon(false);using var connected=ToolkitVisuals.TrayIcon(true);Assert(plain.Width==32&&connected.Width==32,"Native plug tray icons render");
            using(var ico=File.Create(Path.Combine(output,"mcp-toolkit.ico")))plain.Save(ico);
            File.WriteAllText(Path.Combine(output,"report.json"),JsonSerializer.Serialize(new{passed=true,assertions=count,scope="Native WPF render, real assets, keyboard focus, state labels; fixture data, no CAD edits"}));Console.WriteLine("Desktop checks passed: "+count);app.Shutdown(0);
        }catch(Exception ex){Console.Error.WriteLine(ex);app.Shutdown(1);}};app.Run();
    }
}
