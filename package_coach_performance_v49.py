"""從已發布v48來源包加入本次明確檔案，不把髒工作樹整批打包。"""
import ast
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parents[1] / 'output/教練績效_20261121_v1.13.49'
BASE = ROOT.parents[1] / 'output/分期入帳日期區間_20261121_v1.13.48/gym-operations-system_v1.13.48.zip'
CHANGED = ['VERSION', 'app.py', 'operations_ui.py', 'CHANGELOG.md', 'SYSTEM_DOCUMENTATION.md', '資料字典.md', 'README.md']
ADDED = ['coach_performance.py', 'coach_performance_repository.py', 'coach_performance_ui.py',
         'performance_demo.py', 'performance_demo_data.py', 'tests/test_coach_performance_v49.py',
         'tests/test_coach_performance_v49.mjs', 'verify_coach_performance_v49.py',
         'package_coach_performance_v49.py', 'UPGRADE_v1.13.49.md',
         'supabase/migrations/20261121061449_coach_performance_monthly_hours_v1_13_49.sql']


if __name__ == '__main__':
    results = json.loads((OUTPUT / '驗證結果.json').read_text(encoding='utf-8'))
    assert results['successful'] and results['python_result']['tests'] >= 163
    assert '"tests":9,"passed":true' in results['postgresql_output']
    assert sha256(BASE.read_bytes()).hexdigest() == '08cc7ed5f01ed8bc5960524530ff41881791bf02d9c7f5a317457c961c94dbcd'
    with ZipFile(BASE) as old:
        files = {name: old.read(name) for name in old.namelist()}
    assert len(files) == 420
    original_app = files['app.py'].decode('utf-8-sig').replace('\r\n', '\n')
    candidate_app = (ROOT / 'app.py').read_text(encoding='utf-8-sig')
    assert candidate_app == original_app.replace('or "v1.13.48"', 'or "v1.13.49"'), 'app.py含非本次改動，停止封裝'
    for name in CHANGED + ADDED:
        data = (ROOT / name).read_bytes()
        if name.endswith('.py'):
            ast.parse(data.decode('utf-8-sig'), filename=name)
        if name in ADDED:
            assert name not in files
        files[name] = data
    assert not any(any(part in name.split('/') for part in ['.git', 'private_backup', '__pycache__']) or name.endswith('secrets.toml') for name in files)
    target = OUTPUT / 'gym-operations-system_v1.13.49_local_candidate.zip'
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()): archive.writestr(name, data)
    manifest = {'version': 'v1.13.49', 'status': 'local_candidate_not_deployed',
                'production_modified': False, 'base_version': 'v1.13.48', 'base_source_files': 420,
                'source_files': len(files), 'changed': CHANGED, 'added': ADDED,
                'archive': target.name, 'archive_sha256': sha256(target.read_bytes()).hexdigest(),
                'source_sha256': {name: sha256(data).hexdigest() for name, data in sorted(files.items())}}
    (OUTPUT / 'source_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'source_sha256'}, ensure_ascii=False))
