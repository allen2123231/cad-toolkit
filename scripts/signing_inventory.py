"""Inventory executable content, including wheels/Yak, without executing it."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

EXECUTABLES={'.exe','.dll','.pyd','.rhp','.ps1'}
ARCHIVES={'.zip','.whl','.yak'}

def inventory(archive, installer, output):
    output=Path(output).resolve();staging=output.parent/(output.stem+'-files');staging.mkdir(parents=True,exist_ok=True)
    records=[]
    def add(name,data):
        digest=hashlib.sha256(data).hexdigest();suffix=Path(name).suffix.lower()
        file=staging/(digest+suffix)
        if not file.exists():file.write_bytes(data)
        records.append({'source':name,'sha256':digest,'path':str(file),'extension':suffix})
    def scan(data,prefix,depth=0):
        if depth>3:raise ValueError('Nested archive depth exceeds supported release format')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                if entry.is_dir():continue
                name=entry.filename.replace('\\','/')
                if name.startswith('/') or '..' in Path(name).parts:raise ValueError('Unsafe archive entry')
                extension=Path(name).suffix.lower()
                if extension in EXECUTABLES:add(prefix+name,archive.read(entry))
                elif extension in ARCHIVES:scan(archive.read(entry),prefix+name+'!/',depth+1)
    add(Path(installer).name,Path(installer).read_bytes())
    scan(Path(archive).read_bytes(),'payload!/')
    result={'schema':1,'installer_sha256':hashlib.sha256(Path(installer).read_bytes()).hexdigest(),'payload_sha256':hashlib.sha256(Path(archive).read_bytes()).hexdigest(),'files':records,'note':'Inventory includes archive templates; installed console launchers and extracted .NET files also require an installation-time audit.'}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--payload',type=Path,required=True);parser.add_argument('--installer',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=inventory(args.payload,args.installer,args.output)
    print(json.dumps({'executable_entries':len(result['files']),'distinct_bytes':len({f['sha256'] for f in result['files']})}))
