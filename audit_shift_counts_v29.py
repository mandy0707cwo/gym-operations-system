"""僅核對來源差異及本輪測試證據，不連正式系統。"""
from hashlib import sha256
import json
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parent

def audit():
    previous=ROOT.parent/'scheduling_v1.13.28'
    files=runpy.run_path(str(ROOT/'package_scheduling_v28.py'))['FILES']
    protected=[name for name in files if name.startswith('supabase/') or
        (name.endswith('_repository.py') and name!='schedule_demo_repository.py') or
        name.startswith(('financial_','finance_','money_','usage_','idempotency'))]
    assert protected
    assert all((ROOT/name).read_bytes()==(previous/name).read_bytes() for name in protected)
    evidence={}
    for name in ('verification_schedule_ui.json','verification_schedule_database.json','verification_schedule_security.json'):
        report=json.loads((ROOT/name).read_text(encoding='utf-8'))
        assert report['version']=='v1.13.29' and report['successful'],name
        evidence[name]=sha256((ROOT/name).read_bytes()).hexdigest()
    result={'version':'v1.13.29','successful':True,'production_modified':False,
        'scope':'source boundary and localhost evidence verification','unchanged_protected_files':protected,
        'new_migration':'20261022021115_schedule_manager_parity_v1_13_29.sql','evidence_sha256':evidence}
    (ROOT/'verification_shift_counts_release.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    result=audit()
    print(json.dumps({'version':result['version'],'successful':True,'unchanged_protected_files':len(result['unchanged_protected_files'])}))
