"""封裝完整v33來源；沿用已驗證v32清單，不夾帶資料庫、憑證或快取。"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
EXTRAS={'UPGRADE_v1.13.33.md','RELEASE_STATUS_v1.13.33.md','VERIFICATION_v1.13.33.md',
 'verify_schedule_manager_v33.py','verification_schedule_manager_v1.13.33.json','package_scheduling_v33.py',
 'supabase/migrations/20261023134850_schedule_manager_notes_v1_13_33.sql'}

if __name__=='__main__':
    report=json.loads((ROOT/'verification_schedule_manager_v1.13.33.json').read_text(encoding='utf-8'))
    assert report['successful'] and report['database']['successful'] and not report['production_modified']
    assert (ROOT/'VERSION').read_text().strip()=='v1.13.33'
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    previous=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    files=sorted(set(previous)|EXTRAS)
    assert all(not any(p in {'.git','.test-db','.test-temp','__pycache__','.temp'} for p in Path(n).parts) for n in files)
    assert not any(Path(n).name in {'.env','secrets.toml'} for n in files)
    out=ROOT.parents[1]/'output/排班管理_20261023_v1.13.33';out.mkdir(exist_ok=True)
    archive=out/'排班管理_v1.13.33_完整來源.zip';manifest={}
    with ZipFile(archive,'x',ZIP_DEFLATED) as z:
        for name in files:
            content=(ROOT/name).read_bytes();manifest[name]=sha256(content).hexdigest();z.writestr('gym_v1.13.33/'+name,content)
        z.writestr('gym_v1.13.33/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(sha256(z.read('gym_v1.13.33/'+n)).hexdigest()==v for n,v in manifest.items())
    print(json.dumps({'files':len(files),'path':str(archive),'sha256':sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
