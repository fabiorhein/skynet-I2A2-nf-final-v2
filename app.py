import streamlit as st

# Page configuration must be the first Streamlit command
st.set_page_config(
    page_title="SkyNET-I2A2 - Processamento Fiscal Inteligente",
    page_icon="📊",
    layout="wide"
)

from backend.agents import coordinator
from pathlib import Path
import json

# Import the storage manager
from backend.storage import storage_manager, StorageManager

# Initialize storage backend
storage = storage_manager.storage

from frontend.components import document_renderer

st.title('SkyNET-I2A2 - Processamento Fiscal (MVP)')

menu = st.sidebar.selectbox('Navegação', ['Home', 'Upload Documento', 'Upload CSV (EDA)', 'Histórico'])

# Initialize session state for storage info and documents
if 'processed_documents' not in st.session_state:
    st.session_state.processed_documents = []

# Display storage status in the sidebar
storage_manager.display_status()

# Load documents if not already loaded
if not st.session_state.processed_documents:
    try:
        result = storage.get_fiscal_documents(page=1, page_size=1000)
        st.session_state.processed_documents = result.items  # Acessando items diretamente do objeto PaginatedResponse
    except Exception as e:
        st.sidebar.error(f'Erro ao carregar documentos: {str(e)[:150]}')
        st.session_state.processed_documents = []

# Import and render the selected page
if menu == 'Home':
    from frontend.pages import home
    home.render()
elif menu == 'Upload Documento':
    from frontend.pages import upload_document
    upload_document.render(storage)
elif menu == 'Upload CSV (EDA)':
    from frontend.pages import upload_csv
    upload_csv.render(storage)
elif menu == 'Histórico':
    from frontend.pages import history
    history.render(storage)

