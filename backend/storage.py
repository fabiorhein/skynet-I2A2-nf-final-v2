"""
Unified storage implementation for the application.
Supports both local JSON and Supabase backends.
"""
import json
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
        doc_id = event.get('document_id')
        if not doc_id:
            raise ValueError("document_id is required in the event data")
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

    def _handle_response(self, r: requests.Response) -> dict:
        """Processa a resposta da API do Supabase.
        
        Args:
            r: Resposta da requisição HTTP
            
        Returns:
            dict: Dados da resposta como dicionário
            
        Raises:
            SupabaseStorageError: Se houver erro na resposta
        """
        try:
            r.raise_for_status()
            
            # Tenta fazer parse do JSON
            try:
                response_data = r.json()
                # Se for uma lista, retorna o primeiro item
                if isinstance(response_data, list) and response_data:
                    return response_data[0]
                # Se for um dicionário, retorna ele mesmo
                elif isinstance(response_data, dict):
                    return response_data
                # Se for outro tipo, tenta converter para string e depois para dict
                else:
                    return {"response": str(response_data)}
                    
            except ValueError as e:
                # Se não for JSON, retorna o texto da resposta em um dicionário
                if r.text:
                    return {"message": r.text.strip()}
                return {"message": "Resposta vazia do servidor"}
                
        except requests.exceptions.HTTPError as e:
            # Tratamento de erros HTTP
            try:
                error_detail = r.json().get('message', r.text)
            except ValueError:
                error_detail = r.text or str(e)
                
            error_msg = f"Erro na requisição: {r.status_code} - {error_detail}"
            print(f"[ERRO] {error_msg}")
            raise SupabaseStorageError(error_msg)
            
        except Exception as e:
            error_msg = f"Erro inesperado ao processar resposta: {str(e)}"
            print(f"[ERRO] {error_msg}")
            raise SupabaseStorageError(error_msg)

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
            print(f"[DEBUG] Iniciando salvamento do documento. Campos recebidos: {list(document.keys())}")
            
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
            
            # Move raw_text para o nível superior se estiver em extracted_data
            if 'extracted_data' in prepared_record and isinstance(prepared_record['extracted_data'], dict):
                if 'raw_text' in prepared_record['extracted_data'] and not prepared_record.get('raw_text'):
                    prepared_record['raw_text'] = prepared_record['extracted_data'].pop('raw_text')
            
            # Garante que os campos de data estão no formato correto
            for date_field in ['uploaded_at', 'processed_at', 'issue_date']:
                if date_field in prepared_record and prepared_record[date_field]:
                    from datetime import datetime
                    try:
                        # Se a data estiver no formato DD/MM/YYYY, converte para YYYY-MM-DD
                        if isinstance(prepared_record[date_field], str) and '/' in prepared_record[date_field]:
                            day, month, year = prepared_record[date_field].split('/')
                            prepared_record[date_field] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        # Se for um objeto datetime, converte para string
                        elif isinstance(prepared_record[date_field], datetime):
                            prepared_record[date_field] = prepared_record[date_field].isoformat()
                    except (ValueError, AttributeError) as e:
                        print(f"[AVISO] Erro ao formatar data {date_field}: {e}")
                        del prepared_record[date_field]  # Remove o campo se não for possível converter
                elif date_field in prepared_record and not prepared_record[date_field]:
                    # Se o campo existir mas estiver vazio, define como None
                    prepared_record[date_field] = None
            
            # Log para depuração (sem expor dados sensíveis)
            debug_record = prepared_record.copy()
            if 'raw_text' in debug_record and len(debug_record['raw_text']) > 100:
                debug_record['raw_text'] = debug_record['raw_text'][:100] + '... (truncado)'
            print(f"[DEBUG] Dados a serem enviados para o Supabase: {debug_record}")
            
            # Prepara a URL e os cabeçalhos
            url = self._table_url('fiscal_documents')
            print(f"[DEBUG] Enviando requisição para: {url}")
            
            try:
                # Faz a requisição POST para o Supabase
                response = requests.post(
                    url, 
                    json=prepared_record, 
                    headers=self._headers(), 
                    timeout=30
                )
                
                print(f"[DEBUG] Resposta do servidor - Status: {response.status_code}")
                
                # Processa a resposta
                result = self._handle_response(response)
                
                # Se chegou até aqui, o documento foi salvo com sucesso
                print("[SUCESSO] Documento salvo com sucesso no Supabase")
                
                # Adiciona os dados de validação ao resultado
                if 'validation_status' in prepared_record:
                    result['validation_status'] = prepared_record['validation_status']
                if 'validation_details' in prepared_record:
                    result['validation_details'] = prepared_record['validation_details']
                
                # Retorna o resultado com os dados completos
                return {
                    'id': result.get('id'),
                    'success': True,
                    'message': 'Documento salvo com sucesso',
                    'data': result,
                    'validation_status': prepared_record.get('validation_status', 'pending'),
                    'validation_details': prepared_record.get('validation_details', {})
                }
                
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
        """Return paginated fiscal documents with total count."""
        url = self._table_url('fiscal_documents')
        offset = (page - 1) * page_size

        # Build query params
        params: Dict[str, Any] = {'select': '*', 'limit': page_size, 'offset': offset}
        if filters:
            for k, v in filters.items():
                if v is None or v == '':
                    continue
                # ilike for case-insensitive partial match
                params[k] = f'ilike.*{v}*'

        # Get documents for current page
        r = requests.get(url, headers=self._headers(), params=params)
        items = self._handle_response(r)
        if not isinstance(items, list):
            items = [items] if items else []

        # Get total count using COUNT query
        count_params = {'select': 'id', 'count': 'exact'}
        if filters:
            count_params.update({k: v for k, v in params.items() if k not in ['select', 'limit', 'offset']})
        
        r = requests.get(
            url,
            headers={**self._headers(), 'Prefer': 'count=exact'},
            params=count_params
        )
        total = int(r.headers.get('Content-Range', '0-0/0').split('/')[-1])

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size
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
        result = self._handle_response(r)
        return result if isinstance(result, list) else []

    def save_history(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Save a history event."""
        url = self._table_url('document_history')
        r = requests.post(url, json=event, headers=self._headers())
        return self._handle_response(r)

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
