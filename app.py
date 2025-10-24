import streamlit as st
st.set_page_config(page_title='SkyNET-I2A2 - Fiscal Processor', layout='wide')

from backend.agents import coordinator
from pathlib import Path
import json

# centralized config loader
from config import SUPABASE_URL, SUPABASE_KEY
from backend.storage_interface import StorageError
from backend.storage import LocalJSONStorage
from backend.storage_supabase import SupabaseStorage

# Initialize storage backend
storage_info = "Using local storage (JSON files)"
try:
    if SUPABASE_URL and SUPABASE_KEY:
        storage = SupabaseStorage(SUPABASE_URL, SUPABASE_KEY)
        # Test connection by making a simple query
        storage.get_fiscal_documents(page=1, page_size=1)
        storage_info = "✓ Connected to Supabase PostgreSQL"
        st.sidebar.success(storage_info)
    else:
        storage = LocalJSONStorage()
        storage_info = "⚠️ Using local storage (JSON files) - Supabase not configured"
        st.sidebar.info(storage_info)
except Exception as e:
    storage = LocalJSONStorage()
    storage_info = f"❌ Failed to connect to Supabase: {str(e)}. Using local storage fallback."
    st.sidebar.error(storage_info)

from frontend.components import document_renderer

st.title('SkyNET-I2A2 - Processamento Fiscal (MVP)')

menu = st.sidebar.selectbox('Navegação', ['Home', 'Upload Documento', 'Upload CSV (EDA)', 'Histórico'])

# Store consistent storage info across all pages
st.session_state.storage_info = storage_info
st.session_state._sidebar_storage_text = storage_info  # Ensure sidebar is in sync

if 'processed_documents' not in st.session_state:
    try:
        # Both backends implement get_fiscal_documents now
        result = storage.get_fiscal_documents(page=1, page_size=1000)
        st.session_state.processed_documents = result['items']
    except StorageError as e:
        st.error(f'Erro ao carregar documentos: {e}')
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

