import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from backend.tools.ocr_processor import ocr_text_to_document
from backend import storage
import os


def test_ocr_mapping_basic():
    text = """
    EMPRESA X
    CNPJ: 12.345.678/0001-95
    N° 234
    Data: 10/10/2025
    Parafuso 2 2,00 4,00
    Total: 4,00
    """
    doc = ocr_text_to_document(text)
    assert doc['emitente']['cnpj'] == '12345678000195'
    assert doc['numero'] == '234'
    assert abs(doc['total'] - 4.0) < 1e-6


def test_storage_write_read(tmp_path):
    # temporarily point storage file to tmp location
    from backend import storage as stmod
    orig = stmod.STORAGE_PATH
    try:
        stmod.STORAGE_PATH = tmp_path / 'docs.json'
        stmod.save_document({'file': 'a.xml', 'parsed': {'numero': '1'}})
        arr = stmod.load_documents()
        assert len(arr) == 1
        assert arr[0]['file'] == 'a.xml'
    finally:
        stmod.STORAGE_PATH = orig
