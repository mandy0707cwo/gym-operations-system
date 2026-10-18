"""正式共同計算中心第一階段：純Decimal計算，不讀帳號、不連DB、不寫交易。

R22/R24：每筆計算、明細加總；已保存值與重建值分開；未知稅別不補零。
使用者2026-10-18授權歷史也依正式規格統一；重建仍不冒充原始保存值。
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from fractions import Fraction
from types import MappingProxyType
from typing import Mapping

RULE_VERSION = "historical-alignment-v3"
ENGINE_VERSION = "v1.13.18"
HISTORICAL_ALIGNMENT_AUTHORITY = "2026-10-18使用者要求歷史及新資料依正式計算中心規格統一；屬標準化重建，不是原始憑據核實"
_UNSET = object()


class FinancialDataError(ValueError):
    """資料不完整或無法計算時，禁止將其偽裝成零。"""


def decimal_value(value, field="金額"):
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        raise FinancialDataError(f"{field}缺漏或型別錯誤，請查核來源資料。")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise FinancialDataError(f"{field}不是有效數值。") from exc
    if not result.is_finite():
        raise FinancialDataError(f"{field}不是有限數值。")
    return result


@dataclass(frozen=True)
class TaxRule:
    version: str = RULE_VERSION
    divisor: Decimal = Decimal("1.05")  # 沿用正式版既有因子，非認定全歷史稅率。
    quantum: Decimal = Decimal("1")

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version.strip():
            raise FinancialDataError("換算規則版本不可空白。")
        divisor = decimal_value(self.divisor, "換算因子")
        quantum = decimal_value(self.quantum, "取整單位")
        if divisor <= 0 or quantum != Decimal("1"):
            raise FinancialDataError("換算因子須為正數；本階段只支援整元取整。")
        object.__setattr__(self, "divisor", divisor)
        object.__setattr__(self, "quantum", Decimal("1"))


DEFAULT_OPERATION_RULE = TaxRule()


def positive_integer(value, field):
    number = decimal_value(value, field)
    if number <= 0 or number != number.to_integral_value():
        raise FinancialDataError(f"{field}須為正整數，不可截斷或補零。")
    return int(number)


@dataclass(frozen=True)
class CourseNetSchedule:
    total_sessions: int
    total_net: Decimal
    regular_net: Decimal
    final_net: Decimal
    rule_version: str

    def amount_for(self, sequence):
        seq = positive_integer(sequence, "銷課堂次")
        if seq > self.total_sessions:
            raise FinancialDataError("銷課堂次超過購課堂數。")
        return self.final_net if seq == self.total_sessions else self.regular_net


def course_net_schedule(gross_total, sessions, *, rule=DEFAULT_OPERATION_RULE):
    """完整標準化的課程分配。一般堂不先把含稅單價取到小數兩位。"""
    total = decimal_value(gross_total, "課程含稅總額")
    count = positive_integer(sessions, "購課堂數")
    if total < 0 or not isinstance(rule, TaxRule):
        raise FinancialDataError("負數課程或缺少有效規則，不能自動分配。")
    # 有理數整數運算精確處理半元界線，不受 Decimal 全域精度或循環小數影響。
    exact_unit = Fraction(total) / count / Fraction(rule.divisor)
    regular = Decimal((2 * exact_unit.numerator + exact_unit.denominator) //
                      (2 * exact_unit.denominator))
    total_net = calculate_money(total, basis_confirmed=True, rule=rule).net
    with localcontext() as context:
        context.prec = max(38, len(total_net.as_tuple().digits) + len(str(count)) + 8)
        final = total_net - regular * (count - 1)
    if final < 0:
        raise FinancialDataError("固定單價造成最後一堂未稅負值，須查核，不自動截成零。")
    return CourseNetSchedule(count, total_net, regular, final, rule.version)


def session_net_from_prior(gross_total, sessions, sequence, previous_net=(), *,
                          rule=DEFAULT_OPERATION_RULE):
    """單次銷課契約：最後一堂減已確認前期值；不自行改寫前期紀錄。"""
    schedule = course_net_schedule(gross_total, sessions, rule=rule)
    seq = positive_integer(sequence, "銷課堂次")
    expected = schedule.amount_for(seq)
    if seq != schedule.total_sessions:
        return expected
    prior = tuple(decimal_value(value, "前期銷課未稅") for value in previous_net)
    if len(prior) != schedule.total_sessions - 1:
        raise FinancialDataError("最後一堂必須取得完整前期銷課未稅，不可只讀當月。")
    if any(value < 0 or value != value.to_integral_value() for value in prior):
        raise FinancialDataError("前期未稅須為非負整元，須查核，不自動取整。")
    final = _sum_exact((schedule.total_net, _sum_exact(prior).copy_negate()))
    if final < 0:
        raise FinancialDataError("前期銷課未稅超過整筆未稅總額，須人工查核。")
    return final


@dataclass(frozen=True)
class MoneyResult:
    gross: Decimal
    net: Decimal | None
    origin: str  # stored / reconstructed / unconfirmed
    rule_version: str | None
    warnings: tuple[str, ...] = ()

    @property
    def tax_difference(self):
        return None if self.net is None else _sum_exact((self.gross, self.net.copy_negate()))


def _sum_exact(values):
    values = tuple(values)
    with localcontext() as ctx:
        left = max((max(v.adjusted() + 1, 1) for v in values), default=1)
        right = max((max(-v.as_tuple().exponent, 0) for v in values), default=0)
        ctx.prec = max(38, left + right + len(str(len(values))) + 4)
        return sum(values, Decimal("0"))


def calculate_money(amount, *, basis_confirmed=False, rule=DEFAULT_OPERATION_RULE,
                    stored_net=_UNSET, stored_rule_version=None):
    """保存未稅優先；缺值不等於0；重建須顯式確認含稅基礎。

    stored_*是未來寫入端的契約，本階段DB未新增此欄位，查詢端不假裝已保存。
    """
    gross = decimal_value(amount, "含稅原值")
    if not isinstance(basis_confirmed, bool):
        raise FinancialDataError("含稅確認旗標必須為布林值，不可用文字代替確認。")
    warnings = ("negative_amount",) if gross < 0 else ()
    if stored_net is not _UNSET:
        net = decimal_value(stored_net, "保存未稅")
        if not isinstance(stored_rule_version, str) or not stored_rule_version.strip():
            raise FinancialDataError("保存未稅缺少規則版本，不可當成已確認值。")
        if net != net.to_integral_value():
            raise FinancialDataError("保存未稅不是整元，請人工查核，不自動取整。")
        return MoneyResult(gross, net, "stored", stored_rule_version, warnings)
    if not basis_confirmed:
        return MoneyResult(gross, None, "unconfirmed", None, warnings)
    if not isinstance(rule, TaxRule):
        raise FinancialDataError("缺少有效換算規則。")
    # 自訂精度，避免受呼叫者全域Decimal context改動影響。
    with localcontext() as ctx:
        ctx.prec = max(38, len(gross.as_tuple().digits) + abs(gross.adjusted()) + 12)
        net = (gross / rule.divisor).quantize(rule.quantum, rounding=ROUND_HALF_UP)
    return MoneyResult(gross, net, "reconstructed", rule.version, warnings)


def business_date(value):
    if isinstance(value, datetime):
        raise FinancialDataError("業務日期不可含時間，請使用entry_date。")
    if isinstance(value, date):
        return value
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError()
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FinancialDataError("業務日期缺漏或格式錯誤，應為yyyy-mm-dd。") from exc


@dataclass(frozen=True)
class ConfirmedGrossWindow:
    start: date
    end: date
    evidence: str

    def __post_init__(self):
        if self.start > self.end or not self.evidence.strip():
            raise FinancialDataError("含稅確認範圍或依據無效。")


CONFIRMED_GROSS_WINDOWS = (
    ConfirmedGrossWindow(date(2026, 9, 1), date(2026, 9, 30),
                         "使用者2026-10-18確認9月體驗／單次金額含稅；核對文件v1.1"),
)


@dataclass(frozen=True)
class OperationLine:
    source_id: str | None
    entry_date: date
    source: Mapping
    money: MoneyResult
    evidence: str | None


@dataclass(frozen=True)
class OperationResult:
    lines: tuple[OperationLine, ...]
    gross_total: Decimal
    net_total: Decimal | None
    unknown_count: int
    missing_id_count: int

    @property
    def has_reconstruction(self):
        return any(line.money.origin == "reconstructed" for line in self.lines)


def build_operation_result(records, *, confirmed_windows=None):
    """純讀取：順序不變、不改來源；任何重複ID或無效金額使整份計算失敗。"""
    lines, ids = [], set()
    unknown, missing_ids = 0, 0
    for record in records:
        source = dict(record)
        day = business_date(source.get("entry_date"))
        raw_id = source.get("id")
        sid = str(raw_id) if raw_id is not None else None
        if sid:
            if sid in ids:
                raise FinancialDataError(f"來源ID重複：{sid}；未產生部分合計。")
            ids.add(sid)
        else:
            missing_ids += 1
        evidence = (HISTORICAL_ALIGNMENT_AUTHORITY if confirmed_windows is None else
                    next((w.evidence for w in confirmed_windows if w.start <= day <= w.end), None))
        if 'net_amount' in source:
            money = calculate_money(source.get('amount'), stored_net=source['net_amount'],
                                    stored_rule_version=source.get('calculation_rule_version'))
            rebuilt = calculate_money(source.get('amount'), basis_confirmed=True)
            if money.net != rebuilt.net:
                raise FinancialDataError('保存營運未稅與共同規格不同，須查核，不顯示部分合計。')
        else:
            money = calculate_money(source.get("amount"), basis_confirmed=evidence is not None)
        if money.net is None:
            unknown += 1
        lines.append(OperationLine(sid, day, MappingProxyType(source), money, evidence))
    total = _sum_exact(line.money.gross for line in lines)
    net_total = None if unknown else _sum_exact(line.money.net for line in lines)
    return OperationResult(tuple(lines), total, net_total, unknown, missing_ids)
