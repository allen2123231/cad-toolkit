using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Microsoft.Win32;
namespace CadToolkit;

public sealed partial class SetupWindow
{
    void Wizard(){
        switch(state.Step){
            case 0:
                var welcome=Card(body,"從一句話，開始使用你的 CAD","你說明想做的事情，AI 助手透過連線工具，協助你檢查圖面或建立模型。");
                Diagram(welcome,["你 → 在 Codex 說明需求","Toolkit → 傳遞與檢查連線","CAD → 顯示圖面或模型"]);
                welcome.Children.Add(T("你可以先查文件與單位，再練習 AutoCAD 矩形、Rhino 方塊或 Inventor 擠出零件。",16));
                Card(body,"先準備這些","Windows 64 位元電腦、至少一套已啟用的 CAD、網路與約 3 GB 可用空間。安裝工具不需要自己準備 Python、Git 或 .NET 開發工具。");
                Card(body,"設定可以稍後繼續","每一步會自動記錄。現有文件不會被儲存或關閉；原有連線設定會在新工具通過檢查後逐套切換。預覽版仍有待驗收項目，可在「設定」查看。");
                Button(footer,"開始設定 →",()=>Go(1),true);break;
            case 1:
                body.Children.Add(T("勾選你要使用的軟體。沒找到時可以指定程式位置，或先不要勾選，日後再設定。"));
                foreach(var id in ExperienceState.Names.Keys){
                    string? path=state.Paths.GetValueOrDefault(id);if(!File.Exists(path))path=ExperienceState.Detect(id);if(path!=null)state.Paths[id]=path;
                    var c=Card(body,ExperienceState.Names[id]);
                    var check=new CheckBox{Content="安裝這套軟體的連線工具",IsChecked=Selected.Contains(id),Padding=new Thickness(4,8,4,8),MinHeight=40,IsEnabled=!busy};controls.Add(check);c.Children.Add(check);
                    check.Click+=(_,_)=>{state.Selected=check.IsChecked==true?Selected.Append(id).Distinct().ToArray():Selected.Where(x=>x!=id).ToArray();Save();};
                    string version="";try{if(path!=null)version=FileVersionInfo.GetVersionInfo(path).ProductVersion??"";}catch{}
                    c.Children.Add(T(path==null?"○ 尚未偵測到安裝位置；可先安裝工具，CAD 連線稍後設定。":"✓ 已找到  "+version,14,true));
                    c.Children.Add(T(path??"未指定位置",12));
                    Button(c,"指定程式位置…",()=>{
                        var dialog=new OpenFileDialog{Title="選擇 "+ExperienceState.Names[id]+" 的執行檔",Filter="程式 (*.exe)|*.exe"};
                        if(dialog.ShowDialog(this)==true){string expected=id switch{"autocad"=>"acad.exe","inventor"=>"Inventor.exe",_=>"Rhino.exe"};if(!Path.GetFileName(dialog.FileName).Equals(expected,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("請選擇 "+expected);state.Paths[id]=dialog.FileName;}return Task.CompletedTask;
                    });
                }
                Button(footer,"下一步 →",()=>Selected.Length==0?throw new InvalidOperationException("請至少勾選一套 CAD。"):Go(2),true);break;
            case 2:
                Guide(body,"codex");
                var ai=Card(body,ExperienceState.Codex()!=null?"✓ 已找到 Codex":"○ 尚未找到 Codex","程式偵測不代表你已登入。請先完成上方登入與新增對話操作。");
                var aiButtons=new WrapPanel();ai.Children.Add(aiButtons);
                Button(aiButtons,"官方下載與入門 ↗",()=>{Open("https://learn.chatgpt.com/docs/quickstart");return Task.CompletedTask;});
                Button(aiButtons,"重新檢查 Codex",()=>{status.Text=ExperienceState.Codex()!=null?"已找到 Codex。請確認登入後繼續。":"尚未找到 Codex，請完成官方安裝後重試。";return Task.CompletedTask;});
                Button(footer,"下一步 →",()=>ExperienceState.Codex()==null?throw new InvalidOperationException("先完成 Codex 安裝，再按重新檢查。"):Go(3),true);break;
            case 3:
                Card(body,"安裝這些連線工具",string.Join("、",Selected.Select(id=>ExperienceState.Names[id]))+"。安裝程式會準備獨立環境與中文 Skills，並驗證下載檔案。");
                foreach(var id in Selected)Card(body,ExperienceState.Names[id],installProgress.GetValueOrDefault(id)??(Installed(id)?"已安裝元件。重試會核對版本並接續已完成項目；新版先與目前設定並存。":"等待安裝。完成後需要在 CAD 內進行設定。"));
                Card(body,"進度與中斷","下載時可以按「停止下載／安裝」。安裝期間會在安全步驟停止，已完成的元件會保留。切換設定期間請等待完成。");
                Button(footer,"安裝並繼續 →",Install,true);
                if(Selected.All(Installed))Button(body,"元件已備妥，繼續 CAD 設定",()=>Go(4));break;
            case 4:
                body.Children.Add(T("依序完成需要使用的軟體。尚未完成的軟體可以稍後再設定。"));
                var tabs=new WrapPanel();body.Children.Add(tabs);
                if(!Selected.Contains(guideId))guideId=Selected.FirstOrDefault()??"autocad";
                foreach(var id in Selected)Button(tabs,ExperienceState.Names[id],()=>{guideId=id;return Task.CompletedTask;},id==guideId);
                GuideActions(body,guideId);Guide(body,guideId);
                if(checks.ContainsKey(guideId))StatusCard(body,guideId,false);
                Button(footer,"下一步：確認連線 →",()=>Go(5),true);break;
            case 5:
                Card(body,"一套通過，就能先開始","先檢查連線，再逐套啟用工具。安裝成功、CAD 連線與工具啟用是不同狀態。沒有通過的軟體不會切換設定。");
                foreach(var id in Selected)StatusCard(body,id,false);
                Button(footer,"下一步：唯讀練習 →",()=>Go(6),true);break;
            case 6: Practice();break;
        }
    }
    void Diagram(Panel parent,IEnumerable<string> labels){
        var wrapper=new Border{Background=new SolidColorBrush(Color.FromRgb(236,246,246)),CornerRadius=new CornerRadius(8),Padding=new Thickness(16),Margin=new Thickness(0,8,0,12)};
        var panel=new StackPanel();wrapper.Child=panel;parent.Children.Add(wrapper);
        panel.Children.Add(T("操作位置示意 · 非實際軟體截圖",12));
        var row=new WrapPanel();panel.Children.Add(row);
        foreach(var label in labels){var box=new Border{Background=Brushes.White,BorderBrush=Accent,BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(6),Padding=new Thickness(12,8,12,8),Margin=new Thickness(0,4,10,4),MaxWidth=290,Child=T(label,14,true)};row.Children.Add(box);}
    }
    void Guide(Panel parent,string id){
        var g=guides.GetProperty(id);var panel=Card(parent,g.GetProperty("title").GetString()!,g.GetProperty("purpose").GetString());
        panel.Children.Add(T("在哪裡操作："+g.GetProperty("location").GetString(),14,true));
        if(id!="codex")CadSchematic(panel,id);
        Diagram(panel,g.GetProperty("diagram").EnumerateArray().Select(x=>x.GetString()!));
        int i=0;foreach(var item in g.GetProperty("steps").EnumerateArray())panel.Children.Add(T($"{++i:00}   {item.GetString()}",15));
        var success=Card(panel,"完成後你會看到",g.GetProperty("success").GetString());
        var problems=new StackPanel();foreach(var item in g.GetProperty("problems").EnumerateArray())problems.Children.Add(T("• "+item.GetString(),14));
        panel.Children.Add(new Expander{Header="遇到問題？查看解決方式",Content=problems,Margin=new Thickness(0,8,0,8)});
        panel.Children.Add(T(g.GetProperty("version").GetString()!,12));
    }
    void CadSchematic(Panel parent,string id){
        var panel=new StackPanel();parent.Children.Add(new Border{Background=new SolidColorBrush(Color.FromRgb(239,244,248)),Padding=new Thickness(14),CornerRadius=new CornerRadius(8),Child=panel,Margin=new Thickness(0,8,0,8)});
        panel.Children.Add(T(ExperienceState.Names[id]+" 視窗位置示意（非實際截圖）",12,true));
        panel.Children.Add(T(id=="inventor"?"檔案  →  新增／開啟     ｜     目前文件分頁：練習.ipt":"功能表與工具列",13));
        var command=new Border{Background=Accent,Padding=new Thickness(10),Child=new TextBlock{Text=id=="autocad"?"下方指令列  >  APPLOAD ↵":"上方指令列  >  mcpstart ↵",Foreground=Brushes.White,TextWrapping=TextWrapping.Wrap}};
        if(id=="rhino")panel.Children.Add(command);
        var viewport=new Border{Height=92,Background=Brushes.White,Margin=new Thickness(0,6,0,6),Child=new TextBlock{Text=id=="inventor"?"零件 .ipt   ／   組合 .iam   ／   工程圖 .idw、.dwg":"空白繪圖區域",HorizontalAlignment=HorizontalAlignment.Center,VerticalAlignment=VerticalAlignment.Center,TextWrapping=TextWrapping.Wrap,Foreground=Muted}};panel.Children.Add(viewport);
        if(id=="autocad")panel.Children.Add(command);
    }
    string? CadFile(string id){var target=Target(id);if(target==null)return null;return id switch{"autocad"=>Path.Combine(target,"autocad/mcp_dispatch.lsp"),"rhino"=>Path.Combine(target,"payload/cad/rhino/rhinomcp.rhp"),_=>null};}
    void GuideActions(Panel parent,string id){
        var card=Card(parent,"現在就做這一步");
        var row=new WrapPanel();card.Children.Add(row);string command=guides.GetProperty(id).GetProperty("command").GetString()!;
        if(command.Length>0)Button(row,"複製指令："+command,()=>Copy(command));
        if(id!="inventor"){
            var file=CadFile(id);card.Children.Add(T(file??"尚未安裝元件。請回到第 4 步安裝。",12));
            Button(row,"開啟檔案位置",()=>{if(file==null||!File.Exists(file))throw new InvalidOperationException("請先完成「安裝連線工具」。");Open(Path.GetDirectoryName(file)!);return Task.CompletedTask;});
            Button(row,"複製完整路徑",()=>file==null?throw new InvalidOperationException("請先完成安裝。"):Copy(file));
        }
        Button(row,"檢查這一步",()=>Diagnose(id),true);
    }
    Task Copy(string text){Clipboard.SetText(text);status.Text="已複製。請切換到指定應用程式貼上。";return Task.CompletedTask;}
    void GuidePage(){
        body.Children.Add(T("圖解教學",28,true));body.Children.Add(T("內容已內建，可離線閱讀。取得軟體與帳號登入需要網路。"));
        var row=new WrapPanel();body.Children.Add(row);
        foreach(var id in new[]{"codex","autocad","inventor","rhino"})Button(row,id=="codex"?"AI 助手":ExperienceState.Names[id],()=>{guideId=id;return Task.CompletedTask;},guideId==id);
        if(guideId!="codex")GuideActions(body,guideId);Guide(body,guideId);
        Button(body,"第一次唯讀練習",()=>Go(6));
    }
    void Practice(){
        var first=Card(body,"先做一次不修改文件的檢查","切換到桌面 Codex，新增一個對話。把下面的指令貼進輸入框並送出。");
        first.Children.Add(T(guides.GetProperty("readonly_prompt").GetString()!,20,true));
        Button(first,"複製唯讀指令",()=>Copy(guides.GetProperty("readonly_prompt").GetString()!),true);
        first.Children.Add(T("正確結果：AI 先呼叫工具，回覆 CAD 名稱、目前文件與單位。請和 CAD 的目前文件分頁核對。若 AI 只提供一般教學、沒有實際讀到文件，表示還未成功，請回第 6 步檢查並啟用。"));
        first.Children.Add(T("接下來的練習一定要另建空白文件。保留現有工作文件；不要直接在工作圖上練習。",14,true));
        foreach(var id in Selected){
            var e=guides.GetProperty("exercises").GetProperty(id);var content=new StackPanel();content.Children.Add(T("1  "+e.GetProperty("prepare").GetString()));content.Children.Add(T("2  貼到 Codex：\n"+e.GetProperty("prompt").GetString()));
            Button(content,"複製練習指令",()=>Copy(e.GetProperty("prompt").GetString()!));content.Children.Add(T("3  預期結果："+e.GetProperty("expect").GetString()));content.Children.Add(T("4  "+e.GetProperty("save").GetString()));
            body.Children.Add(new Expander{Header="自選練習｜"+e.GetProperty("title").GetString(),Content=content,Padding=new Thickness(16),Margin=new Thickness(0,6,0,6),Background=Brushes.White});
        }
        var finish=Button(footer,"我已核對唯讀結果，進入首頁",()=>{state.Completed=true;page="home";status.Text="下次開啟會進入首頁。使用前請重新檢查連線。";return Task.CompletedTask;},true);
        finish.IsEnabled=!busy&&checks.Any(p=>Fresh(p.Key)&&ExperienceState.Text(p.Value,"code")=="READY");
        if(!finish.IsEnabled)body.Children.Add(T("可先閱讀練習。請先返回連線檢查，讓至少一套工具通過且已啟用，再核對唯讀結果完成設定。",14,true));
        Button(body,"尚未成功，返回連線檢查",()=>Go(5));
    }
}
