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
        body.Children.Add(Text(pending?"上一批指令結果待確認":"AutoCAD 中斷恢復",23,true));
        if(!pending){body.Children.Add(Text("目前沒有等待恢復的指令。",14,color:Muted));return;}
        var record=state.GetProperty("recovery");
        var warning=new StackPanel();warning.Children.Add(Text("不會自動重送，也不會補執行舊指令",16,true));
        warning.Children.Add(Text("CAD 關閉或回覆逾時後，無法確定圖面是否已部分修改。新的操作仍可收到，但會先暫停執行。",13));
        body.Children.Add(new Border{Child=warning,Background=Color("#FFF3D5"),Padding=new Thickness(16),CornerRadius=new CornerRadius(7),Margin=new Thickness(0,18,0,16)});
        string operation=ExperienceState.Text(record,"command") switch{"execute-lisp"=>"圖面操作","create-circle"=>"建立圓",var command=>command};
        body.Children.Add(Text("上一批操作："+operation,13,true));
        body.Children.Add(Text("識別碼："+ExperienceState.Text(record,"request_id"),11,color:Muted));
        body.Children.Add(Text("處理方式：先儲存可保留的工作、關閉並重新開啟 CAD，再檢查實際圖面。不要直接重做上一批。",13));
        var actions=new WrapPanel{Margin=new Thickness(0,12,0,16)};
        actions.Children.Add(Button("開啟／顯示 AutoCAD",async()=>{try{await host.OpenCad("autocad");}catch(Exception ex){MessageBox.Show(this,ex.Message,"MCP Toolkit");}}));
        actions.Children.Add(Button("重新檢查",async()=>{try{await host.RefreshWindows();}catch(Exception ex){MessageBox.Show(this,ex.Message,"MCP Toolkit");}}));body.Children.Add(actions);
        string doc="尚未讀取";
        if(state.TryGetProperty("current_document",out var current)&&current.ValueKind==JsonValueKind.Object){
            doc=ExperienceState.Text(current,"name");body.Children.Add(Text("目前圖面："+doc,15,true));
            string path=ExperienceState.Text(current,"path");body.Children.Add(Text("位置："+(path.Length>0?path:"尚未儲存"),11,color:Muted));
            string units=ExperienceState.Text(current,"units") switch{"1"=>"英吋","2"=>"英呎","4"=>"毫米","5"=>"公分","6"=>"公尺",_=>"未指定／其他"};
            body.Children.Add(Text("圖面單位："+units,12));
        }else body.Children.Add(Text("目前圖面："+doc,14,true));
        bool ready=state.TryGetProperty("can_confirm",out var can)&&can.ValueKind==JsonValueKind.True;
        string status=ready?"已偵測到重新開啟的 CAD。請確認圖面內容與單位，再繼續。":ExperienceState.Text(state,"code") switch{
            "BRIDGE_UPDATE_REQUIRED"=>"外掛需要更新。請到「MCP 管理」修復，儲存並重新開啟 CAD。",
            "SELECT_TARGET"=>"目前有多個 AutoCAD／LT 視窗。請保留要恢復的唯一視窗，再重新檢查。",
            "CAD_BUSY"=>"CAD 目前仍有指令或對話框，請先完成處理。",
            "CAD_CLOSED"=>"CAD 尚未開啟。開啟並完成載入後，這裡會自動更新。",
            _=>"尚未完成重新開啟或外掛載入。完成後這裡會自動更新。"};
        body.Children.Add(Text(status,12,color:Muted));
        var check=new CheckBox{Content="我已檢查目前圖面，確認可繼續後續操作",IsEnabled=ready,Margin=new Thickness(0,18,0,10)};body.Children.Add(check);
        string request=ExperienceState.Text(record,"request_id"),token=ExperienceState.Text(state,"target_token");
        var confirm=Button("確認圖面並解除暫停",async()=>{
            running=true;
            try{await host.WindowAction("confirm-autocad-recovery","--request-id",request,"--target-token",token);MessageBox.Show(this,"已解除暫停。請回對話重新提出後續操作；舊指令不會自動重送。","MCP Toolkit");Close();}
            catch(Exception ex){MessageBox.Show(this,ex.Message,"MCP Toolkit");}
            finally{running=false;fingerprint=null;Render();}
        },true);confirm.IsEnabled=false;check.Checked+=(_,_)=>confirm.IsEnabled=ready;check.Unchecked+=(_,_)=>confirm.IsEnabled=false;body.Children.Add(confirm);
        body.Children.Add(Text("確認只允許接收新的操作，並不代表上一批成功或失敗。",11,color:Muted));
    }
}
