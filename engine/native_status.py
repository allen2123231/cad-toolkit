"""Read a single existing Autodesk session; never Dispatch or change a document."""
import argparse
import json
import pythoncom
import win32com.client

parser = argparse.ArgumentParser()
parser.add_argument("component", choices=["autocad", "inventor"])
args = parser.parse_args()
pythoncom.CoInitialize()
try:
    if args.component == "autocad":
        app = win32com.client.GetActiveObject("AutoCAD.Application")
        doc = app.ActiveDocument if app.Documents.Count else None
        result = {"version": app.Version, "hwnd": int(app.HWND), "document": None}
        if doc:
            result["document"] = {"name": doc.Name, "path": doc.FullName, "dirty": bool(doc.GetVariable("DBMOD")),
                                  "units": doc.GetVariable("INSUNITS"), "busy": int(doc.GetVariable("CMDACTIVE")) != 0}
    else:
        app = win32com.client.GetActiveObject("Inventor.Application")
        doc = app.ActiveDocument
        result = {"version": app.SoftwareVersion.DisplayVersion, "hwnd": int(app.MainFrameHWND),
                  "ready": bool(app.Ready), "document": None}
        if doc:
            result["document"] = {"name": doc.DisplayName, "path": doc.FullFileName, "dirty": bool(doc.Dirty),
                                  "units": str(doc.UnitsOfMeasure.LengthUnits)}
    print(json.dumps(result, ensure_ascii=True))
finally:
    pythoncom.CoUninitialize()
