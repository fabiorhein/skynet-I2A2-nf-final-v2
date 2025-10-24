"""Home page of the Streamlit app."""
import streamlit as st
from backend.storage import storage_manager


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
    
    ## Status do Armazenamento
    """)
    
    # Display storage status using the storage manager
    status_container = st.container(border=True)
    with status_container:
        st.markdown("### Configuração de Armazenamento")
        
        # Get status from storage manager
        status = storage_manager.status
        status_type = storage_manager.status_type
        
        # Display status with appropriate color
        if status_type == "success":
            st.success(f"✅ {status}")
        elif status_type == "warning":
            st.warning(f"⚠️ {status}")
        elif status_type == "error":
            st.error(f"❌ {status}")
        else:
            st.info(f"ℹ️ {status}")
        
        # Show storage details
        if "Supabase" in status:
            st.markdown("""
            - **Tipo**: Banco de Dados Supabase (PostgreSQL)
            - **Status**: Conectado
            - **Tabelas**: fiscal_documents, document_analyses
            """)
        else:
            st.markdown("""
            - **Tipo**: Armazenamento Local (JSON)
            - **Status**: Ativo
            - **Local**: Pasta local do aplicativo
            - **Observação**: Dados não serão persistidos entre reinicializações do servidor
            """)