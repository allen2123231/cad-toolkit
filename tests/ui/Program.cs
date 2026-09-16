using CadToolkit;
using System.IO;
using System.Text.Json;
using System.Net.Http;
using System.Security.Cryptography;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
class UiChecks
{
    class Transport : HttpMessageHandler {
        public bool Fail;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token){
            token.ThrowIfCancellationRequested();
            if(Fail)throw new HttpRequestException("network unavailable");
            return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK){Content=new ByteArrayContent([1,2,3])});
        }
    }
    static int assertions;
    static void Assert(bool value,string description){if(!value)throw new Exception(description);assertions++;}
    static IEnumerable<T> Descendants<T>(DependencyObject item) where T:DependencyObject {
        for(int i=0;i<VisualTreeHelper.GetChildrenCount(item);i++){
            var child=VisualTreeHelper.GetChild(item,i);if(child is T match)yield return match;
            foreach(var nested in Descendants<T>(child))yield return nested;
        }
    }
    [STAThread] static void Main(string[] args){
        var output=Path.GetFullPath(args.Length>0?args[0]:"test-results/ui");Directory.CreateDirectory(output);
        var app=new Application{ShutdownMode=ShutdownMode.OnExplicitShutdown};
        app.Startup+=async(_,_)=>{
            try{
                var root=Path.Combine(output,"中文 空白路徑");Directory.CreateDirectory(root);
                foreach(var mask in Enumerable.Range(1,7)){
                    var selected=ExperienceState.Names.Keys.Where((_,i)=>(mask&(1<<i))!=0).ToArray();
                    var state=new ExperienceState{Step=4,Selected=selected};state.Save(root);
                    var saved=ExperienceState.Load(root);Assert(saved.Step==4&&saved.Selected.SequenceEqual(selected),"Wizard roundtrip " +mask);
                }
                File.Delete(Path.Combine(root,"ui-state.json"));
                File.WriteAllText(Path.Combine(root,"state.json"),"{\"schema\":1,\"active\":{},\"candidate\":{\"path\":\"old\",\"selected\":[\"inventor\"],\"version\":\"0.1.0-preview.1\"}}");
                var legacy=ExperienceState.Load(root);Assert(legacy.Step==4&&!legacy.Completed&&legacy.Selected.SequenceEqual(new[]{"inventor"}),"Legacy candidate migration");
                var original=File.ReadAllText(Path.Combine(root,"state.json"));legacy.Save(root);Assert(File.ReadAllText(Path.Combine(root,"state.json"))==original,"Preserve engine state");
                File.WriteAllText(Path.Combine(root,"ui-state.json"),"{\"Schema\":1,\"Step\":5,\"Selected\":[\"inventor\"]}");
                Assert(ExperienceState.Load(root).Step==6,"Legacy diagnostics step migrates past Plugin page");
                File.WriteAllText(Path.Combine(root,"ui-state.json"),"{\"Schema\":1,\"Step\":6,\"Selected\":[\"rhino\"]}");
                Assert(ExperienceState.Load(root).Step==7,"Legacy practice step migrates");
                var resume=new ExperienceState{Step=4,Interrupted=true,LastOperation="install",GuideSteps=new(){{"rhino",1}}};resume.Save(root);
                Assert(ExperienceState.Load(root).Interrupted&&ExperienceState.Load(root).GuideSteps["rhino"]==1,"Interrupted operation and guide page persist");
                var transport=new Transport();var service=new ToolkitService(root,new HttpClient(transport));
                var download=Path.Combine(root,"download.bin");File.WriteAllText(download,"old");
                string url="https://github.com/allen2123231/cad-toolkit/releases/download/v0.2.0-preview.1/test.bin";
                try{await service.Download(url,download,new string('0',64));throw new Exception("Bad checksum accepted");}catch(InvalidDataException){}
                Assert(File.ReadAllText(download)=="old"&&!Directory.EnumerateFiles(root,"*.part").Any(),"Bad hash preserves file and cleans partial");
                transport.Fail=true;
                try{await service.Download(url,download,new string('0',64));throw new Exception("Network failure accepted");}catch(HttpRequestException){}
                Assert(File.ReadAllText(download)=="old","Network failure preserves file");transport.Fail=false;
                service.Token=new CancellationToken(true);
                try{await service.Download(url,download,new string('0',64));throw new Exception("Cancellation ignored");}catch(OperationCanceledException){}
                Assert(File.ReadAllText(download)=="old"&&!Directory.EnumerateFiles(root,"*.part").Any(),"Cancellation preserves file");service.Token=default;
                await service.Download(url,download,Convert.ToHexString(SHA256.HashData(new byte[]{1,2,3})));
                Assert(File.ReadAllBytes(download).SequenceEqual(new byte[]{1,2,3}),"Retry succeeds with verified bytes");
                if(args.Contains("--payload")){
                    File.Copy(Path.GetFullPath("dist/cad-toolkit-payload.zip"),Path.Combine(AppContext.BaseDirectory,"cad-toolkit-payload.zip"),true);
                    var offline=new ToolkitService(Path.Combine(root,"離線 解壓"),new HttpClient(new Transport{Fail=true}));
                    var extracted=await offline.Payload();
                    using var bundle=JsonDocument.Parse(File.ReadAllText(Path.Combine(extracted,"bundle.json")));
                    Assert(bundle.RootElement.GetProperty("version").GetString()==offline.Version,"Embedded release matches offline bundle");
                    foreach(var file in bundle.RootElement.GetProperty("files").EnumerateObject()){
                        using var input=File.OpenRead(Path.Combine(extracted,file.Name));
                        Assert(Convert.ToHexString(SHA256.HashData(input)).Equals(file.Value.GetString(),StringComparison.OrdinalIgnoreCase),"Extracted checksum "+file.Name);
                    }
                    Assert(await offline.Payload()==extracted,"Completed extraction reused");
                }
                var screens=new List<object>();
                var imageLoader=typeof(SetupWindow).GetMethod("GuideImage",System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Static)!;
                foreach(var name in new[]{"autocad-command.png","autocad-appload.png","autocad-success.png","inventor-home.png","rhino-input.png","rhino-result.png"}){
                    var image=(System.Windows.Media.Imaging.BitmapSource)imageLoader.Invoke(null,new object[]{name})!;
                    Assert(image.PixelWidth>0&&image.PixelHeight>0,"Offline screenshot embedded "+name);
                    Assert(image.DpiX==96&&image.DpiY==96,"Screenshot metadata does not shrink text "+name);
                }
                foreach(var dpi in new[]{96,144,192})foreach(var page in new[]{"0","1","2","3","4","5","6","7","home","guides","settings","updates","restore","uninstall","help","complete"}){
                    var size=dpi==96?"1180x820":"640x540";
                    var png=Path.Combine(output,$"{page}-{dpi}.png");
                    var window=new SetupWindow(new[]{"--root="+Path.Combine(output,"empty"),"--page="+page,"--size="+size,"--dpi="+dpi,"--render-preview="+png});
                    window.ShowActivated=false;var closed=new TaskCompletionSource();window.Closed+=(_,_)=>closed.SetResult();window.Show();window.UpdateLayout();
                    var buttons=Descendants<Button>(window).Where(b=>b.IsEnabled&&b.IsVisible).ToArray();Assert(buttons.Length>=3,"Navigation available "+page);
                    var footer=(WrapPanel)typeof(SetupWindow).GetField("footer",System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Instance)!.GetValue(window)!;
                    // Primary wizard actions live outside the scrolling content.
                    if(int.TryParse(page,out _)){
                        var main=Descendants<Button>(footer).FirstOrDefault(b=>b.Background is SolidColorBrush brush&&brush.Color.R==9&&brush.Color.G==108);
                        if(main!=null){var bounds=main.TransformToAncestor(window).TransformBounds(new Rect(0,0,main.ActualWidth,main.ActualHeight));Assert(bounds.Right<=window.ActualWidth&&bounds.Bottom<=window.ActualHeight,"Primary action is clipped "+page+" "+dpi);}
                    }
                    Assert(buttons.All(b=>b.Focusable),"Buttons support keyboard focus");
                    if(page=="home")Assert(!Descendants<TextBlock>(window).Any(t=>t.Text.Contains("✓ 可以使用")),"History must not imply connection");
                    await closed.Task;Assert(File.Exists(png)&&new FileInfo(png).Length>1000,"Rendered "+png);
                    screens.Add(new{page,dpi,size});
                }
                File.WriteAllText(Path.Combine(output,"report.json"),JsonSerializer.Serialize(new{passed=true,assertions,screens,scope="WPF layout/render and focusability; not physical monitor DPI or human testing"}));
                Console.WriteLine($"UI checks passed: {assertions} assertions, {screens.Count} screens");app.Shutdown(0);
            }catch(Exception e){File.WriteAllText(Path.Combine(output,"report.json"),JsonSerializer.Serialize(new{passed=false,error=e.ToString()}));Console.Error.WriteLine(e);app.Shutdown(1);}
        };app.Run();
    }
}
