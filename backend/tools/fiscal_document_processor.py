"""
Processador de documentos fiscais com suporte a PDF e imagens usando OCR.

Este módulo fornece uma interface unificada para extrair texto de documentos fiscais
e mapeá-los para um formato estruturado, independentemente do formato de entrada.
"""
import os
import io
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Tuple
import mimetypes

import pytesseract
from pdf2image import convert_from_bytes, convert_from_path
from PIL import Image, UnidentifiedImageError

# Importa o config para acessar as configurações do Tesseract
from config import TESSERACT_PATH

# Configura o logger
logger = logging.getLogger(__name__)

# Configura o caminho do Tesseract, se disponível
if TESSERACT_PATH and Path(TESSERACT_PATH).exists():
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

class FiscalDocumentProcessor:
    """
    Processador de documentos fiscais que suporta PDF e imagens.
    
    Esta classe fornece métodos para extrair texto de documentos fiscais em vários formatos
    e mapear o texto extraído para um formato estruturado.
    """
    
    def __init__(self, language: str = 'por'):
        """
        Inicializa o processador de documentos fiscais.
        
        Args:
            language: Idioma a ser usado pelo OCR (padrão: 'por' para português)
        """
        self.language = language
        self.supported_formats = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp']
        
    def is_supported_file(self, file_path: Union[str, Path]) -> bool:
        """
        Verifica se o arquivo é de um tipo suportado.
        
        Args:
            file_path: Caminho para o arquivo
            
        Returns:
            bool: True se o arquivo for suportado, False caso contrário
        """
        file_path = Path(file_path)
        return file_path.suffix.lower() in self.supported_formats
    
    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Pré-processa a imagem para melhorar a qualidade do OCR.
        
        Args:
            image: Imagem a ser pré-processada
            
        Returns:
            Imagem pré-processada
        """
        # Converte para escala de cinza
        if image.mode != 'L':
            image = image.convert('L')
        
        # Aumenta o contraste
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)
        
        # Redimensiona se a imagem for muito pequena
        min_size = 1000
        if image.size[0] < min_size or image.size[1] < min_size:
            ratio = min_size / min(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        return image
    
    def _extract_text_from_image(self, image: Image.Image) -> str:
        """
        Extrai texto de uma imagem usando Tesseract OCR.
        
        Args:
            image: Imagem da qual extrair o texto
            
        Returns:
            Texto extraído da imagem
        """
        try:
            # Aplica pré-processamento
            processed_img = self._preprocess_image(image)
            
            # Configura o OCR para melhor precisão
            custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'
            
            # Executa OCR com configurações otimizadas
            text = pytesseract.image_to_string(
                processed_img,
                lang=self.language,
                config=custom_config
            )
            
            return text.strip()
        except Exception as e:
            logger.error(f"Erro ao extrair texto da imagem: {str(e)}")
            raise
    
    def _extract_text_from_pdf(self, pdf_path: Union[str, Path], dpi: int = 300) -> Dict[int, str]:
        """
        Extrai texto de um arquivo PDF, página por página.
        
        Args:
            pdf_path: Caminho para o arquivo PDF
            dpi: Resolução para conversão do PDF (padrão: 300)
            
        Returns:
            Dicionário com número da página e texto extraído
        """
        try:
            # Tenta extrair texto diretamente do PDF primeiro (se for um PDF com texto)
            try:
                from pypdf import PdfReader
                reader = PdfReader(pdf_path)
                if reader.pages and len(reader.pages[0].extract_text() or '') > 50:  # Se houver texto significativo
                    return {i+1: page.extract_text() or '' for i, page in enumerate(reader.pages)}
            except Exception as e:
                logger.debug(f"Não foi possível extrair texto diretamente do PDF, usando OCR: {str(e)}")
            
            # Se não conseguir extrair texto diretamente, usa OCR
            images = convert_from_path(pdf_path, dpi=dpi)
            results = {}
            
            for i, image in enumerate(images, 1):
                text = self._extract_text_from_image(image)
                results[i] = text
                
            return results
        except Exception as e:
            logger.error(f"Erro ao processar PDF {pdf_path}: {str(e)}")
            raise
    
    def extract_text(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Extrai texto de um arquivo (PDF ou imagem).
        
        Args:
            file_path: Caminho para o arquivo
            
        Returns:
            Dicionário com metadados e texto extraído
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
            
        if not self.is_supported_file(file_path):
            raise ValueError(f"Formato de arquivo não suportado: {file_path.suffix}")
        
        try:
            result = {
                'file_name': file_path.name,
                'file_type': file_path.suffix.lower(),
                'file_size': file_path.stat().st_size,
                'language': self.language,
                'success': False,
                'error': None,
                'pages': {},
                'text': ''
            }
            
            if file_path.suffix.lower() == '.pdf':
                # Processa PDF
                result['pages'] = self._extract_text_from_pdf(file_path)
                result['text'] = '\n\n'.join(
                    f"--- PÁGINA {page} ---\n{text}" 
                    for page, text in result['pages'].items()
                )
            else:
                # Processa imagem
                try:
                    with Image.open(file_path) as img:
                        text = self._extract_text_from_image(img)
                        result['pages'][1] = text
                        result['text'] = text
                except UnidentifiedImageError:
                    raise ValueError(f"Não foi possível identificar a imagem: {file_path}")
            
            result['success'] = True
            return result
            
        except Exception as e:
            error_msg = f"Erro ao processar arquivo {file_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'file_name': file_path.name,
                'file_type': file_path.suffix.lower(),
                'file_size': file_path.stat().st_size,
                'success': False,
                'error': str(e),
                'pages': {},
                'text': ''
            }
    
    def process_document(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Processa um documento fiscal e retorna os dados estruturados.
        
        Args:
            file_path: Caminho para o documento
            
        Returns:
            Dicionário com os dados estruturados do documento
        """
        # Extrai o texto do documento
        extraction_result = self.extract_text(file_path)
        
        if not extraction_result['success']:
            return {
                'success': False,
                'error': extraction_result.get('error', 'Erro desconhecido ao extrair texto'),
                'raw_text': '',
                'document_type': 'unknown'
            }
        
        # Tenta identificar o tipo de documento
        document_type = self.identify_document_type(extraction_result['text'])
        
        # Extrai os campos estruturados
        if document_type == 'xml':
            # Se for XML, usa o parser de XML existente
            from .xml_parser import parse_xml_file
            try:
                parsed_data = parse_xml_file(str(file_path))
                parsed_data['document_type'] = 'xml'
                parsed_data['success'] = True
                return parsed_data
            except Exception as e:
                return {
                    'success': False,
                    'error': f"Erro ao processar XML: {str(e)}",
                    'raw_text': extraction_result['text'],
                    'document_type': 'xml'
                }
        else:
            # Para documentos baseados em imagem/PDF, usa o LLM para extrair os campos
            return self._extract_structured_data(extraction_result['text'], document_type)
    
    def identify_document_type(self, text: str) -> str:
        """
        Identifica o tipo de documento com base no texto extraído.
        
        Args:
            text: Texto extraído do documento
            
        Returns:
            String com o tipo de documento ('nfe', 'nfce', 'cte', 'mdfe' ou 'unknown')
        """
        text_lower = text.lower()
        
        # Verifica se é um XML
        if any(tag in text_lower for tag in ['<nfe', '<nfce', '<cte', '<mdfe']):
            if '<nfe' in text_lower:
                return 'nfe'
            elif '<nfce' in text_lower:
                return 'nfce'
            elif '<cte' in text_lower:
                return 'cte'
            elif '<mdfe' in text_lower:
                return 'mdfe'
        
        # Tenta identificar por padrões de texto
        if any(term in text_lower for term in ['nota fiscal de consumidor eletrônica', 'nfce']):
            return 'nfce'
        elif any(term in text_lower for term in ['nota fiscal eletrônica', 'nfe']):
            return 'nfe'
        elif any(term in text_lower for term in ['conhecimento de transporte eletrônico', 'cte']):
            return 'cte'
        elif any(term in text_lower for term in ['manifesto de documentos fiscais', 'mdfe']):
            return 'mdfe'
        
        return 'unknown'
    
    def _extract_structured_data(self, text: str, document_type: str) -> Dict[str, Any]:
        """
        Extrai dados estruturados do texto usando o LLM ou heurísticas.
        
        Args:
            text: Texto extraído do documento
            document_type: Tipo do documento ('nfe', 'nfce', 'cte', 'mdfe' ou 'unknown')
            
        Returns:
            Dicionário com os dados estruturados
        """
        # Tenta usar o LLM se disponível
        try:
            from .llm_ocr_mapper import LLMOCRMapper
            mapper = LLMOCRMapper()
            if mapper.available:
                result = mapper.map_ocr_text(text)
                result['document_type'] = document_type
                result['success'] = True
                return result
        except Exception as e:
            logger.warning(f"Erro ao usar LLM para extração de dados: {str(e)}")
        
        # Se o LLM não estiver disponível, usa heurísticas
        return self._extract_with_heuristics(text, document_type)
    
    def _extract_with_heuristics(self, text: str, document_type: str) -> Dict[str, Any]:
        """
        Extrai dados estruturados usando heurísticas baseadas em expressões regulares.
        
        Args:
            text: Texto extraído do documento
            document_type: Tipo do documento ('nfe', 'nfce', 'cte', 'mdfe' ou 'unknown')
            
        Returns:
            Dicionário com os dados estruturados
        """
        import re
        
        # Inicializa a estrutura do documento
        doc = {
            'success': True,
            'document_type': document_type,
            'raw_text': text,
            'numero': None,
            'data_emissao': None,
            'valor_total': None,
            'emitente': {},
            'destinatario': {},
            'itens': [],
            'impostos': {},
            'chave_acesso': None,
            'protocolo_autorizacao': None
        }
        
        # Expressões regulares para extração de campos
        patterns = {
            'cnpj': re.compile(r'CNPJ[\s:]*([\d./-]+)', re.IGNORECASE),
            'cpf': re.compile(r'CPF[\s:]*([\d.-]+)', re.IGNORECASE),
            'ie': re.compile(r'(?:I[.\s]*E\.?|Inscri[çc][aã]o\s*Estadual)[\s:]*([^\s]+)', re.IGNORECASE),
            'data_emissao': re.compile(r'(?:Data\s*de\s*Emiss[ãa]o|Emiss[ãa]o)[\s:]*([\d/]+)', re.IGNORECASE),
            'valor_total': re.compile(r'(?:Valor\s*Total\s*R?\$|Total\s*da\s*Nota)[\s:]*([\d.,]+)', re.IGNORECASE),
            'numero': re.compile(r'(?:N[º°]+\s*da\s*Nota|Nota\s*Fiscal\s*N?[º°\s]*)(\d+)', re.IGNORECASE),
            'chave_acesso': re.compile(r'([0-9]{44})'),
            'protocolo': re.compile(r'Protocolo[\s:]*([0-9]+)', re.IGNORECASE),
            'razao_social': re.compile(r'(?:Raz[ãa]o\s*Social|Nome\s*do\s*Emitente)[\s:]*([^\n]+)', re.IGNORECASE),
            'nome_destinatario': re.compile(r'(?:Destinat[áa]rio|Nome\s*do\s*Destinat[áa]rio)[\s:]*([^\n]+)', re.IGNORECASE),
        }
        
        # Extrai campos básicos
        for field, pattern in patterns.items():
            match = pattern.search(text)
            if match:
                if field == 'cnpj' and not doc['emitente'].get('cnpj'):
                    doc['emitente']['cnpj'] = match.group(1).strip()
                elif field == 'cpf' and not doc['destinatario'].get('cpf'):
                    doc['destinatario']['cpf'] = match.group(1).strip()
                elif field == 'ie' and not doc['emitente'].get('inscricao_estadual'):
                    doc['emitente']['inscricao_estadual'] = match.group(1).strip()
                elif field == 'data_emissao' and not doc.get('data_emissao'):
                    doc['data_emissao'] = match.group(1).strip()
                elif field == 'valor_total' and not doc.get('valor_total'):
                    try:
                        doc['valor_total'] = float(match.group(1).replace('.', '').replace(',', '.'))
                    except (ValueError, TypeError):
                        pass
                elif field == 'numero' and not doc.get('numero'):
                    doc['numero'] = match.group(1).strip()
                elif field == 'chave_acesso' and not doc.get('chave_acesso'):
                    doc['chave_acesso'] = match.group(1).strip()
                elif field == 'protocolo' and not doc.get('protocolo_autorizacao'):
                    doc['protocolo_autorizacao'] = match.group(1).strip()
                elif field == 'razao_social' and not doc['emitente'].get('razao_social'):
                    doc['emitente']['razao_social'] = match.group(1).strip()
                elif field == 'nome_destinatario' and not doc['destinatario'].get('razao_social'):
                    doc['destinatario']['razao_social'] = match.group(1).strip()
        
        # Tenta extrair itens (seção de produtos/serviços)
        self._extract_items(text, doc)
        
        # Tenta extrair impostos
        self._extract_taxes(text, doc)
        
        return doc
    
    def _extract_items(self, text: str, doc: Dict[str, Any]) -> None:
        """
        Extrai itens do documento usando heurísticas.
        
        Args:
            text: Texto extraído do documento
            doc: Dicionário com os dados do documento (será atualizado com os itens)
        """
        import re
        
        # Tenta encontrar a seção de itens
        items_section = re.search(
            r'(?i)(?:Itens\s*da\s*Nota|Produtos\s*e\s*Servi[çc]os|Discrimina[çc][aã]o\s*dos\s*Produtos)(.*?)(?=Total\s*R?\$|$)',
            text,
            re.DOTALL
        )
        
        if not items_section:
            return
            
        items_text = items_section.group(1)
        
        # Padrão para linhas de itens (simplificado)
        item_pattern = re.compile(
            r'(\d+)\s+'  # Código (opcional)
            r'([\w\s.,-]+?)'  # Descrição
            r'\s+(\d+[.,]?\d*)\s+'  # Quantidade
            r'([A-Z]{2,3})\s+'  # Unidade (opcional)
            r'([R$]?\s*\d{1,3}(?:\.\d{3})*,\d{2})\s+'  # Valor unitário
            r'([R$]?\s*\d{1,3}(?:\.\d{3})*,\d{2})'  # Valor total
        )
        
        # Tenta encontrar itens usando o padrão
        for match in item_pattern.finditer(items_text):
            try:
                item = {
                    'codigo': match.group(1).strip() if match.group(1) else None,
                    'descricao': match.group(2).strip(),
                    'quantidade': float(match.group(3).replace('.', '').replace(',', '.')),
                    'unidade': match.group(4).strip() if len(match.groups()) > 3 and match.group(4) else 'UN',
                    'valor_unitario': float(match.group(5).replace('R$', '').replace('.', '').replace(',', '.')),
                    'valor_total': float(match.group(6).replace('R$', '').replace('.', '').replace(',', '.'))
                }
                doc['itens'].append(item)
            except (ValueError, IndexError):
                continue
    
    def _extract_taxes(self, text: str, doc: Dict[str, Any]) -> None:
        """
        Extrai informações de impostos do documento.
        
        Args:
            text: Texto extraído do documento
            doc: Dicionário com os dados do documento (será atualizado com os impostos)
        """
        import re
        
        # Padrões para impostos comuns
        tax_patterns = {
            'icms': r'(?:ICMS|Valor\s+ICMS)[\s:]*R?\$?\s*([\d.,]+)',
            'pis': r'(?:PIS|Valor\s+PIS)[\s:]*R?\$?\s*([\d.,]+)',
            'cofins': r'(?:COFINS|Valor\s+COFINS)[\s:]*R?\$?\s*([\d.,]+)',
            'ipi': r'(?:IPI|Valor\s+IPI)[\s:]*R?\$?\s*([\d.,]+)',
        }
        
        for tax, pattern in tax_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace('.', '').replace(',', '.'))
                    doc['impostos'][tax] = value
                except (ValueError, AttributeError):
                    continue


def process_fiscal_document(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Função de conveniência para processar um documento fiscal.
    
    Args:
        file_path: Caminho para o arquivo a ser processado
        
    Returns:
        Dicionário com os dados estruturados do documento
    """
    processor = FiscalDocumentProcessor()
    return processor.process_document(file_path)


if __name__ == "__main__":
    import sys
    import json
    
    # Configura o logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) < 2:
        print("Uso: python -m backend.tools.fiscal_document_processor <caminho_do_arquivo>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Erro: Arquivo não encontrado: {file_path}")
        sys.exit(1)
    
    try:
        processor = FiscalDocumentProcessor()
        result = processor.process_document(file_path)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Erro ao processar o documento: {str(e)}", file=sys.stderr)
        sys.exit(1)
