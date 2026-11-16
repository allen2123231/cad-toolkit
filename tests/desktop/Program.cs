using CadToolkit;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;

class DesktopChecks
{
    static int count;
    static void Assert(bool value,string label){count++;if(!value)throw new Exception(label);}
    static IEnumerable<T> Find<T>(DependencyObject root) where T:DependencyObject {
        for(int i=0;i<VisualTreeHelper.GetChildrenCount(root);i++){var child=VisualTreeHelper.GetChild(root,i);if(child is T value)yield return value;foreach(var nested in Find<T>(child))yield return nested;}
    }
    static void Capture(Window window,string file,double dpi=96){window.UpdateLayout();var surface=(FrameworkElement)window.Content;var bitmap=new RenderTargetBitmap((int)Math.Ceiling(surface.ActualWidth*dpi/96),(int)Math.Ceiling(surface.ActualHeight*dpi/96),dpi,dpi,PixelFormats.Pbgra32);bitmap.Render(surface);var png=new PngBitmapEncoder();png.Frames.Add(BitmapFrame.Create(bitmap));using var output=File.Create(file);png.Save(output);}
    [STAThread] static void Main(string[] args){
        string output=Path.GetFullPath(args.Length>0?args[0]:"test-results/desktop");Directory.CreateDirectory(output);var app=new Application{ShutdownMode=ShutdownMode.OnExplicitShutdown};
        app.Startup+=(_,_)=>{try{
            using var host=new RuntimeHost(Path.Combine(output,"isolated-root"),[],false);
            var fixture=JsonDocument.Parse("""
            {"at":"2026-11-16T10:00:00Z","rows":[
            {"id":"rhino","code":"READY","installed":true,"managed":true,"version":"0.5.2","update":"compatible","endpoint":"127.0.0.1:1999","document":{"name":"練習模型.3dm"}},
            {"id":"autocad","code":"CAD_NOT_RUNNING","installed":true,"managed":true,"version":"3.2.0","update":"compatible","endpoint":"檔案 IPC · 無網路端口","document":null},
            {"id":"inventor","code":"READY","installed":true,"managed":true,"version":"0.1.0","update":"compatible","endpoint":"COM · 無網路端口","document":null}],
            "history":[{"component":"rhino","tool":"create_object","outcome":"succeeded","at":"2026-11-16T10:00:00Z","duration_ms":142}]}
            """);
            typeof(RuntimeHost).GetProperty("Snapshot")!.SetValue(host,fixture.RootElement.Clone());
            var window=new ManagerWindow(host,(_,_)=>{});window.ShowActivated=false;window.Show();
            foreach(string page in new[]{"overview","history","install","settings"}){
                window.Navigate(page);window.UpdateLayout();Assert(Find<Button>(window).All(b=>b.Focusable),"Keyboard focus "+page);
                Assert(!Find<TextBlock>(window).Any(t=>t.Text.Contains("最新版本")),"Compatibility is not an online latest assertion");
                if(page=="overview"){
                    foreach(string name in new[]{"Rhino","AutoCAD","Inventor"})Assert(Find<Button>(window).Any(b=>b.Content?.ToString()=="開啟 "+name),"Correct application action "+name);
                    Assert(Find<TextBlock>(window).Any(t=>t.Text=="首頁／無文件"),"Inventor home is valid");
                    Assert(Find<Image>(window).Count()>=6,"Native application and document icons");
                }
                foreach(int dpi in new[]{96,144,192})Capture(window,Path.Combine(output,page+"-"+dpi+".png"),dpi);
            }
            window.Close();
            var install=new InstallWindow(host,"rhino");install.ShowActivated=false;install.Show();install.UpdateLayout();
            Assert(Find<TextBlock>(install).Any(t=>t.Text=="安裝一次，開啟軟體就能連線"),"New installer entry point");
            Assert(!Find<TextBlock>(install).Any(t=>t.Text.Contains("首次設定 ·")||t.Text.Contains("1 / 8")),"Old wizard is not presented");
            Assert(Find<CheckBox>(install).Count()==3,"Three independently selectable MCPs");
            var installPath=Find<TextBlock>(install).FirstOrDefault(t=>t.Text==host.Root);if(installPath!=null)installPath.Text=@"C:\Users\Demo\AppData\Local\McpToolkit";
            Capture(install,Path.Combine(output,"install-selection-144.png"),144);install.Close();
            var popup=new TrayPanel(host,_=>{});popup.ShowActivated=false;popup.Show();popup.UpdateLayout();
            Assert(popup.ShowInTaskbar==false&&popup.Width==390,"Compact notification-area panel");
            Assert(Find<TextBlock>(popup).Any(t=>t.Text=="練習模型.3dm"),"Tray reads actual snapshot document");
            Capture(popup,Path.Combine(output,"tray-192.png"),192);popup.Close();
            using var plain=ToolkitVisuals.TrayIcon(false);using var connected=ToolkitVisuals.TrayIcon(true);Assert(plain.Width==32&&connected.Width==32,"Native plug tray icons render");
            using(var ico=File.Create(Path.Combine(output,"mcp-toolkit.ico")))plain.Save(ico);
            File.WriteAllText(Path.Combine(output,"report.json"),JsonSerializer.Serialize(new{passed=true,assertions=count,scope="Native WPF render, real assets, keyboard focus, state labels; fixture data, no CAD edits"}));Console.WriteLine("Desktop checks passed: "+count);app.Shutdown(0);
        }catch(Exception ex){Console.Error.WriteLine(ex);app.Shutdown(1);}};app.Run();
    }
}
