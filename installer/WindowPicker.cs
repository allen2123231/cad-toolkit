using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Automation;
using static CadToolkit.ToolkitVisuals;

namespace CadToolkit;

public sealed class WindowPicker : Window
{
    readonly RuntimeHost host;
    readonly StackPanel body=new();
    string? selectedRequest;
    public WindowPicker(RuntimeHost host){
        this.host=host;Title="MCP Toolkit · 選擇 Rhino 視窗";Width=630;Height=720;MinWidth=530;MinHeight=450;
        AutomationProperties.SetAutomationId(this,"picker-"+ToolkitApplication.Identity(host.Root));
        FontFamily=new FontFamily("Microsoft JhengHei UI");Background=Brushes.White;Foreground=Ink;WindowStartupLocation=WindowStartupLocation.CenterScreen;Icon=AppIcon();
        Resources.Add(typeof(Button),ButtonStyle());Content=new ScrollViewer{Content=body,Background=Brushes.White,Padding=new Thickness(25),VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        host.WindowsChanged+=Render;Closed+=(_,_)=>host.WindowsChanged-=Render;Render();
    }
    void Render(){
        var requests=host.WindowPanel.GetProperty("requests").EnumerateArray().ToArray();
        bool hasRhino=host.Windows.Any(w=>ExperienceState.Text(w,"kind")=="rhino");
        body.Children.Clear();body.Children.Add(Text(!hasRhino&&requests.Length>0?"正在開啟 Rhino":"選擇這段對話使用的 Rhino",23,true));body.Children.Add(Text(!hasRhino&&requests.Length>0?"視窗與外掛準備完成後，就能在這裡選擇；不需要另外手動啟動。":"一個視窗對應一個連線，檔案切換不會改變視窗名稱。",12,color:Muted));
        if(!requests.Any(r=>ExperienceState.Text(r,"id")==selectedRequest))selectedRequest=requests.FirstOrDefault().ValueKind==JsonValueKind.Object?ExperienceState.Text(requests[0],"id"):null;
        if(requests.Length>0){
            var choices=new ComboBox{Margin=new Thickness(0,16,0,10),Padding=new Thickness(8)};
            foreach(var r in requests)choices.Items.Add(new ComboBoxItem{Content=ExperienceState.Text(r,"label")+" · "+ExperienceState.Text(r,"code"),Tag=ExperienceState.Text(r,"id"),IsSelected=ExperienceState.Text(r,"id")==selectedRequest});
            choices.SelectionChanged+=(_,_)=>{if(choices.SelectedItem is ComboBoxItem c&&(string)c.Tag!=selectedRequest){selectedRequest=(string)c.Tag;Render();}};body.Children.Add(choices);
            string request=selectedRequest!;
            body.Children.Add(Button("取消這次連線",async()=>await Act("cancel-binding","--request-id",request)));
        }else body.Children.Add(Text("目前沒有等待選窗的對話。",12,color:Muted));
        foreach(var confirmation in host.WindowPanel.GetProperty("confirmations").EnumerateArray()){
            var c=confirmation;var context=c.GetProperty("context");
            var note=new StackPanel();note.Children.Add(Text(ExperienceState.Text(c,"window_name")+" · 文件已切換",15,true));
            note.Children.Add(Text("連線："+ExperienceState.Text(c,"label"),12));note.Children.Add(Text("目前文件："+ExperienceState.Text(context,"document","未命名文件"),12));
            note.Children.Add(Text("確認後請回對話重新提出操作；先前的指令不會自動執行。",11,color:Muted));
            string binding=ExperienceState.Text(c,"id"),serial=context.GetProperty("document_serial").ToString(),epoch=context.GetProperty("document_epoch").ToString();
            note.Children.Add(Button("確認使用目前文件",async()=>await Act("confirm-document","--binding-id",binding,"--serial",serial,"--epoch",epoch),true));
            body.Children.Add(new Border{Child=note,Background=Color("#FFF7E6"),Padding=new Thickness(14),CornerRadius=new CornerRadius(6),Margin=new Thickness(0,15,0,0)});
        }
        var windows=host.Windows.Where(w=>ExperienceState.Text(w,"kind")=="rhino").ToArray();
        foreach(var w in windows)WindowCards.Add(body,host,w,this,selectedRequest);
        if(windows.Length==0){
            string message=host.WindowPanel.TryGetProperty("application",out var app)?ExperienceState.Text(app,"message"):"正在準備 Rhino 視窗，完成後會自動出現在這裡。";
            body.Children.Add(Text(message,13,color:Muted));
            if(requests.Length>0)body.Children.Add(new ProgressBar{IsIndeterminate=true,Height=4,Margin=new Thickness(0,18,0,12)});
            body.Children.Add(Button("開啟／顯示 Rhino",async()=>{try{await host.OpenCad("rhino");await host.RefreshWindows();}catch(Exception e){MessageBox.Show(this,e.Message,"MCP Toolkit");}}));
        }
    }
    async Task Act(string action,params string[] args){try{await host.WindowAction(action,args);}catch(Exception e){MessageBox.Show(this,e.Message,"MCP Toolkit",MessageBoxButton.OK,MessageBoxImage.Information);}}
}

public static class WindowCards
{
    static string Get(JsonElement item,string key,string fallback="")=>ExperienceState.Text(item,key,fallback);
    public static void Add(Panel parent,RuntimeHost host,JsonElement window,Window owner,string? request=null){
        string id=Get(window,"window_id"),kind=Get(window,"kind"),name=Get(window,"display_name");bool rhino=kind=="rhino";
        bool guarded=rhino&&window.TryGetProperty("guard_protocol",out var p)&&p.GetInt32()==1;
        bool quarantined=window.TryGetProperty("quarantined",out var q)&&q.ValueKind==JsonValueKind.True;
        JsonElement binding=window.TryGetProperty("binding",out var b)?b:default;bool occupied=binding.ValueKind==JsonValueKind.Object;
        var card=new StackPanel();var title=new StackPanel{Orientation=Orientation.Horizontal};title.Children.Add(NativeIcon(kind,false,25));title.Children.Add(Text(name,16,true));card.Children.Add(title);
        card.Children.Add(Text(!rhino?"可查看與定位 · 對話綁定尚未開放":!guarded?(Get(window,"version").Length==0?"正在準備 Rhino MCP 外掛":"需要更新 Rhino MCP 外掛並重開 Rhino"):quarantined?"先前指令結果待確認 · 請儲存後重開 Rhino":occupied?"使用中 · "+Get(binding,"label")+(Get(binding,"busy","0")!="0"?" · 指令執行中":""):"可連線",12,color:occupied?Blue:Muted));
        async Task Action(string action,params string[] args){try{await host.WindowAction(action,args);}catch(Exception e){MessageBox.Show(owner,e.Message,"MCP Toolkit",MessageBoxButton.OK,MessageBoxImage.Information);}}
        var actions=new WrapPanel{Margin=new Thickness(0,8,0,0)};
        actions.Children.Add(Button("定位視窗",async()=>await Action("locate-window","--window-id",id)));
        actions.Children.Add(Button("改名",async()=>{string? value=Rename(owner,name);if(value!=null)await Action("rename-window","--window-id",id,"--name",value);}));
        if(request!=null&&guarded&&!quarantined){
            string req=request;
            var connect=Button(occupied?"轉交並連線":"連線",async()=>{
                if(occupied){if(MessageBox.Show(owner,"等候目前指令完成後，將「"+name+"」轉交給這個新連線？原對話將無法繼續操作。","轉交連線",MessageBoxButton.YesNo,MessageBoxImage.Question)!=MessageBoxResult.Yes)return;
                    await Action("bind-window","--request-id",req,"--window-id",id,"--binding-id",Get(binding,"id"));}
                else await Action("bind-window","--request-id",req,"--window-id",id);
            },true);AutomationProperties.SetAutomationId(connect,"bind-window-"+id);actions.Children.Add(connect);
        }
        if(occupied)actions.Children.Add(Button("解除連線",async()=>{if(MessageBox.Show(owner,"解除「"+Get(binding,"label")+"」與這個視窗的連線？文件會保留。","解除連線",MessageBoxButton.YesNo)!=MessageBoxResult.Yes)return;await Action("release-binding","--binding-id",Get(binding,"id"));}));
        card.Children.Add(actions);
        var details=new StackPanel();var file=new StackPanel{Orientation=Orientation.Horizontal};file.Children.Add(NativeIcon(kind,true,17));file.Children.Add(Text("目前文件："+Get(window,"document",rhino?"未命名文件":"尚未讀取"),11,color:Muted));details.Children.Add(file);
        details.Children.Add(Text("文件位置："+Get(window,"documentPath","尚未儲存／尚未讀取"),11,color:Muted));
        details.Children.Add(Text(rhino?"端口："+Get(window,"port","尚未連線"):kind=="autocad"?"檔案 IPC · 無網路端口":"COM · 無網路端口",11,color:Muted));
        details.Children.Add(Text("PID："+Get(window,"pid")+" · 視窗："+Get(window,"hwnd"),11,color:Muted));
        details.Children.Add(Text("外掛版本："+Get(window,"version","尚未確認"),11,color:Muted));
        card.Children.Add(new Expander{Header="詳細資料",Content=details,Margin=new Thickness(0,8,0,0)});
        parent.Children.Add(new Border{Child=card,BorderBrush=Line,BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(7),Padding=new Thickness(15),Margin=new Thickness(0,13,0,0)});
    }
    static string? Rename(Window owner,string current){
        var dialog=new Window{Owner=owner,Title="視窗名稱",Width=420,Height=210,ResizeMode=ResizeMode.NoResize,WindowStartupLocation=WindowStartupLocation.CenterOwner,FontFamily=owner.FontFamily,Background=Brushes.White,Foreground=Ink};
        var panel=new StackPanel{Margin=new Thickness(22)};panel.Children.Add(Text("視窗名稱與檔案名稱分開保存",14,true));
        var edit=new TextBox{Text=current,MaxLength=48,Padding=new Thickness(8),Margin=new Thickness(0,12,0,14)};panel.Children.Add(edit);
        var save=Button("儲存",()=>dialog.DialogResult=true,true);save.IsDefault=true;panel.Children.Add(save);dialog.Content=panel;dialog.Loaded+=(_,_)=>{edit.Focus();edit.SelectAll();};
        return dialog.ShowDialog()==true?edit.Text:null;
    }
}
