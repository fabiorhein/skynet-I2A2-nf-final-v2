"""
Unified storage implementation for the application.
Supports both local JSON and Supabase backends.
"""
import json
import traceback
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Type, TypeVar, Generic
from dataclasses import dataclass
from datetime import datetime, timezone, UTC
import uuid
import requests
from enum import Enum, auto
from abc import ABC, abstractmethod
import warnings

# Importa datetime no escopo global para evitar problemas de referência
from datetime import datetime as dt

# Import configuration
from config import SUPABASE_URL, SUPABASE_KEY

# Type variable for the storage implementation
T = TypeVar('T', bound='BaseStorage')

class StorageType(Enum):
    """Supported storage types."""
    LOCAL_JSON = auto()
    SUPABASE = auto()

class StorageError(Exception):
    """Base class for storage-related errors."""
    pass

@dataclass
class PaginatedResponse:
    """Standard response format for paginated queries."""
    items: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages
        }

class StorageInterface(ABC):
    """Abstract base class defining storage backend interface."""

    def save_document(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Save a document record. Returns the saved record with generated id.
        DEPRECATED: Use save_fiscal_document() instead.
        """
        warnings.warn(
            "save_document() is deprecated, use save_fiscal_document() instead",
            DeprecationWarning,
            stacklevel=2
        )
        return self.save_fiscal_document(record)

    @abstractmethod
    def get_fiscal_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single fiscal document by ID."""
        pass

    @abstractmethod
    def get_fiscal_documents(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters
    ) -> PaginatedResponse:
        """Return paginated list of fiscal documents with total count.
        Args:
            page: Page number (1-based)
            page_size: Number of items per page
            **filters: Optional filters to apply (e.g., document_type='NFe')
        Returns:
            PaginatedResponse containing the documents and pagination info
        """
        pass

    @abstractmethod
    def delete_fiscal_document(self, doc_id: str) -> bool:
        """Delete a fiscal document by ID.
        Args:
            doc_id: ID of the document to delete
        Returns:
            bool: True if the document was deleted, False if not found
        """
        pass

    @abstractmethod
    def save_fiscal_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Save a fiscal document.
        Args:
            document: Document data to save
        Returns:
            The saved document with any generated fields
        """
        pass

    @abstractmethod
    def add_document_analysis(self, doc_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Add an analysis to a document.
        Args:
            doc_id: ID of the document to add analysis to
            analysis: Analysis data to add
        Returns:
            The saved analysis with any generated fields
        """
        pass

    # Deprecated/legacy methods for backward compatibility

    def get_document_history(self, fiscal_document_id: str) -> List[Dict[str, Any]]:
        """Get history events for a document.
        DEPRECATED: Use get_fiscal_document() and check the 'analyses' field.
        """
        doc = self.get_fiscal_document(fiscal_document_id)
        return doc.get('analyses', []) if doc else []

    def save_history(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Save a history event. Returns the saved event.
        DEPRECATED: Use add_document_analysis() instead.
        """
        doc_id = event.get('document_id')
        if not doc_id:
            raise ValueError("document_id is required in the event data")
        return self.add_document_analysis(doc_id, event)

    def load_documents(self) -> List[Dict[str, Any]]:
        """Backward compatibility method: loads all documents.
        WARNING: This method is deprecated and will be removed in a future version.
        Use get_fiscal_documents() instead.
        """
        result = self.get_fiscal_documents(page=1, page_size=1000)
        return result.items
    
    def save_fiscal_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Save a fiscal document. Returns the saved document with generated id."""
        raise NotImplementedError()
    
    def get_fiscal_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single fiscal document by ID."""
        raise NotImplementedError()
    
    def get_fiscal_documents(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters
    ) -> PaginatedResponse:
        """Get a paginated list of fiscal documents with optional filtering."""
        raise NotImplementedError()
    
    def delete_fiscal_document(self, doc_id: str) -> bool:
        """Delete a fiscal document by ID."""
        raise NotImplementedError()
    
    def add_document_analysis(self, doc_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Add an analysis to a document."""
        raise NotImplementedError()
    
    # Backward compatibility methods
    def save_document(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Save a document (legacy method)."""
        import warnings
        warnings.warn(
            "save_document() is deprecated, use save_fiscal_document() instead",
            DeprecationWarning,
            stacklevel=2
        )
        return self.save_fiscal_document(record)
    
    def get_document_history(self, fiscal_document_id: str) -> List[Dict[str, Any]]:
        """Get history events for a document (legacy method)."""
        doc = self.get_fiscal_document(fiscal_document_id)
        return doc.get('analyses', []) if doc else []
    
    def save_history(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Save a history event (legacy method)."""
        doc_id = event.get('fiscal_document_id')
        if not doc_id:
            # Para compatibilidade com versões antigas
            doc_id = event.get('document_id')
            if doc_id:
                event['fiscal_document_id'] = doc_id
            else:
                raise ValueError("fiscal_document_id is required in the event data")
        return self.add_document_analysis(doc_id, event)

class LocalJSONStorage(StorageInterface):
    """Local JSON file storage implementation."""

    def __init__(self, data_dir: str = 'data'):
        self.data_dir = Path(data_dir)
        self.docs_path = self.data_dir / 'documents.json'
        self._ensure_data_dir()
    
    def _ensure_data_dir(self):
        """Ensure the data directory exists."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.docs_path.exists():
            self.docs_path.write_text('{"documents": [], "next_id": 1}')
    
    def _read_data(self) -> Dict[str, Any]:
        """Read data from the JSON file."""
        try:
            return json.loads(self.docs_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, FileNotFoundError):
            # If file is corrupted or doesn't exist, reset it
            self._ensure_data_dir()
            return {"documents": [], "next_id": 1}
    
    def _write_data(self, data: Dict[str, Any]):
        """Write data to the JSON file."""
        self.docs_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

    def save_fiscal_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Save a fiscal document to local JSON storage."""
        data = self._read_data()
        documents = data.get("documents", [])
        
        # Generate ID if not provided
        if "id" not in document or not document["id"]:
            document["id"] = str(data["next_id"])
            data["next_id"] += 1
            document["created_at"] = datetime.now(UTC).isoformat()
            documents.append(document)
        else:
            # Update existing document
            doc_id = document["id"]
            for i, doc in enumerate(documents):
                if doc.get("id") == doc_id:
                    document["updated_at"] = datetime.now(UTC).isoformat()
                    documents[i] = document
                    break
            else:
                document["created_at"] = datetime.now(UTC).isoformat()
                documents.append(document)
        
        # Save back to file
        data["documents"] = documents
        self._write_data(data)
        return document
    
    def get_fiscal_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single fiscal document by ID."""
        data = self._read_data()
        for doc in data.get("documents", []):
            if doc.get("id") == doc_id:
                return doc
        return None
    
    def get_fiscal_documents(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters
    ) -> PaginatedResponse:
        """Get a paginated list of fiscal documents with optional filtering."""
        data = self._read_data()
        documents = data.get("documents", [])
        
        # Apply filters
        if filters:
            filtered_docs = []
            for doc in documents:
                match = True
                for key, value in filters.items():
                    if key in doc and doc[key] != value:
                        match = False
                        break
                if match:
                    filtered_docs.append(doc)
            documents = filtered_docs
        
        # Pagination
        total = len(documents)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_docs = documents[start:end]
        
        return PaginatedResponse(
            items=paginated_docs,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size
        )
    
    def delete_fiscal_document(self, doc_id: str) -> bool:
        """Delete a fiscal document by ID."""
        data = self._read_data()
        documents = data.get("documents", [])
        
        for i, doc in enumerate(documents):
            if doc.get("id") == doc_id:
                del documents[i]
                data["documents"] = documents
                self._write_data(data)
                return True
        
        return False
    
    def add_document_analysis(self, doc_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Add an analysis to a document."""
        document = self.get_fiscal_document(doc_id)
        if not document:
            raise StorageError(f"Document {doc_id} not found")
        
        # Add analysis to document
        if "analyses" not in document:
            document["analyses"] = []
        
        # Generate analysis ID
        analysis_id = len(document["analyses"]) + 1
        analysis["id"] = analysis_id
        analysis["created_at"] = datetime.now(UTC).isoformat()
        
        document["analyses"].append(analysis)
        document["updated_at"] = datetime.now(UTC).isoformat()
        
        # Update the document
        self.save_fiscal_document(document)
        return analysis
    
    # Backward compatibility methods
    def _load_docs(self) -> List[Dict[str, Any]]:
        """Load documents from the JSON file.
        
        Returns:
            List[Dict[str, Any]]: List of documents
        """
        try:
            data = self._read_data()
            if not isinstance(data, dict):
                return []
            return data.get("documents", [])
        except Exception as e:
            print(f"[ERROR] Failed to load documents: {e}")
            return []
    
    def save_document(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy method for backward compatibility."""
        import warnings
        warnings.warn(
            "save_document() is deprecated, use save_fiscal_document() instead",
            DeprecationWarning,
            stacklevel=2
        )
        return self.save_fiscal_document(record)

    def get_fiscal_documents(
        self,
        filters: Optional[Dict[str, str]] = None,
        page: int = 1,
        page_size: int = 50
    ) -> PaginatedResponse:
        """Get a paginated list of fiscal documents with optional filtering.
        
        Args:
            filters: Dictionary of filters to apply
            page: Page number (1-based)
            page_size: Number of items per page (if 0, returns all items)
            
        Returns:
            PaginatedResponse: Paginated response with documents
        """
        try:
            # Carrega todos os documentos
            docs = self._load_docs()
            
            # Aplica os filtros, se houver
            if filters:
                docs = [d for d in docs if self._matches_filters(d, filters)]
            
            # Calcula o total de documentos
            total = len(docs)
            
            # Se page_size for 0, retorna todos os itens
            if page_size <= 0:
                return PaginatedResponse(
                    items=docs,
                    total=total,
                    page=1,
                    page_size=total if total > 0 else 1,
                    total_pages=1
                )
            
            # Calcula a paginação
            start = (page - 1) * page_size
            end = start + page_size
            
            # Calcula o número total de páginas
            total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
            
            # Retorna a resposta paginada
            return PaginatedResponse(
                items=docs[start:end],
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages
            )
            
        except Exception as e:
            print(f"[ERROR] Failed to get fiscal documents: {e}")
            return PaginatedResponse(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                total_pages=0
            )

    def get_document_history(self, fiscal_document_id: str) -> List[Dict[str, Any]]:
        events = self._load_history()
        return [
            e for e in events
            if e.get('fiscal_document_id') == fiscal_document_id
        ]

    def save_history(self, event: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_data_dir()
        events = self._load_history()
        
        if not isinstance(events, list):
            events = []
            
        if 'id' not in event:
            event['id'] = str(uuid.uuid4())
        if 'created_at' not in event:
            event['created_at'] = datetime.now(UTC).isoformat()
            
        events.append(event)
        
        # Garante que o diretório existe antes de salvar
        self._ensure_data_dir()
        history_path = Path(self.data_dir) / 'document_history.json'
        history_path.write_text(
            json.dumps(events, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        
        return event

    def _load_history(self) -> List[Dict[str, Any]]:
        history_path = Path(self.data_dir) / 'document_history.json'
        if not history_path.exists():
            return []
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            print(f"Error loading history file: {history_path}. Returning empty list.")
            return []

    def save_history(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Save a history event to local storage.
        
        Args:
            event: The event data to save
            
        Returns:
            The saved event with generated fields
        """
        self._ensure_data_dir()
        events = self._load_history()

        if not isinstance(events, list):
            events = []

        if 'id' not in event:
            event['id'] = str(uuid.uuid4())
        if 'created_at' not in event:
            event['created_at'] = datetime.now(UTC).isoformat()

        events.append(event)

        # Ensure directory exists before saving
        self._ensure_data_dir()
        history_path = Path(self.data_dir) / 'document_history.json'
        history_path.write_text(
            json.dumps(events, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

        return event

def _load_history(self) -> List[Dict[str, Any]]:
    history_path = Path(self.data_dir) / 'document_history.json'
    if not history_path.exists():
        return []
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
    except Exception as e:
        raise LocalStorageError(f"Failed to load history: {e}")

def _matches_filters(self, doc: Dict[str, Any], filters: Dict[str, str]) -> bool:
    """Check if document matches all filters."""
    for k, v in filters.items():
        if not v:
            continue

        # Special handling for common filter fields
        if k == 'document_number':
            # Check numero in parsed or document_number directly
            val = doc.get('document_number') or (doc.get('parsed') or {}).get('numero')
            if val is None:
                return False
            if v.lower() not in str(val).lower():
                return False
            continue

        if k == 'issuer_cnpj':
            # Check emitente.cnpj in parsed or issuer_cnpj directly
            val = doc.get('issuer_cnpj') or (doc.get('parsed') or {}).get('emitente', {}).get('cnpj')
            if val is None:
                return False
            if v.lower() not in str(val).lower():
                return False
            continue

        # Default field lookup
        val = doc.get(k)
        if val is None and 'parsed' in doc:
            val = (doc['parsed'] or {}).get(k)
        if val is None and 'extracted_data' in doc:
            val = (doc['extracted_data'] or {}).get(k)
        if val is None:
            return False
        if v.lower() not in str(val).lower():
            return False
    return True


class SupabaseStorageError(StorageError):
    """Supabase-specific storage errors."""
    def __init__(self, message, *args, **kwargs):
        self.message = message
        super().__init__(message, *args, **kwargs)

    def __str__(self):
        return str(self.message)


class SupabaseStorage(StorageInterface):
    """Supabase storage implementation using REST API."""

    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
        self._ensure_tables_exist()

    def _ensure_tables_exist(self):
        """Ensure required tables exist in the database.

        This is a no-op in this implementation since we're using migrations.
        """
        pass

    def _headers(self) -> Dict[str, str]:
        return {
            'Content-Type': 'application/json',
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}'
        }

    def _table_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def _extract_document_id(self, response_obj: Any, response_headers: Dict[str, str] = None, status_code: int = None) -> Optional[str]:
        """
        Extrai o ID do documento de várias fontes possíveis.
        
        Args:
            response_obj: Objeto de resposta (dict, list, ou outro)
            response_headers: Headers da resposta HTTP
            status_code: Status code da resposta HTTP
            
        Returns:
            str: ID do documento, ou None se não encontrado
        """
        # 1. Tenta extrair do header Location
        if response_headers:
            location = response_headers.get('Location', '')
            if location:
                # Extrai o ID da URL (último segmento)
                doc_id = location.split('/')[-1]
                if doc_id and doc_id.strip():
                    print(f"[DEBUG] ID extraído do header Location: {doc_id}")
                    return doc_id
        
        # 2. Tenta extrair do header Content-Location (alternativa do Supabase)
        if response_headers:
            content_location = response_headers.get('Content-Location', '')
            if content_location:
                # Extrai o ID da URL (último segmento antes de ?)
                doc_id = content_location.split('/')[-1].split('?')[0]
                if doc_id and doc_id.strip():
                    print(f"[DEBUG] ID extraído do header Content-Location: {doc_id}")
                    return doc_id
        
        # 3. Tenta extrair do corpo da resposta
        if isinstance(response_obj, dict):
            # Tenta chaves comuns para ID
            id_keys = ['id', 'ID', 'document_id', 'doc_id', 'fiscal_document_id']
            for key in id_keys:
                if key in response_obj and response_obj[key]:
                    doc_id = str(response_obj[key]).strip()
                    if doc_id:
                        print(f"[DEBUG] ID extraído da chave '{key}': {doc_id}")
                        return doc_id
            
            # Tenta extrair de estruturas aninhadas
            if 'data' in response_obj and isinstance(response_obj['data'], dict):
                for key in id_keys:
                    if key in response_obj['data'] and response_obj['data'][key]:
                        doc_id = str(response_obj['data'][key]).strip()
                        if doc_id:
                            print(f"[DEBUG] ID extraído de data.{key}: {doc_id}")
                            return doc_id
        
        # 4. Tenta extrair de lista
        elif isinstance(response_obj, list) and response_obj:
            first_item = response_obj[0]
            if isinstance(first_item, dict):
                id_keys = ['id', 'ID', 'document_id', 'doc_id', 'fiscal_document_id']
                for key in id_keys:
                    if key in first_item and first_item[key]:
                        doc_id = str(first_item[key]).strip()
                        if doc_id:
                            print(f"[DEBUG] ID extraído do primeiro item da lista, chave '{key}': {doc_id}")
                            return doc_id
        
        # 5. Para respostas 201 sem conteúdo, tenta gerar um ID baseado em timestamp
        # (Esta é uma fallback, não é ideal, mas melhor que nada)
        if status_code == 201 and not response_obj:
            print("[AVISO] Resposta 201 sem conteúdo. Tentando estratégia alternativa...")
            # Nota: Idealmente, o Supabase deveria retornar o ID, mas se não retornar,
            # precisamos de uma estratégia alternativa (como fazer um SELECT após INSERT)
            return None
        
        print("[AVISO] Não foi possível extrair o ID da resposta")
        return None

    def _handle_response(self, r: requests.Response, preserve_list: bool = False) -> Union[dict, list]:
        """Processa a resposta da API do Supabase.

        Args:
            r: Resposta da requisição HTTP
            preserve_list: Se True, sempre retorna uma lista, mesmo que vazia.
                         Se False, retorna um único item (o primeiro) ou um dicionário vazio.

        Returns:
            Union[dict, list]: Dados da resposta como dicionário ou lista, dependendo do parâmetro preserve_list.
                             Retorna uma lista vazia ou dicionário vazio em caso de erro ou resposta vazia.

        Raises:
            SupabaseStorageError: Se houver um erro na requisição HTTP
        """
        try:
            print("\n[DEBUG] ========== INÍCIO DO PROCESSAMENTO DA RESPOSTA ==========")
            print(f"[DEBUG] URL da requisição: {r.request.method} {r.request.url}")
            print(f"[DEBUG] Cabeçalhos da requisição: {dict(r.request.headers)}")
            print(f"[DEBUG] Status code: {r.status_code}")
            print(f"[DEBUG] Cabeçalhos da resposta: {dict(r.headers)}")
            
            # Para respostas 201 (Created) sem conteúdo, tenta extrair o ID do header Location
            if r.status_code == 201:
                location = r.headers.get('Location', '')
                if location:
                    # Extrai o ID da URL (último segmento)
                    doc_id = location.split('/')[-1]
                    print(f"[DEBUG] ID do documento extraído do header Location: {doc_id}")
                    return {
                        'id': doc_id,
                        'success': True,
                        'message': 'Documento criado com sucesso',
                        'created': True
                    }
                else:
                    print("[AVISO] Resposta 201 sem header Location. Não foi possível obter o ID do documento.")
                    return {'success': True, 'message': 'Documento criado com sucesso', 'created': True}
            
            # Tenta extrair o conteúdo da resposta para log
            try:
                content_type = r.headers.get('content-type', '').lower()
                if 'application/json' in content_type and r.content:
                    response_data = r.json()
                    print(f"[DEBUG] Conteúdo da resposta (JSON): {json.dumps(response_data, ensure_ascii=False, indent=2)[:1000]}...")
                elif r.content:
                    print(f"[DEBUG] Conteúdo da resposta (texto): {r.text[:1000]}...")
            except Exception as e:
                print(f"[AVISO] Não foi possível exibir o conteúdo da resposta: {str(e)}")
                if r.text:
                    print(f"[DEBUG] Conteúdo bruto: {r.text[:1000]}...")

            # Verifica se houve erro na requisição HTTP
            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError as http_err:
                error_detail = f"Erro HTTP {r.status_code}"
                try:
                    if r.content:
                        error_data = r.json()
                        error_detail = error_data.get('message', str(error_data))
                        print(f"[ERRO] Erro detalhado: {error_detail}")
                except Exception as json_err:
                    error_detail = f"{r.text[:500]}..." if r.text else str(http_err)
                    print(f"[ERRO] Erro ao processar resposta JSON: {str(json_err)}")
                
                print(f"[ERRO] Falha na requisição: {error_detail}")
                raise SupabaseStorageError(f"Erro na requisição: {error_detail}") from http_err

            # Para respostas 201 (Created)
            if r.status_code == 201:
                print("[DEBUG] Resposta 201 - Documento criado com sucesso")
                
                # Tenta obter o ID do header Location
                location = r.headers.get('Location', '')
                if location:
                    # Extrai o ID da URL (último segmento)
                    doc_id = location.split('/')[-1]
                    print(f"[DEBUG] ID do documento extraído do header Location: {doc_id}")
                    return {
                        'id': doc_id,
                        'success': True,
                        'message': 'Documento criado com sucesso',
                        'created': True
                    }
                
                # Se não tiver Location, tenta obter do corpo da resposta
                if r.content:
                    try:
                        response_data = r.json()
                        if isinstance(response_data, dict) and 'id' in response_data:
                            doc_id = response_data['id']
                            print(f"[DEBUG] ID do documento obtido do corpo da resposta: {doc_id}")
                            return {
                                'id': doc_id,
                                'success': True,
                                'message': 'Documento criado com sucesso',
                                'created': True,
                                **response_data
                            }
                    except json.JSONDecodeError:
                        pass
                
                print("[AVISO] Resposta 201 sem ID do documento. Não foi possível obter o ID.")
                return {'success': True, 'message': 'Documento criado com sucesso', 'created': True}

            # Para respostas com conteúdo JSON
            if r.content and 'application/json' in r.headers.get('content-type', '').lower():
                print("[DEBUG] Tentando fazer parse do JSON da resposta...")
                try:
                    response_data = r.json()
                    print(f"[DEBUG] JSON parseado com sucesso. Tipo: {type(response_data)}")

                    # Se for uma lista
                    if isinstance(response_data, list):
                        print(f"[DEBUG] Resposta é uma lista com {len(response_data)} itens")
                        if not response_data:
                            print("[AVISO] Lista vazia retornada")
                            return [] if preserve_list else {}

                        if preserve_list:
                            print("[DEBUG] Retornando lista completa (preserve_list=True)")
                            return response_data

                        first_item = response_data[0]
                        if not isinstance(first_item, dict):
                            print(f"[AVISO] O primeiro item não é um dicionário: {first_item}")
                            return {"data": first_item}
                        
                        print("[DEBUG] Retornando primeiro item da lista")
                        return first_item

                    # Se for um dicionário
                    elif isinstance(response_data, dict):
                        print("[DEBUG] Resposta é um dicionário")
                        
                        # Verifica se há uma chave 'data' que contém os resultados
                        if 'data' in response_data:
                            print(f"[DEBUG] Encontrada chave 'data' do tipo: {type(response_data['data'])}")
                            if isinstance(response_data['data'], list):
                                data_list = response_data['data']
                                print(f"[DEBUG] 'data' é uma lista com {len(data_list)} itens")
                                if preserve_list:
                                    return data_list
                                return data_list[0] if data_list else {}
                            elif isinstance(response_data['data'], dict):
                                print("[DEBUG] 'data' é um dicionário")
                                return response_data['data']
                        
                        # Verifica se há uma chave 'items' que contém os resultados
                        if 'items' in response_data and isinstance(response_data['items'], list):
                            items = response_data['items']
                            print(f"[DEBUG] Encontrada chave 'items' com {len(items)} itens")
                            if preserve_list:
                                return items
                            return items[0] if items else {}

                        # Se for uma resposta de erro
                        if 'error' in response_data:
                            error_msg = response_data.get('message', str(response_data.get('error', 'Erro desconhecido')))
                            print(f"[ERRO] Erro na resposta: {error_msg}")
                            raise SupabaseStorageError(error_msg)
                        
                        # Se não for nenhum dos casos acima, retorna o dicionário como está
                        print("[DEBUG] Retornando dicionário completo")
                        return [response_data] if preserve_list else response_data

                except json.JSONDecodeError as e:
                    print(f"[ERRO] Falha ao decodificar JSON: {str(e)}")
                    print(f"[DEBUG] Conteúdo da resposta: {r.text[:1000]}...")
                    
                    if r.text.strip():
                        return [{"raw_response": r.text.strip()}] if preserve_list else {"raw_response": r.text.strip()}
                    
                    print("[AVISO] Resposta vazia do servidor (após falha no parse do JSON)")
                    return [] if preserve_list else {}

            # Se chegou até aqui, retorna a resposta como texto
            print("[DEBUG] Retornando resposta como texto")
            if r.text.strip():
                return [{"response": r.text.strip()}] if preserve_list else {"response": r.text.strip()}
            
            return [] if preserve_list else {}

        except Exception as e:
            error_msg = f"Erro inesperado ao processar resposta: {str(e)}"
            print(f"[ERRO] {error_msg}")
            print(f"[DEBUG] Tipo de exceção: {type(e).__name__}")
            print(f"[DEBUG] Traceback: {traceback.format_exc()}")
            
            # Retorna uma lista vazia ou dicionário vazio em vez de levantar exceção
            # para permitir que o código continue executando
            return [] if preserve_list else {}

    def save_fiscal_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Salva um documento fiscal no Supabase.

        Args:
            document: Dicionário contendo os dados do documento a ser salvo

        Returns:
            Dict[str, Any]: Dicionário com os dados do documento salvo, incluindo o ID gerado

        Raises:
            SupabaseStorageError: Se ocorrer algum erro durante o salvamento
        """
        # Cria uma cópia do registro para não modificar o original
        db_record = document.copy()

        try:
            # Removed verbose debug output of document fields

            # Função auxiliar para validar e padronizar os dados de validação
            def _validate_validation_data(validation_data):
                if not validation_data or not isinstance(validation_data, dict):
                    return {
                        'issues': [],
                        'warnings': ['Dados de validação ausentes ou em formato inválido'],
                        'validations': {}
                    }
                
                # Garante que os campos obrigatórios existam
                result = {
                    'issues': validation_data.get('issues', []),
                    'warnings': validation_data.get('warnings', []),
                    'validations': validation_data.get('validations', {})
                }
                
                # Converte para lista se não for
                if not isinstance(result['issues'], list):
                    result['issues'] = [str(result['issues'])] if result['issues'] else []
                
                if not isinstance(result['warnings'], list):
                    result['warnings'] = [str(result['warnings'])] if result['warnings'] else []
                
                if not isinstance(result['validations'], dict):
                    result['validations'] = {}
                
                return result

            # Mapeamento de campos para extrair do registro
            field_mapping = {
                # Campos principais
                'file_name': ('file_name', 'documento_sem_nome.pdf'),
                'document_type': ('document_type', 'NFe'),
                'document_number': ('document_number', None),
                'issuer_cnpj': ('issuer_cnpj', None),
                'issuer_name': ('issuer_name', None),
                'issue_date': ('issue_date', None),
                'total_value': ('total_value', 0.0),
                'cfop': ('cfop', None),
                'validation_status': ('validation_status', 'pending'),
                'raw_text': ('raw_text', ''),
                'uploaded_at': ('uploaded_at', None),
                'processed_at': ('processed_at', None),

                # Campos aninhados
                'extracted_data': ('extracted_data', {}),
                'classification': ('classification', {}),
                'validation_details': ('validation_details', {
                    'issues': [],
                    'warnings': [],
                    'validations': {}
                }),
                'validation_metadata': ('validation_metadata', {
                    'validated_at': None,
                    'validator_version': '1.0',
                    'validation_rules_applied': []
                })
            }

            # Prepara o registro para o banco de dados
            prepared_record = {}

            # Preenche os campos mapeados
            for field, (source_field, default) in field_mapping.items():
                if source_field in db_record:
                    prepared_record[field] = db_record[source_field]
                elif default is not None:
                    prepared_record[field] = default
            
            # Valida e padroniza os dados de validação
            if 'validation_details' in prepared_record:
                prepared_record['validation_details'] = _validate_validation_data(
                    prepared_record['validation_details']
                )
            
            # Atualiza os metadados de validação, mas não força a existência do campo
            # para evitar erros com colunas que podem não existir no banco de dados
            if 'validation_metadata' in prepared_record and isinstance(prepared_record['validation_metadata'], dict):
                prepared_record['validation_metadata'].update({
                    'validated_at': prepared_record['validation_metadata'].get('validated_at') or datetime.now(UTC).isoformat(),
                    'validator_version': prepared_record['validation_metadata'].get('validator_version', '1.0')
                })
            else:
                # Se não houver validation_metadata, não forçamos sua criação
                # para evitar erros com colunas que não existem no banco de dados
                prepared_record.pop('validation_metadata', None)
            
            # Removed verbose validation debug output

            # Move raw_text para o nível superior se estiver em extracted_data
            if 'extracted_data' in prepared_record and isinstance(prepared_record['extracted_data'], dict):
                extracted_data = prepared_record['extracted_data']
                
                # Move raw_text para o nível superior se estiver em extracted_data
                if 'raw_text' in extracted_data and not prepared_record.get('raw_text'):
                    prepared_record['raw_text'] = extracted_data.pop('raw_text')
                
                # Lógica específica para MDFe - extrai vCarga como total_value
                if prepared_record.get('document_type') == 'MDFe' and 'vCarga' in extracted_data:
                    try:
                        # Tenta converter para float, se possível
                        vcarga = extracted_data.get('vCarga')
                        if vcarga is not None:
                            prepared_record['total_value'] = float(vcarga)
                            # Removed debug output for vCarga value
                    except (ValueError, TypeError) as e:
                        print(f"[MDFe] Erro ao converter vCarga para valor numérico: {e}")
                        # Se não conseguir converter, mantém o valor original ou o padrão

            # Função auxiliar para formatar datas corretamente
            def _format_date(date_value):
                """Formata uma data para o padrão ISO 8601 aceito pelo PostgreSQL."""
                if not date_value:
                    return None
                
                try:
                    # Se for um objeto datetime, converte para string ISO 8601
                    if hasattr(date_value, 'isoformat'):
                        return date_value.isoformat()
                    
                    # Se for uma string
                    if isinstance(date_value, str):
                        date_value = date_value.strip()
                        
                        # Formato DD/MM/YYYY ou DD/MM/YYYY HH:MM:SS
                        if '/' in date_value:
                            parts = date_value.split()
                            date_part = parts[0]
                            time_part = parts[1] if len(parts) > 1 else None
                            
                            try:
                                day, month, year = date_part.split('/')
                                formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                                if time_part:
                                    formatted += f"T{time_part}"
                                return formatted
                            except (ValueError, IndexError):
                                pass
                        
                        # Formato YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS (já correto)
                        if date_value.count('-') >= 2:
                            # Tenta validar se é um formato válido
                            if 'T' in date_value or ' ' in date_value:
                                # Tem hora, tenta parsear
                                try:
                                    # Tenta remover caracteres inválidos
                                    # Formato malformado: "2025 09:40:31-08-08"
                                    # Esperado: "2025-09-24T09:40:31"
                                    if date_value.count(' ') > 0 and date_value.count('-') > 2:
                                        # Parece ser malformado
                                        parts = date_value.split()
                                        if len(parts) >= 2:
                                            year = parts[0]
                                            time_str = parts[1]
                                            # Remove caracteres inválidos da hora
                                            time_str = time_str.replace('-', ':')
                                            return f"{year}T{time_str}"
                                except Exception:
                                    pass
                            return date_value
                        
                        # Formato YYYY-MM-DD (data apenas)
                        if date_value.count('-') == 2 and len(date_value) == 10:
                            return date_value
                    
                    # Se for um timestamp numérico
                    if isinstance(date_value, (int, float)):
                        try:
                            dt_obj = dt.fromtimestamp(date_value)
                            return dt_obj.isoformat()
                        except (ValueError, OSError):
                            return None
                    
                    return None
                    
                except Exception as e:
                    print(f"[AVISO] Erro ao formatar data (valor: {date_value}): {e}")
                    return None
            
            # Garante que os campos de data estão no formato correto
            for date_field in ['uploaded_at', 'processed_at', 'issue_date']:
                if date_field in prepared_record:
                    formatted_date = _format_date(prepared_record[date_field])
                    prepared_record[date_field] = formatted_date
                    if formatted_date:
                        print(f"[DEBUG] Data {date_field} formatada: {formatted_date}")
                    else:
                        print(f"[DEBUG] Data {date_field} definida como None")

            # Log para depuração (sem expor dados sensíveis)
            debug_record = prepared_record.copy()
            if 'raw_text' in debug_record and len(debug_record['raw_text']) > 100:
                debug_record['raw_text'] = debug_record['raw_text'][:100] + '... (truncado)'
            print(f"[DEBUG] Dados a serem enviados para o Supabase: {debug_record}")

            # Prepara a URL e os cabeçalhos
            url = self._table_url('fiscal_documents')
            print(f"[DEBUG] Enviando requisição para: {url}")

            try:
                # Remove campos que podem não existir no banco de dados
                record_to_save = prepared_record.copy()
                
                # Remove validation_metadata se não for um dicionário
                if 'validation_metadata' in record_to_save and not isinstance(record_to_save['validation_metadata'], dict):
                    record_to_save.pop('validation_metadata')
                
                # Tenta salvar o documento
                try:
                    url = self._table_url('fiscal_documents')
                    headers = self._headers()
                    
                    # Log dos dados que serão enviados
                    print(f"[DEBUG] Enviando requisição para: {url}")
                    print(f"[DEBUG] Headers: {headers}")
                    print(f"[DEBUG] Dados a serem enviados: {json.dumps(record_to_save, default=str, ensure_ascii=False)[:500]}...")
                    
                    # Faz a requisição
                    r = requests.post(
                        url,
                        json=record_to_save,
                        headers=headers,
                        timeout=30  # Aumenta o timeout para 30 segundos
                    )
                    
                    print(f"[DEBUG] Resposta recebida - Status: {r.status_code}")
                    print(f"[DEBUG] Cabeçalhos da resposta: {dict(r.headers)}")
                    print(f"[DEBUG] Conteúdo da resposta: {r.text[:1000]}")
                    
                    # Se houver erro 400, tenta novamente sem os campos opcionais
                    if r.status_code == 400:
                        error_msg = r.json().get('message', r.text)
                        print(f"[AVISO] Erro ao salvar documento: {error_msg}")
                        
                        # Remove campos opcionais que podem estar causando o problema
                        optional_fields = ['validation_metadata', 'validation_details']
                        for field in optional_fields:
                            if field in record_to_save:
                                record_to_save.pop(field)
                        
                        # Tenta novamente sem os campos opcionais
                        r = requests.post(
                            self._table_url('fiscal_documents'),
                            json=record_to_save,
                            headers=self._headers(),
                            timeout=10
                        )
                except requests.exceptions.RequestException as e:
                    error_msg = f"Erro na requisição HTTP: {str(e)}"
                    print(f"[ERRO] {error_msg}")
                    raise SupabaseStorageError(error_msg)

                # Verifica se a resposta foi bem sucedida (2xx)
                if 200 <= r.status_code < 300:
                    try:
                        # Tenta extrair o ID usando o novo método robusto
                        response_data = None
                        if r.content:
                            try:
                                response_data = r.json()
                            except json.JSONDecodeError:
                                response_data = None
                        
                        # Extrai o ID de várias fontes possíveis
                        doc_id = self._extract_document_id(response_data, dict(r.headers), r.status_code)
                        
                        # Se não conseguiu extrair o ID e foi 201, tenta fazer um SELECT para obter o ID
                        if not doc_id and r.status_code == 201:
                            print("[DEBUG] Tentando recuperar ID via SELECT após INSERT...")
                            try:
                                # Tenta buscar o documento mais recente com base no file_name
                                file_name = prepared_record.get('file_name', '')
                                if file_name:
                                    select_url = self._table_url('fiscal_documents')
                                    select_params = {
                                        'select': 'id',
                                        'file_name': f'eq.{file_name}',
                                        'order': 'created_at.desc',
                                        'limit': 1
                                    }
                                    select_response = requests.get(
                                        select_url,
                                        headers=self._headers(),
                                        params=select_params,
                                        timeout=10
                                    )
                                    
                                    if select_response.status_code == 200:
                                        select_data = select_response.json()
                                        if isinstance(select_data, list) and select_data:
                                            doc_id = select_data[0].get('id')
                                            print(f"[DEBUG] ID recuperado via SELECT: {doc_id}")
                            except Exception as e:
                                print(f"[AVISO] Erro ao tentar recuperar ID via SELECT: {str(e)}")
                        
                        if doc_id:
                            print(f"[SUCESSO] Documento salvo com sucesso. ID: {doc_id}")
                            return {
                                'id': doc_id,
                                'success': True,
                                'message': 'Documento salvo com sucesso',
                                'data': {'id': doc_id} if response_data is None else response_data,
                                'validation_status': prepared_record.get('validation_status', 'pending'),
                                'validation_details': prepared_record.get('validation_details', {})
                            }
                        
                        # Se chegou aqui, é porque a resposta foi 2xx mas não temos um ID
                        print("[AVISO] Resposta de sucesso sem ID do documento")
                        return {
                            'success': True,
                            'message': 'Documento processado com sucesso',
                            'data': {},
                            'validation_status': prepared_record.get('validation_status', 'pending'),
                            'validation_details': prepared_record.get('validation_details', {})
                        }
                            
                    except Exception as e:
                        print(f"[AVISO] Erro ao processar resposta de sucesso: {str(e)}")
                        # Mesmo com erro no processamento, se o status for 2xx, consideramos sucesso
                        return {
                            'success': True,
                            'message': 'Documento processado com sucesso',
                            'data': {},
                            'validation_status': prepared_record.get('validation_status', 'pending'),
                            'validation_details': prepared_record.get('validation_details', {})
                        }
                else:
                    # Se não for um status de sucesso, tenta extrair a mensagem de erro
                    error_msg = f"Erro ao salvar documento (HTTP {r.status_code})"
                    try:
                        if r.content:
                            error_data = r.json()
                            error_msg = error_data.get('message', str(error_data))
                    except:
                        if r.text:
                            error_msg = f"{error_msg}: {r.text[:200]}"
                    
                    print(f"[ERRO] {error_msg}")
                    raise SupabaseStorageError(error_msg)

            except requests.exceptions.RequestException as e:
                error_msg = f"Erro na requisição HTTP: {str(e)}"
                print(f"[ERRO] {error_msg}")
                self._last_error = error_msg
                raise SupabaseStorageError(error_msg)

            except Exception as e:
                error_msg = f"Erro inesperado ao processar resposta: {str(e)}"
                print(f"[ERRO] {error_msg}")
                self._last_error = error_msg
                raise SupabaseStorageError(error_msg)

        except Exception as e:
            error_msg = f"Erro ao processar documento: {str(e)}"
            print(f"[ERRO] {error_msg}")
            self._last_error = error_msg
            raise SupabaseStorageError(error_msg)

    def get_fiscal_documents(
        self,
        filters: Optional[Dict[str, str]] = None,
        page: int = 1,
        page_size: int = 50
    ) -> PaginatedResponse:
        """Return paginated fiscal documents with total count.

        Args:
            filters: Dictionary of filters to apply (e.g., {'issuer_cnpj': '12345678'})
            page: Page number (1-based)
            page_size: Number of items per page (1-100, default: 50)

        Returns:
            PaginatedResponse: Paginated response with documents and pagination info

        Raises:
            SupabaseStorageError: If there's an error communicating with the storage backend
        """
        # Validação dos parâmetros
        page = max(1, int(page))
        page_size = max(1, min(100, int(page_size)))  # Limita a 100 itens por página

        url = self._table_url('fiscal_documents')
        offset = (page - 1) * page_size

        print(f"[DEBUG] Buscando documentos - página {page}, tamanho da página: {page_size}, offset: {offset}")
        if filters:
            print(f"[DEBUG] Filtros aplicados: {filters}")

        # Parâmetros da consulta
        params: Dict[str, Any] = {
            'select': '*',
            'order': 'created_at.desc',  # Ordena por data de criação (mais recentes primeiro)
            'limit': page_size,
            'offset': offset
        }

        # Aplica filtros
        if filters:
            for k, v in filters.items():
                if v is None or v == '':
                    continue

                # Remove espaços em branco extras
                v = str(v).strip()

                # Se for um CNPJ, remove formatação para busca
                if k in ['issuer_cnpj', 'recipient_cnpj']:
                    v = ''.join(filter(str.isdigit, v))

                # Usa ilike para busca parcial case-insensitive
                params[k] = f'ilike.%{v}%'
                print(f"[DEBUG] Aplicando filtro: {k}={params[k]}")

        try:
            # 1. Primeiro, busca o total de itens que correspondem aos filtros
            count_url = f"{url}?select=count"
            count_headers = {**self._headers(), 'Prefer': 'count=exact'}

            # Remove parâmetros de paginação e ordenação para a contagem
            count_params = {k: v for k, v in params.items() 
                          if k not in ['limit', 'offset', 'order']}

            print(f"[DEBUG] Contando documentos com filtros: {count_params}")

            r = requests.get(
                count_url,
                headers=count_headers,
                params=count_params
            )

            # Extrai o total de itens da resposta
            total = 0
            if r.status_code in (200, 206):  # Adiciona suporte para status 206 (Partial Content)
                try:
                    response_data = r.json()
                    print(f"[DEBUG] Resposta da contagem: {response_data}")

                    # Tenta extrair a contagem da resposta JSON
                    if isinstance(response_data, list) and response_data:
                        if isinstance(response_data[0], dict) and 'count' in response_data[0]:
                            total = int(response_data[0]['count'])
                            print(f"[DEBUG] Total extraído do JSON: {total}")
                        elif len(response_data) == 1 and isinstance(response_data[0], (int, float)):
                            total = int(response_data[0])
                            print(f"[DEBUG] Total extraído de lista numérica: {total}")

                    # Se não encontrou no JSON, tenta do header Content-Range
                    if total == 0 and 'Content-Range' in r.headers:
                        content_range = r.headers['Content-Range']
                        if '/' in content_range:
                            total = int(content_range.split('/')[-1])
                            print(f"[DEBUG] Total extraído do Content-Range: {total}")
                except (ValueError, KeyError, IndexError) as e:
                    print(f"[WARNING] Erro ao extrair contagem total: {e}")
                    print(f"[DEBUG] Conteúdo da resposta: {r.text}")
            else:
                print(f"[WARNING] Falha ao obter contagem total: {r.status_code} - {r.text}")

            print(f"[DEBUG] Total de itens encontrados: {total}")

            # Se não há itens, retorna resposta vazia
            if total == 0:
                print("[DEBUG] Nenhum documento encontrado com os filtros fornecidos")
                return PaginatedResponse(
                    items=[],
                    total=0,
                    page=page,
                    page_size=page_size,
                    total_pages=0
                )

            # 2. Agora busca os itens da página atual
            print(f"[DEBUG] Buscando itens da página {page} (offset: {offset}, limit: {page_size})")

            # Usa o método _handle_response para processar a resposta
            items = self._handle_response(
                requests.get(url, headers=self._headers(), params=params),
                preserve_list=True
            )

            # Garante que items seja uma lista
            if not isinstance(items, list):
                print(f"[WARNING] Resposta inesperada do servidor (não é uma lista): {items}")
                items = []

            print(f"[DEBUG] Itens retornados: {len(items)}")

            # Calcula o total de páginas
            total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1

            # Cria a resposta paginada
            response = PaginatedResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages
            )

            print(f"[DEBUG] Resposta paginada criada: {len(items)} itens, {total} no total, {total_pages} páginas")

            return response

        except requests.exceptions.RequestException as e:
            error_msg = f"Erro na requisição HTTP: {str(e)}"
            print(f"[ERRO] {error_msg}")
            print(f"[DEBUG] Traceback: {traceback.format_exc()}")
            # Retorna uma resposta vazia em caso de erro
            return PaginatedResponse(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                total_pages=0
            )

        except Exception as e:
            error_msg = f"Erro inesperado ao buscar documentos: {str(e)}"
            print(f"[ERRO] {error_msg}")
            print(f"[DEBUG] Traceback: {traceback.format_exc()}")
            # Retorna uma resposta vazia em caso de erro
            return PaginatedResponse(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                total_pages=0
            )

    def get_document_history(self, fiscal_document_id: str) -> List[Dict[str, Any]]:
        """Get history events for a document."""
        url = self._table_url('document_history')
        params = {
            'select': '*',
            'fiscal_document_id': f'eq.{fiscal_document_id}',
            'order': 'created_at.desc'
        }
        r = requests.get(url, headers=self._headers(), params=params)
        result = self._handle_response(r, preserve_list=True)
        return result if isinstance(result, list) else []

    def save_history(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Save a history event.

        Args:
            event: Dictionary containing history event data. Must include 'fiscal_document_id'.

        Returns:
            Dict containing the saved history event or an error message if it's a temporary document.

        Raises:
            ValueError: If fiscal_document_id is missing or invalid.
            StorageError: If there's an error communicating with the storage backend.
        """
        try:
            # Verifica se o fiscal_document_id está presente
            fiscal_document_id = event.get('fiscal_document_id')

            # Para compatibilidade com versões antigas
            if not fiscal_document_id:
                fiscal_document_id = event.get('document_id')
                if fiscal_document_id:
                    event['fiscal_document_id'] = fiscal_document_id

            if not fiscal_document_id:
                raise ValueError("fiscal_document_id is required in the event data")

            # Verifica se é um documento temporário (marcado com _is_temporary)
            event_data = event.get('event_data', {})
            is_temporary = (
                event.get('_is_temporary', False) or 
                event_data.get('_is_temporary', False) or
                '_is_temporary' in str(event)
            )

            if is_temporary:
                print(f"[AVISO] Não é possível salvar histórico para documento temporário: {fiscal_document_id}")
                return {
                    'success': False,
                    'message': 'Histórico não salvo - documento temporário',
                    'temporary': True,
                    'document_id': fiscal_document_id
                }

            # Verifica se o fiscal_document_id existe na tabela fiscal_documents
            try:
                doc_url = self._table_url(f'fiscal_documents?id=eq.{fiscal_document_id}')
                r = requests.get(doc_url, headers=self._headers())

                if r.status_code == 200 and not r.json():
                    print(f"[AVISO] Documento não encontrado: {fiscal_document_id}")
                    return {
                        'success': False,
                        'message': f'Documento {fiscal_document_id} não encontrado',
                        'not_found': True,
                        'document_id': fiscal_document_id
                    }

            except requests.exceptions.RequestException as e:
                error_msg = f"Erro ao verificar documento: {str(e)}"
                print(f"[ERRO] {error_msg}")
                raise StorageError(error_msg) from e

            # Salva o histórico
            url = self._table_url('document_history')
            try:
                # Remove campos internos antes de salvar
                clean_event = {k: v for k, v in event.items() if not k.startswith('_')}
                if 'event_data' in clean_event and isinstance(clean_event['event_data'], dict):
                    clean_event['event_data'] = {k: v for k, v in clean_event['event_data'].items() 
                                               if not k.startswith('_')}

                # Adiciona timestamp se não existir
                if 'created_at' not in clean_event:
                    clean_event['created_at'] = datetime.now(timezone.utc).isoformat()

                print(f"[DEBUG] Enviando histórico para {url}")
                print(f"[DEBUG] Dados do histórico: {clean_event}")

                r = requests.post(url, json=clean_event, headers=self._headers(), timeout=10)
                r.raise_for_status()
                
                # Processa a resposta manualmente para garantir que temos o ID
                try:
                    saved_history = {}
                    
                    # Tenta extrair o ID do cabeçalho Location
                    if 'Location' in r.headers:
                        location = r.headers['Location']
                        if location:
                            # Extrai o ID da URL (assumindo formato padrão do Supabase)
                            import re
                            match = re.search(r'/([^/]+)$', location)
                            if match:
                                saved_history['id'] = match.group(1)
                    
                    # Tenta extrair do corpo da resposta (pode estar vazio)
                    if r.content:
                        try:
                            response_data = r.json()
                            print(f"[DEBUG] Resposta do servidor (raw): {response_data}")
                            
                            # Se for uma lista, pega o primeiro item
                            if isinstance(response_data, list) and response_data:
                                saved_history.update(response_data[0])
                            # Se for um dicionário, atualiza com os dados
                            elif isinstance(response_data, dict):
                                saved_history.update(response_data)
                            
                        except ValueError as json_error:
                            print(f"[AVISO] Resposta não é um JSON válido: {r.text}")
                            saved_history['raw_response'] = r.text
                    
                    # Se chegou aqui sem ID, tenta buscar o histórico mais recente
                    if not saved_history.get('id') and fiscal_document_id:
                        try:
                            print(f"[DEBUG] Tentando buscar histórico mais recente para o documento {fiscal_document_id}")
                            history = self.get_document_history(fiscal_document_id)
                            if history and isinstance(history, list) and history:
                                latest = max(history, key=lambda x: x.get('created_at', ''))
                                saved_history.update(latest)
                        except Exception as history_error:
                            print(f"[AVISO] Erro ao buscar histórico recente: {history_error}")
                    
                    # Se ainda não tem ID, gera um ID temporário
                    if not saved_history.get('id'):
                        import uuid
                        saved_history['id'] = str(uuid.uuid4())
                        saved_history['_temporary_id'] = True
                    
                    print(f"[DEBUG] Histórico processado: {saved_history}")
                    return saved_history
                    
                except Exception as json_error:
                    print(f"[ERRO] Erro inesperado ao processar resposta: {json_error}")
                    # Se não conseguir processar, retorna o que temos até agora
                    saved_history = saved_history or {}
                    saved_history.update({
                        'message': 'Histórico salvo, mas houve um erro ao processar a resposta',
                        'error': str(json_error),
                        'status_code': r.status_code,
                        'headers': dict(r.headers)
                    })
                    return saved_history
                
            except requests.exceptions.RequestException as e:
                error_msg = f"Erro ao salvar histórico: {str(e)}"
                if hasattr(e, 'response') and e.response is not None:
                    error_msg += f" - Status: {e.response.status_code} - Resposta: {e.response.text}"
                print(f"[ERRO] {error_msg}")
                raise StorageError(error_msg) from e
                
        except Exception as e:
            error_msg = f"Erro inesperado em save_history: {str(e)}"
            print(f"[ERRO CRÍTICO] {error_msg}")
            raise StorageError(error_msg) from e

    def upsert_fiscal_document(self, record: Dict[str, Any], conflict_target: str = 'id') -> Dict[str, Any]:
        """Upsert a document using POST with ?on_conflict."""
        url = self._table_url('fiscal_documents') + f"?on_conflict={conflict_target}"
        r = requests.post(url, json=record, headers=self._headers())
        return self._handle_response(r)

    def get_fiscal_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single fiscal document by ID."""
        url = self._table_url('fiscal_documents')
        params = {'select': '*', 'id': f'eq.{doc_id}'}
        
        try:
            response = requests.get(url, headers=self._headers(), params=params)
            if response.status_code == 200:
                documents = response.json()
                return documents[0] if documents else None
            return None
        except Exception as e:
            error_msg = f"Erro ao buscar documento {doc_id}: {str(e)}"
            print(f"[ERRO] {error_msg}")
            raise SupabaseStorageError(error_msg)
    
    def delete_fiscal_document(self, doc_id: str) -> bool:
        """Delete a fiscal document by ID."""
        url = f"{self._table_url('fiscal_documents')}?id=eq.{doc_id}"
        
        try:
            response = requests.delete(url, headers=self._headers())
            if response.status_code == 204:
                return True
            elif response.status_code == 404:
                return False
            else:
                raise SupabaseStorageError(f"Failed to delete document: {response.text}")
        except Exception as e:
            error_msg = f"Erro ao deletar documento {doc_id}: {str(e)}"
            print(f"[ERRO] {error_msg}")
            raise SupabaseStorageError(error_msg)
    
    def add_document_analysis(self, doc_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Add an analysis to a document."""
        # First, get the document to update
        document = self.get_fiscal_document(doc_id)
        if not document:
            raise SupabaseStorageError(f"Document {doc_id} not found")
        
        # Add analysis to document
        if 'analyses' not in document:
            document['analyses'] = []
        
        # Generate analysis ID
        analysis_id = len(document['analyses']) + 1
        analysis['id'] = analysis_id
        analysis['created_at'] = datetime.now(timezone.utc).isoformat()
        
        document['analyses'].append(analysis)
        document['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        # Update the document
        url = f"{self._table_url('fiscal_documents')}?id=eq.{doc_id}"
        
        try:
            response = requests.patch(
                url,
                headers=self._headers(),
                json={
                    'analyses': document['analyses'],
                    'updated_at': document['updated_at']
                }
            )
            
            if response.status_code != 200 and response.status_code != 204:
                raise SupabaseStorageError(f"Failed to update document: {response.text}")
                
            return analysis
            
        except Exception as e:
            error_msg = f"Erro ao adicionar análise ao documento {doc_id}: {str(e)}"
            print(f"[ERRO] {error_msg}")
            raise SupabaseStorageError(error_msg)
    
    # Backward compatibility
    def get_fiscal_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single document by ID. (Deprecated, use get_fiscal_document instead)"""
        return self.get_fiscal_document(doc_id)

    def insert_analysis(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Save an analysis record."""
        url = self._table_url('analyses')
        r = requests.post(url, json=record, headers=self._headers())
        return self._handle_response(r)


class StorageManager:
    """
    Centralized storage manager for the application.
    Ensures consistent storage status across all components.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StorageManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._storage = None
        self._status = "🔃 Inicializando armazenamento..."
        self._status_type = "info"  # Can be "info", "success", "warning", or "error"
        self._initialize_storage()
    
    def _initialize_storage(self):
        """Initialize the appropriate storage backend."""
        try:
            if not SUPABASE_URL or not SUPABASE_KEY:
                raise ValueError("URL ou chave do Supabase não configuradas")
                
            # Test Supabase connection
            self._storage = SupabaseStorage(SUPABASE_URL, SUPABASE_KEY)
            
            # Test the connection with a simple query
            try:
                self._storage.get_fiscal_documents(page=1, page_size=1)
                self._status = "✅ Conectado ao Supabase PostgreSQL"
                self._status_type = "success"
            except Exception as query_error:
                # If the table doesn't exist, we'll still consider the connection successful
                if "relation" in str(query_error) and "does not exist" in str(query_error):
                    self._status = "✅ Conectado ao Supabase (tabela fiscal_documents não encontrada)"
                    self._status_type = "warning"
                else:
                    raise query_error
                    
        except Exception as error:
            # Fall back to local storage
            self._storage = LocalJSONStorage()
            self._status = "⚠️ Usando armazenamento local (arquivos JSON)"
            self._status_type = "warning"
            print(f"Erro ao conectar ao Supabase: {str(error)}")
    
    @property
    def storage(self) -> StorageInterface:
        """Get the storage instance."""
        if self._storage is None:
            self._initialize_storage()
        return self._storage
    
    @property
    def status(self) -> str:
        """Get the current storage status message."""
        return self._status
    
    @property
    def status_type(self) -> str:
        """Get the status type for display (info, success, warning, error)."""
        return self._status_type
    
    def display_status(self, container=None):
        """Display the storage status in the provided container or the sidebar.
        
        Args:
            container: Streamlit container to display the status in. If None, uses the sidebar.
        """
        import streamlit as st
        display = container if container is not None else st.sidebar
        
        if self._status_type == "success":
            display.success(self._status)
        elif self._status_type == "warning":
            display.warning(self._status)
        elif self._status_type == "error":
            display.error(self._status)
        else:
            display.info(self._status)


# Global instance
storage_manager = StorageManager()

# Create a default instance for backward compatibility
STORAGE_PATH = Path('data') / 'processed_documents.json'
_default = LocalJSONStorage()

# For backward compatibility, expose default instance methods
save_document = _default.save_document
load_documents = _default.load_documents
list_documents = lambda **kwargs: _default.get_fiscal_documents(**kwargs)
save_history = _default.save_history
load_history = _default.get_document_history


def _ensure_dir():
    """Ensure data directory exists."""
    STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)


def save_document(record: Dict[str, Any]):
    _ensure_dir()
    arr = []
    if STORAGE_PATH.exists():
        try:
            arr = json.loads(STORAGE_PATH.read_text(encoding='utf-8'))
        except Exception:
            arr = []
    # ensure an id and created_at
    if 'id' not in record:
        record['id'] = str(uuid.uuid4())
    arr.append(record)
    STORAGE_PATH.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding='utf-8')
    return record['id']


def load_documents() -> List[Dict[str, Any]]:
    _ensure_dir()
    if not STORAGE_PATH.exists():
        return []
    try:
        return json.loads(STORAGE_PATH.read_text(encoding='utf-8'))
    except Exception:
        return []


def list_documents(filters: dict = None, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    """Return paginated documents and total count. Filters: issuer_cnpj or document_number partial match."""
    docs = load_documents()
    if filters:
        def match(d):
            for k, v in (filters.items() if filters else []):
                if not v:
                    continue
                # support nested parsed fields
                val = d.get(k) or (d.get('parsed') or {}).get(k) or (d.get('extracted_data') or {}).get(k)
                if val is None:
                    return False
                if v.lower() not in str(val).lower():
                    return False
            return True
        docs = [d for d in docs if match(d)]
    total = len(docs)
    start = (page - 1) * page_size
    end = start + page_size
    return {'total': total, 'items': docs[start:end], 'page': page, 'page_size': page_size}


HISTORY_PATH = Path('data') / 'document_history.json'


def _ensure_history():
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)


def save_history(event: Dict[str, Any]):
    _ensure_history()
    arr = []
    if HISTORY_PATH.exists():
        try:
            arr = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
        except Exception:
            arr = []
    if 'id' not in event:
        event['id'] = str(uuid.uuid4())
    arr.append(event)
    HISTORY_PATH.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding='utf-8')
    return event['id']


def load_history(fiscal_document_id: str = None) -> List[Dict[str, Any]]:
    _ensure_history()
    if not HISTORY_PATH.exists():
        return []
    try:
        arr = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
    except Exception:
        return []
    if fiscal_document_id:
        return [a for a in arr if a.get('fiscal_document_id') == fiscal_document_id]
    return arr
