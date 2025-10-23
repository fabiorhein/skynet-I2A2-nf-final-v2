"""Basic fiscal validations for documents.

Returns a dict with status and list of issues.
"""
from typing import Dict, Any, List, Tuple
import re


def _only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def validate_cnpj(cnpj: str) -> bool:
    """Validate CNPJ using modulus 11 algorithm."""
    if not cnpj:
        return False
    c = _only_digits(cnpj)
    if len(c) != 14:
        return False

    def _calc(digs):
        nums = [6,5,4,3,2,9,8,7,6,5,4,3,2]
        s = sum(int(a)*b for a,b in zip(digs, nums[1:]))
        r = s % 11
        return '0' if r < 2 else str(11 - r)

    base = c[:12]
    v1 = _calc(base)
    v2 = _calc(base + v1)
    return c[-2:] == v1 + v2


def validate_totals(items: List[Dict[str, Any]], total: float) -> Tuple[bool, float]:
    s = 0.0
    for it in items:
        v = it.get('valor_total') or 0.0
        s += float(v)
    ok = abs(s - (total or 0.0)) <= 0.01
    return ok, s


def cfop_type(cfop: str) -> str:
    if not cfop:
        return 'unknown'
    # Simplified rules: 1xxxx / 2xxxx entrada compra, 5xxxx venda
    if cfop.startswith('5') or cfop.startswith('6'):
        return 'venda'
    if cfop.startswith('1') or cfop.startswith('2'):
        return 'compra'
    if cfop.startswith('3'):
        return 'devolucao'
    return 'other'


def validate_impostos(doc: Dict[str, Any]) -> List[str]:
    issues = []
    impostos = doc.get('impostos') or {}
    # Naive checks: ICMS/IPI present if expected
    icms = impostos.get('icms')
    ipi = impostos.get('ipi')
    if icms is None:
        issues.append('ICMS ausente')
    if ipi is None:
        issues.append('IPI ausente')
    return issues


def validate_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    issues = []
    status = 'success'

    emitente = doc.get('emitente') or {}
    cnpj = emitente.get('cnpj')
    if not validate_cnpj(cnpj):
        issues.append('CNPJ inválido do emitente')

    items = doc.get('itens') or []
    total = doc.get('total') or 0.0
    ok_totals, calc_sum = validate_totals(items, total)
    if not ok_totals:
        issues.append(f'Soma dos itens {calc_sum:.2f} difere do total {total:.2f}')

    cfop = doc.get('cfop')
    # Check CFOP compatibility
    doc_type = cfop_type(cfop)
    # If totals mismatch or cnpj invalid mark warning/error
    if issues:
        status = 'error'

    # tax checks
    tax_issues = validate_impostos(doc)
    issues.extend(tax_issues)
    if tax_issues and status != 'error':
        status = 'warning'

    return {
        'status': status,
        'issues': issues,
        'calculated_sum': calc_sum
    }
