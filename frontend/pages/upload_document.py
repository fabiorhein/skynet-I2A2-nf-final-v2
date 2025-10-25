"""Upload Document page for processing XML/PDF/image files."""
import logging
import streamlit as st
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from backend.agents import coordinator
from backend.tools.ocr_processor import ocr_text_to_document

# Configuração do logger
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('upload_document.log')
    ]
)


def _validate_document_data(data: any) -> bool:
    """Valida se os dados extraídos estão no formato esperado."""
    if not isinstance(data, dict):
        st.error(f"Erro: Dados em formato inválido. Esperado dicionário, obtido {type(data).__name__}")
        return False
    
    required_fields = ['emitente', 'itens', 'total']
    missing = [field for field in required_fields if field not in data]
    if missing:
        st.error(f"Erro: Campos obrigatórios ausentes: {', '.join(missing)}")
        return False
        
    if not isinstance(data.get('itens'), list):
        st.error("Erro: O campo 'itens' deve ser uma lista")
        return False
        
    return True

def _prepare_document_record(uploaded, parsed, classification=None) -> dict:
    """Prepara o registro do documento para ser salvo."""
    if not isinstance(parsed, dict):
        raise ValueError("Dados do documento devem ser um dicionário")
    
    # Extrair dados de validação da classificação, se disponível
    validation = {}
    if classification and isinstance(classification, dict):
        validation = classification.get('validacao', {})
    
    # Obter o status de validação ou definir como 'pending' se não houver
    validation_status = validation.get('status', 'pending')
    
    # Extrair dados do emitente
    emitente = parsed.get('emitente', {})
    
    # Extrair dados do destinatário, se disponível
    destinatario = parsed.get('destinatario', {})
    
    # Extrair dados de itens, se disponível
    itens = parsed.get('itens', [])
    
    # Extrair totais, se disponível
    totais = parsed.get('totals', {})
    
    # Preparar dados do documento
    doc_data = {
        'file_name': str(uploaded.name if hasattr(uploaded, 'name') else 'documento_sem_nome.pdf'),
        'document_type': parsed.get('document_type', 'CTe' if 'cte' in str(uploaded.name).lower() else 'NFe'),
        'document_number': parsed.get('numero') or parsed.get('nNF') or parsed.get('nCT'),
        'issuer_cnpj': emitente.get('cnpj') or emitente.get('CNPJ'),
        'issuer_name': emitente.get('razao_social') or emitente.get('nome') or emitente.get('xNome', ''),
        'recipient_cnpj': destinatario.get('cnpj') or destinatario.get('CNPJ'),
        'recipient_name': destinatario.get('razao_social') or destinatario.get('nome') or destinatario.get('xNome', ''),
        'issue_date': parsed.get('data_emissao') or parsed.get('dhEmi'),
        'total_value': parsed.get('total') or totais.get('valorTotal') or 0.0,
        'cfop': parsed.get('cfop') or (itens[0].get('cfop') if itens else None),
        'extracted_data': parsed,
        'validation_status': validation_status,
        'validation_details': {
            'issues': validation.get('issues', []),
            'warnings': validation.get('warnings', []),
            'validations': validation.get('validations', {})
        },
        'classification': classification or {},
        'raw_text': parsed.get('raw_text', ''),
        'uploaded_at': datetime.now(ZoneInfo('UTC')).isoformat(),
        'processed_at': datetime.now(ZoneInfo('UTC')).isoformat(),
        # Adiciona metadados adicionais para facilitar buscas
        'metadata': {
            'has_issues': len(validation.get('issues', [])) > 0,
            'has_warnings': len(validation.get('warnings', [])) > 0,
            'item_count': len(itens),
            'document_subtype': parsed.get('tipoDocumento') or 'Outros'
        }
    }
    
    # Garante que todos os campos necessários tenham valores padrão
    doc_data.setdefault('document_type', 'Outros')
    doc_data.setdefault('document_number', 'SEM_NUMERO')
    doc_data.setdefault('issuer_cnpj', '00000000000000')
    doc_data.setdefault('issuer_name', 'Emitente não identificado')
    doc_data.setdefault('total_value', 0.0)
    
    return doc_data

def render(storage):
    """Render the upload document page."""
    st.header('📄 Upload de Documento Fiscal')
    st.caption('Suporta XML, PDF ou imagens (JPG, PNG)')
    
    uploaded = st.file_uploader(
        'Arraste ou selecione um arquivo',
        type=['xml', 'pdf', 'png', 'jpg', 'jpeg'],
        help='Envie um documento fiscal para processamento automático.'
    )
    
    if not uploaded:
        st.info('Por favor, selecione um arquivo para começar.')
        return
        
    # Save uploaded file to temporary location
    tmp = Path('tmp_upload')
    tmp.mkdir(exist_ok=True, parents=True)
    dest = tmp / uploaded.name
    
    try:
        with open(dest, 'wb') as f:
            f.write(uploaded.getbuffer())
    except Exception as e:
        st.error(f'Erro ao salvar arquivo temporário: {str(e)}')
        return

    file_type = dest.suffix.lower()
    
    with st.spinner(f'Processando {file_type.upper()}...'):
        try:
            # Extract data based on file type
            if file_type == '.xml':
                parsed = coordinator.run_task('extract', {'path': str(dest)})
                
                if not _validate_document_data(parsed):
                    return
                    
                st.subheader('✅ Dados extraídos')
                with st.expander('Visualizar dados extraídos', expanded=False):
                    st.json(parsed)
                
                # Classify document
                with st.spinner('Classificando documento...'):
                    classification = coordinator.run_task('classify', {'parsed': parsed})
                    st.subheader('🏷️ Classificação')
                    st.json(classification)
                
                # Exibir resultados da validação
                validation = classification.get('validacao', {})
                
                # Mostrar status da validação
                status = validation.get('status', 'unknown')
                status_emoji = {
                    'success': '✅',
                    'warning': '⚠️',
                    'error': '❌',
                    'pending': '⏳'
                }.get(status, '❓')
                
                st.subheader(f'{status_emoji} Status da Validação: {status.upper()}')
                
                # Mostrar problemas e avisos
                col1, col2 = st.columns(2)
                
                with col1:
                    if validation.get('issues'):
                        with st.expander(f'❌ {len(validation["issues"])} Problemas Encontrados', expanded=True):
                            for issue in validation['issues']:
                                st.error(issue)
                    else:
                        st.success('✅ Nenhum problema crítico encontrado')
                
                with col2:
                    if validation.get('warnings'):
                        with st.expander(f'⚠️ {len(validation["warnings"])} Avisos', expanded=False):
                            for warning in validation['warnings']:
                                st.warning(warning)
                    else:
                        st.info('ℹ️ Nenhum aviso')
                
                # Mostrar detalhes da validação
                with st.expander('🔍 Detalhes da Validação', expanded=False):
                    validations = validation.get('validations', {})
                    
                    # Validação do Emitente
                    if 'emitente' in validations:
                        st.subheader('Emitente')
                        emit = validations['emitente']
                        cols = st.columns(2)
                        cols[0].metric("CNPJ Válido", "✅ Sim" if emit.get('cnpj') else "❌ Não")
                        cols[1].metric("Razão Social", "✅ Informada" if emit.get('razao_social') else "⚠️ Ausente")
                    
                    # Validação de Itens
                    if 'itens' in validations:
                        st.subheader('Itens')
                        itens = validations['itens']
                        cols = st.columns(2)
                        cols[0].metric("Itens Encontrados", 
                                    f"✅ {len(parsed.get('itens', []))}" if itens.get('has_items') else "❌ Nenhum")
                        cols[1].metric("Itens Válidos", 
                                    "✅ Todos" if itens.get('all_valid') else "⚠️ Alguns itens inválidos")
                    
                    # Validação de Totais
                    if 'totals' in validations:
                        st.subheader('Totais')
                        totais = validations['totals']
                        if totais.get('valid') is not None:
                            if totais['valid']:
                                st.success("✅ Soma dos itens confere com o total do documento")
                            else:
                                st.error(f"❌ Diferença de R$ {abs(totais.get('document_total', 0) - totais.get('calculated_total', 0)):.2f} nos totais")
                
                # Preparar e salvar o documento
                try:
                    record = _prepare_document_record(uploaded, parsed, classification)
                    saved = storage.save_document(record)
                    
                    # Debug: Exibir a estrutura da resposta salva
                    logger.info(f"Resposta do save_document: {saved}")
                    
                    # Função auxiliar para extrair ID de forma robusta
                    def extract_document_id(response):
                        """Extrai o ID do documento da resposta de forma robusta."""
                        if not response:
                            return None
                        
                        # Se for um dicionário
                        if isinstance(response, dict):
                            # Tenta chaves comuns
                            for key in ['id', 'ID', 'document_id', 'doc_id', 'fiscal_document_id']:
                                if key in response and response[key]:
                                    return str(response[key]).strip()
                            
                            # Tenta em estruturas aninhadas
                            if 'data' in response and isinstance(response['data'], dict):
                                for key in ['id', 'ID', 'document_id', 'doc_id', 'fiscal_document_id']:
                                    if key in response['data'] and response['data'][key]:
                                        return str(response['data'][key]).strip()
                            
                            # Se data for uma lista
                            if 'data' in response and isinstance(response['data'], list) and response['data']:
                                first_item = response['data'][0]
                                if isinstance(first_item, dict):
                                    for key in ['id', 'ID', 'document_id', 'doc_id', 'fiscal_document_id']:
                                        if key in first_item and first_item[key]:
                                            return str(first_item[key]).strip()
                        
                        # Se for uma lista
                        elif isinstance(response, list) and response:
                            first_item = response[0]
                            if isinstance(first_item, dict):
                                for key in ['id', 'ID', 'document_id', 'doc_id', 'fiscal_document_id']:
                                    if key in first_item and first_item[key]:
                                        return str(first_item[key]).strip()
                        
                        return None
                    
                    # Extrai o ID usando a função auxiliar
                    document_id = extract_document_id(saved)
                    logger.info(f"ID do documento obtido: {document_id}")
                    
                    # Se encontrou o ID, salva o histórico
                    if document_id and hasattr(storage, 'save_history'):
                        try:
                            history_data = {
                                'fiscal_document_id': document_id,
                                'event_type': 'created',
                                'event_data': {
                                    'source': 'xml_upload',
                                    'file_type': file_type,
                                    'validation_status': record.get('validation_status', 'pending'),
                                    'document_number': record.get('document_number', ''),
                                    'issuer_cnpj': record.get('issuer_cnpj', '')
                                },
                                'created_at': datetime.now(ZoneInfo('UTC')).isoformat()
                            }
                            
                            logger.info(f"Tentando salvar histórico: {history_data}")
                            storage.save_history(history_data)
                            logger.info("Histórico salvo com sucesso")
                            
                        except Exception as history_error:
                            error_msg = f'Erro ao salvar histórico: {str(history_error)}'
                            st.warning(f'Documento salvo, mas houve um erro ao registrar o histórico.')
                            logger.error(error_msg, exc_info=True)
                    elif not document_id:
                        logger.warning('Documento salvo, mas não foi possível obter o ID para registrar o histórico.')
                        logger.warning(f'Resposta completa do save_document: {saved}')
                    
                    st.success('✅ Documento processado e salvo com sucesso!')
                    
                    # Debug: Exibir o ID do documento salvo
                    if document_id:
                        st.info(f'ID do documento: {document_id}')
                    else:
                        st.warning('Não foi possível obter o ID do documento salvo. Verifique os logs para mais detalhes.')
                    
                except Exception as e:
                    st.error(f'Erro ao salvar documento: {str(e)}')
                    st.exception(e)  # Show full traceback in logs
            
            else:  # PDF/Image
                st.info('Processando documento não-XML via OCR...')
                parsed = coordinator.run_task('extract', {'path': str(dest)})
                
                # Tratamento de erros com mensagens claras
                if isinstance(parsed, dict) and parsed.get('error'):
                    error_code = parsed.get('error', 'unknown')
                    error_message = parsed.get('message', 'Erro desconhecido na extração')
                    
                    if error_code == 'empty_ocr':
                        st.error(f'''
                            ❌ Não foi possível extrair texto do documento.
                            
                            Motivo: {error_message}
                            
                            Verifique se:
                            - O documento está legível e em boa qualidade
                            - O PDF contém texto selecionável (não é apenas imagem)
                            - O Poppler está instalado (para PDFs escaneados)
                            - A imagem tem resolução suficiente
                        ''')
                    elif error_code == 'tesseract_not_installed':
                        st.error(f'''
                            ❌ Tesseract OCR não está disponível
                            
                            {error_message}
                            
                            **Instruções de instalação:**
                            - **Windows:** Baixe em https://github.com/UB-Mannheim/tesseract/wiki
                            - **Linux:** `sudo apt-get install tesseract-ocr`
                            - **macOS:** `brew install tesseract`
                            
                            Após instalar, reinicie a aplicação.
                        ''')
                    elif error_code == 'invalid_image_format':
                        st.error(f"❌ Formato de imagem inválido: {error_message}")
                    elif error_code == 'file_not_found':
                        st.error(f"❌ Arquivo não encontrado: {error_message}")
                    elif error_code == 'unsupported_file_type':
                        st.error(f"❌ Tipo de arquivo não suportado: {error_message}")
                    else:
                        st.error(f"❌ Erro na extração ({error_code}): {error_message}")
                    
                    logger.error(f"Erro de extração: {error_code} - {error_message}")
                    return
                
                # Validação adicional
                if not isinstance(parsed, dict):
                    st.error(f"❌ Resposta inválida da extração: {type(parsed).__name__}")
                    logger.error(f"Resposta inválida: {parsed}")
                    return
                
                # Show raw OCR text with better formatting
                st.subheader('📝 Texto extraído (OCR)')
                raw_text = parsed.get('raw_text', '').strip()
                
                if not raw_text:
                    st.warning('Nenhum texto foi extraído do documento.')
                    return
                    
                with st.expander('Visualizar texto extraído', expanded=False):
                    st.text_area(
                        'Texto extraído (apenas leitura)',
                        value=raw_text[:5000] + ('...' if len(raw_text) > 5000 else ''),
                        height=200,
                        disabled=True
                    )
                
                # Processamento automático com IA
                with st.spinner('Processando texto com IA para extração estruturada...'):
                    try:
                        # Usar IA para extrair campos automaticamente
                        extracted_data = ocr_text_to_document(raw_text, use_llm=True)
                        
                        # Garantir que extracted_data é um dicionário
                        if not isinstance(extracted_data, dict):
                            st.error('Erro: Dados extraídos não estão no formato esperado')
                            st.stop()
                        
                        # Adicionar o texto bruto extraído
                        extracted_data['raw_text'] = raw_text
                        
                        # Se não conseguiu extrair dados suficientes, tentar com heurística
                        if not extracted_data.get('emitente') or not extracted_data.get('itens'):
                            st.warning('IA não conseguiu extrair todos os campos automaticamente. Tentando com heurística...')
                            extracted_data = ocr_text_to_document(raw_text, use_llm=False)
                            
                            # Garantir que os dados extraídos são válidos
                            if not isinstance(extracted_data, dict):
                                st.error('Erro: Falha ao extrair dados usando heurística')
                                st.stop()
                                
                            extracted_data['raw_text'] = raw_text
                        
                        # Classificar o documento
                        classification = coordinator.run_task('classify', {'parsed': extracted_data})
                        
                        try:
                            # Validar os dados extraídos antes de salvar
                            if not _validate_document_data(extracted_data):
                                st.error('Erro: Dados extraídos não contêm campos obrigatórios')
                                st.stop()
                                
                            # Preparar e salvar o registro
                            record = _prepare_document_record(uploaded, extracted_data, classification)
                            
                            # Validar o registro antes de salvar
                            required_fields = ['file_name', 'document_type', 'extracted_data', 'raw_text']
                            missing_fields = [field for field in required_fields if field not in record]
                            if missing_fields:
                                st.error(f'Erro: Registro inválido. Campos faltando: {missing_fields}')
                                st.stop()
                            
                            # Garantir que extracted_data é serializável
                            try:
                                import json
                                json.dumps(record['extracted_data'])
                            except (TypeError, OverflowError) as e:
                                st.error(f'Erro: Dados extraídos contêm valores não serializáveis: {str(e)}')
                                st.stop()
                            
                            # Salvar o documento
                            saved = storage.save_document(record)
                            
                            # Verificar se o documento foi salvo com sucesso
                            if not isinstance(saved, dict) or 'id' not in saved:
                                error_msg = str(saved) if not isinstance(saved, dict) else 'Resposta do servidor não contém ID do documento'
                                st.error(f'Erro ao salvar documento: {error_msg}')
                                if hasattr(storage, '_last_error'):
                                    st.error(f'Detalhes do erro: {getattr(storage, "_last_error", "")}')
                                st.stop()
                            
                            # Documento salvo com sucesso
                            st.success('✅ Documento salvo com sucesso!')
                            st.balloons()
                            
                            # Salvar histórico se suportado
                            try:
                                if hasattr(storage, 'save_history'):
                                    history_data = {
                                        'fiscal_document_id': saved.get('id'),
                                        'event_type': 'created',
                                        'event_data': {
                                            'source': 'ocr_auto',
                                            'file_type': file_type,
                                            'validation_status': record.get('validation_status')
                                        }
                                    }
                                    storage.save_history(history_data)
                            except Exception as history_error:
                                st.warning(f'Aviso: Não foi possível salvar o histórico: {str(history_error)}')
                            
                            # Mostrar dados extraídos
                            st.subheader('📊 Dados extraídos automaticamente')
                            st.json(extracted_data)
                            
                            # Mostrar link para visualizar o documento salvo
                            if 'id' in saved:
                                st.markdown(f'''
                                **Ações:**
                                - [Visualizar documento](#)
                                - [Editar informações](#)
                                ''', unsafe_allow_html=True)
                            
                        except Exception as e:
                            st.error(f'Erro ao salvar documento: {str(e)}')
                            st.exception(e)  # Log detalhado no console
                        
                    except Exception as e:
                        st.error(f'Erro ao processar documento automaticamente: {str(e)}')
                        st.exception(e)
        
        except Exception as e:
            st.error(f'❌ Ocorreu um erro inesperado: {str(e)}')
            st.exception(e)  # Show full traceback in logs
        
        finally:
            # Clean up temporary file
            try:
                if dest.exists():
                    dest.unlink()
            except Exception as e:
                st.warning(f'Aviso: Não foi possível remover o arquivo temporário: {str(e)}')
    
    # Update session state
    if 'processed_documents' in st.session_state:
        try:
            result = storage.get_fiscal_documents(page=1, page_size=1000)
            # Acessa items diretamente do objeto PaginatedResponse
            st.session_state.processed_documents = result.items if hasattr(result, 'items') else []
        except Exception as e:
            st.warning('Não foi possível atualizar a lista de documentos.')
            st.exception(e)  # Show full traceback in logs