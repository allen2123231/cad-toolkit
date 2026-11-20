using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using static CadToolkit.ToolkitVisuals;

namespace CadToolkit;

public sealed class TrayPanel : Window
{
    readonly RuntimeHost host;
    readonly Action<string> manage;
    readonly StackPanel rows=new();
    readonly TextBlock footer=Text("",10,color:Muted);
    string tab="status";
    public TrayPanel(RuntimeHost host,Action<string> manage) {
        this.host=host;this.manage=manage;Width=390;MaxHeight=640;SizeToContent=SizeToContent.Height;WindowStyle=WindowStyle.None;ResizeMode=ResizeMode.NoResize;ShowInTaskbar=false;Topmost=true;AllowsTransparency=true;Background=Brushes.Transparent;FontFamily=new FontFamily("Microsoft JhengHei UI");
        Resources.Add(typeof(Button),ButtonStyle());
        var shell=new DockPanel();Content=new Border{Child=shell,Background=Color("#F4F7FC"),BorderBrush=Line,BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(10),ClipToBounds=true};
        var header=new DockPanel{Margin=new Thickness(18,18,14,10)};DockPanel.SetDock(header,Dock.Top);shell.Children.Add(header);
        var settings=Button("",()=>{Hide();manage("settings");});settings.Content=Gear();settings.ToolTip="設定與更新";System.Windows.Automation.AutomationProperties.SetName(settings,"設定與更新");settings.Background=Brushes.Transparent;settings.BorderThickness=new Thickness(0);DockPanel.SetDock(settings,Dock.Right);header.Children.Add(settings);header.Children.Add(Logo(20));header.Children.Add(Text("MCP Toolkit",14,true));
        var tabs=new WrapPanel{Margin=new Thickness(18,0,18,3)};tabs.Children.Add(Button("MCP 狀態",()=>{tab="status";Render();}));tabs.Children.Add(Button("最近指令",()=>{tab="history";Render();}));DockPanel.SetDock(tabs,Dock.Top);shell.Children.Add(tabs);
        var bottom=new DockPanel{Margin=new Thickness(16,9,10,10)};var full=Button("完整管理 ↗",()=>{Hide();manage("overview");});full.Foreground=Blue;full.Background=Brushes.Transparent;full.BorderThickness=new Thickness(0);DockPanel.SetDock(full,Dock.Right);bottom.Children.Add(full);bottom.Children.Add(footer);DockPanel.SetDock(bottom,Dock.Bottom);shell.Children.Add(bottom);
        shell.Children.Add(new ScrollViewer{Content=rows,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,MaxHeight=470,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled});
        Deactivated+=(_,_)=>Hide();host.Changed+=Render;Closed+=(_,_)=>host.Changed-=Render;Render();
    }
    public void ShowNearTray() {
        Render();Show();UpdateLayout();var point=System.Windows.Forms.Cursor.Position;var screen=System.Windows.Forms.Screen.FromPoint(point);var dpi=VisualTreeHelper.GetDpi(this);var area=screen.WorkingArea;
        Left=Math.Max(area.Left/dpi.DpiScaleX,Math.Min(point.X/dpi.DpiScaleX-Width+20,area.Right/dpi.DpiScaleX-Width-10));Top=Math.Max(area.Top/dpi.DpiScaleY,area.Bottom/dpi.DpiScaleY-ActualHeight-10);Activate();
    }
    void Render(){
        rows.Children.Clear();footer.Text=host.Message;
        if(host.Updates.Visible)rows.Children.Add(Button("有新版本 "+host.Updates.Version+" · 查看更新",()=>{Hide();manage("settings");},true));
        if(tab=="history"){var panel=new StackPanel{Margin=new Thickness(18,0,18,0)};ManagerWindow.History(panel,host,8);rows.Children.Add(panel);return;}
        var installed=host.InstalledRows.ToArray();
        var summary=Text(installed.Count(r=>ExperienceState.Text(r,"code")=="READY")+" 套可以使用 · 已安裝 "+installed.Length+" 套",11,color:Muted);summary.Margin=new Thickness(18,4,18,0);rows.Children.Add(summary);
        if(installed.Length==0){var note=Text("尚未安裝 MCP，到「MCP 管理」選擇元件。",12,color:Muted);note.Margin=new Thickness(18,20,18,18);rows.Children.Add(note);rows.Children.Add(Button("前往 MCP 管理",()=>{Hide();manage("mcps");},true));}
        foreach(var row in installed){
            string kind=ExperienceState.Text(row,"id");var panel=new StackPanel();var title=new DockPanel();var status=ManagerWindow.Status(row);DockPanel.SetDock(status,Dock.Right);title.Children.Add(status);title.Children.Add(NativeIcon(kind,false,21));title.Children.Add(Text(ExperienceState.Text(row,"product",ExperienceState.Names.GetValueOrDefault(kind,kind)),13,true));panel.Children.Add(title);
            foreach(var window in host.Windows.Where(w=>ExperienceState.Text(w,"kind")==kind)){
                string name=ExperienceState.Text(window,"display_name");var mini=new StackPanel{Orientation=Orientation.Horizontal};mini.Children.Add(NativeIcon(kind,false,16));mini.Children.Add(Text(name,12,true));
                string label=window.TryGetProperty("binding",out var owner)&&owner.ValueKind==JsonValueKind.Object?" · "+ExperienceState.Text(owner,"label"):kind=="rhino"?" · 等待對話連線":" · 可定位";mini.Children.Add(Text(label,10,color:Muted));panel.Children.Add(mini);
            }
            panel.Children.Add(Text(ExperienceState.Text(row,"endpoint","連線方式待確認"),11,color:Muted));var file=new StackPanel{Orientation=Orientation.Horizontal};file.Children.Add(NativeIcon(kind,true,16));file.Children.Add(Text(host.Windows.Any(w=>ExperienceState.Text(w,"kind")==kind)?"點此查看各視窗文件與端口":ManagerWindow.Document(row),11));panel.Children.Add(file);
            panel.Children.Add(Text((ExperienceState.Flag(row,"installed")?"已安裝 "+ExperienceState.Text(row,"version","版本待確認"):"需要安裝")+" · "+ManagerWindow.VersionLabel(row),10,color:Muted));
            var button=Button("",()=>{Hide();manage("overview");});button.Content=panel;button.HorizontalContentAlignment=HorizontalAlignment.Stretch;button.Background=Brushes.Transparent;button.Padding=new Thickness(18,15,18,15);button.Margin=new Thickness(0);button.BorderBrush=Line;button.BorderThickness=new Thickness(0,0,0,1);rows.Children.Add(button);
        }
    }
}
