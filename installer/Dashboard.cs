using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
namespace CadToolkit;

public sealed partial class SetupWindow
{
    void Home(){
        body.Children.Add(T("今天，從哪一套 CAD 開始？",28,true));
        body.Children.Add(T("每次使用：開啟 CAD 與文件 → 啟動連線 → 重新檢查 → 在 Codex 新增對話。"));
        if(!state.Completed)Button(body,"繼續未完成的設定 →",()=>Go(state.Step),true);
        foreach(var id in ExperienceState.Names.Keys)StatusCard(body,id,true);
        var updates=Card(body,"版本更新",service.Update==null?"尚未檢查新版。更新由你決定，不在背景自動下載。":"有新版本 "+service.Update.Value.GetProperty("version").GetString());
        var row=new WrapPanel();updates.Children.Add(row);
        Button(row,"檢查新版",async()=>{await service.CheckUpdate();status.Text=service.Update==null?"目前是此通道最新版本。":"已找到新版，可選擇下載更新。";});
        if(service.Update!=null)Button(row,"下載並更新",Update,true);
    }
    void StatusCard(Panel parent,string id,bool active){
        string? target=Target(id,active);bool installed=target!=null&&File.Exists(Path.Combine(target,"envs",id,"Scripts/python.exe"));
        bool fresh=Fresh(id)&&checkedTargets.GetValueOrDefault(id)==target;JsonElement check=checks.GetValueOrDefault(id);
        string code=fresh?ExperienceState.Text(check,"code"):installed?"STALE":"NOT_INSTALLED";
        string title=code switch{
            "READY"=>"✓ 可以使用（最近檢查通過）","NOT_INSTALLED"=>"○ 尚未設定","CAD_NOT_RUNNING"=>"○ 需要開啟軟體",
            "NOT_ENABLED" or "BRIDGE_NOT_CONNECTED" or "NO_DOCUMENT"=>"○ 需要完成設定","STALE"=>"○ 需要重新檢查",_=>"! 需要處理"};
        string version="";if(target!=null){var data=ExperienceState.Read(target,"ready.json");version=ExperienceState.Text(data,"version");}
        var card=Card(parent,ExperienceState.Names[id]+"    "+title);
        card.Children.Add(T("工具版本："+(version.Length>0?version:"尚未安裝"),12));
        if(state.Paths.GetValueOrDefault(id) is string app&&File.Exists(app)){
            try{card.Children.Add(T("CAD 版本："+FileVersionInfo.GetVersionInfo(app).ProductVersion,12));}catch{}
        }
        if(fresh){
            card.Children.Add(T("最近檢查："+checkedAt[id].ToString("yyyy/MM/dd HH:mm:ss")+"（切換文件或關閉 CAD 後請重查）",12));
            var doc=check.TryGetProperty("document",out var d)?d:default;
            string name=DocumentName(doc);card.Children.Add(T("檢查時的文件："+(name.Length>0?name:"尚未取得文件"),14,true));
            card.Children.Add(T(ExperienceState.Text(check,"next_action")));
            var detail=new StackPanel();foreach(var key in new[]{"installed","mcp","cad","bridge","enabled"})detail.Children.Add(T((key switch{"installed"=>"元件已安裝","mcp"=>"連線工具可啟動","cad"=>"CAD 已啟動","bridge"=>"橋接已連線",_=>"工具已啟用"})+"："+(ExperienceState.Flag(check,key)?"是":"否"),13));
            card.Children.Add(new Expander{Header="查看各項檢查",Content=detail});
        }else{
            var history=ExperienceState.Read(Root,"diagnostics.json");string time="";
            if(history.TryGetProperty("results",out var prior)&&prior.TryGetProperty(id,out var component))
                time=ExperienceState.Text(component,"checked_at",ExperienceState.Text(history,"at"));
            card.Children.Add(T(time.Length==0?"尚無連線檢查紀錄。":"歷史檢查："+time+"；不是目前連線狀態。",12));
            card.Children.Add(T(installed?"元件已存在。請重新檢查目前軟體與文件，再開始使用。":"先完成設定精靈，建立這套軟體的連線。"));
        }
        var row=new WrapPanel();card.Children.Add(row);
        if(code=="NOT_INSTALLED")Button(row,"繼續設定",()=>{state.Selected=Selected.Append(id).Distinct().ToArray();return Go(1);},true);
        else if(code=="NOT_ENABLED")Button(row,"啟用這套工具",()=>Activate(id),true);
        else if(code=="READY")Button(row,"開始使用",()=>Go(6),true);
        else Button(row,"重新檢查",()=>Diagnose(id,active&&HasActive(id)),true);
        if(code!="NOT_INSTALLED"&&code!="READY")Button(row,"查看圖解",()=>{guideId=id;page="guides";return Task.CompletedTask;});
        if(code=="CAD_NOT_RUNNING")Button(row,"開啟 "+ExperienceState.Names[id],()=>{var path=state.Paths.GetValueOrDefault(id)??ExperienceState.Detect(id);if(path==null)throw new InvalidOperationException("找不到 CAD。請到選擇軟體頁指定程式位置。");Open(path);return Task.CompletedTask;});
        if(code=="BRIDGE_NOT_CONNECTED"&&id=="rhino")Button(row,"複製 mcpstart",()=>Copy("mcpstart"));
    }
    static string DocumentName(JsonElement doc){
        if(doc.ValueKind!=JsonValueKind.Object)return "";
        foreach(var key in new[]{"name","document_name","file_name","documentName","Name","title","path","file_path"}){var v=ExperienceState.Text(doc,key);if(v.Length>0)return v;}
        foreach(var key in new[]{"document","identity","summary","payload","result","meta_data"})if(doc.TryGetProperty(key,out var child)){var name=DocumentName(child);if(name.Length>0)return name;}
        return "已取得摘要，請在 Codex 唯讀檢查時核對文件名稱";
    }
    void Settings(){
        body.Children.Add(T("設定",28,true));
        var install=Card(body,"安裝與連線","已完成的軟體不必重做。需要新增另一套工具時，可重新選擇軟體。");
        Button(install,"新增或調整軟體",()=>Go(1));
        var versions=Card(body,"版本與還原","目前管理程式："+service.Version+"。還原僅恢復上一組已啟用的連線設定。若沒有切換紀錄，就沒有可還原版本。");
        Button(versions,"還原上一版",()=>Confirm("rollback","還原上一組工具設定？若涉及 Rhino 外掛，請先自行保存並關閉 Rhino。"));
        Button(versions,"查看發布與驗收紀錄 ↗",()=>{Open("https://github.com/allen2123231/cad-toolkit/releases");return Task.CompletedTask;});
        var technical=Card(body,"技術設定與檔案","安裝位置："+Root+"\nPython 與元件依版本分開保存；本版不提供任意修改通訊路徑的功能。");
        Button(technical,"開啟安裝目錄",()=>{Directory.CreateDirectory(Root);Open(Root);return Task.CompletedTask;});
        Button(technical,"複製技術紀錄",()=>Copy(log.Text));
        var remove=Card(body,"解除安裝","移除 Toolkit 管理的 Plugin、來源與捷徑，還原仍符合備份的舊設定。保留版本檔案與備份。");
        Button(remove,"解除安裝…",()=>Confirm("uninstall","解除 Toolkit 設定並還原舊設定？目前工作文件不會被儲存或關閉。"));
        Card(body,"預覽版限制","完整乾淨 Windows 安裝、三套 CAD 的完整圖形操作流程、實際螢幕 DPI 切換及真人新手測試仍待驗收。畫面示意是操作引導，並非 CAD 的真實截圖。請以 GitHub 驗收紀錄為準。");
    }
    async Task Update(){
        if(service.Update==null)return;var update=service.Update.Value;var setup=update.GetProperty("setup");
        var filename=Path.Combine(Root,"updates",update.GetProperty("version").GetString()!,"CadToolkitSetup.exe");
        await service.Download(setup.GetProperty("url").GetString()!,filename,setup.GetProperty("sha256").GetString()!);
        var launch=new ProcessStartInfo(filename){UseShellExecute=true};launch.ArgumentList.Add("--update");launch.ArgumentList.Add("--root="+Root);launch.ArgumentList.Add("--components="+string.Join(',',Selected));
        Process.Start(launch);busy=false;Close();
    }
}
