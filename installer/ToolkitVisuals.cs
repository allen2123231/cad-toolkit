using System.IO;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;

namespace CadToolkit;

public static class ToolkitVisuals
{
    public static readonly Brush Ink = Color("#202B3D"), Muted = Color("#728096"), Blue = Color("#245CDD"), Line = Color("#E7ECF3"), Soft = Color("#F3F6FB");
    public static Brush Color(string hex) => new SolidColorBrush((System.Windows.Media.Color)ColorConverter.ConvertFromString(hex));
    public static TextBlock Text(string value, double size=13, bool strong=false, Brush? color=null) => new() { Text=value, FontSize=size, FontWeight=strong?FontWeights.SemiBold:FontWeights.Normal, Foreground=color??Ink, TextWrapping=TextWrapping.Wrap, VerticalAlignment=VerticalAlignment.Center, Margin=new Thickness(0,3,0,3) };
    public static Button Button(string label, Action action, bool primary=false) {
        var button=new Button { Content=label, Padding=new Thickness(12,7,12,7), Margin=new Thickness(0,4,7,4), FontSize=12,
            Background=primary?Blue:Brushes.White, Foreground=primary?Brushes.White:Ink, BorderBrush=primary?Blue:Line, BorderThickness=new Thickness(1), HorizontalContentAlignment=HorizontalAlignment.Center, Cursor=System.Windows.Input.Cursors.Hand };
        button.Click+=(_,_)=>action(); return button;
    }
    public static FrameworkElement Logo(double size=28, bool connected=false) {
        var drawing=new DrawingGroup();
        using(var dc=drawing.Open()) {
            dc.DrawRoundedRectangle(new LinearGradientBrush((System.Windows.Media.Color)ColorConverter.ConvertFromString("#3D8BFD"),(System.Windows.Media.Color)ColorConverter.ConvertFromString("#1F5FD0"),90),null,new Rect(0,0,16,16),3.5,3.5);
            foreach(var rect in new[]{new Rect(5.6,2.4,1.5,3.4),new Rect(8.9,2.4,1.5,3.4),new Rect(7.25,11,1.5,3.2)})dc.DrawRectangle(Brushes.White,null,rect);
            dc.DrawRoundedRectangle(Brushes.White,null,new Rect(4.2,5.4,7.6,4.2),1.3,1.3);
            dc.DrawGeometry(Brushes.White,null,Geometry.Parse("M5.4,9.2 L10.6,9.2 9,11.4 7,11.4 Z"));
            if(connected){dc.DrawEllipse(Brushes.White,null,new Point(14,14),4,4);dc.DrawEllipse(Color("#3FB950"),null,new Point(14,14),3,3);}
        }
        return new Image{Source=new DrawingImage(drawing),Width=size,Height=size,Stretch=Stretch.Uniform,Margin=new Thickness(0,0,10,0)};
    }
    public static System.Drawing.Icon TrayIcon(bool connected) {
        var logo=Logo(32,connected);logo.Margin=new Thickness(0);logo.Measure(new Size(32,32));logo.Arrange(new Rect(0,0,32,32));
        var bitmap=new RenderTargetBitmap(32,32,96,96,PixelFormats.Pbgra32);bitmap.Render(logo);
        var png=new PngBitmapEncoder();png.Frames.Add(BitmapFrame.Create(bitmap));using var image=new MemoryStream();png.Save(image);
        using var stream=new MemoryStream();using(var writer=new BinaryWriter(stream,System.Text.Encoding.UTF8,true)) {
            writer.Write((ushort)0);writer.Write((ushort)1);writer.Write((ushort)1);writer.Write((byte)32);writer.Write((byte)32);writer.Write((byte)0);writer.Write((byte)0);writer.Write((ushort)1);writer.Write((ushort)32);writer.Write((uint)image.Length);writer.Write((uint)22);writer.Write(image.ToArray());
        }
        stream.Position=0;using var icon=new System.Drawing.Icon(stream);return (System.Drawing.Icon)icon.Clone();
    }
    public static Image NativeIcon(string kind,bool file=false,double size=26) {
        string name=kind+ (file?"-file":"-app")+".png";
        using var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("CadToolkitSetup.icons."+name);
        var bitmap=new BitmapImage();if(stream!=null){bitmap.BeginInit();bitmap.CacheOption=BitmapCacheOption.OnLoad;bitmap.StreamSource=stream;bitmap.EndInit();bitmap.Freeze();}
        return new Image{Source=bitmap,Width=size,Height=size,Stretch=Stretch.Uniform,Margin=new Thickness(0,0,11,0)};
    }
    public static FrameworkElement Gear() {
        var group=new GeometryGroup();
        group.Children.Add(Geometry.Parse("M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"));
        group.Children.Add(new EllipseGeometry(new Point(12,12),3,3));
        return new System.Windows.Shapes.Path{Data=group,Stroke=Ink,StrokeThickness=1.7,Width=19,Height=19,Stretch=Stretch.Uniform};
    }
    public static Style ButtonStyle() {
        var style=new Style(typeof(Button));var template=new ControlTemplate(typeof(Button));var border=new FrameworkElementFactory(typeof(Border));border.Name="surface";
        border.SetValue(Border.CornerRadiusProperty,new CornerRadius(5));
        foreach(var pair in new[]{(Border.BackgroundProperty,Control.BackgroundProperty),(Border.BorderBrushProperty,Control.BorderBrushProperty),(Border.BorderThicknessProperty,Control.BorderThicknessProperty),(Border.PaddingProperty,Control.PaddingProperty)})border.SetValue(pair.Item1,new TemplateBindingExtension(pair.Item2));
        var content=new FrameworkElementFactory(typeof(ContentPresenter));content.SetValue(FrameworkElement.HorizontalAlignmentProperty,new TemplateBindingExtension(Control.HorizontalContentAlignmentProperty));content.SetValue(FrameworkElement.VerticalAlignmentProperty,VerticalAlignment.Center);border.AppendChild(content);template.VisualTree=border;style.Setters.Add(new Setter(Control.TemplateProperty,template));
        var hover=new Trigger{Property=UIElement.IsMouseOverProperty,Value=true};hover.Setters.Add(new Setter(UIElement.OpacityProperty,0.8));style.Triggers.Add(hover);
        var focus=new Trigger{Property=UIElement.IsKeyboardFocusedProperty,Value=true};focus.Setters.Add(new Setter(Control.BorderBrushProperty,Blue));focus.Setters.Add(new Setter(Control.BorderThicknessProperty,new Thickness(2)));style.Triggers.Add(focus);
        var disabled=new Trigger{Property=UIElement.IsEnabledProperty,Value=false};disabled.Setters.Add(new Setter(UIElement.OpacityProperty,0.45));style.Triggers.Add(disabled);return style;
    }
}
