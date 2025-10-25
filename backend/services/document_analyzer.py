"""
Document Analyzer Service

Fornece funcionalidades avançadas de análise de documentos fiscais
usando RAG (Retrieval-Augmented Generation).
"""
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class DocumentAnalyzer:
    """Serviço de análise de documentos fiscais."""
    
    def __init__(self, supabase_client):
        self.supabase = supabase_client
    
    async def get_documents_summary(self, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Obtém um resumo dos documentos com base nos filtros fornecidos."""
        try:
            query = self.supabase.table('fiscal_documents').select('*')
            
            # Aplicar filtros
            if filters:
                if 'date' in filters:
                    date = filters['date']
                    if isinstance(date, str):
                        date = datetime.fromisoformat(date)
                    next_day = date + timedelta(days=1)
                    query = query.gte('created_at', date.isoformat()).lt('created_at', next_day.isoformat())
                
                if 'document_type' in filters:
                    query = query.eq('document_type', filters['document_type'])
            
            result = query.execute()
            documents = result.data if result.data else []
            
            # Processar e resumir os documentos
            summary = {
                'total_documents': len(documents),
                'by_type': {},
                'by_issuer': {},
                'total_value': 0.0,
                'documents': []
            }
            
            for doc in documents:
                # Contagem por tipo
                doc_type = doc.get('document_type', 'Desconhecido')
                summary['by_type'][doc_type] = summary['by_type'].get(doc_type, 0) + 1
                
                # Contagem por emissor
                issuer = doc.get('issuer_cnpj', 'Desconhecido')
                summary['by_issuer'][issuer] = summary['by_issuer'].get(issuer, 0) + 1
                
                # Extrair valor total se disponível
                try:
                    if doc.get('extracted_data') and 'total' in doc['extracted_data']:
                        total = float(doc['extracted_data']['total'])
                        summary['total_value'] += total
                except (ValueError, TypeError):
                    pass
                
                # Adicionar documento à lista
                summary['documents'].append({
                    'id': doc['id'],
                    'file_name': doc.get('file_name', 'Sem nome'),
                    'document_type': doc_type,
                    'issuer_cnpj': issuer,
                    'created_at': doc.get('created_at'),
                    'validation_status': doc.get('validation_status', 'não validado')
                })
            
            return summary
            
        except Exception as e:
            logger.error(f"Erro ao resumir documentos: {e}")
            raise
    
    async def search_documents(self, query: str, limit: int = 5) -> List[Dict]:
        """Busca documentos relevantes usando busca simples por texto."""
        try:
            # Busca simples por texto usando o método mais compatível
            search_term = f'%{query}%'

            # Tentar busca direta primeiro
            result = self.supabase.table('fiscal_documents').select('*').or_(
                f'file_name.ilike.{search_term},document_type.ilike.{search_term},document_number.ilike.{search_term},issuer_cnpj.ilike.{search_term}'
            ).order('created_at', desc=True).limit(limit).execute()

            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Erro na busca de documentos: {e}")
            return []
