using System.Text.Json;
using RhinoMCPPlugin;
namespace RhinoMCPPlugin { static class RhinoMCPServerController { public const string PortEnvironmentVariable="RHINO_MCP_PORT"; } }
class Program {
 static int checks;
 static void Check(bool condition,string label){checks++;if(!condition)throw new Exception(label);}
 static void Main(){
  string root=Path.Combine(Path.GetTempPath(),"RhinoTrayChecks-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
  string marker=Path.Combine(AppContext.BaseDirectory,"toolkit-integration.json");
  try{
   Check(!ToolkitIntegration.IsManagedAt(root),"Standalone without marker preserves native tray policy");
   File.WriteAllText(Path.Combine(root,"toolkit-integration.json"),"{broken");
   Check(!ToolkitIntegration.IsManagedAt(root),"Malformed marker never becomes a guessed Toolkit installation");
   File.WriteAllText(Path.Combine(root,"toolkit-integration.json"),"""{"schema":1,"mode":"mcp-toolkit"}""");
   Check(ToolkitIntegration.IsManagedAt(root),"Persistent managed marker works without running manager");
   File.WriteAllText(marker,"""{"schema":1,"mode":"mcp-toolkit"}""");
   Check(StatusTray.Launch(false),"Managed server startup succeeds without spawning or requiring a tray EXE");
   string locator=Path.Combine(root,"locator.json");File.WriteAllText(locator,JsonSerializer.Serialize(new{schema=1,root}));
   Check(ToolkitIntegration.ManagerStartInfo(locator)==null,"Missing manager produces no arbitrary fallback launch");
   File.WriteAllText(Path.Combine(root,"McpToolkit.exe"),"fixture");File.WriteAllText(Path.Combine(root,"state.json"),"{}");
   var start=ToolkitIntegration.ManagerStartInfo(locator);
   Check(start!=null&&start.FileName==Path.Combine(root,"McpToolkit.exe"),"Only exact manager executable is used");
   Check(start.ArgumentList.Contains("--page=mcps")&&start.ArgumentList.Contains("--root="+root)&&!start.UseShellExecute,"Custom roots and management page use separate arguments");
   File.WriteAllText(locator,"""{"schema":1,"root":"../outside"}""");
   Check(ToolkitIntegration.ManagerStartInfo(locator)==null,"Relative root is rejected");
   Console.WriteLine(JsonSerializer.Serialize(new{passed=true,checks,scope="Real shared plugin integration and StatusTray source; no Rhino or manager processes started"}));
  }finally{if(File.Exists(marker))File.Delete(marker);Directory.Delete(root,true);}
 }
}
