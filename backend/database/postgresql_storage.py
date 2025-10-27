"""
PostgreSQL storage implementation using psycopg2 for direct database access.
This replaces the HTTP-based SupabaseStorage for better performance.
"""
import json
import logging
import re
import traceback
from typing import Dict, Any, List, Optional, Union

# Import psycopg2 only when needed to avoid import errors
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

from datetime import datetime, timezone, UTC

from config import DATABASE_CONFIG
from .base_storage import (
    StorageInterface,
    PaginatedResponse,
    StorageError,
    generate_id,
    get_current_timestamp
)

logger = logging.getLogger(__name__)


class PostgreSQLStorageError(StorageError):
    """PostgreSQL-specific storage errors."""
    pass


class PostgreSQLStorage(StorageInterface):
    """PostgreSQL storage implementation using psycopg2."""

    def __init__(self):
        if not PSYCOPG2_AVAILABLE:
            raise PostgreSQLStorageError(
                "psycopg2 is not available. Install with: pip install psycopg2-binary"
            )

        self.db_config = DATABASE_CONFIG
        self._connection = None

    def _get_connection(self):
        """Get database connection, creating if necessary."""
        if self._connection is None or self._connection.closed:
            try:
                self._connection = psycopg2.connect(**self.db_config)
                logger.info("Database connection established")
            except Exception as e:
                logger.error(f"Failed to connect to database: {e}")
                raise PostgreSQLStorageError(f"Database connection failed: {e}")
        return self._connection

    def _execute_query(self, query: str, params: tuple = None, fetch: str = None):
        """Execute a query and return results based on fetch type."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query, params or ())

                if fetch == "all":
                    return cursor.fetchall()
                elif fetch == "one":
                    return cursor.fetchone()
                elif fetch == "count":
                    return cursor.fetchone()['count']
                else:
                    return cursor.rowcount

        except psycopg2.Error as e:
            logger.error(f"Database query failed: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise PostgreSQLStorageError(f"Query execution failed: {e}")

    def _get_table_columns(self) -> List[str]:
        """Get list of existing columns in fiscal_documents table."""
        try:
            query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'fiscal_documents'
            ORDER BY ordinal_position
            """
            result = self._execute_query(query, fetch="all")
            return [row['column_name'] for row in result] if result else []
        except Exception as e:
            logger.error(f"Error getting table columns: {e}")
            # Return a basic set of known columns if query fails
            return ['id', 'file_name', 'document_type', 'document_number', 'issuer_cnpj',
                   'issuer_name', 'extracted_data', 'validation_status', 'classification',
                   'created_at', 'updated_at', 'cfop', 'issue_date', 'total_value',
                   'validation_details', 'raw_text', 'uploaded_at', 'processed_at']

    def save_fiscal_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Save a fiscal document to PostgreSQL."""
        # Generate ID if not provided
        if "id" not in document or not document["id"]:
            document["id"] = generate_id()
            document["created_at"] = get_current_timestamp()

        document["updated_at"] = get_current_timestamp()

        # Prepare the query
        columns = list(document.keys())
        values = list(document.values())
        placeholders = ", ".join(["%s"] * len(columns))

        # Convert datetime objects to strings for JSON serialization
        for i, value in enumerate(values):
            if isinstance(value, datetime):
                values[i] = value.isoformat()
            elif columns[i] == 'issue_date' and value is not None:
                # Convert date strings to proper format if needed
                try:
                    if isinstance(value, str) and '/' in value:
                        # Try to parse Brazilian format DD/MM/YYYY
                        if len(value.split('/')) == 3:
                            parts = value.split('/')
                            if len(parts[0]) == 2 and len(parts[1]) == 2:  # DD/MM/YYYY
                                dt = datetime.strptime(value, '%d/%m/%Y')
                                values[i] = dt.strftime('%Y-%m-%dT00:00:00Z')
                            elif len(parts[2]) == 2:  # DD/MM/YY
                                dt = datetime.strptime(value, '%d/%m/%y')
                                values[i] = dt.strftime('%Y-%m-%dT00:00:00Z')
                except (ValueError, IndexError):
                    logger.warning(f"Could not parse date format: {value}")

        # Debug: Log all fields and their types
        logger.debug("=== DEBUG save_fiscal_document ===")
        for col, value in zip(columns, values):
            logger.debug(f"Field: {col} = {type(value)} - {str(value)[:100]}...")
        logger.debug("=== END DEBUG ===")

        # Convert numeric fields from Brazilian format to American format
        numeric_fields = ['total_value', 'base_calculo_icms', 'valor_icms', 'base_calculo_icms_st', 'valor_icms_st']
        for i, (col, value) in enumerate(zip(columns, values)):
            if col in numeric_fields and value is not None:
                try:
                    # Convert Brazilian number format to float
                    if isinstance(value, str):
                        # Remove currency symbols and spaces
                        clean_value = re.sub(r'[R$\s]', '', value)
                        # Convert Brazilian format (1.234,56) to American format (1234.56)
                        if ',' in clean_value and '.' in clean_value:
                            clean_value = clean_value.replace('.', '').replace(',', '.')
                        elif ',' in clean_value:
                            clean_value = clean_value.replace(',', '.')
                        values[i] = float(clean_value)
                        logger.debug(f"Converted {col} from '{value}' to {values[i]}")
                    else:
                        values[i] = float(value)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not convert {col} value '{value}' to number: {e}")
                    values[i] = 0.0

        # Check if columns exist in the table before executing query
        try:
            # Get existing columns from the table
            existing_columns = self._get_table_columns()
            logger.debug(f"Existing columns in fiscal_documents: {existing_columns}")

            # Filter out columns that don't exist in the table
            filtered_columns = []
            filtered_values = []
            for col, value in zip(columns, values):
                if col in existing_columns:
                    filtered_columns.append(col)
                    filtered_values.append(value)
                else:
                    logger.warning(f"Column '{col}' does not exist in fiscal_documents table, skipping")

            if not filtered_columns:
                raise PostgreSQLStorageError("No valid columns to save")

            columns = filtered_columns
            values = filtered_values
            placeholders = ", ".join(["%s"] * len(columns))

        except Exception as e:
            logger.error(f"Error checking table columns: {e}")
            # Continue with original columns if check fails

        query = f"""
        INSERT INTO fiscal_documents ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT (id)
        DO UPDATE SET
            {", ".join([f"{col} = EXCLUDED.{col}" for col in columns if col != "id"])}
        RETURNING *
        """

        try:
            # Debug: Log query and parameters
            logger.debug(f"Executing query: {query}")
            logger.debug(f"Parameters: {len(tuple(values))} params")
            for i, (col, val) in enumerate(zip(columns, values)):
                logger.debug(f"  Param {i}: {col} = {type(val)} - {str(val)[:100]}...")

            result = self._execute_query(query, tuple(values), "one")
            if result:
                # Convert result back to dict format expected by the interface
                saved_doc = dict(result)
                logger.info(f"Document saved successfully. ID: {saved_doc['id']}")
                return saved_doc
            else:
                raise PostgreSQLStorageError("Failed to save document - no result returned")

        except Exception as e:
            logger.error(f"Error saving document: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Columns: {columns}")
            logger.error(f"Values types: {[type(v).__name__ for v in values]}")
            raise PostgreSQLStorageError(f"Failed to save document: {e}")

    def get_fiscal_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single fiscal document by ID."""
        query = "SELECT * FROM fiscal_documents WHERE id = %s"
        result = self._execute_query(query, (doc_id,), "one")
        if result:
            # Convert result back to dict format expected by the interface
            doc = dict(result)

            # Convert JSONB fields back from string to dict/list
            jsonb_fields = ['extracted_data', 'classification', 'validation_details', 'metadata', 'document_data']
            for field in jsonb_fields:
                if field in doc and doc[field] is not None:
                    if isinstance(doc[field], str):
                        try:
                            import json
                            doc[field] = json.loads(doc[field])
                        except (json.JSONDecodeError, TypeError):
                            # Keep as string if cannot decode
                            pass

            return doc
        return None

    def get_fiscal_documents(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters
    ) -> PaginatedResponse:
        """Get a paginated list of fiscal documents with optional filtering."""

        # Handle page_size=0 as "use default"
        if page_size <= 0:
            page_size = 10  # Default page size

        # Build WHERE clause
        where_conditions = []
        params = []
        param_index = 1

        for key, value in filters.items():
            if value is not None and value != "":
                # Campos UUID devem usar igualdade exata, não ILIKE
                uuid_fields = ['id', 'fiscal_document_id', 'session_id']  # Campos UUID em várias tabelas
                if key in uuid_fields:
                    where_conditions.append(f"{key} = %s")
                    params.append(value)
                elif key in ['issuer_cnpj', 'recipient_cnpj']:
                    # Remove formatting for CNPJ search
                    value = ''.join(filter(str.isdigit, str(value)))
                    where_conditions.append(f"REPLACE({key}, '.', '') ILIKE %s")
                    params.append(f"%{value}%")
                else:
                    where_conditions.append(f"{key} ILIKE %s")
                    params.append(f"%{value}%")
                param_index += 1

        where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""

        # Get total count
        count_query = f"SELECT COUNT(*) FROM fiscal_documents{where_clause}"
        total = self._execute_query(count_query, tuple(params), "count")

        # Get paginated results
        offset = (page - 1) * page_size
        query = f"""
        SELECT * FROM fiscal_documents{where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """

        items = self._execute_query(query, tuple(params) + (page_size, offset), "all")
        items = [dict(item) for item in items] if items else []

        # Convert JSONB fields back from string to dict/list for each item
        jsonb_fields = ['extracted_data', 'classification', 'validation_details', 'metadata', 'document_data']
        for item in items:
            for field in jsonb_fields:
                if field in item and item[field] is not None:
                    if isinstance(item[field], str):
                        try:
                            import json
                            item[field] = json.loads(item[field])
                        except (json.JSONDecodeError, TypeError):
                            # Keep as string if cannot decode
                            pass

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )

    def delete_fiscal_document(self, doc_id: str) -> bool:
        """Delete a fiscal document by ID."""
        query = "DELETE FROM fiscal_documents WHERE id = %s"
        result = self._execute_query(query, (doc_id,))
        return result > 0

    def add_document_analysis(self, doc_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Add an analysis to a document."""
        # First, get the document
        document = self.get_fiscal_document(doc_id)
        if not document:
            raise PostgreSQLStorageError(f"Document {doc_id} not found")

        # Add analysis to document
        if "analyses" not in document:
            document["analyses"] = []

        # Generate analysis ID
        analysis_id = len(document["analyses"]) + 1
        analysis["id"] = analysis_id
        analysis["created_at"] = get_current_timestamp()

        document["analyses"].append(analysis)
        document["updated_at"] = get_current_timestamp()

        # Update the document
        return self.save_fiscal_document(document)

    def save_history(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Save a history event.
        
        Args:
            event: Dicionário contendo os dados do evento, incluindo:
                - fiscal_document_id: ID do documento fiscal relacionado
                - event_type: Tipo do evento (ex: 'created', 'updated', 'validated')
                - event_data: Dados adicionais do evento (será convertido para JSON)
                - id: Opcional, será gerado se não fornecido
                - created_at: Opcional, será definido como agora se não fornecido
                
        Returns:
            Dicionário com os dados do evento salvo, incluindo o ID gerado
            
        Raises:
            ValueError: Se fiscal_document_id não for fornecido
            PostgreSQLStorageError: Se ocorrer um erro ao salvar no banco de dados
        """
        # Fazer uma cópia para não modificar o dicionário original
        event = event.copy()
        
        if "fiscal_document_id" not in event:
            # Para compatibilidade com versões antigas
            if "document_id" in event:
                event["fiscal_document_id"] = event.pop("document_id")
            else:
                raise ValueError("fiscal_document_id é obrigatório nos dados do evento")

        # Gerar ID e timestamp se não fornecidos
        if "id" not in event:
            event["id"] = generate_id()
        if "created_at" not in event:
            event["created_at"] = get_current_timestamp()

        # Converter event_data para JSON se for um dicionário
        if "event_data" in event and event["event_data"] is not None:
            import json
            if not isinstance(event["event_data"], (str, bytes, bytearray)):
                event["event_data"] = json.dumps(event["event_data"], ensure_ascii=False)

        # Preparar a query
        columns = list(event.keys())
        values = list(event.values())
        placeholders = ", ".join(["%s"] * len(columns))

        query = f"""
        INSERT INTO document_history ({", ".join(columns)})
        VALUES ({placeholders})
        RETURNING *
        """

        try:
            result = self._execute_query(query, tuple(values), "one")
            if result:
                saved_event = dict(result)
                # Converter event_data de volta para dicionário se for uma string JSON
                if 'event_data' in saved_event and isinstance(saved_event['event_data'], str):
                    try:
                        import json
                        saved_event['event_data'] = json.loads(saved_event['event_data'])
                    except (json.JSONDecodeError, TypeError):
                        # Maném como string se não for possível decodificar
                        pass
                logger.debug(f"Evento de histórico salvo com sucesso. ID: {saved_event['id']}")
                return saved_event
            else:
                raise PostgreSQLStorageError("Falha ao salvar o evento de histórico - nenhum resultado retornado")

        except Exception as e:
            logger.error(f"Erro ao salvar histórico: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {values}")
            raise PostgreSQLStorageError(f"Falha ao salvar histórico: {e}")

    def get_document_history(self, fiscal_document_id: str) -> List[Dict[str, Any]]:
        """Obtém o histórico de eventos para um documento.
        
        Args:
            fiscal_document_id: ID do documento fiscal
            
        Returns:
            Lista de dicionários contendo os eventos de histórico do documento,
            com event_data convertido de volta para dicionário quando apropriado
        """
        query = """
        SELECT * FROM document_history
        WHERE fiscal_document_id = %s
        ORDER BY created_at DESC
        """
        try:
            results = self._execute_query(query, (fiscal_document_id,), "all")
            
            if not results:
                return []
                
            # Converter os resultados para dicionários e processar event_data
            history_events = []
            for result in results:
                event = dict(result)
                
                # Converter event_data de volta para dicionário se for uma string JSON
                if 'event_data' in event and event['event_data'] is not None:
                    if isinstance(event['event_data'], str):
                        try:
                            import json
                            event['event_data'] = json.loads(event['event_data'])
                        except (json.JSONDecodeError, TypeError):
                            # Manter como está se não for possível decodificar
                            pass
                    # Se for um objeto JSONB do PostgreSQL, já deve vir como dicionário
                    
                history_events.append(event)
                
            return history_events
            
        except Exception as e:
            logger.error(f"Erro ao recuperar histórico do documento {fiscal_document_id}: {e}")
            # Retornar lista vazia em caso de erro para não quebrar o fluxo da aplicação
            return []

    def close(self):
        """Close the database connection."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            logger.info("Database connection closed")
