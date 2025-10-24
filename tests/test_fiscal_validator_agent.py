"""Testes para o FiscalValidatorAgent."""
import os
import sys
import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import asyncio
from pathlib import Path

# Adiciona o diretório raiz ao path para importar os módulos
sys.path.append(str(Path(__file__).parent.parent))

from backend.agents.fiscal_validator_agent import (
    FiscalValidatorAgent,
    FiscalCodeValidation,
    FiscalDocumentValidation
)

# Desativa os avisos de depreciação do Pydantic
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Configuração de logging para testes
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dados de teste
TEST_API_KEY = "test-api-key"
TEST_FISCAL_DATA = {
    "cfop": "5102",
    "cst_icms": "00",
    "cst_pis": "01",
    "cst_cofins": "01",
    "ncm": "22030010"
}

# Mock de resposta do LLM
MOCK_LLM_RESPONSE = """
{
    "cfop": {
        "is_valid": true,
        "normalized_code": "5102",
        "description": "Venda de mercadoria adquirida ou recebida de terceiros",
        "confidence": 0.98
    },
    "cst_icms": {
        "is_valid": true,
        "normalized_code": "00",
        "description": "Tributada integralmente",
        "confidence": 0.99
    },
    "cst_pis": {
        "is_valid": true,
        "normalized_code": "01",
        "description": "Operação tributável com alíquota básica",
        "confidence": 0.97
    },
    "cst_cofins": {
        "is_valid": true,
        "normalized_code": "01",
        "description": "Operação tributável com alíquota básica",
        "confidence": 0.97
    },
    "ncm": {
        "is_valid": true,
        "normalized_code": "22030010",
        "description": "Cervejas de malte",
        "confidence": 0.99
    }
}
"""

@pytest.fixture
def fiscal_validator():
    """Fixture para criar uma instância do FiscalValidatorAgent com mock."""
    with patch('google.generativeai.GenerativeModel') as mock_model, \
         patch('google.generativeai.configure') as mock_configure:
        
        # Configura o mock do modelo
        mock_instance = MagicMock()
        mock_model.return_value = mock_instance
        
        # Configura a resposta da geração de conteúdo
        mock_response = MagicMock()
        mock_response.text = MOCK_LLM_RESPONSE
        
        # Configura o mock para retornar a resposta de teste
        mock_instance.generate_content.return_value = mock_response
        
        # Cria uma instância do validador com a chave de teste
        validator = FiscalValidatorAgent(api_key=TEST_API_KEY, cache_enabled=False)
        
        # Armazena o mock para uso nos testes
        validator.model = mock_instance
        
        yield validator

@pytest.mark.asyncio
async def test_validate_document_success(fiscal_validator):
    """Testa a validação de um documento com sucesso."""
    # Configura o mock para retornar uma resposta de sucesso
    mock_response = MagicMock()
    mock_response.text = MOCK_LLM_RESPONSE
    fiscal_validator.model.generate_content.return_value = mock_response
    
    # Chama o método de validação
    result = await fiscal_validator.validate_document(TEST_FISCAL_DATA)
    
    # Verifica se o resultado contém os campos esperados
    assert 'cfop' in result
    assert 'cst_icms' in result
    assert 'cst_pis' in result
    assert 'cst_cofins' in result
    assert 'ncm' in result
    
    # Verifica se os códigos foram validados corretamente
    assert isinstance(result['cfop'], dict)
    assert isinstance(result['cst_icms'], dict)
    assert isinstance(result['cst_pis'], dict)
    assert isinstance(result['cst_cofins'], dict)
    assert isinstance(result['ncm'], dict)
    
    # Verifica se as descrições estão presentes
    assert 'description' in result['cfop']
    assert 'description' in result['cst_icms']
    assert 'description' in result['ncm']

@pytest.mark.asyncio
async def test_validate_document_partial_data(fiscal_validator):
    """Testa a validação com dados parciais."""
    # Dados parciais para teste
    partial_data = {
        'cfop': '5102',
        'ncm': '22030010'
    }
    
    # Configura o mock para retornar uma resposta de sucesso
    mock_response = MagicMock()
    mock_response.text = """
    {
        "cfop": {
            "is_valid": true,
            "normalized_code": "5102",
            "description": "Venda de mercadoria adquirida ou recebida de terceiros",
            "confidence": 0.98
        },
        "ncm": {
            "is_valid": true,
            "normalized_code": "22030010",
            "description": "Cervejas de malte",
            "confidence": 0.99
        }
    }
    """
    fiscal_validator.model.generate_content.return_value = mock_response
    
    # Chama o método de validação
    result = await fiscal_validator.validate_document(partial_data)
    
    # Verifica se apenas os campos fornecidos foram validados
    assert 'cfop' in result
    assert 'ncm' in result
    # Os outros campos podem existir, mas devem ter valores padrão
    if 'cst_icms' in result:
        assert result['cst_icms'].get('is_valid') is not True

@pytest.mark.asyncio
async def test_validate_document_invalid_json(fiscal_validator):
    """Testa o tratamento de respostas inválidas do LLM."""
    # Configura o mock para retornar um JSON inválido
    mock_response = MagicMock()
    mock_response.text = "{invalid json}"
    fiscal_validator.model.generate_content.return_value = mock_response
    
    # Chama o método de validação
    result = await fiscal_validator.validate_document(TEST_FISCAL_DATA)
    
    # Verifica se o resultado indica erro (deve conter chaves, mas com valores vazios ou inválidos)
    assert result, "O resultado não deve ser vazio"
    # Verifica se todos os campos esperados estão presentes
    for field in ['cfop', 'cst_icms', 'cst_pis', 'cst_cofins', 'ncm']:
        assert field in result, f"Campo {field} não encontrado no resultado"
        assert not result[field]['is_valid'], f"O campo {field} não deve ser válido"
        assert 'Erro:' in result[field]['description'], f"A descrição do erro não está correta para o campo {field}"
        assert result[field]['normalized_code'] == '', f"O campo {field} deve ter normalized_code vazio"
        assert result[field]['confidence'] == 0.0, f"O campo {field} deve ter confiança 0.0"

@pytest.mark.asyncio
async def test_validate_document_llm_error(fiscal_validator):
    """Testa o tratamento de erros na chamada ao LLM."""
    # Configura o mock para levantar uma exceção
    fiscal_validator.model.generate_content.side_effect = Exception("Erro no LLM")
    
    # Chama o método de validação
    result = await fiscal_validator.validate_document(TEST_FISCAL_DATA)
    
    # Verifica se o resultado indica erro (deve conter chaves, mas com valores vazios ou inválidos)
    assert result, "O resultado não deve ser vazio"
    # Verifica se todos os campos esperados estão presentes
    for field in ['cfop', 'cst_icms', 'cst_pis', 'cst_cofins', 'ncm']:
        assert field in result, f"Campo {field} não encontrado no resultado"
        assert not result[field]['is_valid'], f"O campo {field} não deve ser válido"
        assert 'Erro:' in result[field]['description'], f"A descrição do erro não está correta para o campo {field}"
        assert result[field]['normalized_code'] == '', f"O campo {field} deve ter normalized_code vazio"
        assert result[field]['confidence'] == 0.0, f"O campo {field} deve ter confiança 0.0"

def test_fiscal_code_validation_model():
    """Testa o modelo Pydantic para validação de códigos fiscais."""
    # Cria uma instância válida
    validation = FiscalCodeValidation(
        is_valid=True,
        normalized_code="5102",
        description="Venda de mercadoria adquirida ou recebida de terceiros",
        confidence=0.98
    )
    
    # Verifica se os valores foram atribuídos corretamente
    assert validation.is_valid is True
    assert validation.normalized_code == "5102"
    assert "Venda" in validation.description
    assert 0 <= validation.confidence <= 1
    
    try:
        # Tenta usar model_dump() (Pydantic v2)
        validation_dict = validation.model_dump()
    except AttributeError:
        # Fallback para dict() (Pydantic v1)
        validation_dict = validation.dict()
    
    assert validation_dict["is_valid"] is True
    assert validation_dict["normalized_code"] == "5102"
    assert "Venda" in validation_dict["description"]
    assert 0 <= validation_dict["confidence"] <= 1

def test_fiscal_document_validation_model():
    """Testa o modelo Pydantic para validação de documentos fiscais."""
    # Cria uma instância válida
    validation = FiscalDocumentValidation(
        cfop=FiscalCodeValidation(
            is_valid=True,
            normalized_code="5102",
            description="Venda de mercadoria adquirida ou recebida de terceiros",
            confidence=0.98
        ),
        cst_icms=FiscalCodeValidation(
            is_valid=True,
            normalized_code="00",
            description="Tributada integralmente",
            confidence=0.99
        ),
        ncm=FiscalCodeValidation(
            is_valid=True,
            normalized_code="22030010",
            description="Cervejas de malte",
            confidence=0.99
        )
    )
    
    # Verifica se os valores foram atribuídos corretamente
    assert validation.cfop.is_valid is True
    assert validation.cst_icms.normalized_code == "00"
    assert validation.ncm is not None
    assert validation.cst_pis is None  # Campo opcional não definido
    
    try:
        # Tenta usar model_dump() (Pydantic v2)
        validation_dict = validation.model_dump()
    except AttributeError:
        # Fallback para dict() (Pydantic v1)
        validation_dict = validation.dict()
    
    assert validation_dict["cfop"]["is_valid"] is True
    assert validation_dict["cst_icms"]["normalized_code"] == "00"
    assert validation_dict["ncm"] is not None
    assert validation_dict.get("cst_pis") is None  # Campo opcional não definido
