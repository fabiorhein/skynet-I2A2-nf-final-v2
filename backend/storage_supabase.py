"""Supabase storage backend implementation.

Uses Supabase REST API to store and query documents. Implements the StorageInterface.
"""
from typing import Dict, Any, List, Optional
import requests
from .storage_interface import StorageInterface, PaginatedResponse, StorageError


class SupabaseStorageError(Exception):
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

    def save_document(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Salva um documento fiscal no Supabase.
        
        Args:
            record: Dicionário contendo os dados do documento a ser salvo
            
        Returns:
            Dict[str, Any]: Dicionário com os dados do documento salvo, incluindo o ID gerado
            
        Raises:
            SupabaseStorageError: Se ocorrer algum erro durante o salvamento
        """
        # Cria uma cópia do registro para não modificar o original
        db_record = record.copy()
        
        try:
            print(f"[DEBUG] Iniciando salvamento do documento. Campos recebidos: {list(record.keys())}")
            
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
            for date_field in ['uploaded_at', 'processed_at']:
                if date_field in prepared_record and not prepared_record[date_field]:
                    from datetime import datetime, timezone
                    prepared_record[date_field] = datetime.now(timezone.utc).isoformat()
            
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

        return {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size
        }

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

    # Additional Supabase-specific methods
    def upsert_fiscal_document(self, record: Dict[str, Any], conflict_target: str = 'id') -> Dict[str, Any]:
        """Upsert a document using POST with ?on_conflict."""
        url = self._table_url('fiscal_documents') + f"?on_conflict={conflict_target}"
        r = requests.post(url, json=record, headers=self._headers())
        return self._handle_response(r)

    def get_fiscal_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single document by ID."""
        url = self._table_url('fiscal_documents')
        params = {'select': '*', 'id': f'eq.{doc_id}'}
        r = requests.get(url, headers=self._headers(), params=params)
        result = self._handle_response(r)
        if isinstance(result, list):
            return result[0] if result else None
        return result

    def insert_analysis(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Save an analysis record."""
        url = self._table_url('analyses')
        r = requests.post(url, json=record, headers=self._headers())
        return self._handle_response(r)
