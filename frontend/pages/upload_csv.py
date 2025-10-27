"""Upload CSV page for EDA analysis."""
import streamlit as st
from pathlib import Path
from backend.agents import coordinator


def render(storage):
    """Render the CSV upload and analysis page."""
    st.header('Upload CSV para EDA')
    
    csv = st.file_uploader('Escolha um CSV', type=['csv'])
    if not csv:
        return
        
    with st.spinner('Analisando dados...'):
        # Save uploaded file
        tmp = Path('tmp_upload')
        tmp.mkdir(exist_ok=True)
        dest = tmp / csv.name
        with open(dest, 'wb') as f:
            f.write(csv.getbuffer())
            
        # Run analysis
        analysis = coordinator.run_task('analyze', {'path': str(dest)})
        
        # Show stats
        st.subheader('Estatísticas')
        st.json(analysis.get('stats'))
        
        # Show charts
        st.subheader('Gráficos')
        for ch in analysis.get('charts', []):
            st.plotly_chart(ch['figure'], use_container_width=True)
        
        # Save analysis
        try:
            record = {'file': csv.name, 'analysis': analysis}
            saved = storage.save_fiscal_document(record)
            if hasattr(storage, 'save_history'):
                storage.save_history({
                    'fiscal_document_id': saved.get('id'),
                    'event_type': 'created',
                    'event_data': {'source': 'csv_analysis'}
                })
            st.success('✓ Análise salva com sucesso')
        except Exception as e:
            st.error(f'Erro ao salvar análise: {e}')
            
        # Update session state
        if 'processed_documents' in st.session_state:
            try:
                result = storage.get_fiscal_documents(page=1, page_size=1000)
                st.session_state.processed_documents = result.items if hasattr(result, 'items') else []
            except Exception:
                pass  # Keep existing list if refresh fails