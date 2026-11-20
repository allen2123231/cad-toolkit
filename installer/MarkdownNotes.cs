using System.Diagnostics;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using Markdig;
using Markdig.Syntax;
using Markdig.Syntax.Inlines;
using MdBlock=Markdig.Syntax.Block;
using WpfBlock=System.Windows.Documents.Block;
using MdInline=Markdig.Syntax.Inlines.Inline;
using WpfInline=System.Windows.Documents.Inline;

namespace CadToolkit;

/// <summary>Native Markdown text; no HTML engine, scripts or remote image loading.</summary>
public static class MarkdownNotes {
    static readonly MarkdownPipeline Pipeline=new MarkdownPipelineBuilder().UsePipeTables().UseEmphasisExtras().Build();
    public static FlowDocumentScrollViewer View(string markdown)=>new(){Document=Document(markdown),IsToolBarVisible=false,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,MaxHeight=300,Margin=new Thickness(0,8,0,10)};
    public static FlowDocument Document(string markdown){
        var document=new FlowDocument{FontFamily=new FontFamily("Microsoft JhengHei UI"),FontSize=12,Foreground=ToolkitVisuals.Ink,PagePadding=new Thickness(0),ColumnWidth=double.PositiveInfinity};
        foreach(var block in Markdown.Parse(markdown,Pipeline))document.Blocks.Add(Block(block));return document;
    }
    static WpfBlock Block(MdBlock block){
        switch(block){
            case HeadingBlock heading:
                var title=Paragraph(heading.Inline);title.FontSize=heading.Level==1?18:heading.Level==2?15:13;title.FontWeight=FontWeights.SemiBold;title.Margin=new Thickness(0,12,0,6);return title;
            case ParagraphBlock paragraph:return Paragraph(paragraph.Inline);
            case Markdig.Extensions.Tables.Table table:
                var grid=new System.Windows.Documents.Table{CellSpacing=0,Margin=new Thickness(0,6,0,10)};var group=new TableRowGroup();grid.RowGroups.Add(group);
                foreach(Markdig.Extensions.Tables.TableRow row in table){var line=new System.Windows.Documents.TableRow();group.Rows.Add(line);
                    foreach(Markdig.Extensions.Tables.TableCell cell in row){var content=new System.Windows.Documents.TableCell{BorderBrush=ToolkitVisuals.Line,BorderThickness=new Thickness(1),Padding=new Thickness(6)};if(row.IsHeader){content.FontWeight=FontWeights.SemiBold;content.Background=ToolkitVisuals.Soft;}foreach(var child in cell)content.Blocks.Add(Block(child));line.Cells.Add(content);}
                }return grid;
            case ListBlock list:
                var result=new System.Windows.Documents.List{MarkerStyle=list.IsOrdered?TextMarkerStyle.Decimal:TextMarkerStyle.Disc,Padding=new Thickness(18,0,0,0),Margin=new Thickness(0,4,0,10)};
                if(list.IsOrdered&&int.TryParse(list.OrderedStart?.ToString(),out var start)&&start>0)result.StartIndex=start;
                foreach(ListItemBlock item in list){var entry=new ListItem();foreach(var child in item)entry.Blocks.Add(Block(child));result.ListItems.Add(entry);}return result;
            case CodeBlock code:return new Paragraph(new Run(code.Lines.ToString())){FontFamily=new FontFamily("Consolas"),FontSize=11,Background=ToolkitVisuals.Soft,Padding=new Thickness(8),Margin=new Thickness(0,6,0,10)};
            case QuoteBlock quote:
                var section=new Section{BorderBrush=ToolkitVisuals.Line,BorderThickness=new Thickness(3,0,0,0),Padding=new Thickness(10,0,0,0)};foreach(var child in quote)section.Blocks.Add(Block(child));return section;
            case ThematicBreakBlock:return new Paragraph{BorderBrush=ToolkitVisuals.Line,BorderThickness=new Thickness(0,0,0,1),Margin=new Thickness(0,6,0,10)};
            case ContainerBlock container:
                var children=new Section();foreach(var child in container)children.Blocks.Add(Block(child));return children;
            case LeafBlock leaf:return new Paragraph(new Run(leaf.Lines.ToString()));
            default:return new Paragraph();
        }
    }
    static Paragraph Paragraph(ContainerInline? children){var paragraph=new Paragraph{Margin=new Thickness(0,3,0,8),LineHeight=19};if(children!=null)foreach(var child in children)paragraph.Inlines.Add(Inline(child));return paragraph;}
    static Span Children(ContainerInline children){var span=new Span();foreach(var child in children)span.Inlines.Add(Inline(child));return span;}
    static WpfInline Inline(MdInline inline){
        switch(inline){
            case LiteralInline literal:return new Run(literal.Content.ToString());
            case CodeInline code:return new Run(code.Content){FontFamily=new FontFamily("Consolas"),Background=ToolkitVisuals.Soft};
            case LineBreakInline line:return line.IsHard?new LineBreak():new Run(" ");
            case EmphasisInline emphasis:
                var span=Children(emphasis);if(emphasis.DelimiterChar=='~')span.TextDecorations=TextDecorations.Strikethrough;else if(emphasis.DelimiterCount>=2)span.FontWeight=FontWeights.Bold;else span.FontStyle=FontStyles.Italic;return span;
            case LinkInline link:
                var label=Children(link);
                if(!link.IsImage&&Uri.TryCreate(link.Url,UriKind.Absolute,out var uri)&&uri.Scheme is "https" or "http"){
                    var anchor=new Hyperlink(label){NavigateUri=uri,Foreground=ToolkitVisuals.Blue};anchor.RequestNavigate+=(_,e)=>{try{Process.Start(new ProcessStartInfo(e.Uri.AbsoluteUri){UseShellExecute=true});}catch(Exception ex) when(ex is System.ComponentModel.Win32Exception or InvalidOperationException or System.IO.IOException){}e.Handled=true;};return anchor;
                }
                return label;
            case HtmlEntityInline entity:return new Run(entity.Transcoded.ToString());
            case ContainerInline container:return Children(container);
            case HtmlInline html:return new Run(html.Tag);
            default:return new Run();
        }
    }
}
