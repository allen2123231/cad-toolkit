"""Read the existing AutoCAD document and command state through COM."""
import json
import pythoncom
import win32com.client
pythoncom.CoInitialize()
try:
    app = win32com.client.GetActiveObject("AutoCAD.Application")
    if app.Documents.Count == 0:
        print(json.dumps({"document_missing": True}))
    else:
        doc = app.ActiveDocument
        print(json.dumps({"path": doc.FullName, "name": doc.Name, "dbmod": doc.GetVariable("DBMOD"),
                          "units": doc.GetVariable("INSUNITS"), "cmdactive": doc.GetVariable("CMDACTIVE")}, ensure_ascii=False))
finally:
    pythoncom.CoUninitialize()
