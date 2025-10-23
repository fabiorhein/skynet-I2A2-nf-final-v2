"""Simple XML parser for NFe/NFCe/CTe extracting main fiscal fields.

This is a pragmatic parser using lxml and local-name() XPaths to avoid namespace issues.
"""
from lxml import etree
from typing import Dict, Any, List
import re


def _text(node):
    # node may be an Element or a string result from xpath (ElementUnicodeResult)
    try:
        if node is None:
            return None
        if hasattr(node, 'text'):
            return node.text.strip() if node.text else None
        return str(node).strip()
    except Exception:
        return None


def parse_xml_string(xml_string: str) -> Dict[str, Any]:
    if not isinstance(xml_string, str):
        return {
            'error': 'invalid_input',
            'message': f'Expected string input, got {type(xml_string)}',
            'raw_text': str(xml_string),
            'numero': None,
            'emitente': {},
            'destinatario': {},
            'itens': [],
            'impostos': {},
            'total': None,
            'data_emissao': None
        }
        
    try:
        root = etree.fromstring(xml_string.encode('utf-8'))
    except Exception as e:
        return {
            'error': 'xml_parse_error',
            'message': f'Failed to parse XML: {str(e)}',
            'raw_text': xml_string,
            'numero': None,
            'emitente': {},
            'destinatario': {},
            'itens': [],
            'impostos': {},
            'total': None,
            'data_emissao': None
        }

    def findtext(xpath):
        try:
            res = root.xpath(xpath)
            return _text(res[0]) if res else None
        except Exception:
            return None

    # Emitente/destinatario: try to find under 'emit' and 'dest' parents first
    def _find_under(parent_local_name: str, tag: str):
        res = root.xpath(f'.//*[local-name()="{parent_local_name}"]//*[local-name()="{tag}"]')
        return _text(res[0]) if res else None

    emitente = {
        'razao_social': _find_under('emit', 'xNome') or findtext('.//*[local-name()="xNome"][1]'),
        'cnpj': _find_under('emit', 'CNPJ') or findtext('.//*[local-name()="CNPJ"][1]'),
        'inscricao_estadual': _find_under('emit', 'IE') or findtext('.//*[local-name()="IE"][1]')
    }

    destinatario = {
        'razao_social': _find_under('dest', 'xNome') or findtext('.//*[local-name()="xNome"][2]'),
        'cnpj_cpf': _find_under('dest', 'CNPJ') or _find_under('dest', 'CPF') or findtext('.//*[local-name()="CNPJ"][2]') or findtext('.//*[local-name()="CPF"][1]')
    }

    # numero may be under ide/nNF
    numero = findtext('.//*[local-name()="ide"]/*[local-name()="nNF"]') or findtext('.//*[local-name()="nNF"][1]')

    data_emissao = findtext('.//*[local-name()="dhEmi"]') or findtext('.//*[local-name()="dEmi"]')

    # Items
    itens: List[Dict[str, Any]] = []
    dets = root.xpath('.//*[local-name()="det"]')
    for det in dets:
        # product node may be det/prod
        prod = det.xpath('.//*[local-name()="prod"]')
        node = prod[0] if prod else det
        desc = node.xpath('.//*[local-name()="xProd"]')
        qtd = node.xpath('.//*[local-name()="qCom"]')
        vuni = node.xpath('.//*[local-name()="vUnCom"]')
        vtot = node.xpath('.//*[local-name()="vProd"]')
        ncm = node.xpath('.//*[local-name()="NCM"]')
        cfop = node.xpath('.//*[local-name()="CFOP"]')
        cst = node.xpath('.//*[local-name()="CST"]')

        def safe_float(node_list):
            v = _text(node_list[0]) if node_list else None
            if v is None:
                return None
            v = v.replace(',', '.')
            try:
                return float(v)
            except Exception:
                return None

        itens.append({
            'descricao': _text(desc[0]) if desc else None,
            'quantidade': safe_float(qtd),
            'valor_unitario': safe_float(vuni),
            'valor_total': safe_float(vtot),
            'ncm': _text(ncm[0]) if ncm else None,
            'cfop': _text(cfop[0]) if cfop else None,
            'cst': _text(cst[0]) if cst else None,
        })

    # Impostos simple extraction
    def _find_float(xpath):
        v = findtext(xpath)
        if v is None:
            return None
        v = str(v).replace(',', '.')
        try:
            return float(v)
        except Exception:
            return None

    impostos = {
        'icms': _find_float('.//*[local-name()="vICMS"][1]'),
        'ipi': _find_float('.//*[local-name()="vIPI"][1]'),
        'pis': _find_float('.//*[local-name()="vPIS"][1]'),
        'cofins': _find_float('.//*[local-name()="vCOFINS"][1]'),
        'icms_st': _find_float('.//*[local-name()="vICMSST"][1]')
    }

    total = _find_float('.//*[local-name()="vNF"][1]')
    if total is None:
        # fallback to sum of item vProd
        s = 0.0
        any_val = False
        for it in itens:
            if it.get('valor_total') is not None:
                any_val = True
                s += it.get('valor_total', 0.0)
        total = s if any_val else _find_float('.//*[local-name()="vProd"][last()]')

    # CFOP: try to get first occurrence
    cfop = findtext('.//*[local-name()="CFOP"][1]')

    result = {
        'emitente': emitente,
        'destinatario': destinatario,
        'numero': numero,
        'data_emissao': data_emissao,
        'itens': itens,
        'impostos': impostos,
        'cfop': cfop,
        'total': total,
        'raw_text': xml_string
    }

    return result


def parse_xml_file(path: str) -> Dict[str, Any]:
    """Parse an XML file and return a dictionary with extracted data.
    
    Returns a dictionary with error information if parsing fails.
    Always returns a dictionary, even in case of errors.
    """
    try:
        with open(path, 'rb') as f:
            content = f.read()
        text = content.decode('utf-8', errors='ignore')
        try:
            # Parse XML string
            result = parse_xml_string(text)
            
            # Validate result type
            if not isinstance(result, dict):
                return {
                    'error': 'xml_parse_error',
                    'message': f'Parser returned {type(result)}, expected dict',
                    'raw_text': text,
                    'numero': None,
                    'emitente': {},
                    'destinatario': {},
                    'itens': [],
                    'impostos': {},
                    'total': None,
                    'data_emissao': None
                }
                
            # Ensure minimum structure
            if 'emitente' not in result:
                result['emitente'] = {}
            if 'destinatario' not in result:
                result['destinatario'] = {}
            if 'itens' not in result:
                result['itens'] = []
            if 'impostos' not in result:
                result['impostos'] = {}
                
            # Store raw XML
            result['raw_text'] = text
            return result
            
        except Exception as parse_err:
            return {
                'error': 'xml_parse_error',
                'message': str(parse_err),
                'raw_text': text,
                'numero': None,
                'emitente': {},
                'destinatario': {},
                'itens': [],
                'impostos': {},
                'total': None,
                'data_emissao': None
            }
            
    except Exception as e:
        return {
            'error': 'xml_file_error', 
            'message': str(e),
            'raw_text': None,
            'numero': None,
            'emitente': {},
            'destinatario': {},
            'itens': [],
            'impostos': {},
            'total': None,
            'data_emissao': None
        }
