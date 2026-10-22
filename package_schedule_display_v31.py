"""建立完整來源包並核對雜湊；不打包秘密、測試暫存或資料庫備份。"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
EXTRAS={"tests/test_schedule_display_v31.py","verify_schedule_display_v31.py",
        "package_schedule_display_v31.py","UPGRADE_v1.13.31.md","RELEASE_STATUS_v1.13.31.md",
        "VERIFICATION_v1.13.31.md","verification_schedule_display_v1.13.31.json"}
MODIFIED={"app.py","VERSION","CHANGELOG.md","README.md","SYSTEM_DOCUMENTATION.md","資料字典.md",
          "schedule_ui.py","schedule_repository.py","schedule_demo_repository.py",
          "tests/test_scheduling_ui.py","tests/test_account_update_form.py"}


def git_names(*args):
    return set(filter(None,subprocess.check_output(["git",*args,"-z"],cwd=ROOT).decode("utf-8").split("\0")))


if __name__=="__main__":
    report=json.loads((ROOT/"verification_schedule_display_v1.13.31.json").read_text(encoding="utf-8"))
    assert report["successful"] and report["version"]=="v1.13.31" and not report["production_modified"]
    assert git_names("diff","--name-only","HEAD")==MODIFIED
    subprocess.run(["git","diff","--check"],cwd=ROOT,check=True)
    files=sorted(git_names("ls-files")|EXTRAS)
    assert all(not any(p in {".git",".test-temp","__pycache__","private_source"} for p in Path(n).parts) for n in files)
    assert not any(Path(n).name in {".env","secrets.toml"} for n in files)
    out=ROOT.parents[1]/"output/排班顯示_20261022_v1.13.31"
    out.mkdir(exist_ok=True)
    archive=out/"排班顯示_v1.13.31_完整來源_v2.zip"
    manifest={}
    with ZipFile(archive,"x",ZIP_DEFLATED) as z:
        for name in files:
            content=(ROOT/name).read_bytes()
            manifest[name]=sha256(content).hexdigest()
            z.writestr("gym_v1.13.31/"+name,content)
        z.writestr("gym_v1.13.31/SOURCE_MANIFEST.json",json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(sha256(z.read("gym_v1.13.31/"+name)).hexdigest()==digest for name,digest in manifest.items())
    print(json.dumps({"files":len(files),"path":str(archive),"sha256":sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
