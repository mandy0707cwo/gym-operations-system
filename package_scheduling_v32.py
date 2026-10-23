"""建立v32完整來源包，核對CRC／SHA256，不打包資料庫、秘密或暫存。"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
EXTRAS={'schedule_special.py','schedule_special_ui.py','tests/backup_contract_v32.py','tests/refresh_schedule_v32.py',
 'tests/test_schedule_confirm_special.py','tests/test_schedule_confirm_special_database.py','tests/test_schedule_confirm_special_ui.py',
 'supabase/migrations/20261023114054_schedule_confirm_special_v1_13_32.sql','verify_schedule_confirm_v32.py',
 'package_scheduling_v32.py','UPGRADE_v1.13.32.md','RELEASE_STATUS_v1.13.32.md','VERIFICATION_v1.13.32.md',
 'verification_schedule_confirm_v1.13.32.json'}


if __name__=='__main__':
    report=json.loads((ROOT/'verification_schedule_confirm_v1.13.32.json').read_text(encoding='utf-8'))
    assert report['successful'] and report['offline']['successful'] and report['database']['successful'] and not report['production_modified']
    assert (ROOT/'VERSION').read_text().strip()=='v1.13.32'
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    files=sorted(set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').rstrip('\0').split('\0'))|EXTRAS)
    assert all(not any(p in {'.git','.test-db','.test-temp','__pycache__','private_source','.temp'} for p in Path(n).parts) for n in files)
    assert not any(Path(n).name in {'.env','secrets.toml'} for n in files)
    out=ROOT.parents[1]/'output/排班管理_20261023_v1.13.32';out.mkdir(exist_ok=True)
    archive=out/'排班管理_v1.13.32_完整來源.zip';manifest={}
    with ZipFile(archive,'x',ZIP_DEFLATED) as z:
        for name in files:
            content=(ROOT/name).read_bytes();manifest[name]=sha256(content).hexdigest();z.writestr('gym_v1.13.32/'+name,content)
        z.writestr('gym_v1.13.32/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(sha256(z.read('gym_v1.13.32/'+name)).hexdigest()==digest for name,digest in manifest.items())
    print(json.dumps({'files':len(files),'path':str(archive),'sha256':sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
