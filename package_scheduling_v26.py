"""v26完整來源白名單；驗證成功才打包，不帶秘密與測試資料。"""
from hashlib import sha256
import json
from pathlib import Path
import runpy
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parent
FILES=sorted(set(runpy.run_path(str(ROOT/'package_scheduling_v25.py'))['FILES'])|{
    'schedule_leave.py','schedule_leave_repository.py','schedule_leave_ui.py',
    'tests/test_schedule_leave.py','tests/test_schedule_leave_database.py','tests/setup_leave_database.py',
    'UPGRADE_v1.13.26.md','VERIFICATION_v1.13.26.md','RELEASE_STATUS_v1.13.26.md','package_scheduling_v26.py',
    'supabase/migrations/20261021152424_schedule_leave_v1_13_26.sql'})
if __name__=='__main__':
    for name in ('verification_schedule_ui.json','verification_schedule_database.json','verification_schedule_security.json'):
        result=json.loads((ROOT/name).read_text(encoding='utf-8'))
        assert result['successful'] and result['version']=='v1.13.26',name
    out=ROOT.parents[1]/'output/排班管理_20261021_v1.13.26';out.mkdir(exist_ok=True)
    archive=out/'排班管理_v1.13.26_月額度總覽及請假測試版完整來源.zip'
    contents={name:(ROOT/name).read_text(encoding='utf-8').encode() for name in FILES}
    manifest={name:sha256(value).hexdigest() for name,value in contents.items()}
    with ZipFile(archive,'x',ZIP_DEFLATED) as z:
        for name,value in contents.items():z.writestr('gym_v1.13.26/'+name,value)
        z.writestr('gym_v1.13.26/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert sha256(z.read('gym_v1.13.26/'+name)).hexdigest()==digest
        assert not any(token in name.lower() for name in z.namelist() for token in ('.postgres_data','secrets.toml','private_source','.env','.test-temp'))
    print(json.dumps({'files':len(FILES),'path':str(archive),'sha256':sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
