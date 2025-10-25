"""
Chat page with LLM integration for document and CSV analysis.

This page provides an intelligent chat interface that can:
- Answer questions about processed documents
- Analyze CSV data and provide insights
- Cache responses to save tokens
- Maintain conversation context
"""
import streamlit as st
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List
import asyncio
import logging

# Import the chat coordinator
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from backend.agents.chat_coordinator import ChatCoordinator

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize chat coordinator
@st.cache_resource
def get_chat_coordinator():
    """Get or create chat coordinator instance."""
    try:
        from backend.storage import storage_manager
        return ChatCoordinator(storage_manager.supabase_client)
    except Exception as e:
        st.error(f"Erro ao inicializar chat: {e}")
        return None

def render():
    """Render the chat page."""

    st.title("💬 Chat Inteligente")
    st.markdown("### Assistente IA para Análise de Documentos Fiscais")

    # Initialize chat coordinator
    chat_coordinator = get_chat_coordinator()
    if not chat_coordinator:
        st.error("Não foi possível inicializar o sistema de chat.")
        return

    # Initialize session state
    if 'chat_session_id' not in st.session_state:
        st.session_state.chat_session_id = None
    if 'chat_messages' not in st.session_state:
        st.session_state.chat_messages = []
    if 'chat_initialized' not in st.session_state:
        st.session_state.chat_initialized = False

    # Sidebar for session management
    with st.sidebar:
        st.header("🔧 Gerenciar Sessão")

        # Session name input
        session_name = st.text_input(
            "Nome da Sessão",
            value=st.session_state.get('chat_session_name', ''),
            help="Dê um nome descritivo para sua sessão de chat"
        )

        # New session button
        if st.button("🆕 Nova Sessão", type="primary"):
            try:
                session_id = asyncio.run(chat_coordinator.initialize_session(session_name or None))
                st.session_state.chat_session_id = session_id
                st.session_state.chat_session_name = session_name
                st.session_state.chat_messages = []
                st.session_state.chat_initialized = True
                st.success("Nova sessão criada!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao criar sessão: {e}")

        # Session info
        if st.session_state.chat_session_id:
            st.info(f"📝 Sessão: {st.session_state.get('chat_session_name', 'Sem nome')}")
            st.info(f"🆔 ID: {st.session_state.chat_session_id[:8]}...")

            # Load chat history
            if st.button("📚 Carregar Histórico"):
                try:
                    messages = asyncio.run(chat_coordinator.get_session_history(st.session_state.chat_session_id))
                    st.session_state.chat_messages = messages
                    st.success("Histórico carregado!")
                except Exception as e:
                    st.error(f"Erro ao carregar histórico: {e}")

        # Session list
        st.markdown("---")
        st.subheader("📋 Sessões Recentes")

        try:
            sessions = asyncio.run(chat_coordinator.get_chat_sessions())
            if sessions:
                for session in sessions[:5]:  # Show last 5 sessions
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.text(f"{session['session_name']}")
                        st.caption(f"{session['created_at'][:19]}")
                    with col2:
                        if st.button("🔄", key=f"load_{session['id']}", help="Carregar esta sessão"):
                            st.session_state.chat_session_id = session['id']
                            st.session_state.chat_session_name = session['session_name']
                            messages = asyncio.run(chat_coordinator.get_session_history(session['id']))
                            st.session_state.chat_messages = messages
                            st.success("Sessão carregada!")
                            st.rerun()
            else:
                st.info("Nenhuma sessão encontrada")
        except Exception as e:
            st.error(f"Erro ao carregar sessões: {e}")

    # Main chat interface
    if not st.session_state.chat_session_id:
        st.info("👋 Crie uma nova sessão para começar a conversar!")
        return

    # Chat messages display
    st.subheader("💬 Conversa")

    # Display chat messages
    chat_container = st.container()
    with chat_container:
        if not st.session_state.chat_messages:
            st.info("Esta é uma nova sessão. Faça sua primeira pergunta!")

        for message in st.session_state.chat_messages:
            if hasattr(message, 'type') and message.type == 'user':
                with st.chat_message("user"):
                    st.write(message.content)
            elif hasattr(message, 'type') and message.type == 'assistant':
                with st.chat_message("assistant"):
                    st.write(message.content)
        else:
            # Fallback for dict messages
            for message in st.session_state.chat_messages:
                if isinstance(message, dict):
                    msg_type = message.get('message_type', 'user')
                    if msg_type == 'user':
                        with st.chat_message("user"):
                            st.write(message.get('content', ''))
                    elif msg_type == 'assistant':
                        with st.chat_message("assistant"):
                            st.write(message.get('content', ''))

    # Chat input
    st.markdown("---")

    # Context selection
    col1, col2 = st.columns([2, 1])

    with col1:
        # Query type selection
        query_type = st.selectbox(
            "Tipo de Análise",
            ["Geral", "Documentos Fiscais", "Análise CSV", "Financeira", "Validação"],
            help="Selecione o tipo de análise para contextualizar sua pergunta"
        )

    with col2:
        # Document type filter for fiscal analysis
        document_types = []
        if query_type in ["Documentos Fiscais", "Financeira", "Validação"]:
            doc_types = st.multiselect(
                "Tipos de Documento",
                ["NFe", "NFCe", "CTe", "Todos"],
                default=["Todos"],
                help="Filtre por tipo de documento fiscal"
            )
            document_types = [dt for dt in doc_types if dt != "Todos"]

    # Chat input
    if prompt := st.chat_input("Digite sua pergunta..."):

        # Add user message to display
        with st.chat_message("user"):
            st.write(prompt)

        # Add to session state
        st.session_state.chat_messages.append({
            'message_type': 'user',
            'content': prompt,
            'timestamp': datetime.now().isoformat()
        })

        # Prepare context based on query type
        context = {
            'query_type': query_type.lower().replace(' ', '_'),
            'limit': 10
        }

        if document_types:
            context['document_types'] = document_types

        # Show loading
        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                try:
                    # Process query
                    response = asyncio.run(chat_coordinator.process_query(
                        session_id=st.session_state.chat_session_id,
                        query=prompt,
                        context=context
                    ))

                    if response.get('success'):
                        # Display response
                        st.write(response['response'])

                        # Show metadata
                        metadata = response.get('metadata', {})
                        if metadata.get('cached'):
                            st.success("✅ Resposta obtida do cache (tokens economizados!)")
                        else:
                            st.info(f"📊 Tokens utilizados: {response.get('tokens_used', 'N/A')}")

                        # Add assistant response to session state
                        st.session_state.chat_messages.append({
                            'message_type': 'assistant',
                            'content': response['response'],
                            'metadata': metadata,
                            'timestamp': datetime.now().isoformat()
                        })

                    else:
                        st.error(f"Erro: {response.get('error', 'Erro desconhecido')}")

                except Exception as e:
                    st.error(f"Erro ao processar pergunta: {e}")
                    logger.error(f"Chat error: {e}")

    # Additional features section
    st.markdown("---")
    st.subheader("🔍 Análises Especiais")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📄 Análise de Documentos", use_container_width=True):
            st.info("Selecione documentos específicos no histórico para análise detalhada")

    with col2:
        if st.button("📊 Análise de CSV", use_container_width=True):
            st.info("Faça upload de um CSV para análise estatística detalhada")

    with col3:
        if st.button("🔍 Busca Inteligente", use_container_width=True):
            st.info("Digite termos de busca para encontrar documentos relevantes")

    # Quick actions
    st.markdown("### ⚡ Ações Rápidas")

    quick_questions = [
        "Quais são os documentos processados hoje?",
        "Mostre um resumo financeiro dos últimos 30 dias",
        "Quais documentos têm problemas de validação?",
        "Qual é o valor total das notas fiscais?",
        "Mostre os principais fornecedores por volume"
    ]

    cols = st.columns(2)
    for i, question in enumerate(quick_questions):
        col_idx = i % 2
        if cols[col_idx].button(question, key=f"quick_{i}", use_container_width=True):
            # Simulate clicking the question
            st.session_state.chat_input_value = question
            st.rerun()

    # Footer
    st.markdown("---")
    st.caption("💡 Dicas: O sistema usa cache para economizar tokens e acelerar respostas. Perguntas sobre dados específicos são mais eficientes!")
