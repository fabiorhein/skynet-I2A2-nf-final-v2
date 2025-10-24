"""Tests for fiscal_validator.py"""
import pytest
from backend.tools.fiscal_validator import (
    validate_cnpj,
    validate_totals,
    cfop_type,
    validate_impostos,
    validate_document
)

# Test data
VALID_CNPJ = "33.453.678/0001-00"
INVALID_CNPJ = "33.453.678/0001-01"  # Digito verificador inválido
INVALID_FORMAT_CNPJ = "33.453.678/0001"  # Formato inválido

SAMPLE_DOC = {
    "emitente": {
        "cnpj": "33.453.678/0001-00",
        "nome": "Empresa Teste LTDA"
    },
    "itens": [
        {"valor_total": 100.0},
        {"valor_total": 200.0}
    ],
    "total": 300.0,
    "cfop": "5102",
    "impostos": {
        "icms": {"valor": 54.0},
        "ipi": {"valor": 0.0}
    }
}

# CNPJ Validation Tests
def test_validate_cnpj_valid():
    """Test valid CNPJ"""
    assert validate_cnpj(VALID_CNPJ) is True

def test_validate_cnpj_invalid():
    """Test invalid CNPJ"""
    assert validate_cnpj(INVALID_CNPJ) is False

def test_validate_cnpj_short():
    """Test short CNPJ"""
    assert validate_cnpj("123") is False

def test_validate_cnpj_none():
    """Test None CNPJ"""
    assert validate_cnpj(None) is False

def test_validate_cnpj_empty():
    """Test empty CNPJ"""
    assert validate_cnpj("") is False

# Totals Validation Tests
def test_validate_totals_match():
    """Test when totals match"""
    items = [{"valor_total": 100.0}, {"valor_total": 200.0}]
    assert validate_totals(items, 300.0) == (True, 300.0)

def test_validate_totals_within_tolerance():
    """Test when difference is within tolerance (0.01)"""
    items = [{"valor_total": 100.0}, {"valor_total": 200.0}]
    assert validate_totals(items, 300.01) == (True, 300.0)

def test_validate_totals_outside_tolerance():
    """Test when difference is outside tolerance"""
    items = [{"valor_total": 100.0}, {"valor_total": 200.0}]
    assert validate_totals(items, 300.1) == (False, 300.0)

# CFOP Type Tests
def test_cfop_type_venda():
    """Test CFOP types for sales"""
    assert cfop_type("5102") == "venda"
    assert cfop_type("6102") == "venda"

def test_cfop_type_compra():
    """Test CFOP types for purchases"""
    assert cfop_type("1102") == "compra"
    assert cfop_type("2102") == "compra"

def test_cfop_type_devolucao():
    """Test CFOP types for returns"""
    assert cfop_type("3202") == "devolucao"

def test_cfop_type_other():
    """Test other CFOP types"""
    assert cfop_type("4202") == "other"
    assert cfop_type("") == "unknown"

# Document Validation Tests
def test_validate_document_valid():
    """Test validation of a valid document"""
    valid_doc = {
        'emitente': {
            'cnpj': '33.453.678/0001-00',
            'razao_social': 'Empresa Teste LTDA',
            'nome': 'Empresa Teste LTDA'
        },
        'destinatario': {
            'cnpj': '12.345.678/0001-99',
            'razao_social': 'Cliente Teste SA'
        },
        'itens': [
            {'descricao': 'Produto 1', 'quantidade': 2, 'valor_unitario': 50.0, 'valor_total': 100.0, 'ncm': '1234.56.78', 'cfop': '5102', 'quantity': 2},
            {'descricao': 'Produto 2', 'quantidade': 1, 'valor_unitario': 200.0, 'valor_total': 200.0, 'ncm': '8765.43.21', 'cfop': '5102', 'quantity': 1}
        ],
        'total': 300.0,
        'cfop': '5102',
        'document_type': 'NFe',
        'numero': '12345',
        'data_emissao': '2025-10-24',
        'impostos': {
            'icms': {'valor': 54.0},
            'ipi': {'valor': 0.0}
        }
    }
    
    result = validate_document(valid_doc)
    assert result['status'] == 'success'
    assert not result['issues']
    assert not result.get('warnings', [])
    assert result['calculated_sum'] == 300.0
    assert result['validations']['emitente']['cnpj'] is True
    assert result['validations']['itens']['all_valid'] is True
    assert result['validations']['totals']['valid'] is True

def test_validate_document_invalid_cnpj():
    """Test validation with invalid CNPJ"""
    invalid_doc = {
        'emitente': {
            'cnpj': '11.111.111/1111-11',  # CNPJ inválido
            'razao_social': 'Empresa Inválida',
            'nome': 'Empresa Inválida'
        },
        'itens': [
            {'descricao': 'Produto 1', 'quantidade': 2, 'valor_unitario': 50.0, 'valor_total': 100.0}
        ],
        'total': 100.0
    }
    
    result = validate_document(invalid_doc)
    assert result['status'] == 'error'
    assert any('CNPJ do emitente inválido' in issue for issue in result['issues'])
    assert result['validations']['emitente']['cnpj'] is False

def test_validate_document_missing_totals():
    """Test validation with missing totals"""
    doc = {
        'emitente': {
            'cnpj': '33.453.678/0001-00',
            'razao_social': 'Empresa Teste LTDA'
        },
        'itens': [
            {'descricao': 'Produto 1', 'quantidade': 2, 'valor_unitario': 50.0, 'valor_total': 100.0, 'ncm': '1234.56.78', 'cfop': '5102'}
        ],
        'total': 400.0  # Total incorreto (deveria ser 100.0)
    }
    
    result = validate_document(doc)
    assert result['status'] == 'error'
    assert any('Divergência nos totais' in issue for issue in result['issues'])
    assert result['validations']['totals']['valid'] is False

def test_validate_document_missing_taxes():
    """Test validation with missing taxes"""
    doc = {
        'emitente': {
            'cnpj': '33.453.678/0001-00',
            'razao_social': 'Empresa Teste LTDA'
        },
        'itens': [
            {'descricao': 'Produto 1', 'quantidade': 1, 'valor_unitario': 100.0, 'valor_total': 100.0, 'ncm': '1234.56.78', 'cfop': '5102', 'quantity': 1}
        ],
        'total': 100.0,
        'cfop': '5102',
        'document_type': 'NFe',
        'numero': '12345',
        'data_emissao': '2025-10-24',
        'impostos': {}  # Impostos ausentes
    }
    
    result = validate_document(doc)
    # Deve ser um warning porque são apenas questões de impostos
    assert result['status'] == 'warning', f"Expected status 'warning', but got '{result['status']}'"
    
    # Verificar se as mensagens de imposto estão presentes
    tax_messages = ["ICMS ausente", "IPI ausente"]
    for msg in tax_messages:
        assert any(msg in issue for issue in result['issues']), \
            f"Expected '{msg}' in issues, but got: {result['issues']}"

# Test edge cases
def test_validate_document_empty():
    """Test validation of empty document"""
    result = validate_document({})
    assert result['status'] == 'error'
    assert any('CNPJ do emitente não informado' in issue for issue in result['issues'])
    assert any('Documento não contém itens' in issue for issue in result['issues'])
    assert not result['validations']['itens']['has_items']

def test_validate_document_missing_items():
    """Test validation with missing items"""
    doc = {
        'emitente': {
            'cnpj': '33.453.678/0001-00',
            'razao_social': 'Empresa Teste LTDA'
        },
        'itens': [],
        'total': 0.0
    }
    
    result = validate_document(doc)
    assert result['status'] == 'error'
    assert any('Documento não contém itens' in issue for issue in result['issues'])
    assert not result['validations']['itens']['has_items']
