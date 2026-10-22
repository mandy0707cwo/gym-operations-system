"""完整來源白名單，保留前版資料庫證據版本，不含秘密或測試資料。"""
from hashlib import sha256
import json
from pathlib import Path
import runpy
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
FILES=sorted(set(runpy.run_path(str(ROOT/'package_scheduling_v27.py'))['FILES'])|{
    'schedule_headcounts.py','schedule_headcount_component.py','schedule_headcount_ui.py',
    'schedule_demo_examples.py','tests/test_schedule_headcounts.py','audit_headcount_release.py',
    'verification_headcount_release.json','package_scheduling_v28.py',
    'UPGRADE_v1.13.28.md','VERIFICATION_v1.13.28.md','RELEASE_STATUS_v1.13.28.md'})

if __name__=='__main__':
    for name in ('verification_schedule_ui.json','verification_headcount_release.json'):
        report=json.loads((ROOT/name).read_text(encoding='utf-8'))
        assert report['version']=='v1.13.28' and report['successful'],name
    for name in ('verification_schedule_database.json','verification_schedule_security.json'):
        report=json.loads((ROOT/name).read_text(encoding='utf-8'))
        assert report['version']=='v1.13.27' and report['successful'],name
    out=ROOT.parents[1]/'output/排班管理_20261022_v1.13.28';out.mkdir(exist_ok=True)
    archive=out/'排班管理_v1.13.28_人數簡表測試版完整來源.zip'
    contents={name:(ROOT/name).read_text(encoding='utf-8').encode() for name in FILES}
    manifest={name:sha256(value).hexdigest() for name,value in contents.items()}
    with ZipFile(archive,'x',ZIP_DEFLATED) as z:
        for name,value in contents.items():z.writestr('gym_v1.13.28/'+name,value)
        z.writestr('gym_v1.13.28/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert sha256(z.read('gym_v1.13.28/'+name)).hexdigest()==digest
        assert not any(token in name.lower() for name in z.namelist() for token in ('.postgres_data','secrets.toml','private_source','.env','.test-temp'))
    print(json.dumps({'files':len(FILES),'path':str(archive),'sha256':sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
