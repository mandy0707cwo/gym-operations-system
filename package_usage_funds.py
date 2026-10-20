"""候選完整來源包：無資料庫、憑證、客戶資料及測試暫存。"""
from hashlib import sha256
import json
from pathlib import Path
import runpy
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
FILES=sorted((set(runpy.run_path(str(ROOT/'package_monthly_tabs.py'))['FILES'])-{'verification_summary.json'})|{
    'usage_funds.py','verify_usage_funds.py','package_usage_funds.py','UPGRADE_v1.13.21.md',
    'VERIFICATION_v1.13.21.md','tests/test_usage_funds.py','tests/test_usage_funds_ui.py',
    'tests/test_usage_funds_database.py','tests/setup_usage_funds_database.py',
    'tests/fixtures/release_v20_contract.json','verification_ui_v21.json','verification_database_v21.json',
    'supabase/migrations/20261020023026_usage_funds_guard_v1_13_21.sql'})
if __name__=='__main__':
    for name in ('verification_ui_v21.json','verification_database_v21.json'):
        assert json.loads((ROOT/name).read_text(encoding='utf-8'))['successful'],name
    out=ROOT.parents[1]/'output/銷課實收餘額檢查_20261020_v1.13.21'
    out.mkdir(exist_ok=True)
    archive=out/'銷課實收餘額檢查_v1.13.21_候選來源.zip'
    contents={name:(ROOT/name).read_text(encoding='utf-8').encode() for name in FILES}
    manifest={name:sha256(data).hexdigest() for name,data in contents.items()}
    with ZipFile(archive,'x',ZIP_DEFLATED) as z:
        for name,data in contents.items():z.writestr('gym_v1.13.21/'+name,data)
        z.writestr('gym_v1.13.21/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert sha256(z.read('gym_v1.13.21/'+name)).hexdigest()==digest
    print(json.dumps({'files':len(FILES),'path':str(archive),'sha256':sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
