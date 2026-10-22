"""v23候選來源：延續白名單，不納入本機資料、憑證或暫存。"""
from hashlib import sha256
import json
from pathlib import Path
import runpy
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
FILES=sorted(set(runpy.run_path(str(ROOT/'package_scheduling.py'))['FILES'])|{
    'package_scheduling_v23.py','UPGRADE_v1.13.23.md','VERIFICATION_v1.13.23.md','RELEASE_STATUS_v1.13.23.md',
    'supabase/migrations/20261021091712_schedule_approved_visibility_v1_13_23.sql'})
if __name__=='__main__':
    for name in ('verification_schedule_ui.json','verification_schedule_database.json','verification_schedule_security.json'):
        result=json.loads((ROOT/name).read_text(encoding='utf-8'))
        assert result['successful'] and result['version']=='v1.13.23',name
    out=ROOT.parents[1]/'output/排班管理_20261021_v1.13.23'
    out.mkdir(exist_ok=True)
    archive=out/'排班管理_v1.13.23_精簡測試版完整來源.zip'
    contents={name:(ROOT/name).read_text(encoding='utf-8').encode() for name in FILES}
    manifest={name:sha256(data).hexdigest() for name,data in contents.items()}
    with ZipFile(archive,'x',ZIP_DEFLATED) as z:
        for name,data in contents.items():z.writestr('gym_v1.13.23/'+name,data)
        z.writestr('gym_v1.13.23/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert sha256(z.read('gym_v1.13.23/'+name)).hexdigest()==digest
        assert not any(token in name.lower() for name in z.namelist() for token in ('.postgres_data','secrets.toml','private_source','.env','.test-temp'))
    print(json.dumps({'files':len(FILES),'path':str(archive),'sha256':sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
