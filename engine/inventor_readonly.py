"""Read an existing Inventor session only; no Dispatch or document mutations."""
import json
import pythoncom
import win32com.client
pythoncom.CoInitialize()
try:
    app = win32com.client.GetActiveObject("Inventor.Application")
    doc = app.ActiveDocument
    result = {"version": app.SoftwareVersion.DisplayVersion, "hwnd": app.MainFrameHWND,
              "document": None}
    if doc is not None:
        result["document"] = {"name": doc.DisplayName, "path": doc.FullFileName,
                              "type": doc.DocumentType, "dirty": bool(doc.Dirty),
                              "length_units": doc.UnitsOfMeasure.LengthUnits}
    print(json.dumps(result, ensure_ascii=False))
finally:
    pythoncom.CoUninitialize()
