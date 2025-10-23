from ..tools import xml_parser, ocr_processor
from ..models.document import FiscalDocument, Emitente, Destinatario, Item, Impostos
from typing import Dict, Any
import os


def extract_from_file(path: str) -> Dict[str, Any]:
    _, ext = os.path.splitext(path.lower())
    if ext == '.xml':
        parsed = xml_parser.parse_xml_file(path)
        # Ensure consistent structure with raw_text
        if isinstance(parsed, dict):
            raw_text = parsed.get('raw_text', '')
            if isinstance(raw_text, str):
                parsed['document_type'] = 'NFe'  # Set default type for XML
                return parsed
        # Return error structure if parsing failed
        return {'error': 'xml_parse_error', 'message': 'Failed to parse XML', 'raw_text': '', 'document_type': 'unknown'}
    elif ext in ['.pdf']:
        try:
            text = ocr_processor.pdf_to_text(path)
            if not text:
                return {'error': 'empty_ocr', 'message': 'PDF could not be converted to images (Poppler missing) and no selectable text found.'}
            return {'raw_text': text, 'document_type': 'unknown'}
        except Exception as e:
            return {'error': 'ocr_failed', 'message': str(e)}
    else:
        # try to read as image
        try:
            from PIL import Image
            img = Image.open(path)
            text = ocr_processor.image_to_text(img)
            return {'raw_text': text, 'document_type': 'unknown'}
        except Exception:
            return {'error': 'unsupported file type'}
