using System.Text.Json;

namespace CadToolkit;

public sealed record McpCatalogEntry(string Id,string Name,JsonElement Row,string ExpectedVersion){
    public bool Installed=>ExperienceState.Flag(Row,"installed");
    public bool CanManage=>ExperienceState.Names.ContainsKey(Id);
}

public static class McpCatalog {
    public static McpCatalogEntry[] Entries(JsonElement manifest,IEnumerable<JsonElement> rows){
        var installed=rows.Where(r=>ExperienceState.Text(r,"id").Length>0).GroupBy(r=>ExperienceState.Text(r,"id")).ToDictionary(g=>g.Key,g=>g.First());
        var components=manifest.TryGetProperty("components",out var catalog)?catalog.EnumerateObject().ToDictionary(p=>p.Name,p=>p.Value):new Dictionary<string,JsonElement>();
        return components.Keys.Concat(installed.Keys).Distinct().Select(id=>{
            installed.TryGetValue(id,out var row);components.TryGetValue(id,out var spec);
            string name=ExperienceState.Text(row,"product",ExperienceState.Text(spec,"display_name",ExperienceState.Text(row,"name",ExperienceState.Names.GetValueOrDefault(id,id))));
            return new McpCatalogEntry(id,name,row,ExperienceState.Text(spec,"package_version"));
        }).OrderBy(e=>e.Name,StringComparer.CurrentCultureIgnoreCase).ToArray();
    }
}
