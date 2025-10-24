from backend.tools.llm_ocr_mapper import LLMOCRMapper


def test_llm_mapper_heuristic_fallback():
    sample = """
    NF-e
    CNPJ 12.345.678/0001-95
    Data 10/10/2020
    Item Agua 10 1,50 15,00
    TOTAL 15,00
    """
    mapper = LLMOCRMapper()
    result = mapper.map_ocr_text(sample)
    assert isinstance(result, dict)
    assert result.get('raw_text') == sample
    # heuristic should at least locate cnpj or total (one of them)
    assert 'emitente' in result and isinstance(result['emitente'], dict)
