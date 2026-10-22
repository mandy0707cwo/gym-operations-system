"""完整候選白名單來源；不含資料庫、憑證、客戶或測試工作階段。"""
from hashlib import sha256
import json
from pathlib import Path
import runpy
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parent
FILES=sorted(set(runpy.run_path(str(ROOT/'package_scheduling_v24.py'))['FILES'])|{
    'schedule_allowance.py','schedule_allowance_ui.py','schedule_allowance_repository.py',
    'tests/test_schedule_allowance.py','tests/test_schedule_allowance_database.py',
    'UPGRADE_v1.13.25.md','VERIFICATION_v1.13.25.md','RELEASE_STATUS_v1.13.25.md','package_scheduling_v25.py',
    'supabase/migrations/20261021100055_schedule_allowance_v1_13_25.sql'})
if __name__=='__main__':
    for name in ('verification_schedule_ui.json','verification_schedule_database.json','verification_schedule_security.json'):
        result=json.loads((ROOT/name).read_text(encoding='utf-8'))
        assert result['successful'] and result['version']=='v1.13.25',name
    out=ROOT.parents[1]/'output/排班管理_20261021_v1.13.25';out.mkdir(exist_ok=True)
    archive=out/'排班管理_v1.13.25_月排休額度測試版完整來源.zip'
    contents={name:(ROOT/name).read_text(encoding='utf-8').encode() for name in FILES}
    manifest={name:sha256(value).hexdigest() for name,value in contents.items()}
    with ZipFile(archive,'x',ZIP_DEFLATED) as z:
        for name,value in contents.items():z.writestr('gym_v1.13.25/'+name,value)
        z.writestr('gym_v1.13.25/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert sha256(z.read('gym_v1.13.25/'+name)).hexdigest()==digest
        assert not any(token in name.lower() for name in z.namelist() for token in ('.postgres_data','secrets.toml','private_source','.env','.test-temp'))
    print(json.dumps({'files':len(FILES),'path':str(archive),'sha256':sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
