"""Upload Document page for processing XML/PDF/image files."""
import streamlit as st
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from backend.agents import coordinator
from backend.tools.ocr_processor import ocr_text_to_document


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
        
    validation_status = None
    if classification and isinstance(classification, dict):
        validation_status = classification.get('validacao', {}).get('status')
    
    return {
        'file_name': str(uploaded.name),
        'document_type': parsed.get('document_type', 'NFe'),
        'document_number': parsed.get('numero'),
        'issuer_cnpj': (parsed.get('emitente') or {}).get('cnpj'),
        'extracted_data': parsed,
        'validation_status': validation_status or 'pending',
        'classification': classification or {},
        'raw_text': parsed.get('raw_text', ''),
        'uploaded_at': datetime.now(ZoneInfo('UTC')).isoformat()
    }

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
                
                # Prepare and save document record
                try:
                    record = _prepare_document_record(uploaded, parsed, classification)
                    saved = storage.save_document(record)
                    
                    # Save history if supported
                    if hasattr(storage, 'save_history'):
                        storage.save_history({
                            'fiscal_document_id': saved.get('id'),
                            'event_type': 'created',
                            'event_data': {
                                'source': 'xml_upload',
                                'file_type': file_type,
                                'validation_status': record.get('validation_status')
                            }
                        })
                    
                    st.success('✅ Documento processado e salvo com sucesso!')
                    
                except Exception as e:
                    st.error(f'Erro ao salvar documento: {str(e)}')
                    st.exception(e)  # Show full traceback in logs
            
            else:  # PDF/Image
                st.info('Processando documento não-XML via OCR...')
                parsed = coordinator.run_task('extract', {'path': str(dest)})
                
                if parsed.get('error') == 'empty_ocr':
                    st.error('''
                        ❌ Não foi possível extrair texto do documento. Verifique se:
                        - O documento está legível
                        - O PDF contém texto selecionável
                        - O Poppler está instalado (para PDFs escaneados)
                    ''')
                    return
                    
                if parsed.get('error'):
                    st.error(f"Erro na extração: {parsed.get('message')}")
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
                                
                            # Salvar histórico se suportado
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
                                
                            # Mostrar dados extraídos
                            st.subheader('📊 Dados extraídos automaticamente')
                            st.json(extracted_data)
                            
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
            st.session_state.processed_documents = result.get('items', [])
        except Exception as e:
            st.warning('Não foi possível atualizar a lista de documentos.')
            st.exception(e)  # Show full traceback in logs