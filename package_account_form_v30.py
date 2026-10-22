"""建立可直接使用的完整來源包；不打包本機秘密、測試暫存或資料備份。"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
EXTRAS={"tests/test_account_update_form.py","tests/fixtures/account_form_v29_contract.json","verify_account_form_v30.py",
        "package_account_form_v30.py","UPGRADE_v1.13.30.md","RELEASE_STATUS_v1.13.30.md",
        "VERIFICATION_v1.13.30.md","verification_account_form_v1.13.30.json"}
MODIFIED={"app.py","VERSION","CHANGELOG.md","README.md","SYSTEM_DOCUMENTATION.md"}

if __name__=="__main__":
    report=json.loads((ROOT/"verification_account_form_v1.13.30.json").read_text(encoding="utf-8"))
    assert report["successful"] and report["version"]=="v1.13.30" and not report["production_modified"]
    changed=set(subprocess.check_output(["git","diff","--name-only","HEAD"],cwd=ROOT,text=True).splitlines())
    assert changed==MODIFIED,changed
    tracked=set(subprocess.check_output(["git","ls-files","-z"],cwd=ROOT).decode("utf-8").rstrip("\0").split("\0"))
    files=sorted(tracked|EXTRAS)
    assert all(not any(part in {".git",".test-temp","__pycache__","private_source"} for part in Path(n).parts) for n in files)
    assert not any(Path(n).name in {".env","secrets.toml"} for n in files)
    out=ROOT.parents[1]/"output/帳號管理_20261022_v1.13.30"
    out.mkdir(exist_ok=True)
    archive=out/"帳號管理_v1.13.30_完整來源_v2.zip"
    manifest={}
    with ZipFile(archive,"x",ZIP_DEFLATED) as z:
        for name in files:
            content=(ROOT/name).read_bytes()
            manifest[name]=sha256(content).hexdigest()
            z.writestr("gym_v1.13.30/"+name,content)
        z.writestr("gym_v1.13.30/SOURCE_MANIFEST.json",json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(sha256(z.read("gym_v1.13.30/"+name)).hexdigest()==digest for name,digest in manifest.items())
    print(json.dumps({"files":len(files),"path":str(archive),"sha256":sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
