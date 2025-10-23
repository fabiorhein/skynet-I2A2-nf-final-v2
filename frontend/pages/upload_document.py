"""Upload Document page for processing XML/PDF/image files."""
import streamlit as st
from pathlib import Path
from backend.agents import coordinator
from backend.tools.ocr_processor import ocr_text_to_document


def render(storage):
    """Render the upload document page."""
    st.header('Upload de Documento (XML / PDF / Imagem)')
    
    uploaded = st.file_uploader(
        'Escolha um XML, PDF ou imagem',
        type=['xml', 'pdf', 'png', 'jpg', 'jpeg']
    )
    
    if not uploaded:
        return
        
    # Save uploaded file
    tmp = Path('tmp_upload')
    tmp.mkdir(exist_ok=True)
    dest = tmp / uploaded.name
    with open(dest, 'wb') as f:
        f.write(uploaded.getbuffer())

    if dest.suffix.lower() == '.xml':
        with st.spinner('Processando XML...'):
            # Extract data
            parsed = coordinator.run_task('extract', {'path': str(dest)})
            st.subheader('Dados extraídos')
            st.json(parsed)
            
            # Classify
            # Ensure parsed is a dictionary
            if not isinstance(parsed, dict):
                st.error(f"Erro na extração: formato inválido {type(parsed)}")
                return

            # Run classification
            cls = coordinator.run_task('classify', {'parsed': parsed})
            st.subheader('Classificação')
            st.json(cls)
            
            # Save
            validation_status = None
            try:
                validation_status = cls.get('validacao', {}).get('status')
            except AttributeError:
                validation_status = 'error'

            record = {
                'file_name': uploaded.name,
                'document_type': parsed.get('document_type', 'NFe'),
                'document_number': parsed.get('numero'),
                'issuer_cnpj': (parsed.get('emitente') or {}).get('cnpj'),
                'extracted_data': parsed,
                'validation_status': validation_status,
                'classification': cls,
                'raw_text': parsed.get('raw_text', '')
            }
            try:
                saved = storage.save_document(record)
                if hasattr(storage, 'save_history'):
                    storage.save_history({
                        'fiscal_document_id': saved.get('id'),
                        'event_type': 'created',
                        'event_data': {'source': 'xml_upload'}
                    })
                st.success('✓ Documento salvo com sucesso')
            except Exception as e:
                st.error(f'Erro ao salvar documento: {e}')
            
    else:  # PDF/Image
        with st.spinner('Processando imagem/PDF via OCR...'):
            parsed = coordinator.run_task('extract', {'path': str(dest)})
            
            # Handle extraction errors
            if parsed.get('error') == 'empty_ocr':
                st.error('Não foi possível converter o PDF para imagens (Poppler não instalado) e não foi encontrado texto selecionável no PDF.')
                st.markdown('''
                    Instale o Poppler (adicione a pasta bin do Poppler ao PATH) para permitir OCR de PDFs escaneados,
                    ou envie o XML/um PDF com texto selecionável.
                ''')
                return
                
            if parsed.get('error'):
                st.error(f"Erro na extração: {parsed.get('message')}")
                return
                
            # Show raw OCR text
            st.info('Extração via OCR — texto bruto abaixo (a seguir mapeamento heurístico).')
            raw = parsed.get('raw_text', '')
            with st.expander('Ver texto extraído (OCR)'):
                st.text(raw[:2000])
                if len(raw) > 2000:
                    st.caption('(texto truncado)')
            
            # Map OCR text to structured fields
            use_llm = st.checkbox(
                'Usar IA para melhorar extração',
                help='Usa modelo de linguagem para melhorar a extração de campos do texto OCR'
            )
            
            with st.spinner('Mapeando campos...'):
                mapped = ocr_text_to_document(raw, use_llm=use_llm)
                st.subheader(f'Campos mapeados {"(IA)" if use_llm else "(heurística)"}')
                st.json(mapped)
            
            # Run classification
            cls = coordinator.run_task('classify', {'parsed': mapped})
            st.subheader('Classificação')
            st.json(cls)
            
            # Save
            record = {
                'file_name': uploaded.name,
                'document_type': 'OCR',  # Document from OCR
                'document_number': mapped.get('numero'),
                'issuer_cnpj': (mapped.get('emitente') or {}).get('cnpj'),
                'extracted_data': mapped,
                'validation_status': cls.get('validacao', {}).get('status', 'pending'),
                'classification': cls,
                'raw_text': raw
            }
            try:
                saved = storage.save_document(record)
                if hasattr(storage, 'save_history'):
                    storage.save_history({
                        'fiscal_document_id': saved.get('id'),
                        'event_type': 'created',
                        'event_data': {'source': 'ocr_upload'}
                    })
                st.success('✓ Documento salvo com sucesso')
            except Exception as e:
                st.error(f'Erro ao salvar documento: {e}')

    # Update session state
    if 'processed_documents' in st.session_state:
        try:
            result = storage.get_fiscal_documents(page=1, page_size=1000)
            st.session_state.processed_documents = result['items']
        except Exception:
            pass  # Keep existing list if refresh fails