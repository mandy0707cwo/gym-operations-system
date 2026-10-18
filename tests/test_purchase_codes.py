"""固定購課編號回歸測試；只使用虛構資料，不連線正式資料庫。"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def helper():
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_build_purchase_code_map')
    ns = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<fixed-code>', 'exec'), ns)
    return ns['_build_purchase_code_map']

def test_admin_coach_and_filtered_rows_have_same_code():
    records = [dict(id='recovery', purchase_code='20261008-001'), dict(id='training', purchase_code='20261008-002')]
    build = helper()
    assert build(records)['training'] == build(records[1:])['training'] == '20261008-002'

def test_delete_sort_date_change_does_not_renumber():
    record = dict(id='training', purchase_code='20261008-002', purchase_date='2020-01-01')
    assert helper()([record])['training'] == '20261008-002'

def test_missing_code_only_shows_uuid_never_invents_number():
    assert helper()([dict(id='original-uuid', purchase_date='2026-10-08')]) == {'original-uuid': 'original-uuid'}

def test_duplicate_saved_code_is_not_silently_overwritten():
    with unittest.TestCase().assertRaisesRegex(ValueError, '重複'):
        helper()([dict(id='a', purchase_code='20261008-001'), dict(id='b', purchase_code='20261008-001')])

def test_every_lightweight_purchase_lookup_selects_saved_code():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert '"id,purchase_date,created_at"' not in source
    assert source.count('"id,purchase_code,purchase_date,created_at"') >= 12
    assert 'daily_sequences' not in source

def test_usage_import_guards_old_ambiguous_codes_and_exports_uuid():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert '購課編號與 UUID 不一致' in source
    assert '固定購課編號須附 purchase_uuid' in source
    assert 'usage_export_columns=["purchase_uuid","purchase_id"' in source
    assert 'usage_template=pd.DataFrame(columns=["purchase_uuid","purchase_id"' in source

def test_formal_snapshot_does_not_publish_paused_activity_pilot():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'activity_pilot' not in source
    assert '"v1.13.18"' in source
    assert 'daily_sequences' not in source
