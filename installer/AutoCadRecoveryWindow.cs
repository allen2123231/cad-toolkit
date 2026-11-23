using System;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using static CadToolkit.ToolkitVisuals;

namespace CadToolkit;

public sealed class AutoCadRecoveryWindow : Window
{
    readonly RuntimeHost host;
    readonly StackPanel body=new(){Margin=new Thickness(26)};
    string? fingerprint;
    bool running;
    string? recoveryError;
    public AutoCadRecoveryWindow(RuntimeHost host){
        this.host=host;Title="MCP Toolkit · AutoCAD 中斷恢復";Width=640;Height=600;MinWidth=520;MinHeight=450;
        FontFamily=new FontFamily("Microsoft JhengHei UI");Background=Brushes.White;Foreground=Ink;Icon=AppIcon();WindowStartupLocation=WindowStartupLocation.CenterScreen;
        Resources.Add(typeof(Button),ButtonStyle());Content=new ScrollViewer{Content=body,Background=Brushes.White,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        host.WindowsChanged+=Render;Closed+=(_,_)=>host.WindowsChanged-=Render;Render();
    }
    void Render(){
        if(running)return;
        var state=host.WindowPanel.TryGetProperty("autocad_recovery",out var s)?s:default;
        bool pending=state.ValueKind==JsonValueKind.Object&&state.TryGetProperty("recovery",out var r)&&r.ValueKind==JsonValueKind.Object;
        string next=state.ValueKind==JsonValueKind.Object?state.GetRawText():"";
        if(fingerprint==next)return;fingerprint=next;body.Children.Clear();
        body.Children.Add(Text(pending?"修改已暫停，上一批結果待確認":"AutoCAD 中斷恢復",23,true));
        if(!pending){body.Children.Add(Text("目前沒有等待恢復的指令。",14,color:Muted));return;}
        var record=state.GetProperty("recovery");
        bool switched=record.TryGetProperty("document",out var original)&&original.ValueKind==JsonValueKind.Object
            &&state.TryGetProperty("current_document",out var active)&&active.ValueKind==JsonValueKind.Object
            &&ExperienceState.Text(original,"id")!=ExperienceState.Text(active,"id");
        string request=ExperienceState.Text(record,"request_id"),token=ExperienceState.Text(state,"target_token");
        var warning=new StackPanel();warning.Children.Add(Text("不會自動重送，也不會補執行舊指令",16,true));
        warning.Children.Add(Text("上一批修改的結果不明。新的修改要求會被阻擋，不會排隊或自動重送。唯讀查詢不代表已解除修改暫停。",13));
        body.Children.Add(new Border{Child=warning,Background=Color("#FFF3D5"),Padding=new Thickness(16),CornerRadius=new CornerRadius(7),Margin=new Thickness(0,18,0,16)});
        bool readable=state.TryGetProperty("read_available",out var read)&&read.ValueKind==JsonValueKind.True;
        body.Children.Add(Text(readable?"唯讀查詢：可使用 MCP 查圖　｜　修改：已暫停":"唯讀查詢：尚未就緒　｜　修改：已暫停",14,true));
        body.Children.Add(Text("此保護適用於 Toolkit 管理的操作；不會封鎖其他程式直接存取 AutoCAD。",11,color:Muted));
        string operation=ExperienceState.Text(record,"command") switch{"execute-lisp"=>"圖面操作","create-circle"=>"建立圓",var command=>command};
        body.Children.Add(Text("上一批操作："+operation,13,true));
        body.Children.Add(Text("識別碼："+ExperienceState.Text(record,"request_id"),11,color:Muted));
        string reason=ExperienceState.Text(record,"reason"),error=ExperienceState.Text(record,"error");
        string cause=reason switch{"completion_timeout"=>"等待 AutoCAD 回覆逾時","cad_process_closed"=>"AutoCAD 曾關閉","native_waiting_for_input"=>"上一批指令停在等待輸入",_=>"通訊中斷，上一批結果尚未確認"};
        body.Children.Add(Text("中斷原因："+cause,13));
        body.Children.Add(new Expander{Header="技術詳細資料",Content=Text(reason+(error.Length>0?"\n"+error:""),11,color:Muted),Margin=new Thickness(0,5,0,8)});
        if(record.TryGetProperty("document",out var interrupted)&&interrupted.ValueKind==JsonValueKind.Object){
            body.Children.Add(Text("中斷時圖面："+ExperienceState.Text(interrupted,"name"),14,true));
            body.Children.Add(Text("位置："+ExperienceState.Text(interrupted,"path"),11,color:Muted));
        }
        string doc="尚未讀取";
        if(state.TryGetProperty("current_document",out var current)&&current.ValueKind==JsonValueKind.Object){
            doc=ExperienceState.Text(current,"name");body.Children.Add(Text("目前圖面："+doc,15,true));
            string path=ExperienceState.Text(current,"path");body.Children.Add(Text("位置："+(path.Length>0?path:"尚未儲存"),11,color:Muted));
            string units=ExperienceState.Text(current,"units") switch{"1"=>"英吋","2"=>"英呎","4"=>"毫米","5"=>"公分","6"=>"公尺",_=>"未指定／其他"};
            body.Children.Add(Text("圖面單位："+units,12));
        }else body.Children.Add(Text("目前圖面："+doc,14,true));
        if(switched)body.Children.Add(new Border{Child=Text("目前已切換至另一份圖面。檢查會確認所有開啟圖面均無進行中的指令，再隔離舊指令；完成後保留目前圖面，不會重送。請同時檢查原圖與目前圖面的內容。",13),Background=Color("#FFF3D5"),Padding=new Thickness(12),Margin=new Thickness(0,8,0,8)});
        if(recoveryError!=null)body.Children.Add(new Border{Child=Text(recoveryError,13,true),Background=Color("#FFF3D5"),Padding=new Thickness(12),Margin=new Thickness(0,8,0,8)});
        body.Children.Add(Text("先按「檢查並恢復連線」。檢查通過後，確認目前圖面並勾選下方選項；不必先關閉 AutoCAD。舊指令不會重送。",13));
        var actions=new WrapPanel{Margin=new Thickness(0,12,0,16)};
        Button? repair=null;repair=Button("檢查並恢復連線",async()=>{
            running=true;
            recoveryError=null;
            repair!.IsEnabled=false;repair.Content="正在檢查與隔離舊指令…";
            try{await host.WindowAction("prepare-autocad-recovery","--request-id",request,"--target-token",token);}
            catch(Exception ex){recoveryError=ex.Message+"\n修改仍暫停，舊指令不會重送。";}
            finally{running=false;fingerprint=null;Render();}
        },true);actions.Children.Add(repair);
        actions.Children.Add(Button("開啟／顯示 AutoCAD",async()=>{try{await host.OpenCad("autocad");}catch(Exception ex){MessageBox.Show(this,ex.Message,"MCP Toolkit");}}));
        actions.Children.Add(Button("重新檢查",async()=>{try{await host.RefreshWindows();}catch(Exception ex){MessageBox.Show(this,ex.Message,"MCP Toolkit");}}));body.Children.Add(actions);
        bool ready=state.TryGetProperty("can_confirm",out var can)&&can.ValueKind==JsonValueKind.True;
        string status=ready?(ExperienceState.Text(state,"recovery_mode")=="in_place"?"原視窗已恢復連線，舊指令已隔離。請檢查圖面並勾選確認，才會解除修改暫停。":"已偵測到重新開啟的 CAD。請確認圖面內容與單位，再繼續。"):ExperienceState.Text(state,"code") switch{
            "BRIDGE_UPDATE_REQUIRED"=>"外掛需要更新。請到「MCP 管理」修復，儲存並重新開啟 CAD。",
            "SELECT_TARGET"=>"目前有多個 AutoCAD／LT 視窗。請保留要恢復的唯一視窗，再重新檢查。",
            "CAD_BUSY"=>"CAD 目前仍有指令或對話框，請先完成處理。",
            "CAD_CLOSED"=>"CAD 尚未開啟。開啟並完成載入後，這裡會自動更新。",
            _=>"尚未完成恢復檢查。請按「檢查並恢復連線」；單純重新檢查狀態不會解除暫停。"};
        body.Children.Add(Text(status,12,color:Muted));
        var check=new CheckBox{Content=switched?"我已檢查中斷時及目前圖面，確認可繼續後續操作":"我已檢查目前圖面，確認可繼續後續操作",IsEnabled=ready,Margin=new Thickness(0,18,0,10)};body.Children.Add(check);
        var confirm=Button("確認圖面並解除暫停",async()=>{
            running=true;
            try{await host.WindowAction("confirm-autocad-recovery","--request-id",request,"--target-token",token);MessageBox.Show(this,"已解除暫停。請回對話重新提出後續操作；舊指令不會自動重送。","MCP Toolkit");Close();}
            catch(Exception ex){MessageBox.Show(this,ex.Message,"MCP Toolkit");}
            finally{running=false;fingerprint=null;Render();}
        },true);confirm.IsEnabled=false;check.Checked+=(_,_)=>confirm.IsEnabled=ready;check.Unchecked+=(_,_)=>confirm.IsEnabled=false;body.Children.Add(confirm);
        body.Children.Add(Text("確認只允許接收新的操作，並不代表上一批成功或失敗。",11,color:Muted));
    }
}
