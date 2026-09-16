using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Microsoft.Win32;
namespace CadToolkit;
public sealed partial class SetupWindow
{
    void Wizard(){switch(state.Step){
        case 0:
            var welcome=Card(body,"讓 AI 助手看得見你的 CAD","跟著精靈完成工具安裝、CAD 設定與第一次使用。不需要自己準備 Python、Git 或 .NET 開發工具。");
            var diagram=new WrapPanel();welcome.Children.Add(diagram);
            foreach(var text in new[]{"✦  AI 助手\n在 Codex 說出需求","⇄  CAD Toolkit\n連線工具與操作教學","▧  你的 CAD\n查看文件、繪圖與建模"})diagram.Children.Add(new Border{Background=Mint,CornerRadius=new CornerRadius(10),Padding=new Thickness(18),Margin=new Thickness(0,8,10,8),Child=T(text,16,true)});
            Card(body,"只有第一次","勾選軟體 → 安裝工具 → 完成 CAD 端設定 → 安裝 Plugin → 檢查並逐套啟用。");
            Card(body,"每次使用","開啟 CAD，依軟體啟動連線，再先確認目前文件與單位。Inventor 可以先停在首頁。");
            Notice(body,"先準備","Windows x64、至少一套已啟用的 CAD、可登入的 ChatGPT 帳號、網路與約 3 GB 空間。中途離開會記錄進度。");
            Button(footer,"開始設定 →",()=>Go(1),true);break;
        case 1:
            body.Children.Add(T("先選一套也可以，日後到「設定」加入其他軟體。沒找到時可指定程式位置或稍後設定。"));
            var choiceRow=new WrapPanel();body.Children.Add(choiceRow);
            Button(choiceRow,"全部勾選",()=>{state.Selected=ExperienceState.Names.Keys.ToArray();return Task.CompletedTask;});
            Button(choiceRow,"清除選取",()=>{state.Selected=[];return Task.CompletedTask;});
            foreach(var id in ExperienceState.Names.Keys){
                string? path=state.Paths.GetValueOrDefault(id);var c=Card(body,ExperienceState.Names[id]);
                var check=new CheckBox{Content="安裝這套軟體的連線工具",IsChecked=Selected.Contains(id),Padding=new Thickness(4,8,4,8),MinHeight=40,IsEnabled=!busy};controls.Add(check);c.Children.Add(check);
                check.Click+=(_,_)=>{state.Selected=check.IsChecked==true?Selected.Append(id).Distinct().ToArray():Selected.Where(x=>x!=id).ToArray();Save();Render();};
                string version="";try{if(File.Exists(path))version=FileVersionInfo.GetVersionInfo(path).ProductVersion??"";}catch{}
                c.Children.Add(T(File.Exists(path)?"✓ 已找到  "+version:"○ 尚未偵測到安裝位置",14,true));c.Children.Add(T(path??"可先安裝連線工具，CAD 稍後設定。",12));
                Button(c,"指定程式位置…",()=>{var dialog=new OpenFileDialog{Title="選擇 "+ExperienceState.Names[id]+" 的執行檔",Filter="程式 (*.exe)|*.exe"};if(dialog.ShowDialog(this)==true){string expected=id switch{"autocad"=>"acad.exe","inventor"=>"Inventor.exe",_=>"Rhino.exe"};if(!Path.GetFileName(dialog.FileName).Equals(expected,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("請選擇 "+expected);state.Paths[id]=dialog.FileName;}return Task.CompletedTask;});
            }
            var next=Button(footer,$"下一步 · 已選 {Selected.Length} 套 →",()=>Go(2),true);next.IsEnabled=!busy&&Selected.Length>0;break;
        case 2:
            Guide(body,"codex");
            var ai=Card(body,ExperienceState.Codex()!=null?"✓ 已找到 Codex":"○ 尚未找到 Codex","程式偵測不代表已登入。請在官方應用程式完成登入，Toolkit 不會要求你的密碼。");
            Button(ai,"官方 Windows 入門 ↗",()=>{Open("https://learn.chatgpt.com/docs/windows/windows-app");return Task.CompletedTask;});
            Button(ai,"重新檢查",()=>{status.Text=ExperienceState.Codex()!=null?"已找到 Codex，請自行確認登入。":"尚未找到 Codex。請完成安裝後重新開啟應用程式再試。";return Task.CompletedTask;});
            var ack=new CheckBox{Content=T("我已登入，並能在 Codex 新增對話",14),IsChecked=state.AiReady,IsEnabled=!busy};controls.Add(ack);ai.Children.Add(ack);ack.Click+=(_,_)=>{state.AiReady=ack.IsChecked==true;Save();Render();};
            var aiNext=Button(footer,"下一步：安裝工具 →",()=>Go(3),true);aiNext.IsEnabled=!busy&&state.AiReady&&ExperienceState.Codex()!=null;break;
        case 3:
            Card(body,"安裝選定的連線工具",string.Join("、",Selected.Select(id=>ExperienceState.Names[id]))+"。工具使用獨立環境，先和原有設定並存。");
            foreach(var id in Selected)Card(body,ExperienceState.Names[id],installProgress.GetValueOrDefault(id)??(Installed(id)?"✓ 元件已存在，重試會核對並接續已完成項目。":"○ 等待安裝"));
            Notice(body,"準備流程","下載固定套件 → 驗證完整性 → 建立獨立環境 → 檢查 MCP → 完成元件準備。進度會顯示在下方。下載可取消，安裝在安全步驟停止。");
            if(state.Interrupted)Notice(body,"繼續上次作業","已完成元件會保留。按「安裝並繼續」重試未完成部分。",true);
            Button(footer,"安裝並繼續 →",Install,true).IsEnabled=!busy&&Selected.Length>0;
            if(Selected.Length>0&&Selected.All(Installed)&&ExperienceState.Text(Candidate,"version")==service.Version)Button(body,"元件已備妥，繼續 CAD 設定",()=>Go(4));break;
        case 4:
            body.Children.Add(T("依照每套軟體的真實截圖操作；暫時無法完成的項目可以稍後處理。"));
            var tabs=new WrapPanel();body.Children.Add(tabs);if(!Selected.Contains(guideId))guideId=Selected.FirstOrDefault()??"autocad";
            foreach(var id in Selected)Button(tabs,ExperienceState.Names[id],()=>{guideId=id;return Task.CompletedTask;},id==guideId);
            Guide(body,guideId);GuideActions(body,guideId);
            if(checks.ContainsKey(guideId))StatusCard(body,guideId,false);
            Button(footer,"下一步：安裝 Plugin →",()=>Go(5),true);break;
        case 5:PluginPage();break;
        case 6:
            Notice(body,"通過一套，就能先開始","先檢查連線，再逐套啟用。未通過的元件保留原有設定；Inventor 在首頁即可確認應用程式連線。");
            Button(body,"檢查所選軟體",()=>CheckAll(false),true).IsEnabled=!busy&&Selected.Length>0;
            StatusCards(body,Selected,false);
            Button(footer,"使用已通過的工具 →",()=>Go(7),true).IsEnabled=!busy&&AnyReady;break;
        case 7:Practice();break;
    }}
    void PluginPage(){
        var c=Card(body,"把 CAD 工具加入 Codex","先備份現有設定。新元件先保持停用，連線通過後才逐套切換。");
        foreach(var id in Selected)c.Children.Add(T("✓ "+ExperienceState.Names[id]+" MCP",16,true));
        c.Children.Add(T("一起提供的中文 Skills",17,true));
        var skills=new List<string>{"安裝與診斷","跨軟體檔案交接"};if(Selected.Contains("autocad"))skills.Add("AutoCAD 繪圖");if(Selected.Contains("inventor"))skills.AddRange(["Inventor 建模","Inventor 標準件"]);if(Selected.Contains("rhino"))skills.Add("Rhino 建模");c.Children.Add(T(string.Join("、",skills),14));
        Notice(body,PluginReady?"✓ 這組 Plugin 已安裝":"○ 等待安裝 Plugin","透過 Codex 的 marketplace 與 plugin 指令安裝，不直接改寫快取。完成後還需要檢查 CAD 連線。");
        Button(body,PluginReady?"重新安裝 Plugin":"安裝整合 Plugin",async()=>{if(!Selected.All(Installed))throw new InvalidOperationException("先回到「安裝連線工具」準備所選元件。");await Work("正在安裝 Plugin",async()=>await service.Engine("configure_plugin",Selected));status.Text="Plugin 已安裝。接著檢查 CAD 並逐套啟用。";},!PluginReady).IsEnabled=!busy&&Selected.Length>0&&Selected.All(Installed);
        Button(footer,"下一步：確認可以使用 →",()=>Go(6),true).IsEnabled=!busy&&PluginReady;
    }
    void Guide(Panel parent,string id){
        var g=guides.GetProperty(id);
        if(id=="codex"){
            var c=Card(parent,g.GetProperty("title").GetString()!,g.GetProperty("purpose").GetString());int i=0;foreach(var item in g.GetProperty("steps").EnumerateArray())c.Children.Add(T($"{++i:00}   {item.GetString()}"));c.Children.Add(T(g.GetProperty("version").GetString()!,12));return;
        }
        var pages=g.GetProperty("pages").EnumerateArray().ToArray();int index=Math.Clamp(state.GuideSteps.GetValueOrDefault(id),0,pages.Length-1);
        var panel=Card(parent,g.GetProperty("title").GetString()!,g.GetProperty("purpose").GetString());
        if(g.TryGetProperty("first_time",out var initial)){
            var first=new StackPanel();foreach(var item in initial.EnumerateArray())first.Children.Add(T(item.GetString()!,14));panel.Children.Add(new Expander{Header="只有第一次需要：註冊 RhinoMCP 外掛",Content=first,Margin=new Thickness(0,8,0,12)});
        }
        var tabs=new WrapPanel();panel.Children.Add(tabs);for(int i=0;i<pages.Length;i++){int n=i;Button(tabs,$"{i+1}  {pages[i].GetProperty("title").GetString()}",()=>{state.GuideSteps[id]=n;return Task.CompletedTask;},i==index);}
        var step=pages[index];panel.Children.Add(T($"第 {index+1} 步，共 {pages.Length} 步",12,true));panel.Children.Add(T(step.GetProperty("title").GetString()!,23,true));panel.Children.Add(T("操作位置："+step.GetProperty("location").GetString(),13,true));panel.Children.Add(T(step.GetProperty("text").GetString()!));
        string command=ExperienceState.Text(step,"command");if(command.Length>0)Button(panel,"複製指令："+command,()=>Copy(command));
        ShowGuideImage(panel,step.GetProperty("image").GetString()!,step.GetProperty("caption").GetString()!);
        Notice(panel,"完成後，你應該看到",step.GetProperty("success").GetString()!);
        var row=new WrapPanel();panel.Children.Add(row);
        if(index>0)Button(row,"← 上一步",()=>{state.GuideSteps[id]=index-1;return Task.CompletedTask;});
        if(index<pages.Length-1)Button(row,"下一步："+pages[index+1].GetProperty("title").GetString()+" →",()=>{state.GuideSteps[id]=index+1;return Task.CompletedTask;},true);
        var problems=new StackPanel();foreach(var item in g.GetProperty("problems").EnumerateArray())problems.Children.Add(T("• "+item.GetString(),14));panel.Children.Add(new Expander{Header="遇到問題？查看解決方式",Content=problems,Margin=new Thickness(0,12,0,8)});panel.Children.Add(T(g.GetProperty("version").GetString()!,12));
    }
    static BitmapSource GuideImage(string filename){using var stream=typeof(SetupWindow).Assembly.GetManifestResourceStream("CadToolkitSetup.images."+filename)??throw new InvalidDataException("缺少內建教學圖片。");var image=new BitmapImage();image.BeginInit();image.CacheOption=BitmapCacheOption.OnLoad;image.StreamSource=stream;image.EndInit();image.Freeze();return image;}
    void ShowGuideImage(Panel parent,string filename,string caption){
        var source=GuideImage(filename);var image=new Image{Source=source,Stretch=Stretch.Uniform,StretchDirection=StretchDirection.DownOnly,HorizontalAlignment=HorizontalAlignment.Left,MaxWidth=source.PixelWidth,Margin=new Thickness(0,12,0,8)};System.Windows.Automation.AutomationProperties.SetName(image,caption);parent.Children.Add(image);parent.Children.Add(T(caption,12));
        Button(parent,"查看原尺寸圖片 ↗",()=>{var full=new Image{Source=source,Width=source.PixelWidth,Height=source.PixelHeight,Stretch=Stretch.Fill};var viewer=new ScrollViewer{Content=full,HorizontalScrollBarVisibility=ScrollBarVisibility.Auto,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};var w=new Window{Owner=this,Title=caption,Width=Math.Min(source.PixelWidth+40,SystemParameters.WorkArea.Width),Height=Math.Min(source.PixelHeight+70,SystemParameters.WorkArea.Height),Content=viewer,WindowStartupLocation=WindowStartupLocation.CenterOwner};w.ShowDialog();return Task.CompletedTask;});
    }
    string? CadFile(string id){var target=Target(id)??Target(id,true);return target==null?null:id switch{"autocad"=>Path.Combine(target,"autocad/mcp_dispatch.lsp"),"rhino"=>Path.Combine(target,"payload/cad/rhino/rhinomcp.rhp"),_=>null};}
    void GuideActions(Panel parent,string id){
        var c=Card(parent,"回到 Toolkit，確認這一步");var row=new WrapPanel();c.Children.Add(row);
        if(id!="inventor"){var file=CadFile(id);c.Children.Add(T(file??"請先完成連線工具安裝。",12));Button(row,"開啟檔案位置",()=>{if(file==null||!File.Exists(file))throw new InvalidOperationException("請先安裝連線工具。");Open(Path.GetDirectoryName(file)!);return Task.CompletedTask;});Button(row,"複製完整路徑",()=>file==null?throw new InvalidOperationException("請先安裝連線工具。"):Copy(file));}
        Button(row,"檢查這一步",()=>Diagnose(id),true);c.Children.Add(T("只讀取應用程式、橋接與文件狀態，不修改、儲存或關閉文件。",12));
    }
    void GuidePage(){Header("離線教學","依真實畫面，一步一步操作","教學已內建於程式，取得軟體與帳號登入仍需官方網頁。");var row=new WrapPanel();body.Children.Add(row);foreach(var id in new[]{"codex","autocad","inventor","rhino"})Button(row,id=="codex"?"AI 助手":ExperienceState.Names[id],()=>{guideId=id;return Task.CompletedTask;},guideId==id);Guide(body,guideId);if(guideId!="codex")GuideActions(body,guideId);}
    void Practice(){
        var c=Card(body,"先完成一次唯讀操作","到 Codex 新增對話，貼上這段文字，核對 AI 實際讀到的狀態。");c.Children.Add(T(guides.GetProperty("readonly_prompt").GetString()!,18,true));Button(c,"複製唯讀指令",()=>Copy(guides.GetProperty("readonly_prompt").GetString()!),true);
        Notice(c,"我應該看到什麼？","AI 呼叫工具後，回報 CAD 名稱及實際狀態。有文件時核對名稱、類型、單位與未儲存變更；Inventor 在首頁可先確認應用程式已連線。只提供一般教學不算完成。");
        var ack=new CheckBox{Content=T("我已在 Codex 核對唯讀回覆",14),IsChecked=state.ReadonlyAcknowledged,IsEnabled=!busy&&AnyReady};controls.Add(ack);c.Children.Add(ack);ack.Click+=(_,_)=>{state.ReadonlyAcknowledged=ack.IsChecked==true;Save();Render();};
        Button(c,"AI 看不到工具？",()=>Navigate("help"));
        foreach(var id in Selected){var e=guides.GetProperty("exercises").GetProperty(id);var p=new StackPanel();p.Children.Add(T("1  "+e.GetProperty("prepare").GetString()));p.Children.Add(T("2  貼到 Codex：\n"+e.GetProperty("prompt").GetString()));Button(p,"複製練習指令",()=>Copy(e.GetProperty("prompt").GetString()!));p.Children.Add(T("3  預期結果："+e.GetProperty("expect").GetString()));p.Children.Add(T("4  "+e.GetProperty("save").GetString()));body.Children.Add(new Expander{Header="自選練習｜"+e.GetProperty("title").GetString(),Content=p,Padding=new Thickness(16),Margin=new Thickness(0,6,0,6),Background=Brushes.White});}
        if(!AnyReady)Notice(body,"先完成連線與啟用","目前沒有仍有效的已啟用檢查結果。請返回連線頁，至少通過並啟用一套工具。",true);
        Button(body,"返回連線檢查",()=>Go(6));Button(footer,"完成首次設定 →",()=>{if(!AnyReady||!state.ReadonlyAcknowledged)throw new InvalidOperationException("先核對唯讀結果。");state.Completed=true;return Navigate("complete");},true).IsEnabled=!busy&&AnyReady&&state.ReadonlyAcknowledged;
    }
    void Complete(){Header("首次設定完成","可以開始使用了","下次開啟直接進入首頁，不需要重新安裝。");foreach(var id in Selected)Notice(body,ExperienceState.Names[id],HasActive(id)?"已啟用。每次使用請重新檢查目前狀態。":"稍後處理：從首頁繼續設定。",!HasActive(id));Notice(body,"每次使用","開啟 CAD → 啟動連線 → 重新檢查 → 在 Codex 先做唯讀確認。");Button(footer,"進入日常首頁 →",()=>Navigate("home"),true);}
}
