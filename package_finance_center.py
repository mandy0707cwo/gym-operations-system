"""建立候選來源包，明確白名單，絕不包含機密、快照或會員明細。"""
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT.parents[1]/'output/共同計算中心_20261018_v1.13.18'
FILES=['app.py','financial_calculations.py','financial_reconciliation.py','history_proposal.py','dry_run_history.py','monthly_operation_queries.py','course_query_views.py',
       'confirmed_queries.py','navigation_platforms.py','ui_text.py','course_defaults.py','project_queries.py',
       'requirements.txt','VERSION','VERSIONING.md','AGENTS.md','CHANGELOG.md','README.md',
       'SYSTEM_DOCUMENTATION.md','資料字典.md','FINANCIAL_CALCULATION_CENTER.md',
       'UPGRADE_v1.13.18.md','VERIFICATION_v1.13.18.md','RELEASE_STATUS_v1.13.18.md','verification_result.json','verify_finance_center.py',
       'finance_reporting.py','audit_online_release.py','ROLLBACK_v1.13.18.sql','test_finance_transactions.sql',
       'supabase/migrations/20261018091440_finance_center_v1_13_18.sql',
       'tests/test_financial_calculations.py','tests/test_financial_reconciliation.py','tests/test_historical_alignment.py','tests/test_finance_center_integration.py',
       'tests/test_query_views_v1_13_14.py','tests/test_confirmed_queries.py','tests/test_purchase_installment_ui.py',
       'tests/test_online_finance.py','tests/test_project_queries.py','tests/test_project_queries_ui.py',
       'tests/test_course_defaults.py','tests/test_navigation_platforms.py','tests/test_ui_text.py','tests/test_purchase_codes.py']

if __name__=='__main__':
    OUTPUT.mkdir(exist_ok=True)
    target=OUTPUT/'共同計算中心_正式修正_v1.13.18_已部署來源包.zip'
    if target.exists():raise FileExistsError('來源包已存在，請另建版本，不覆蓋。')
    manifest={}
    for name in FILES:
        p=ROOT/name
        if not p.is_file():raise FileNotFoundError(name)
        manifest[name]=sha256(p.read_bytes()).hexdigest()
    with ZipFile(target,'x',ZIP_DEFLATED) as z:
        for name in FILES:z.write(ROOT/name,'finance_center_v1.13.18/'+name)
        z.writestr('finance_center_v1.13.18/SOURCE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with ZipFile(target) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(FILES)+1
        assert not any(s in name.lower() for name in z.namelist() for s in ('secrets.toml','private_source','price_audit_payload','activity_pilot','.test-temp'))
        for name,digest in manifest.items():assert sha256(z.read('finance_center_v1.13.18/'+name)).hexdigest()==digest
    print(json.dumps({'archive':str(target),'file_count':len(FILES)+1,'sha256':sha256(target.read_bytes()).hexdigest()},ensure_ascii=False))
