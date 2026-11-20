"""Independent prepared environments; candidate is only the latest install job."""
from pathlib import Path
from common import COMPONENTS,read_json


def load(path):
    try:return read_json(path)
    except (OSError,ValueError):return {}


def component_ready(target,component):
    target=Path(target)
    return (target/'ready.json').is_file() or ((target/(component+'.complete.json')).is_file() and (target/'envs'/component/'Scripts/python.exe').is_file())


def prepared_targets(root,state):
    result={c:p for c,p in state.get('active',{}).items() if c in COMPONENTS and isinstance(p,str)}
    candidate=state.get('candidate') or {}
    if candidate.get('path'):
        result.update({c:candidate['path'] for c in candidate.get('selected',[]) if c in COMPONENTS})
    result.update({c:p for c,p in state.get('prepared',{}).items() if c in COMPONENTS and isinstance(p,str)})
    # Recover environments hidden by older single-component repairs. Recovery
    # describes installation only; it never enables or routes a CAD operation.
    versions=Path(root)/'versions';found={}
    if versions.is_dir() and not versions.is_symlink() and not versions.is_junction():
        for target in versions.iterdir():
            if not target.is_dir() or target.is_symlink() or target.is_junction():continue
            ready=load(target/'ready.json')
            for component in COMPONENTS:
                marker=target/(component+'.complete.json')
                if component in result or not (target/'envs'/component/'Scripts/python.exe').is_file():continue
                if component not in ready.get('selected',[]) and not marker.is_file():continue
                stamp=(marker if marker.exists() else target/'ready.json').stat().st_mtime_ns
                if component not in found or stamp>found[component][0]:found[component]=(stamp,str(target))
    result.update({c:p for c,(_,p) in found.items()})
    return {c:p for c,p in result.items() if c not in state.get('removed_components',[])}
