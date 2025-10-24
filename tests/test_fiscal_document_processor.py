"""
Testes para o processador de documentos fiscais.
"""
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Adiciona o diretório raiz ao path para importar os módulos
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.tools.fiscal_document_processor import FiscalDocumentProcessor

# Caminho para a pasta de fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Verifica se o Tesseract está instalado
pytesseract_available = True
try:
    import pytesseract
    # Tenta encontrar o Tesseract no PATH
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        pytesseract_available = False
except ImportError:
    pytesseract_available = False

# Pula os testes se o Tesseract não estiver disponível
pytestmark = pytest.mark.skipif(
    not pytesseract_available,
    reason="Tesseract OCR não está instalado ou não está no PATH"
)

class TestFiscalDocumentProcessor:
    """Testes para a classe FiscalDocumentProcessor."""
    
    @classmethod
    def setup_class(cls):
        """Configuração inicial para os testes."""
        cls.processor = FiscalDocumentProcessor()
        
        # Cria diretório de saída se não existir
        cls.output_dir = Path("test_output")
        cls.output_dir.mkdir(exist_ok=True)
    
    def test_is_supported_file(self):
        """Testa a verificação de formatos suportados."""
        assert self.processor.is_supported_file("teste.pdf") is True
        assert self.processor.is_supported_file("teste.PDF") is True
        assert self.processor.is_supported_file("teste.jpg") is True
        assert self.processor.is_supported_file("teste.png") is True
        assert self.processor.is_supported_file("teste.tiff") is True
        assert self.processor.is_supported_file("teste.bmp") is True
        assert self.processor.is_supported_file("teste.txt") is False
        assert self.processor.is_supported_file("teste.doc") is False
    
    def test_extract_text_from_image(self, tmp_path):
        """Testa a extração de texto de uma imagem."""
        # Cria uma imagem de teste com texto
        from PIL import Image, ImageDraw, ImageFont
        
        # Cria uma imagem em branco
        img = Image.new('RGB', (800, 200), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        
        # Tenta carregar uma fonte, usa a padrão se não conseguir
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except IOError:
            font = ImageFont.load_default()
        
        # Adiciona texto à imagem
        d.text((10, 10), "NOTA FISCAL ELETRÔNICA", fill=(0, 0, 0), font=font)
        d.text((10, 40), "Nº 12345", fill=(0, 0, 0), font=font)
        d.text((10, 70), "Emitente: LOJA TESTE LTDA", fill=(0, 0, 0), font=font)
        d.text((10, 100), "CNPJ: 12.345.678/0001-90", fill=(0, 0, 0), font=font)
        d.text((10, 130), "Valor Total: R$ 1.234,56", fill=(0, 0, 0), font=font)
        
        # Salva a imagem temporariamente
        img_path = tmp_path / "test_image.png"
        img.save(img_path)
        
        # Extrai o texto
        result = self.processor.extract_text(img_path)
        
        # Verifica o resultado
        assert result['success'] is True
        assert "NOTA FISCAL ELETRÔNICA" in result['text']
        assert "12345" in result['text']
        assert "LOJA TESTE" in result['text']
        assert "12.345.678/0001-90" in result['text']
        assert "1.234,56" in result['text']
    
    def test_extract_text_from_pdf(self, tmp_path):
        """Testa a extração de texto de um PDF."""
        # Cria um PDF de teste com texto
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        
        # Cria um PDF com texto
        pdf_path = tmp_path / "test_pdf.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=letter)
        width, height = letter
        
        # Adiciona texto ao PDF
        c.setFont("Helvetica", 12)
        c.drawString(100, height - 100, "NOTA FISCAL ELETRÔNICA")
        c.drawString(100, height - 130, "Nº 67890")
        c.drawString(100, height - 160, "Emitente: EMPRESA TESTE LTDA")
        c.drawString(100, height - 190, "CNPJ: 98.765.432/0001-21")
        c.drawString(100, height - 220, "Valor Total: R$ 5.678,90")
        
        # Adiciona uma segunda página
        c.showPage()
        c.setFont("Helvetica", 12)
        c.drawString(100, height - 100, "Continuação da Nota Fiscal")
        c.drawString(100, height - 130, "Página 2")
        
        c.save()
        
        # Extrai o texto
        result = self.processor.extract_text(pdf_path)
        
        # Verifica o resultado
        assert result['success'] is True
        assert "NOTA FISCAL ELETRÔNICA" in result['text']
        assert "67890" in result['text']
        assert "EMPRESA TESTE" in result['text']
        assert "98.765.432/0001-21" in result['text']
        assert "5.678,90" in result['text']
        assert len(result['pages']) >= 1  # Deve ter pelo menos uma página
    
    def test_identify_document_type(self):
        """Testa a identificação do tipo de documento."""
        # Teste para NFe
        nfe_text = """
        NOTA FISCAL ELETRÔNICA
        Nº 12345
        EMITENTE: LOJA TESTE LTDA
        CNPJ: 12.345.678/0001-90
        """
        assert self.processor.identify_document_type(nfe_text) == 'nfe'
        
        # Teste para NFCe
        nfce_text = """
        NFC-e
        Nº 12345
        EMITENTE: LOJA TESTE LTDA
        CNPJ: 12.345.678/0001-90
        """
        assert self.processor.identify_document_type(nfce_text) == 'nfce'
        
        # Teste para CTe
        cte_text = """
        CONHECIMENTO DE TRANSPORTE ELETRÔNICO
        Nº 12345
        EMITENTE: TRANSPORTADORA TESTE LTDA
        CNPJ: 12.345.678/0001-90
        """
        assert self.processor.identify_document_type(cte_text) == 'cte'
        
        # Teste para MDFe
        mdfe_text = """
        MANIFESTO DE DOCUMENTOS FISCAIS ELETRÔNICOS
        Nº 12345
        EMITENTE: TRANSPORTADORA TESTE LTDA
        CNPJ: 12.345.678/0001-90
        """
        assert self.processor.identify_document_type(mdfe_text) == 'mdfe'
        
        # Teste para tipo desconhecido
        unknown_text = "Documento qualquer sem identificação clara"
        assert self.processor.identify_document_type(unknown_text) == 'unknown'
    
    def test_extract_with_heuristics(self):
        """Testa a extração de dados estruturados usando heurísticas."""
        # Texto de exemplo de uma nota fiscal
        text = """
        NOTA FISCAL ELETRÔNICA
        Nº 12345
        
        EMITENTE:
        LOJA TESTE LTDA
        CNPJ: 12.345.678/0001-90
        Inscrição Estadual: 123.456.789.111
        
        DESTINATÁRIO:
        CONSUMIDOR
        CPF: 123.456.789-00
        
        ITENS DA NOTA:
        CÓDIGO  DESCRIÇÃO               QTD  UN  VL UNIT   VL TOTAL
        001      PRODUTO TESTE 1         2    UN  50,00     100,00
        002      PRODUTO TESTE 2         1    UN  75,50     75,50
        
        VALOR TOTAL R$ 175,50
        ICMS: R$ 31,59
        PIS: R$ 2,84
        COFINS: R$ 13,10
        
        Chave de Acesso: 35210123456789012345678901234567890123456789
        Protocolo de Autorização: 123456789012345
        """
        
        # Extrai os dados estruturados
        doc = self.processor._extract_with_heuristics(text, 'nfe')
        
        # Verifica os campos básicos
        assert doc['success'] is True
        assert doc['document_type'] == 'nfe'
        assert doc['numero'] == '12345'
        assert doc['valor_total'] == 175.50
        
        # Verifica o emitente
        assert doc['emitente']['cnpj'] == '12.345.678/0001-90'
        assert doc['emitente']['inscricao_estadual'] == '123.456.789.111'
        
        # Verifica o destinatário
        assert doc['destinatario']['cpf'] == '123.456.789-00'
        
        # Verifica os itens
        assert len(doc['itens']) == 2
        assert doc['itens'][0]['descricao'] == 'PRODUTO TESTE 1'
        assert doc['itens'][0]['quantidade'] == 2.0
        assert doc['itens'][0]['valor_unitario'] == 50.0
        assert doc['itens'][0]['valor_total'] == 100.0
        
        # Verifica os impostos
        assert 'icms' in doc['impostos']
        assert doc['impostos']['icms'] == 31.59
        assert 'pis' in doc['impostos']
        assert doc['impostos']['pis'] == 2.84
        assert 'cofins' in doc['impostos']
        assert doc['impostos']['cofins'] == 13.10
        
        # Verifica a chave de acesso e protocolo
        assert doc['chave_acesso'] == '35210123456789012345678901234567890123456789'
        assert doc['protocolo_autorizacao'] == '123456789012345'
    
    @patch('backend.tools.fiscal_document_processor.LLMOCRMapper')
    def test_process_document_with_llm(self, mock_llm_mapper):
        """Testa o processamento de um documento com LLM."""
        # Configura o mock do LLM
        mock_mapper = MagicMock()
        mock_mapper.available = True
        mock_mapper.map_ocr_text.return_value = {
            'success': True,
            'document_type': 'nfe',
            'numero': '12345',
            'data_emissao': '01/01/2023',
            'valor_total': 175.50,
            'emitente': {
                'razao_social': 'LOJA TESTE LTDA',
                'cnpj': '12.345.678/0001-90',
                'inscricao_estadual': '123.456.789.111'
            },
            'destinatario': {
                'razao_social': 'CONSUMIDOR',
                'cpf': '123.456.789-00'
            },
            'itens': [
                {
                    'descricao': 'PRODUTO TESTE 1',
                    'quantidade': 2.0,
                    'valor_unitario': 50.0,
                    'valor_total': 100.0
                },
                {
                    'descricao': 'PRODUTO TESTE 2',
                    'quantidade': 1.0,
                    'valor_unitario': 75.5,
                    'valor_total': 75.5
                }
            ],
            'impostos': {
                'icms': 31.59,
                'pis': 2.84,
                'cofins': 13.10
            },
            'chave_acesso': '35210123456789012345678901234567890123456789',
            'protocolo_autorizacao': '123456789012345'
        }
        mock_llm_mapper.return_value = mock_mapper
        
        # Cria um arquivo de teste temporário
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'%PDF-1.4\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n3 0 obj\n<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>/MediaBox[0 0 612 792]/Contents 5 0 R>>\nendobj\n4 0 obj\n<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>\nendobj\n5 0 obj\n<</Length 44>>\nstream\nBT\n/F1 24 Tf\n100 700 Td\n(Hello, World!) Tj\nET\nendstream\nendobj\nxref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \n0000000109 00000 n \n0000000202 00000 n \n0000000149 00000 n \ntrailer\n<</Size 6/Root 1 0 R>>\nstartxref\n307\n%%EOF')
            file_path = f.name
        
        try:
            # Processa o documento
            result = self.processor.process_document(file_path)
            
            # Verifica se o LLM foi chamado
            mock_mapper.map_ocr_text.assert_called_once()
            
            # Verifica o resultado
            assert result['success'] is True
            assert result['document_type'] == 'nfe'
            assert result['numero'] == '12345'
            assert result['valor_total'] == 175.50
            assert result['emitente']['razao_social'] == 'LOJA TESTE LTDA'
            assert len(result['itens']) == 2
            
        finally:
            # Remove o arquivo temporário
            try:
                os.unlink(file_path)
            except:
                pass

if __name__ == "__main__":
    pytest.main(["-v", "test_fiscal_document_processor.py"])
