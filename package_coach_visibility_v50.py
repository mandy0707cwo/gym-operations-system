"""從已發布v49來源包加入本版明確檔案，保留其他來源，不打包私人備份。"""
import ast
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parents[1] / 'output/教練績效停用顯示_20261121_v1.13.50'
BASE = ROOT.parents[1] / 'output/教練績效_20261121_v1.13.49/gym-operations-system_v1.13.49_local_candidate.zip'
CHANGED = ['VERSION', 'app.py', 'coach_performance_ui.py', 'tests/test_coach_performance_v49.py',
           'performance_demo.py', 'performance_demo_data.py', 'CHANGELOG.md', 'SYSTEM_DOCUMENTATION.md', '資料字典.md', 'README.md']
ADDED = ['coach_visibility.py', 'tests/test_coach_visibility_v50.py', 'verify_coach_visibility_v50.py',
         'package_coach_visibility_v50.py', 'UPGRADE_v1.13.50.md']


if __name__ == '__main__':
    result = json.loads((OUTPUT / '驗證結果.json').read_text(encoding='utf-8'))
    assert result['result']['successful']
    assert sha256(BASE.read_bytes()).hexdigest() == '348d341a410dec4f14a8c1ceff42cf37da35448a89b839157fd42e0617d641e5'
    with ZipFile(BASE) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    assert len(files) == 431
    original = files['app.py'].decode('utf-8-sig').replace('\r\n', '\n')
    assert (ROOT / 'app.py').read_text(encoding='utf-8-sig') == original.replace('or "v1.13.49"', 'or "v1.13.50"')
    for name in CHANGED + ADDED:
        data = (ROOT / name).read_bytes()
        if name.endswith('.py'): ast.parse(data.decode('utf-8-sig'), filename=name)
        if name in ADDED: assert name not in files
        files[name] = data
    target = OUTPUT / 'gym-operations-system_v1.13.50_local_candidate.zip'
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            assert not any(part in name.split('/') for part in ['.git', 'private_backup', '__pycache__'])
            assert not name.endswith('secrets.toml')
            archive.writestr(name, data)
    manifest = {'version': 'v1.13.50', 'status': 'local_candidate_not_deployed', 'production_modified': False,
        'base_commit': '2d1c1b376f67c9a22268960b3d2b557db95f842c', 'base_tree': '6b79f8b42b02931f9ced3ccd392127925de2f0be',
        'changed': CHANGED, 'added': ADDED, 'source_files': len(files), 'archive': target.name,
        'archive_sha256': sha256(target.read_bytes()).hexdigest(), 'database_migration_required': False,
        'source_sha256': {name: sha256(data).hexdigest() for name, data in sorted(files.items())}}
    (OUTPUT / 'source_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'source_sha256'}, ensure_ascii=False))
