"""
Document Agent - Processa documentos fiscais e extrai informações estruturadas.

Este módulo fornece um agente que pode processar diferentes tipos de documentos fiscais,
extraindo informações estruturadas e integrando-se com o restante do sistema.
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
import shutil
from datetime import datetime

from ..tools.fiscal_document_processor import FiscalDocumentProcessor
from ..tools.ocr_processor import ocr_text_to_document
from ..tools.llm_ocr_mapper import LLMOCRMapper
from ..models.document import Document, DocumentType, DocumentStatus

# Configura o logger
logger = logging.getLogger(__name__)

class DocumentAgent:
    """
    Agente responsável por processar documentos fiscais e extrair informações estruturadas.
    
    Este agente lida com diferentes tipos de documentos (NFe, NFCe, CTe, etc.)
    e extrai informações estruturadas usando OCR e processamento de texto.
    """
    
    def __init__(self, upload_dir: str = "uploads", processed_dir: str = "processed"):
        """
        Inicializa o DocumentAgent.
        
        Args:
            upload_dir: Diretório onde os arquivos enviados são armazenados temporariamente
            processed_dir: Diretório onde os arquivos processados são armazenados
        """
        self.upload_dir = Path(upload_dir)
        self.processed_dir = Path(processed_dir)
        self.processor = FiscalDocumentProcessor()
        
        # Cria os diretórios se não existirem
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
    
    def process_uploaded_file(self, file_path: Union[str, Path], move_after_process: bool = True) -> Dict[str, Any]:
        """
        Processa um arquivo enviado e extrai informações estruturadas.
        
        Args:
            file_path: Caminho para o arquivo a ser processado
            move_after_process: Se True, move o arquivo para o diretório de processados após o processamento
            
        Returns:
            Dicionário com os resultados do processamento
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
        
        logger.info(f"Processando arquivo: {file_path}")
        
        try:
            # Processa o documento
            result = self.processor.process_document(file_path)
            
            # Se o processamento foi bem-sucedido, move o arquivo para o diretório de processados
            if result.get('success') and move_after_process:
                self._move_to_processed(file_path)
            
            return result
            
        except Exception as e:
            logger.error(f"Erro ao processar o arquivo {file_path}: {str(e)}", exc_info=True)
            raise
    
    def _move_to_processed(self, file_path: Path) -> Path:
        """
        Move um arquivo processado para o diretório de processados.
        
        Args:
            file_path: Caminho para o arquivo a ser movido
            
        Returns:
            Novo caminho do arquivo
        """
        # Cria um nome único para o arquivo processado
        timestamp = int(datetime.now().timestamp())
        new_filename = f"{timestamp}_{file_path.name}"
        new_path = self.processed_dir / new_filename
        
        # Move o arquivo
        shutil.move(str(file_path), str(new_path))
        
        return new_path
    
    def save_document_to_db(self, result: Dict[str, Any], user_id: Optional[str] = None) -> Document:
        """
        Salva os resultados do processamento no banco de dados.
        
        Args:
            result: Resultado do processamento do documento
            user_id: ID do usuário que enviou o documento (opcional)
            
        Returns:
            Instância do documento salvo
        """
        # Mapeia o tipo de documento para o enum DocumentType
        doc_type_map = {
            'nfe': DocumentType.NFE,
            'nfce': DocumentType.NFCE,
            'cte': DocumentType.CTE,
            'mdfe': DocumentType.MDFE
        }
        
        doc_type = doc_type_map.get(result.get('document_type', '').lower(), DocumentType.UNKNOWN)
        
        # Cria o documento no banco de dados
        document = Document.create(
            document_type=doc_type,
            document_number=result.get('numero'),
            issue_date=result.get('data_emissao'),
            total_amount=result.get('valor_total', 0.0),
            issuer_name=result.get('emitente', {}).get('razao_social'),
            issuer_document=result.get('emitente', {}).get('cnpj'),
            receiver_name=result.get('destinatario', {}).get('razao_social'),
            receiver_document=result.get('destinatario', {}).get('cpf') or result.get('destinatario', {}).get('cnpj'),
            access_key=result.get('chave_acesso'),
            authorization_protocol=result.get('protocolo_autorizacao'),
            raw_data=json.dumps(result, ensure_ascii=False),
            status=DocumentStatus.PROCESSED,
            user_id=user_id
        )
        
        # Salva os itens do documento
        for item_data in result.get('itens', []):
            document.add_item(
                code=item_data.get('codigo'),
                description=item_data.get('descricao'),
                quantity=item_data.get('quantidade', 0),
                unit_value=item_data.get('valor_unitario', 0),
                total_value=item_data.get('valor_total', 0)
            )
        
        # Salva os impostos do documento
        for tax_type, tax_value in result.get('impostos', {}).items():
            document.add_tax(
                tax_type=tax_type.upper(),
                amount=float(tax_value)
            )
        
        return document
    
    def process_and_save(self, file_path: Union[str, Path], user_id: Optional[str] = None) -> Document:
        """
        Processa um documento e salva os resultados no banco de dados.
        
        Args:
            file_path: Caminho para o arquivo a ser processado
            user_id: ID do usuário que enviou o documento (opcional)
            
        Returns:
            Instância do documento salvo
        """
        # Processa o documento
        result = self.process_uploaded_file(file_path)
        
        # Salva no banco de dados
        return self.save_document_to_db(result, user_id)
    
    def batch_process(self, directory: Union[str, Path], user_id: Optional[str] = None) -> List[Document]:
        """
        Processa todos os arquivos em um diretório.
        
        Args:
            directory: Diretório contendo os arquivos a serem processados
            user_id: ID do usuário que enviou os documentos (opcional)
            
        Returns:
            Lista de documentos processados
        """
        directory = Path(directory)
        if not directory.is_dir():
            raise NotADirectoryError(f"O diretório não existe: {directory}")
        
        processed_docs = []
        
        # Processa todos os arquivos suportados no diretório
        for file_path in directory.glob("*"):
            if file_path.suffix.lower() in ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.xml']:
                try:
                    logger.info(f"Processando arquivo: {file_path}")
                    doc = self.process_and_save(file_path, user_id)
                    processed_docs.append(doc)
                    logger.info(f"Documento processado com sucesso: {doc.id}")
                except Exception as e:
                    logger.error(f"Erro ao processar o arquivo {file_path}: {str(e)}", exc_info=True)
        
        return processed_docs


def create_document_agent() -> DocumentAgent:
    """
    Função de fábrica para criar uma instância do DocumentAgent.
    
    Returns:
        Instância do DocumentAgent configurada
    """
    from config import UPLOAD_DIR, PROCESSED_DIR
    
    return DocumentAgent(
        upload_dir=UPLOAD_DIR or "uploads",
        processed_dir=PROCESSED_DIR or "processed"
    )


if __name__ == "__main__":
    # Exemplo de uso
    import sys
    
    # Configura o logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) < 2:
        print("Uso: python -m backend.agents.document_agent <caminho_do_arquivo_ou_diretorio> [user_id]")
        sys.exit(1)
    
    path = Path(sys.argv[1])
    user_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        agent = create_document_agent()
        
        if path.is_file():
            # Processa um único arquivo
            doc = agent.process_and_save(path, user_id)
            print(f"Documento processado com sucesso! ID: {doc.id}")
        else:
            # Processa todos os arquivos no diretório
            docs = agent.batch_process(path, user_id)
            print(f"Processados {len(docs)} documentos com sucesso!")
            
    except Exception as e:
        print(f"Erro: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
