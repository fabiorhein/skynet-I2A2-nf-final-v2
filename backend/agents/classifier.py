from ..tools import fiscal_validator
from typing import Dict, Any


def classify_document(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a fiscal document based on its parsed data."""
    if not isinstance(parsed, dict):
        return {
            'tipo': 'unknown',
            'setor': 'unknown',
            'perfil_emitente': 'unknown',
            'validacao': {
                'status': 'error',
                'issues': ['Documento inválido'],
                'calculated_sum': 0.0
            }
        }

    # Get CFOP from document or first item
    cfop = None
    try:
        cfop = parsed.get('cfop') or (parsed.get('itens', [])[0] or {}).get('cfop')
    except (IndexError, TypeError, AttributeError):
        cfop = None
    
    tipo = 'unknown'
    if cfop:
        tipo = fiscal_validator.cfop_type(cfop)

    # Simple issuer profile: if issuer has cnpj and company-like name -> fornecedor
    emit = parsed.get('emitente') or {}
    cnpj = emit.get('cnpj')
    perfil = 'fornecedor' if cnpj else 'cliente'

    # Sector rules (very naive)
    setor = 'servicos'
    total = parsed.get('total') or 0.0
    if total and total > 10000:
        setor = 'industria'
    else:
        setor = 'comercio'

    validation = fiscal_validator.validate_document(parsed)

    return {
        'tipo': tipo,
        'setor': setor,
        'perfil_emitente': perfil,
        'validacao': validation
    }
