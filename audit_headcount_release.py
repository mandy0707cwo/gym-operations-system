"""比較前版關鍵界線，僅讀來源，不連資料庫。"""
from hashlib import sha256
import json
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parent

def audit():
    previous=ROOT.parent/'scheduling_v1.13.27'
    files=runpy.run_path(str(ROOT/'package_scheduling_v27.py'))['FILES']
    protected=[name for name in files if name.startswith('supabase/') or
        name.endswith('_repository.py') or name.startswith(('financial_','finance_','money_','usage_','idempotency'))]
    assert protected,'找不到應核對的核心檔案'
    differences=[name for name in protected if (ROOT/name).read_bytes()!=(previous/name).read_bytes()]
    assert not differences, differences
    prior={}
    for name in ('verification_schedule_database.json','verification_schedule_security.json'):
        report=json.loads((ROOT/name).read_text(encoding='utf-8'))
        assert report['version']=='v1.13.27' and report['successful'],name
        assert (ROOT/name).read_bytes()==(previous/name).read_bytes(),name
        prior[name]={'version':report['version'],'sha256':sha256((ROOT/name).read_bytes()).hexdigest()}
    result={'version':'v1.13.28','successful':True,'scope':'source boundary comparison, not a database rerun',
        'database_modified':False,'production_modified':False,'previous_version':'v1.13.27',
        'unchanged_protected_files':protected,'previous_database_evidence':prior}
    (ROOT/'verification_headcount_release.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    result=audit()
    print(json.dumps({'version':result['version'],'successful':True,
        'unchanged_protected_files':len(result['unchanged_protected_files']),'database_rerun':False},ensure_ascii=False))
