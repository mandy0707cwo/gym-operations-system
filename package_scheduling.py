"""完整候選來源，白名單排除秘密、真實資料、虛構DB及測試暫存。"""
from hashlib import sha256
import json
from pathlib import Path
import runpy
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parent
FILES=sorted(set(runpy.run_path(str(ROOT/'package_usage_funds.py'))['FILES'])|{
    'scheduling.py','schedule_ui.py','schedule_repository.py','schedule_demo_repository.py','schedule_demo.py',
    'verify_scheduling.py','audit_scheduling.py','package_scheduling.py','開啟排班測試版.cmd',
    'UPGRADE_v1.13.22.md','VERIFICATION_v1.13.22.md','RELEASE_STATUS_v1.13.22.md',
    'tests/test_scheduling.py','tests/test_scheduling_ui.py','tests/test_scheduling_database.py','tests/test_schedule_export.py',
    'tests/setup_scheduling_database.py','tests/refresh_scheduling_command.py','tests/fixtures/release_v21_contract.json',
    'tests/test_navigation_platforms.py','verification_schedule_ui.json','verification_schedule_database.json','verification_schedule_security.json',
    'supabase/migrations/20261021083833_staff_scheduling_v1_13_22.sql'})
if __name__=='__main__':
    for name in ('verification_schedule_ui.json','verification_schedule_database.json','verification_schedule_security.json'):
        assert json.loads((ROOT/name).read_text(encoding='utf-8'))['successful'],name
    out=ROOT.parents[1]/'output/排班管理_20261021_v1.13.22';out.mkdir(exist_ok=True)
    archive=out/'排班管理_v1.13.22_測試版完整來源.zip'
    contents={name:(ROOT/name).read_text(encoding='utf-8').encode() for name in FILES}
    manifest={name:sha256(data).hexdigest() for name,data in contents.items()}
    with ZipFile(archive,'x',ZIP_DEFLATED) as z:
        for name,data in contents.items():z.writestr('gym_v1.13.22/'+name,data)
        z.writestr('gym_v1.13.22/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert sha256(z.read('gym_v1.13.22/'+name)).hexdigest()==digest
        assert not any(token in name.lower() for name in z.namelist() for token in ('.postgres_data','secrets.toml','private_source','.env','.test-temp'))
    print(json.dumps({'files':len(FILES),'path':str(archive),'sha256':sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
