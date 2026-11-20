using System;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using static CadToolkit.ToolkitVisuals;

namespace CadToolkit;

public sealed class ComponentUninstallWindow : Window {
    readonly RuntimeHost host;
    readonly string kind;
    readonly TextBlock status=Text("",12,color:Muted);
    readonly Button remove;
    bool busy,finished;
    public ComponentUninstallWindow(RuntimeHost host,string kind,string name) {
        this.host=host;this.kind=kind;
        Title="解除安裝 "+name+" MCP";Width=530;Height=430;MinWidth=460;MinHeight=390;
        WindowStartupLocation=WindowStartupLocation.CenterOwner;Background=Brushes.White;FontFamily=new FontFamily("Microsoft JhengHei UI");Icon=AppIcon();Resources.Add(typeof(Button),ButtonStyle());
        var body=new StackPanel{Margin=new Thickness(26)};Content=new ScrollViewer{Background=Brushes.White,Content=body,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        body.Children.Add(Text("解除安裝 "+name+" MCP",23,true));
        body.Children.Add(Text("將移除這套 MCP 的 Toolkit 工具入口與自動連線外掛。其他 MCP、Toolkit、CAD 軟體及工作文件會保留。",13));
        body.Children.Add(Text("設定會先備份。共用的版本快取會保留，完整解除安裝 Toolkit 時再清除。",12,color:Muted));
        body.Children.Add(Text("請先儲存並關閉 "+name+"。完成後請重新啟動 Codex，讓既有對話卸載舊工具。",12));
        body.Children.Add(status);
        var actions=new WrapPanel{Margin=new Thickness(0,16,0,0)};actions.Children.Add(Button("取消",Close));remove=Button("確認解除安裝",async()=>await Remove(),true);actions.Children.Add(remove);body.Children.Add(actions);
        Closing+=(_,e)=>{if(busy)e.Cancel=true;};
    }
    async Task Remove() {
        if(busy)return;if(finished){Close();return;}
        if(UpdateController.CloseApplications(new[]{kind}) is string reason){status.Text=reason.Replace("再按更新","再按解除安裝");return;}
        busy=true;remove.IsEnabled=false;status.Text="正在備份並解除安裝，請稍候…";
        try {
            var service=new ToolkitService(host.Root);service.Report=value=>status.Text=value;
            var events=await service.Engine("remove_component",new[]{kind});
            finished=!events.Any(e=>ExperienceState.Text(e,"outcome")=="needs_action");
            if(!finished)status.Text+=" 部分外掛已被修改而保留，請查看備份紀錄或重試。";
            remove.Content=finished?"完成":"重試解除安裝";
        }catch(Exception ex){status.Text="尚未完成："+ex.Message;remove.Content="重試解除安裝";}
        finally{busy=false;remove.IsEnabled=true;await host.Refresh();}
    }
}
