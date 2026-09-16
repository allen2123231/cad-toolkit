using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
namespace CadToolkit;
public sealed partial class SetupWindow
{
    void Home(){
        Header("每次使用","今天想使用哪套 CAD？","先開啟 CAD，再重新檢查。上一次成功不代表目前仍然連線；Inventor 可以停留在首頁。");
        Button(body,"重新檢查全部",()=>CheckAll(true),true).IsEnabled=!busy&&Managed.Length>0;
        if(!state.Completed)Button(body,"繼續未完成設定 →",()=>Go(state.Step));
        if(Managed.Length>0&&ExperienceState.Text(Candidate,"version")!=service.Version){Notice(body,"新版管理程式已開啟","這份程式版本為 "+service.Version+"。原有元件仍保持可用；按下方按鈕準備此版本的元件。");Button(body,"準備新版連線工具",()=>Go(3),true);}
        StatusCards(body,ExperienceState.Names.Keys,true);
        var updates=Card(body,"版本與更新","目前管理程式 "+service.Version+"。由你決定更新時間，不在背景自動更新。");Button(updates,"查看版本更新",()=>Navigate("updates"));
        Button(body,"複製唯讀確認指令",()=>Copy(guides.GetProperty("readonly_prompt").GetString()!));
    }
    void StatusCards(Panel parent,IEnumerable<string> ids,bool active){
        var list=ids.ToArray();var grid=new Grid();parent.Children.Add(grid);int columns=Width>=1100?Math.Max(1,list.Length):1;
        for(int i=0;i<columns;i++)grid.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});
        for(int i=0;i<(list.Length+columns-1)/columns;i++)grid.RowDefinitions.Add(new(){Height=GridLength.Auto});
        for(int i=0;i<list.Length;i++){StatusCard(grid,list[i],active);var child=grid.Children[grid.Children.Count-1];Grid.SetColumn(child,i%columns);Grid.SetRow(child,i/columns);if(columns>1&&child is FrameworkElement element)element.Margin=new Thickness(0,8,i%columns==columns-1?0:12,8);}
    }
    void StatusCard(Panel parent,string id,bool active){
        string? target=Target(id,active);bool installed=target!=null&&File.Exists(Path.Combine(target,"envs",id,"Scripts/python.exe"));
        bool fresh=Fresh(id)&&checkedTargets.GetValueOrDefault(id)==target;JsonElement check=checks.GetValueOrDefault(id);
        string code=fresh?ExperienceState.Text(check,"code"):installed?"STALE":"NOT_INSTALLED";
        string label=code switch{"READY"=>"✓ 可以使用","NOT_INSTALLED"=>"○ 尚未設定","CAD_NOT_RUNNING"=>"○ 需要開啟軟體","NOT_ENABLED"=>"○ 連線通過，待啟用","BRIDGE_NOT_CONNECTED" or "NO_DOCUMENT"=>"○ 需要完成設定","STALE"=>"○ 需要重新檢查",_=>"! 需要處理"};
        var c=Card(parent,ExperienceState.Names[id]+"    "+label);
        string version=target!=null?ExperienceState.Text(ExperienceState.Read(target,"ready.json"),"version"):"";
        c.Children.Add(T("工具版本："+(version.Length>0?version:"尚未安裝"),12));
        if(state.Paths.GetValueOrDefault(id) is string app&&File.Exists(app)){try{c.Children.Add(T("CAD 版本："+FileVersionInfo.GetVersionInfo(app).ProductVersion,12));}catch{}}
        if(fresh){
            c.Children.Add(T("最近檢查："+checkedAt[id].ToString("yyyy/MM/dd HH:mm:ss")+" · 切換文件或關閉 CAD 後請重查",12));
            foreach(var key in new[]{"installed","mcp","cad","bridge","enabled"})c.Children.Add(T((key switch{"installed"=>"元件已安裝","mcp"=>"MCP 可啟動","cad"=>"CAD 已啟動","bridge"=>"橋接已連線",_=>"工具已啟用"})+"　"+(ExperienceState.Flag(check,key)?"✓":"尚未通過"),14));
            var doc=check.TryGetProperty("document",out var d)?d:default;string name=DocumentName(doc);
            if(id=="inventor"&&doc.ValueKind==JsonValueKind.Object&&doc.TryGetProperty("document",out var inv)&&inv.ValueKind==JsonValueKind.Null&&ExperienceState.Flag(check,"bridge"))name="首頁／無文件";
            c.Children.Add(T("目前文件："+(ExperienceState.Flag(check,"bridge")?(name.Length>0?name:"尚未開文件"):"尚未確認"),14,true));
            c.Children.Add(T(ExperienceState.Text(check,"next_action"),14));
            c.Children.Add(new Expander{Header="技術診斷資料",Content=new TextBox{Text=check.ToString(),IsReadOnly=true,TextWrapping=TextWrapping.Wrap,MaxHeight=160,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,FontSize=12}});
        }else{
            var history=ExperienceState.Read(Root,"diagnostics.json");string time="";if(history.TryGetProperty("results",out var prior)&&prior.TryGetProperty(id,out var component))time=ExperienceState.Text(component,"checked_at",ExperienceState.Text(history,"at"));
            c.Children.Add(T(time.Length==0?"尚無連線檢查紀錄。":"歷史檢查："+time+"；不是目前連線狀態。",12));c.Children.Add(T(installed?"元件已存在，重新檢查後再使用。":"先完成設定精靈，建立這套 CAD 的連線。"));
        }
        var row=new WrapPanel();c.Children.Add(row);
        if(code=="NOT_INSTALLED")Button(row,"繼續設定",()=>{state.Selected=Selected.Append(id).Distinct().ToArray();return Go(1);},true);
        else if(code=="NOT_ENABLED")Button(row,PluginReady?"啟用這套工具":"先安裝 Plugin",()=>PluginReady?Activate(id):Go(5),true);
        else if(code=="READY")Button(row,"開始使用",()=>Go(7),true);
        else Button(row,"重新檢查",()=>Diagnose(id,active&&HasActive(id)),true);
        if(code!="NOT_INSTALLED"&&code!="READY")Button(row,"查看圖解",()=>{guideId=id;return Navigate("guides");});
        if(code=="CAD_NOT_RUNNING")Button(row,"開啟 "+ExperienceState.Names[id],()=>{var path=state.Paths.GetValueOrDefault(id)??ExperienceState.Detect(id);if(path==null)throw new InvalidOperationException("找不到 CAD，請到選擇軟體頁指定位置。");Open(path);return Task.CompletedTask;});
        if(code=="BRIDGE_NOT_CONNECTED"&&id=="rhino")Button(row,"複製 mcpstart",()=>Copy("mcpstart"));
    }
    static string DocumentName(JsonElement doc){
        if(doc.ValueKind!=JsonValueKind.Object)return "";
        foreach(var key in new[]{"name","document_name","file_name","documentName","Name","title","path","file_path"}){var v=ExperienceState.Text(doc,key);if(v.Length>0)return v;}
        foreach(var key in new[]{"document","identity","summary","payload","result","meta_data"})if(doc.TryGetProperty(key,out var child)){var name=DocumentName(child);if(name.Length>0)return name;}
        return "";
    }
    void Updates(){
        Header("日常管理 / 更新","只在你準備好時更新","只採用 Toolkit 發布的固定版本組合。失敗保留原有連線設定；不強制關閉 CAD。");
        var c=Card(body,"目前管理程式："+service.Version);
        if(service.Update is JsonElement u){
            c.Children.Add(T("新版："+ExperienceState.Text(u,"version"),22,true));
            Notice(c,"更新流程","下載並驗證新安裝程式 → 建立新環境 → 完成 CAD 端設定 → 安裝 Plugin → 逐套檢查與啟用。未通過的元件不會切換。");
            Notice(c,"Rhino 外掛正在使用時","新檔案先放在獨立版本目錄。請自行保存工作並重開 Rhino，再註冊新版本外掛及重新檢查。",true);
            Button(c,"下載並準備更新",Update,true);Button(c,"查看新版發布說明 ↗",()=>{Open("https://github.com/allen2123231/cad-toolkit/releases/tag/v"+ExperienceState.Text(u,"version"));return Task.CompletedTask;});
        }else c.Children.Add(T(updateChecked?"目前是此通道最新版本。":"尚未檢查新版。"));
        Button(c,"檢查新版",async()=>await Work("正在查詢已發布版本",async()=>{await service.CheckUpdate();updateChecked=true;status.Text=service.Update==null?"目前是此通道最新版本。":"已找到新版，可先查看更新內容。";}),service.Update==null);
        if(Candidate.ValueKind==JsonValueKind.Object&&ExperienceState.Text(Candidate,"version")==service.Version){Notice(body,"已準備的元件","需要完成檢查後才會啟用。");Button(body,"繼續設定與檢查",()=>Go(4));}
        Button(footer,"回日常首頁",()=>Navigate("home"));
    }
    void Settings(){
        Header("日常管理","設定","元件、版本與備份分開管理。已有設定的軟體不必從頭重裝。");
        var install=Card(body,"安裝與連線","新增其他軟體，或查看離線圖解教學。");Button(install,"新增或調整軟體",()=>Go(1));Button(install,"查看所有教學",()=>Navigate("guides"));
        var versions=Card(body,"版本與還原","目前管理程式："+service.Version);Button(versions,"檢查新版",()=>Navigate("updates"));Button(versions,"還原上一組連線設定",()=>Navigate("restore"));
        var technical=Card(body,"檔案與技術資料","安裝位置："+Root+"\n不修改全域 Python；下載、版本環境與備份在此目錄分開保存。");Button(technical,"開啟安裝目錄",()=>{Directory.CreateDirectory(Root);Open(Root);return Task.CompletedTask;});Button(technical,"複製技術紀錄",()=>Copy(log.Text));
        var remove=Card(body,"解除安裝","只移除 Toolkit 管理的連線設定、Plugin 與捷徑。CAD 和工作文件保留。");Button(remove,"查看解除安裝",()=>Navigate("uninstall"));
        Notice(body,"發布限制","本版保留 preview 標示。乾淨 Windows、完整 CAD GUI 流程、實體螢幕 DPI 切換與真人新手測試仍待驗收。",true);Button(body,"查看驗收紀錄 ↗",()=>{Open("https://github.com/allen2123231/cad-toolkit/blob/main/docs/validation.md");return Task.CompletedTask;});
    }
    void RestorePage(){
        Header("設定 / 還原","回到上一組可用連線設定","還原元件設定後，重新檢查連線。管理程式與備份會保留。");
        if(receipt=="rollback"){Notice(body,"已完成還原","所有歷史檢查已清除。請到首頁重新檢查目前連線。");Button(footer,"回首頁重新檢查",()=>Navigate("home"),true);return;}
        var data=Installation;bool hasPrevious=data.TryGetProperty("previous",out var previous)&&previous.ValueKind==JsonValueKind.Object;
        var c=Card(body,"還原影響範圍",hasPrevious?"以下列出目前與備份的實際元件版本。CAD 文件與無關 Codex 設定保留。":"目前沒有切換紀錄，尚無可還原的設定。");
        if(hasPrevious)foreach(var id in ExperienceState.Names.Keys){string? before=Target(id,true);string? after=previous.TryGetProperty(id,out var p)?p.GetString():null;string V(string? path)=>path==null?"未啟用":ExperienceState.Text(ExperienceState.Read(path,"ready.json"),"version","版本資訊不可讀");c.Children.Add(T(ExperienceState.Names[id]+"　"+V(before)+" → "+V(after)));}
        Notice(c,"Rhino 外掛需要另外確認","外掛被 Rhino 載入時，還原會先停止並提示。請自行保存、關閉 Rhino，完成還原後再註冊對應版本。",true);
        Button(footer,"確認還原…",()=>Confirm("rollback","確認還原上面列出的連線設定？CAD 文件與無關 Codex 設定保留，還原後需要重新檢查。"),true).IsEnabled=!busy&&hasPrevious;Button(body,"取消，回設定",()=>Navigate("settings"));
    }
    void UninstallPage(){
        Header("設定 / 解除安裝","只移除 Toolkit 管理的項目","CAD 軟體、工作文件及其他工具的設定保留。");
        if(receipt=="uninstall"){Notice(body,"已解除 Toolkit 設定","Plugin、來源與捷徑已移除。下載、版本與備份仍保留於安裝目錄。");Button(footer,"返回歡迎頁",()=>Go(0),true);return;}
        var c=Card(body,"本次影響範圍");c.Children.Add(T("移除：Toolkit 的 Plugin、來源、MCP 啟用設定及捷徑。"));c.Children.Add(T("保留：AutoCAD／Inventor／Rhino 本體、工作文件、無關 Codex 設定。"));c.Children.Add(T("保留：下載檔、獨立環境與設定備份。本版不提供自動刪除版本檔案。"));
        Button(footer,"確認解除安裝…",()=>Confirm("uninstall","解除 Toolkit 管理的連線設定、Plugin 與捷徑？CAD 和工作文件不變；版本與備份保留。"));Button(body,"取消，回設定",()=>Navigate("settings"));
    }
    async Task Confirm(string action,string text){
        if(MessageBox.Show(this,text,"CAD Toolkit",MessageBoxButton.YesNo,MessageBoxImage.Question)!=MessageBoxResult.Yes)return;
        var selected=Managed.Length>0?Managed:Selected.Length>0?Selected:ExperienceState.Names.Keys.ToArray();
        await Work(action=="rollback"?"正在還原連線設定":"正在解除 Toolkit 設定",async()=>await service.Engine(action,selected));
        checks.Clear();checkedAt.Clear();checkedTargets.Clear();state.ReadonlyAcknowledged=false;receipt=action;
        if(action=="uninstall"){state.Completed=false;state.Step=0;}
        status.Text=action=="rollback"?"已還原，請重新檢查。":"已解除 Toolkit 設定，版本與備份保留。";
    }
    void Help(){
        Header("問題處理","遇到問題，先看下一步","技術錯誤保留在下方詳細資料。操作教學可離線閱讀。");
        foreach(var item in new[]{("找不到 CAD","確認已安裝且授權可用，再指定程式位置。",1),("找不到 Codex","從官方入口安裝並登入，回來重新檢查。",2),("下載中斷／磁碟空間不足","檢查網路，預留至少 3 GB；按原操作重試，已完成元件保留。",3),("外掛未載入／橋接版本不符","依圖解完成 APPLOAD 或 mcpstart；更新外掛後重新啟動 CAD 再查。",4),("新對話看不到工具","檢查 Plugin 已安裝與元件已啟用，再新增 Codex 對話。",5),("沒有文件／多個程序","Inventor 可留首頁；其他軟體選正確文件。多程序時先自行確認目標，不猜測。",6)}){var c=Card(body,item.Item1,item.Item2);Button(c,"查看處理方式 →",()=>Go(item.Item3));}
        Button(body,"查看離線截圖教學",()=>Navigate("guides"));Button(body,"版本更新問題",()=>Navigate("updates"));
    }
    async Task Update(){
        if(service.Update==null)return;var update=service.Update.Value;var setup=update.GetProperty("setup");
        var filename=Path.Combine(Root,"updates",update.GetProperty("version").GetString()!,"CadToolkitSetup.exe");
        await Work("正在下載並驗證新版安裝程式",async()=>await service.Download(setup.GetProperty("url").GetString()!,filename,setup.GetProperty("sha256").GetString()!));
        var launch=new ProcessStartInfo(filename){UseShellExecute=true};launch.ArgumentList.Add("--update");launch.ArgumentList.Add("--root="+Root);launch.ArgumentList.Add("--components="+string.Join(',',Managed.Length>0?Managed:Selected));Process.Start(launch);busy=false;Close();
    }
}
