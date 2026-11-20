using System;
using System.Windows;
using System.Windows.Controls;

namespace CadToolkit;

// Each category uses the same responsive grid; cards remain in catalog order.
public sealed class McpCardGrid : Panel {
    const double Gap=14, Minimum=300;
    int columns=1;
    double cellWidth,rowHeight;
    protected override Size MeasureOverride(Size available) {
        double width=double.IsInfinity(available.Width)?Minimum:available.Width;
        columns=Math.Max(1,Math.Min(3,(int)((width+Gap)/(Minimum+Gap))));
        cellWidth=Math.Max(0,(width-Gap*(columns-1))/columns);rowHeight=0;
        foreach(UIElement child in InternalChildren){child.Measure(new Size(cellWidth,double.PositiveInfinity));rowHeight=Math.Max(rowHeight,child.DesiredSize.Height);}
        int rows=(InternalChildren.Count+columns-1)/columns;
        return new Size(width,rows==0?0:rows*(rowHeight+Gap));
    }
    protected override Size ArrangeOverride(Size final) {
        for(int i=0;i<InternalChildren.Count;i++)InternalChildren[i].Arrange(new Rect(i%columns*(cellWidth+Gap),Gap+i/columns*(rowHeight+Gap),cellWidth,rowHeight));
        return final;
    }
}
