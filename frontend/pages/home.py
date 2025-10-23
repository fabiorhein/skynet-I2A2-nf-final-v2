"""Home page of the Streamlit app."""
import streamlit as st


def render():
    """Render the home page."""
    st.header('Home')
    st.markdown("""
    # SkyNET-I2A2 - Processamento Fiscal (MVP)
    
    Sistema MVP para extração e análise de notas fiscais. O sistema suporta:
    
    - Upload de documentos fiscais (XML, PDF ou imagens)
    - Extração de dados via XML parser ou OCR
    - Validação fiscal e classificação automática
    - Análise exploratória de dados (EDA) via CSV
    - Histórico de documentos com eventos e busca
    
    ## Começando
    
    1. Use "Upload Documento" para processar XML/PDF/imagens
    2. Use "Upload CSV" para análise exploratória
    3. Veja documentos processados em "Histórico"
    
    ## Armazenamento
    
    O sistema suporta armazenamento local (arquivos JSON) ou 
    Supabase (PostgreSQL). O backend atual está configurado para:
    """)

    # Storage info from sidebar (already set in app.py)
    storage_info = st.session_state.get('storage_info', 'Status do storage não disponível')
    st.info(storage_info)