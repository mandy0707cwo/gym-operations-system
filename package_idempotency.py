"""白名單來源包，不包含本機虛構測試資料庫、真實資料或 Secrets。"""
from pathlib import Path
import runpy
import json
from hashlib import sha256
from zipfile import ZipFile, ZIP_DEFLATED
ROOT=Path(__file__).resolve().parent
old=runpy.run_path(str(ROOT/'package_finance_center.py'))['FILES']
FILES=[x for x in old if x not in ('audit_online_release.py',)] + [
    'operation_requests.py','UPGRADE_v1.13.19.md','VERIFICATION_v1.13.19.md','RELEASE_STATUS_v1.13.19.md',
    'audit_idempotency_release.py','package_idempotency.py','package_finance_center.py','test_idempotency_transactions.sql',
    'supabase/migrations/20261018111949_purchase_usage_idempotency_v1_13_19.sql',
    'tests/test_operation_requests.py','tests/test_operation_ui.py','tests/test_usage_idempotency_ui.py',
    'tests/test_idempotency_database.py','tests/setup_test_database.py',
    'tests/fixtures/current_transaction_functions.sql','tests/fixtures/base_database.sql',
    'tests/fixtures/idempotency_setup.sql','tests/fixtures/idempotency_catalog.sql','tests/fixtures/release_v18_contract.json',
    'migration_purchase_code_v1_13_8.sql']
assert len(FILES)==len(set(FILES))
if __name__=='__main__':
    out=ROOT.parents[1]/'output/購課銷課防重送_20261018_v1.13.19'
    out.mkdir(exist_ok=True)
    target=out/'購課銷課防重送_v1.13.19_來源包.zip'
    if target.exists():raise FileExistsError('不覆蓋既有來源包')
    contents={name:(ROOT/name).read_text(encoding='utf-8').encode('utf-8') for name in FILES}
    manifest={name:sha256(data).hexdigest() for name,data in contents.items()}
    with ZipFile(target,'x',ZIP_DEFLATED) as z:
        for name in FILES:z.writestr('gym_v1.13.19/'+name,contents[name])
        z.writestr('gym_v1.13.19/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(target) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert sha256(z.read('gym_v1.13.19/'+name)).hexdigest()==digest
        assert not any(x in n for n in z.namelist() for x in ('.postgres_data','secrets.toml','postgres_test.log','activity_pilot'))
    print(json.dumps({'path':str(target),'files':len(FILES),'sha256':sha256(target.read_bytes()).hexdigest()},ensure_ascii=False))
