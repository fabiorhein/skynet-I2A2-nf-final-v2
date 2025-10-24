"""Document history and listing page."""
import streamlit as st
from frontend.components import document_renderer
import importlib
import importlib.util
import json


def render(storage):
    """Render the documents listing and history page."""
    st.header('Documentos processados')

    # Search and pagination controls
    c1, c2, c3 = st.columns([2,2,1])
    with c1:
        search_cnpj = st.text_input('Buscar por CNPJ (parcial)')
    with c2:
        search_number = st.text_input('Buscar por número (parcial)')
    with c3:
        page_size = st.selectbox('Por página', [10,25,50,100], index=2)

    if 'doc_page' not in st.session_state:
        st.session_state.doc_page = 1

    # Fetch documents with filters and pagination
    filters = {}
    if search_cnpj:
        filters['issuer_cnpj'] = search_cnpj
    if search_number:
        filters['document_number'] = search_number

    try:
        # Both backends now return PaginatedResponse
        result = storage.get_fiscal_documents(
            filters=filters or None,
            page=st.session_state.doc_page,
            page_size=page_size
        )
        # Acessa os atributos diretamente do objeto PaginatedResponse
        docs = result.items if hasattr(result, 'items') else []
        total = result.total if hasattr(result, 'total') else 0
        
        # Show pagination info
        if total > 0:
            start = ((st.session_state.doc_page - 1) * page_size) + 1
            end = min(start + len(docs) - 1, total)
            st.caption(f"Mostrando {start}-{end} de {total} documentos")
        
        # Update max page if needed
        max_page = (total + page_size - 1) // page_size
        if st.session_state.doc_page > max_page and max_page > 0:
            st.session_state.doc_page = max_page
            st.experimental_rerun()

    except Exception as e:
        st.error(f'Erro ao carregar documentos: {e}')
        docs = []
        total = 0

    if not docs:
        st.info('Nenhum documento processado encontrado.')
        return

    # Document selection
    options = [
        f"{d.get('file_name','-')} | {d.get('document_number') or (d.get('extracted_data') or {}).get('numero') or '-'}"
        for d in docs
    ]
    sel = st.selectbox('Selecione um documento', options)
    idx = options.index(sel)
    doc = docs[idx]

    # Pagination controls
    pag_c1, pag_c2 = st.columns([1,3])
    with pag_c1:
        if st.button('<< Anterior'):
            if st.session_state.doc_page > 1:
                st.session_state.doc_page -= 1
                st.experimental_rerun()
    with pag_c2:
        if st.button('Próxima >>'):
            if (st.session_state.doc_page * page_size) < total:
                st.session_state.doc_page += 1
                st.experimental_rerun()

    # Document details
    st.subheader('Documento selecionado')
    col1, col2 = st.columns([2,1])
    
    with col1:
        st.markdown('**Dados extraídos / raw**')
        data = doc.get('parsed') or doc.get('extracted_data') or doc
        st.json(data)
        
        # Download buttons
        c1, c2 = st.columns([1,1])
        with c1:
            st.download_button(
                '⬇️ Baixar JSON',
                json.dumps(data, ensure_ascii=False, indent=2),
                file_name=f"{doc.get('file_name', 'documento').split('.')[0]}.json",
                mime='application/json'
            )
        with c2:
            if doc.get('raw_text'):
                st.download_button(
                    '⬇️ Baixar texto OCR',
                    doc['raw_text'],
                    file_name=f"{doc.get('file_name', 'documento').split('.')[0]}_ocr.txt",
                    mime='text/plain'
                )
        
        # Items table if present
        itens = None
        if doc.get('parsed') and isinstance(doc.get('parsed'), dict):
            itens = doc['parsed'].get('itens')
        elif doc.get('extracted_data'):
            itens = (doc['extracted_data'] or {}).get('itens')
            
        if itens:
            try:
                # dynamic import to avoid static linter errors when pandas isn't available
                pd_spec = importlib.util.find_spec('pandas')
                if pd_spec is not None:
                    pd = importlib.import_module('pandas')
                    df = pd.DataFrame(itens)
                    st.subheader('Itens')
                    st.dataframe(df)
                else:
                    raise ImportError('pandas not installed')
            except Exception:
                st.write(itens)
                
    with col2:
        st.markdown('**Metadados**')
        st.write({
            'file_name': doc.get('file_name'),
            'document_number': doc.get('document_number') or (doc.get('extracted_data') or {}).get('numero'),
            'issuer_cnpj': doc.get('issuer_cnpj') or (doc.get('extracted_data') or {}).get('emitente', {}).get('cnpj')
        })
        if doc.get('classification'):
            document_renderer.render_validation_badge(doc['classification']['validacao']['status'])

    # Document history
    st.subheader('Histórico de eventos')
    history = []
    try:
        # Both backends implement get_document_history
        if doc.get('id'):
            history = storage.get_document_history(doc.get('id'))
    except Exception as e:
        st.error(f'Erro ao carregar histórico: {e}')
        
    if history:
        for h in history:
            st.write(h)
    else:
        st.info('Nenhum evento de histórico encontrado para este documento.')

    # Add history event form
    st.subheader('Adicionar evento ao histórico')
    evt_type = st.selectbox(
        'Tipo de evento',
        ['created', 'validated', 'classified', 'updated', 'note']
    )
    evt_note = st.text_area('Dados do evento (JSON ou texto curto)')
    
    if st.button('Adicionar evento'):
        event = {
            'fiscal_document_id': doc.get('id'),
            'event_type': evt_type,
            'event_data': evt_note or {}
        }
        try:
            storage.save_history(event)
            st.success('✓ Evento adicionado com sucesso')
            st.experimental_rerun()  # Refresh to show new event
        except Exception as e:
            st.error(f'Erro ao adicionar evento: {e}')