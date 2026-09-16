using System.Windows;
namespace CadToolkit;
public static class Program {
    [STAThread] public static void Main(string[] args) {
        var app = new Application();
        app.Run(new SetupWindow(args));
    }
}
