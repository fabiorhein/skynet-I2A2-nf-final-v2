import logging
from ..tools import fiscal_validator
from typing import Dict, Any, Union, List, Tuple


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
        # Primeiro tenta obter o CFOP diretamente do documento
        cfop = parsed.get('cfop')
        
        # Se não encontrou, tenta obter do primeiro item
        if not cfop:
            itens = parsed.get('itens', [])
            # Verifica se itens é uma lista e não está vazia
            if isinstance(itens, (list, tuple)) and itens and isinstance(itens[0], dict):
                cfop = itens[0].get('cfop')
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f'Erro ao obter CFOP: {str(e)}')
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
