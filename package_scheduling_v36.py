"""封裝完整v36來源；沿用v35清單，私人備份與正式資料絕不加入。"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
EXTRAS={'UPGRADE_v1.13.36.md','VERIFICATION_v1.13.36.md','RELEASE_STATUS_v1.13.36.md',
 'verify_schedule_release_v36.py','verification_schedule_release_v1.13.36.json','package_scheduling_v36.py',
 'tests/test_schedule_caption_v36.py'}

if __name__=='__main__':
    report=json.loads((ROOT/'verification_schedule_release_v1.13.36.json').read_text(encoding='utf-8'))
    assert report['successful'] and report['offline']['successful'] and report['database']['successful'] and not report['production_modified']
    assert (ROOT/'VERSION').read_text().strip()=='v1.13.36'
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    previous=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    files=sorted(set(previous)|EXTRAS)
    assert all(not any(p in {'.git','.test-db','.test-temp','__pycache__','.temp'} for p in Path(n).parts) for n in files)
    assert not any(Path(n).name in {'.env','secrets.toml'} for n in files)
    out=ROOT.parents[1]/'output/排班管理_20261023_v1.13.36';out.mkdir(exist_ok=True)
    archive=out/'排班管理_v1.13.36_完整來源.zip';manifest={}
    with ZipFile(archive,'x',ZIP_DEFLATED) as z:
        for name in files:
            content=(ROOT/name).read_bytes();manifest[name]=sha256(content).hexdigest();z.writestr('gym_v1.13.36/'+name,content)
        z.writestr('gym_v1.13.36/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(sha256(z.read('gym_v1.13.36/'+n)).hexdigest()==v for n,v in manifest.items())
    print(json.dumps({'files':len(files),'path':str(archive),'sha256':sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
