"""建立 v20 完整程式來源包；白名單、無憑證、無客戶資料。"""
from pathlib import Path
from hashlib import sha256,sha1
from zipfile import ZipFile,ZIP_DEFLATED
import json
import runpy

ROOT=Path(__file__).resolve().parent
FILES=sorted(set(runpy.run_path(str(ROOT/'package_idempotency.py'))['FILES']) | {
    'audit_monthly_tabs_release.py','package_monthly_tabs.py','UPGRADE_v1.13.20.md',
    'VERIFICATION_v1.13.20.md','RELEASE_STATUS_v1.13.20.md',
    'tests/test_monthly_tabs_v1_13_20.py','tests/fixtures/release_v19_contract.json',
    'tests/test_termination_records.py','verification_summary.json'})

if __name__=='__main__':
    out=ROOT.parents[1]/'output/每月查詢分頁調整_20261019_v1.13.20'
    out.mkdir(exist_ok=True)
    archive=out/'每月查詢分頁調整_v1.13.20_來源備份.zip'
    if archive.exists():
        raise FileExistsError('不覆蓋已建立來源包')
    payloads={name:(ROOT/name).read_text(encoding='utf-8').encode('utf-8') for name in FILES}
    manifest={name:sha256(data).hexdigest() for name,data in payloads.items()}
    with ZipFile(archive,'x',ZIP_DEFLATED) as z:
        for name,data in payloads.items():
            z.writestr('gym_v1.13.20/'+name,data)
        z.writestr('gym_v1.13.20/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():
            assert sha256(z.read('gym_v1.13.20/'+name)).hexdigest()==digest
        assert not any(s in name.lower() for name in z.namelist()
                       for s in ('secrets.toml','.postgres_data','private_source','activity_pilot','full_regression'))
    (out/'來源檔案索引.json').write_text(json.dumps({
        'version':'v1.13.20','files':[{ 'path':name,'sha256':manifest[name],
            'git_blob':sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}
            for name,data in payloads.items()]},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'version':'v1.13.20','files':len(FILES),'archive_sha256':sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
