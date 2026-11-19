"""Executable identities shared by launch, monitoring, update and MCP routing."""
from pathlib import Path

EXECUTABLES={'rhino':('Rhino.exe',),'autocad':('acad.exe','acadlt.exe'),'inventor':('Inventor.exe',)}

def kind_for_executable(path):
    name=Path(path).name.casefold()
    return next((kind for kind,names in EXECUTABLES.items() if name in {n.casefold() for n in names}),None)

def product_for_executable(path):
    return 'AutoCAD LT' if Path(path).name.casefold()=='acadlt.exe' else 'AutoCAD' if Path(path).name.casefold()=='acad.exe' else None

def default_candidates(program,kind):
    program=Path(program)
    if kind=='rhino':return [program/'Rhino 8/System/Rhino.exe']
    if kind=='inventor':return [program/f'Autodesk/Inventor {year}/Bin/Inventor.exe' for year in range(2029,2021,-1)]
    return [program/f'Autodesk/{product} {year}'/exe for year in range(2029,2021,-1)
            for product,exe in [('AutoCAD','acad.exe'),('AutoCAD LT','acadlt.exe')] if product!='AutoCAD LT' or year>=2024]
