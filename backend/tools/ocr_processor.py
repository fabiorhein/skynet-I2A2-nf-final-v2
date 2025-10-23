"""Tesseract OCR helper and PDF->image conversion using pdf2image.

Includes OCR-to-structure mappers:
1. Simple heuristic mapper for MVP (regex-based field extraction)
2. Optional LLM-assisted mapper using Google's generative model
"""
from typing import List, Dict, Any, Optional
import pytesseract
from pdf2image import convert_from_path
from pdf2image.exceptions import PDFInfoNotInstalledError
from PyPDF2 import PdfReader
from PIL import Image
import os
import re
from config import TESSERACT_PATH
from pathlib import Path

# Configure Tesseract path
if TESSERACT_PATH and Path(TESSERACT_PATH).exists():
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

try:
    from .llm_ocr_mapper import LLMOCRMapper
    _llm_mapper = None
except ImportError:
    _llm_mapper = None


def image_to_text(image: Image.Image, lang: str = 'por') -> str:
    return pytesseract.image_to_string(image, lang=lang)


def pdf_to_images(pdf_path: str, dpi: int = 300) -> List[Image.Image]:
    # pdf2image requires poppler on PATH in Windows; user must install poppler
    try:
        images = convert_from_path(pdf_path, dpi=dpi)
        return images
    except (PDFInfoNotInstalledError, FileNotFoundError, OSError):
        # Poppler not installed or executable not found: return empty list to let caller fallback
        return []
    except Exception:
        # Any other error: return empty list and let caller decide
        return []


def pdf_to_text(pdf_path: str, lang: str = 'por') -> str:
    imgs = pdf_to_images(pdf_path)
    if imgs:
        texts = [image_to_text(img, lang=lang) for img in imgs]
        return "\n".join(texts)

    # Fallback: try to extract text using PyPDF2 (works if PDF contains selectable text)
    try:
        reader = PdfReader(pdf_path)
        pages_text = []
        for page in reader.pages:
            try:
                text = page.extract_text() or ''
            except Exception:
                text = ''
            pages_text.append(text)
        return "\n".join(pages_text)
    except Exception:
        # final fallback: empty string
        return ''


def ocr_text_to_document(text: str, use_llm: bool = False) -> Dict[str, Any]:
    """Map OCR text to document structure using heuristics or LLM.
    
    Args:
        text: The OCR text to parse
        use_llm: If True, attempts to use LLM mapper first;
                falls back to heuristics if LLM fails or is not available
    
    Returns:
        Dict with extracted fields (numero, emitente, destinatario, etc.)
    """
    # Try LLM first if requested
    if use_llm:
        global _llm_mapper
        try:
            if _llm_mapper is None:
                _llm_mapper = LLMOCRMapper()
            return _llm_mapper.map_ocr_text(text)
        except Exception as e:
            print(f"LLM mapping failed, falling back to heuristics: {e}")
            # fall through to heuristics
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    doc: Dict[str, Any] = {'raw_text': text, 'emitente': {}, 'destinatario': {}, 'itens': [], 'impostos': {}, 'total': None}

    cnpj_re = re.compile(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})")
    cpf_re = re.compile(r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})")
    money_re = re.compile(r"([\d.,]+)\s*$")
    date_re = re.compile(r"(\d{2}/\d{2}/\d{4})")
    # Match variants: N°, Nº, No, N, Nº:, Numero, num
    num_re = re.compile(r"(?:\bN(?:\s|\s*[º°º\.]\s*)?|no|nº|n°|numero|num)\s*[:\-\.]?\s*(\d{1,10})", re.IGNORECASE)

    for ln in lines:
        # CNPJ
        m = cnpj_re.search(ln)
        if m and not doc['emitente'].get('cnpj'):
            doc['emitente']['cnpj'] = re.sub(r"\D", "", m.group(1))
            continue

        # CPF fallback for destinatario
        m = cpf_re.search(ln)
        if m and not doc['destinatario'].get('cnpj_cpf'):
            doc['destinatario']['cnpj_cpf'] = re.sub(r"\D", "", m.group(1))
            continue

        # document number
        m = num_re.search(ln)
        if m and not doc.get('numero'):
            doc['numero'] = m.group(1)
            continue
        # fallback: line that is 'N 123' or '234' following 'N°' was not captured
        if not doc.get('numero') and ln.strip().isdigit() and len(ln.strip()) <= 10:
            # small heuristic: if line is all digits and not an item total, treat as número
            doc['numero'] = ln.strip()
            continue

        # date
        m = date_re.search(ln)
        if m and not doc.get('data_emissao'):
            doc['data_emissao'] = m.group(1)
            continue

        # totals (look for 'TOTAL' or 'Valor Total')
        if 'total' in ln.lower() or 'valor' in ln.lower():
            m = money_re.search(ln)
            if m:
                candidate = m.group(1).replace('.', '').replace(',', '.')
                try:
                    doc['total'] = float(candidate)
                except Exception:
                    pass
                continue

        # item-like line heuristic: description qty unit_value total
        # e.g. '1x Parafuso 2,00 4,00' or 'Parafuso 2 2,00 4,00'
        parts = ln.split()
        if len(parts) >= 3:
            m = money_re.search(parts[-1])
            m2 = money_re.search(parts[-2])
            if m and m2:
                # assume last is total, second-last is unit or qty
                descricao = ' '.join(parts[:-2])
                try:
                    valor_total = float(parts[-1].replace('.', '').replace(',', '.'))
                except Exception:
                    valor_total = None
                try:
                    quantidade = float(parts[-2].replace(',', '.'))
                except Exception:
                    quantidade = None
                doc['itens'].append({'descricao': descricao, 'quantidade': quantidade, 'valor_unitario': None, 'valor_total': valor_total})

    return doc

