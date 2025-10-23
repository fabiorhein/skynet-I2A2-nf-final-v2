"""LLM-assisted OCR text to structured data mapping.

Uses Google's Gemini API directly to improve OCR text parsing.
Requires GOOGLE_API_KEY in environment or secrets.
"""
from typing import Dict, Any, Optional
import json
import google.generativeai as genai
from config import GOOGLE_API_KEY
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Template for Gemini prompt
EXTRACTION_PROMPT = """Você é um assistente especializado em extrair dados estruturados de textos OCR de notas fiscais.
Recebeu o seguinte texto OCR de uma nota fiscal:

{text}

Por favor extraia os seguintes campos no formato JSON:
- numero: número do documento fiscal
- emitente: objeto com cnpj e nome
- destinatario: objeto com cnpj e nome (se presente)
- data_emissao: data de emissão no formato ISO
- valor_total: valor total do documento
- itens: lista de itens com campos:
  - descricao
  - quantidade
  - valor_unitario
  - valor_total

Responda APENAS com o JSON, sem explicações. Use null para campos não encontrados.
Mantenha números como números (não strings).
"""


class LLMOCRMapper:
    """Maps OCR text to structured fields using LLM."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with optional API key (falls back to config)."""
        self.api_key = api_key or GOOGLE_API_KEY
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is required")
            
        # Configure Gemini
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-pro')
        except Exception as e:
            logger.error(f"Failed to initialize Gemini model: {e}")
            raise
        
    def map_ocr_text(self, text: str) -> Dict[str, Any]:
        """Extract structured fields from OCR text using Gemini."""
        try:
            # Prepare truncated text (limit length)
            truncated = text[:8000]
            
            # Format prompt
            prompt = EXTRACTION_PROMPT.format(text=truncated)
            
            # Generate response
            response = self.model.generate_content(prompt)
            
            # Get text from response
            if not response.text:
                raise ValueError("Empty response from Gemini")
            
            # Parse JSON response
            try:
                parsed = json.loads(response.text)
                return parsed
                    
            except json.JSONDecodeError as je:
                logger.error(f"Failed to parse Gemini response as JSON: {je}")
                logger.error(f"Raw response: {response.text}")
                raise
                
        except Exception as e:
            # Log error and return empty structure
            logger.error(f"Gemini extraction failed: {e}")
            return {
                "numero": None,
                "emitente": {"cnpj": None, "nome": None},
                "destinatario": {"cnpj": None, "nome": None},
                "data_emissao": None,
                "valor_total": None,
                "itens": [],
                "error": str(e)
            }