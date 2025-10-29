"""
Página RAG (Retrieval-Augmented Generation) para o SkyNET-I2A2.

Esta página demonstra o sistema RAG implementado, permitindo:
1. Consultas semânticas em documentos fiscais
2. Visualização de estatísticas do sistema RAG
3. Processamento de documentos para embeddings
4. Validação de documentos usando contexto
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd
import streamlit as st

# Backend imports
from backend.services import RAGService

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_rag_service() -> bool:
    """Inicializa o serviço RAG se ainda não estiver inicializado."""
    if 'rag_service' not in st.session_state or st.session_state.rag_service is None:
        try:
            from backend.services.vector_store_service import VectorStoreService
            vector_store = VectorStoreService()
            st.session_state.rag_service = RAGService(vector_store)
            logger.info("RAG service initialized")
        except Exception as e:
            st.error(f"Erro ao inicializar serviço RAG: {str(e)}")
            st.session_state.rag_service = None
            return False
    return st.session_state.rag_service is not None


def show_rag_monitoring():
    """Monitoramento em tempo real do processamento RAG."""
    st.subheader("🔄 Monitoramento RAG em Tempo Real")

    if not initialize_rag_service():
        return

    rag_service: RAGService = st.session_state.rag_service

    try:
        # Buscar documentos do banco de dados
        from backend.database import storage_manager
        storage = storage_manager.storage

        # Buscar todos os documentos
        all_docs = storage.get_fiscal_documents(page=1, page_size=1000)

        if hasattr(all_docs, 'items') and all_docs.items:
            documents = all_docs.items

            # Análise do status dos embeddings
            embedding_stats = {
                'completed': 0,
                'pending': 0,
                'failed': 0,
                'processing': 0,
                'not_started': 0
            }

            docs_with_embeddings = []
            docs_without_embeddings = []

            for doc in documents:
                status = doc.get('embedding_status', 'not_started')
                if status in embedding_stats:
                    embedding_stats[status] += 1
                else:
                    embedding_stats.setdefault(status, 0)
                    embedding_stats[status] += 1

                if status == 'completed':
                    docs_with_embeddings.append(doc)
                else:
                    docs_without_embeddings.append(doc)

            # Estatísticas do estado atual
            st.markdown("### 📊 Status dos Documentos")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total de Documentos", len(documents))
            with col2:
                st.metric("Com Embeddings", embedding_stats.get('completed', 0),
                         delta=f"{embedding_stats.get('completed', 0)/len(documents)*100:.1f}%" if documents else "0%")
            with col3:
                st.metric("Sem Embeddings", embedding_stats.get('pending', 0) + embedding_stats.get('not_started', 0))
            with col4:
                st.metric("Com Falha", embedding_stats.get('failed', 0))

            # Gráfico de status
            if embedding_stats:
                st.markdown("### 📈 Distribuição por Status")
                status_df = pd.DataFrame(
                    [(k, v) for k, v in embedding_stats.items() if v > 0],
                    columns=['Status', 'Quantidade']
                )

                if not status_df.empty:
                    # Mapear status para cores
                    color_map = {
                        'completed': '🟢',
                        'pending': '🟡',
                        'failed': '🔴',
                        'processing': '🟠',
                        'not_started': '⚪'
                    }

                    status_df['Status_Display'] = status_df['Status'].map(
                        lambda x: f"{color_map.get(x, '⚪')} {x.replace('_', ' ').title()}"
                    )

                    st.bar_chart(status_df.set_index('Status_Display'))

            # Painel de fila de processamento
            queue_stats = rag_service.get_embedding_queue_stats()
            with st.expander("🧵 Status da Fila de Embeddings", expanded=False):
                if queue_stats:
                    col_q1, col_q2, col_q3, col_q4 = st.columns(4)
                    col_q1.metric("Jobs Pendentes", queue_stats.get('pending', 0))
                    col_q2.metric("Em Execução", queue_stats.get('processing', 0))
                    col_q3.metric("Concluídos", queue_stats.get('completed', 0))
                    col_q4.metric("Falharam", queue_stats.get('failed', 0))
                else:
                    st.info("Fila de embeddings indisponível ou vazia.")

            # Lista de documentos que precisam de processamento
            if docs_without_embeddings:
                st.markdown("### 📋 Documentos que Precisam de Processamento")

                # Tabela de documentos sem embeddings
                docs_data = []
                for doc in docs_without_embeddings[:10]:  # Mostrar apenas os 10 primeiros
                    docs_data.append({
                        'ID': doc.get('id', 'N/A')[:8] + '...',
                        'Tipo': doc.get('document_type', 'N/A'),
                        'Número': doc.get('document_number', 'N/A'),
                        'Emissor': doc.get('issuer_cnpj', 'N/A'),
                        'Status': doc.get('embedding_status', 'not_started'),
                        'Data': (
                            doc.get('created_at', 'N/A').strftime('%Y-%m-%d')[:10]
                            if hasattr(doc.get('created_at'), 'strftime')
                            else str(doc.get('created_at', 'N/A'))[:10]
                        ) if doc.get('created_at') else 'N/A'
                    })

                if docs_data:
                    docs_df = pd.DataFrame(docs_data)
                    st.dataframe(
                        docs_df,
                        column_config={
                            "ID": st.column_config.TextColumn("ID", width="small"),
                            "Tipo": st.column_config.TextColumn("Tipo", width="small"),
                            "Número": st.column_config.TextColumn("Número", width="medium"),
                            "Emissor": st.column_config.TextColumn("Emissor", width="medium"),
                            "Status": st.column_config.TextColumn("Status", width="small"),
                            "Data": st.column_config.TextColumn("Data", width="small")
                        },
                        hide_index=True,
                        width='stretch'
                    )

                    # Botão para processar documentos selecionados
                    if st.button(f'🚀 Enfileirar {len(docs_without_embeddings)} Documentos para RAG',
                               type='primary', width='stretch'):
                        enqueue_documents_for_rag(docs_without_embeddings)

            # Lista de documentos já processados
            if docs_with_embeddings:
                st.markdown("### ✅ Documentos com Embeddings Prontos")

                # Tabela de documentos com embeddings
                processed_data = []
                for doc in docs_with_embeddings[:10]:  # Mostrar apenas os 10 primeiros
                    processed_data.append({
                        'ID': doc.get('id', 'N/A')[:8] + '...',
                        'Tipo': doc.get('document_type', 'N/A'),
                        'Número': doc.get('document_number', 'N/A'),
                        'Chunks': doc.get('chunks_count', 0),
                        'Status': doc.get('embedding_status', 'completed'),
                        'Data': (
                            doc.get('created_at', 'N/A').strftime('%Y-%m-%d')[:10]
                            if hasattr(doc.get('created_at'), 'strftime')
                            else str(doc.get('created_at', 'N/A'))[:10]
                        ) if doc.get('created_at') else 'N/A'
                    })

                if processed_data:
                    processed_df = pd.DataFrame(processed_data)
                    st.dataframe(
                        processed_df,
                        column_config={
                            "ID": st.column_config.TextColumn("ID", width="small"),
                            "Tipo": st.column_config.TextColumn("Tipo", width="small"),
                            "Número": st.column_config.TextColumn("Número", width="medium"),
                            "Chunks": st.column_config.NumberColumn("Chunks", width="small"),
                            "Status": st.column_config.TextColumn("Status", width="small"),
                            "Data": st.column_config.TextColumn("Data", width="small")
                        },
                        hide_index=True,
                        width='stretch'
                    )

        else:
            st.info("ℹ️ Nenhum documento encontrado no banco de dados.")
            st.info("💡 **Para usar o monitoramento RAG:**")
            st.markdown("""
            1. **Importe documentos** usando a aba "Importador"
            2. **Aguarde o processamento** - embeddings são gerados automaticamente
            3. **Monitore aqui** o progresso do processamento RAG
            """)

    except Exception as e:
        st.error(f"Erro ao carregar monitoramento: {str(e)}")


def enqueue_documents_for_rag(documents: List[Dict[str, Any]]) -> None:
    """Enfileira uma lista de documentos para processamento RAG."""
    if not documents:
        st.warning("Nenhum documento para enfileirar.")
        return

    rag_service: RAGService = st.session_state.rag_service

    jobs_enqueued = []
    errors = []

    for doc in documents:
        doc_id = doc.get('id')
        if not doc_id:
            errors.append(('sem_id', 'Documento sem ID válido'))
            continue

        try:
            job = rag_service.enqueue_document_for_rag(
                document_id=doc_id,
                payload={
                    'source': 'rag_monitor_batch',
                    'file_name': doc.get('file_name'),
                    'issuer_cnpj': doc.get('issuer_cnpj'),
                },
            )
            jobs_enqueued.append((doc_id, job.get('id')))
        except Exception as exc:
            errors.append((doc_id, str(exc)))

    if jobs_enqueued:
        st.success(f"✅ {len(jobs_enqueued)} documentos enfileirados para processamento")
        with st.expander('📊 Detalhes dos jobs', expanded=False):
            for doc_id, job_id in jobs_enqueued:
                st.markdown(f"- Documento `{doc_id}` → Job `{job_id}`")

    if errors:
        st.warning(f"⚠️ {len(errors)} documentos falharam ao enfileirar")
        with st.expander('❌ Falhas ao enfileirar', expanded=False):
            for doc_id, error in errors:
                st.markdown(f"- Documento `{doc_id}`: {error}")

    # Atualizar a página para refletir novos estados
    st.rerun()


def show_semantic_search():
    """Interface para busca semântica usando RAG."""
    st.subheader("🔍 Busca Semântica")

    if not initialize_rag_service():
        return

    # Filtros para a busca
    col1, col2, col3 = st.columns(3)

    with col1:
        document_type = st.selectbox(
            "Tipo de Documento",
            ["Todos", "NFe", "NFCe", "CTe"],
            help="Filtrar por tipo de documento"
        )

    with col2:
        similarity_threshold = st.slider(
            "Limite de Similaridade",
            0.1, 1.0, 0.6,
            help="Documentos com similaridade acima deste valor serão retornados"
        )

    with col3:
        max_results = st.slider(
            "Máximo de Resultados",
            1, 10, 5,
            help="Número máximo de documentos a retornar"
        )

    # Campo de consulta
    query = st.text_area(
        "Digite sua pergunta sobre os documentos fiscais:",
        height=100,
        placeholder="Ex: 'Encontre notas fiscais da empresa XYZ' ou 'Documentos com produtos de escritório'"
    )

    # Botão de busca
    if st.button("🔍 Buscar", type="primary", width='stretch'):
        if not query.strip():
            st.warning("Por favor, digite uma consulta.")
            return

        try:
            with st.spinner("Buscando documentos relevantes..."):
                # Preparar filtros
                filters = {}
                if document_type != "Todos":
                    filters['document_type'] = document_type

                # Executar busca RAG
                result = asyncio.run(st.session_state.rag_service.answer_query(
                    query=query,
                    filters=filters if filters else None,
                    max_context_docs=3
                ))

            # Exibir resultados
            if result['status'] == 'success':
                st.success("✅ Consulta executada com sucesso!")

                # Resposta principal
                st.subheader("Resposta:")
                st.write(result['answer'])

                # Métricas da busca
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Documentos Relevantes", len(result.get('context_docs', [])))
                with col2:
                    st.metric("Chunks Similares", result.get('total_chunks', 0))
                with col3:
                    st.metric("Filtros Aplicados", len(result.get('filters_applied', {})))

                # Documentos de contexto
                if result.get('context_docs'):
                    with st.expander("📄 Documentos de Contexto"):
                        for i, doc in enumerate(result['context_docs'], 1):
                            st.markdown(f"**Documento {i}**")
                            st.write(f"- **Tipo:** {doc.get('document_type', 'N/A')}")
                            st.write(f"- **Emissor:** {doc.get('issuer_cnpj', 'N/A')}")
                            st.write(f"- **Similaridade:** {doc.get('total_similarity', 0):.3f}")
                            st.write(f"- **Conteúdo:** {doc.get('chunks_content', 'N/A')[:300]}...")
                            st.divider()

                # Chunks similares detalhados
                if result.get('similar_chunks'):
                    with st.expander("🔍 Detalhes dos Chunks"):
                        for chunk in result['similar_chunks'][:5]:  # Mostrar apenas os 5 primeiros
                            st.write(f"**Similaridade:** {chunk.get('similarity', 0):.3f}")
                            st.write(f"**Conteúdo:** {chunk.get('content_text', '')[:200]}...")
                            st.divider()

            elif result['status'] == 'no_documents':
                st.warning("⚠️ Nenhum documento processado")
                st.write(result['answer'])

                # Mostrar estatísticas do sistema
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Documentos Processados", 0)
                with col2:
                    st.metric("Chunks Totais", 0)
                with col3:
                    st.metric("Insights Gerados", 0)

                st.info("📝 **Para usar o sistema RAG:**")
                st.markdown("""
                1. **Processar documentos:** Use a aba "Processar Documento" para adicionar documentos
                2. **Aguardar embeddings:** O sistema gerará automaticamente embeddings
                3. **Fazer consultas:** Retorne aqui para buscar nos documentos processados

                💡 **Dica:** Comece processando alguns documentos fiscais de exemplo!
                """)

            elif result['status'] == 'no_matches':
                st.info("ℹ️ Documentos processados, mas nenhum relevante encontrado")
                st.write(result['answer'])

                # Mostrar métricas do sistema
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Documentos Processados", "N/A")
                with col2:
                    st.metric("Chunks Similares", 0)
                with col3:
                    st.metric("Filtros Aplicados", len(result.get('filters_applied', {})))

                st.info("💡 **Sugestões para melhorar a busca:**")
                st.markdown("""
                - Tente palavras-chave diferentes na consulta
                - Ajuste os filtros (tipo de documento, emissor, etc.)
                - Reduza o limite de similaridade se necessário
                - Use a aba "Estatísticas" para ver quantos documentos foram processados
                """)

            else:
                st.error(f"❌ Erro na consulta: {result.get('error', 'Erro desconhecido')}")

        except Exception as e:
            st.error(f"Erro ao executar consulta: {str(e)}")


def show_document_processing():
    """Interface para processamento de documentos para RAG."""
    st.subheader("📝 Processar Documento para RAG")

    if not initialize_rag_service():
        return

    st.info("💡 Use esta funcionalidade para processar documentos fiscais e gerar embeddings para busca semântica.")

    # Exemplo de documento para teste
    with st.expander("📄 Exemplo de Documento Fiscal"):
        st.json({
            "file_name": "nfe_exemplo_001.xml",
            "document_type": "NFe",
            "document_number": "12345",
            "issuer_cnpj": "12345678000199",
            "extracted_data": {
                "emitente": {
                    "razao_social": "EMPRESA EXEMPLO LTDA",
                    "cnpj": "12345678000199"
                },
                "destinatario": {
                    "razao_social": "CLIENTE EXEMPLO S.A.",
                    "cnpj": "98765432000100"
                },
                "itens": [
                    {
                        "descricao": "Produto A - Material de Escritório",
                        "quantidade": 10,
                        "valor_unitario": 25.50,
                        "valor_total": 255.00
                    }
                ],
                "totais": {
                    "valor_produtos": 255.00,
                    "valor_total": 255.00
                }
            }
        })

    # Formulário para processamento
    with st.form("process_document_form"):
        st.write("**Dados do Documento:**")

        col1, col2 = st.columns(2)

        with col1:
            file_name = st.text_input("Nome do Arquivo", "nfe_exemplo_001.xml")
            document_type = st.selectbox("Tipo de Documento", ["NFe", "NFCe", "CTe"])
            document_number = st.text_input("Número do Documento", "12345")

        with col2:
            issuer_cnpj = st.text_input("CNPJ do Emissor", "12345678000199")
            total_value = st.number_input("Valor Total (R$)", 0.0, 1000000.0, 255.00)

        # Dados extraídos (JSON)
        extracted_data = st.text_area(
            "Dados Extraídos (JSON)",
            height=200,
            value="""{
  "emitente": {
    "razao_social": "EMPRESA EXEMPLO LTDA",
    "cnpj": "12345678000199"
  },
  "destinatario": {
    "razao_social": "CLIENTE EXEMPLO S.A.",
    "cnpj": "98765432000100"
  },
  "itens": [
    {
      "descricao": "Produto A - Material de Escritório",
      "quantidade": 10,
      "valor_unitario": 25.50,
      "valor_total": 255.00
    }
  ],
  "totais": {
    "valor_produtos": 255.00,
    "valor_total": 255.00
  }
}"""
        )

        submitted = st.form_submit_button("🚀 Processar Documento", type="primary", width='stretch')

        if submitted:
            try:
                # Parse JSON data
                import json
                extracted_data_parsed = json.loads(extracted_data)

                # Create document object
                document = {
                    'id': f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    'file_name': file_name,
                    'document_type': document_type,
                    'document_number': document_number,
                    'issuer_cnpj': issuer_cnpj,
                    'extracted_data': extracted_data_parsed,
                    'validation_status': 'pending',
                    'classification': {'tipo': 'venda', 'categoria': 'mercadorias'}
                }

                with st.spinner("Processando documento e gerando embeddings..."):
                    # Process document for RAG
                    result = asyncio.run(st.session_state.rag_service.process_document_for_rag(document))

                if result['success']:
                    st.success("✅ Documento processado com sucesso!")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Chunks Processados", result['chunks_processed'])
                    with col2:
                        st.metric("Total de Chunks", result['total_chunks'])
                    with col3:
                        st.metric("Document ID", document['id'])

                    st.info("💡 O documento agora está disponível para consultas semânticas!")
                else:
                    st.error(f"❌ Erro no processamento: {result['error']}")

            except json.JSONDecodeError:
                st.error("❌ Erro no formato JSON dos dados extraídos.")
            except Exception as e:
                st.error(f"❌ Erro ao processar documento: {str(e)}")


def show_document_validation():
    """Interface para validação de documentos usando RAG."""
    st.subheader("✅ Validação de Documentos")

    if not initialize_rag_service():
        return

    st.info("🔍 Use esta funcionalidade para validar documentos fiscais comparando com padrões de documentos similares.")

    # Formulário de validação
    with st.form("validation_form"):
        st.write("**Documento para Validar:**")

        col1, col2 = st.columns(2)

        with col1:
            doc_type = st.selectbox("Tipo de Documento", ["NFe", "NFCe", "CTe"])
            doc_number = st.text_input("Número do Documento", "99999")

        with col2:
            issuer_cnpj_val = st.text_input("CNPJ do Emissor", "55566677000188")
            total_value_val = st.number_input("Valor Total (R$)", 0.0, 10000000.0, 999999.99)

        # Regras de validação
        validation_rules = st.multiselect(
            "Regras de Validação",
            ["document_format", "required_fields", "value_ranges", "issuer_validation"],
            default=["document_format", "value_ranges", "issuer_validation"]
        )

        validate_submitted = st.form_submit_button("🔍 Validar Documento", type="primary", width='stretch')

        if validate_submitted:
            try:
                # Create validation document
                validation_doc = {
                    'id': f"val_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    'file_name': f'{doc_type.lower()}_validation_{doc_number}.xml',
                    'document_type': doc_type,
                    'document_number': doc_number,
                    'issuer_cnpj': issuer_cnpj_val,
                    'extracted_data': {
                        'emitente': {
                            'razao_social': 'EMPRESA VALIDATION LTDA',
                            'cnpj': issuer_cnpj_val
                        },
                        'totais': {
                            'valor_total': total_value_val
                        }
                    }
                }

                with st.spinner("Validando documento usando contexto de documentos similares..."):
                    # Run validation
                    validation_result = asyncio.run(st.session_state.rag_service.validate_document_with_rag(
                        document=validation_doc,
                        validation_rules=validation_rules
                    ))

                if validation_result.get('validation_results'):
                    st.success("✅ Validação concluída!")

                    # Exibir resultados da validação
                    for i, validation in enumerate(validation_result['validation_results'], 1):
                        confidence = validation.get('confidence', 0)

                        if confidence > 0.7:
                            st.success(f"**✅ {i}. {validation['insight']}**")
                        elif confidence > 0.4:
                            st.warning(f"**⚠️ {i}. {validation['insight']}**")
                        else:
                            st.error(f"**❌ {i}. {validation['insight']}**")

                        st.caption(f"Confiança: {confidence:.2f}")

                        # Metadados adicionais
                        metadata = validation.get('metadata', {})
                        if metadata:
                            with st.expander("📊 Detalhes da Análise"):
                                st.json(metadata)

                        st.divider()

                else:
                    st.warning("⚠️ Nenhum resultado de validação obtido.")

            except Exception as e:
                st.error(f"❌ Erro na validação: {str(e)}")


def show_rag_statistics():
    """Exibe estatísticas do sistema RAG."""
    st.subheader("📊 Estatísticas do Sistema RAG")
    
    if 'rag_service' not in st.session_state:
        st.warning("Serviço RAG não inicializado. Por favor, aguarde...")
        return
    
    try:
        # Get basic statistics
        stats = st.session_state.rag_service.get_statistics()
        
        # Display basic stats
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total de Documentos", stats.get('total_documents', 0))
        with col2:
            st.metric("Total de Embeddings", stats.get('total_embeddings', 0))
        with col3:
            st.metric("Tamanho do Índice", f"{stats.get('index_size_mb', 0):.2f} MB")
        
        # Display document type distribution if available
        if 'documents_by_type' in stats and stats['documents_by_type']:
            st.subheader("📄 Documentos por Tipo")
            df_types = pd.DataFrame(
                list(stats['documents_by_type'].items()),
                columns=['Tipo de Documento', 'Quantidade']
            )
            st.bar_chart(df_types.set_index('Tipo de Documento'))
        
        # Display embedding statistics if available
        if 'embedding_stats' in stats:
            st.subheader("🧮 Estatísticas de Embeddings")
            st.json(stats['embedding_stats'])
            
    except Exception as e:
        st.error(f"Erro ao carregar estatísticas: {str(e)}")
        logger.error(f"Error in show_rag_statistics: {str(e)}")


def show_rag_examples():
    """Exibe exemplos de uso do sistema RAG."""
    st.subheader("💡 Exemplos de Uso")
    st.markdown("""
    ### 🔍 **Consultas Semânticas**

    O sistema RAG permite fazer consultas em linguagem natural sobre os documentos fiscais:

    **Exemplos de consultas:**
    - *"Encontre notas fiscais da empresa XYZ"*
    - *"Documentos com produtos de escritório emitidos este mês"*
    - *"Qual o valor total das compras do fornecedor ABC?"*
    - *"Notas fiscais com CFOP 5102"*
    - *"Documentos com valores acima de R$ 10.000"*

    ### ✅ **Validação Inteligente**

    Valide novos documentos comparando com padrões de documentos similares:

    - **Formato do documento:** Verifica se está de acordo com padrões
    - **Campos obrigatórios:** Confirma se todos os campos necessários estão presentes
    - **Faixas de valores:** Compara com valores típicos para o tipo de documento
    - **Padrões do emissor:** Analisa se o documento segue padrões do emissor

    ### 📊 **Processamento de Documentos**

    1. **Upload:** Documentos são processados (OCR/XML) normalmente
    2. **Chunking:** Conteúdo é dividido em pedaços menores (chunks)
    3. **Embedding:** Cada chunk recebe um vetor de embedding usando Gemini
    4. **Armazenamento:** Chunks e embeddings são salvos no banco vetorial
    5. **Busca:** Consultas geram embeddings e buscam chunks similares

    ### 🎯 **Como Funciona o RAG**

    1. **Consulta do usuário** → Embedding gerado
    2. **Busca semântica** → Documentos similares encontrados
    3. **Contexto extraído** → Chunks relevantes selecionados
    4. **Prompt RAG** → Contexto + pergunta enviados ao Gemini
    5. **Resposta gerada** → Baseada apenas no contexto dos documentos
    """)


def main():
    """Página principal do sistema RAG."""
    st.title("🧠 RAG - Retrieval-Augmented Generation")
    st.markdown("*Sistema de busca semântica e geração de respostas usando IA*")

    # Verificar se o serviço RAG está disponível
    if not initialize_rag_service():
        st.error("❌ Sistema RAG não disponível. Verifique as configurações.")
        return

    # Menu de navegação
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🔄 Monitoramento",
        "🔍 Busca Semântica",
        "📝 Processar Documento",
        "✅ Validação",
        "📊 Estatísticas",
        "💡 Exemplos"
    ])

    with tab1:
        show_rag_monitoring()

    with tab2:
        show_semantic_search()

    with tab3:
        show_document_processing()

    with tab4:
        show_document_validation()

    with tab5:
        show_rag_statistics()

    with tab6:
        show_rag_examples()

    # Rodapé com informações técnicas
    st.divider()
    st.caption("""
    **Sistema RAG - SkyNET-I2A2**

    - **Embeddings:** Google Gemini (768 dimensões)
    - **Vector Store:** Supabase com pgvector
    - **LLM:** Google Gemini 2.0-Flash / 1.5-Flash
    - **Busca:** Similaridade de cosseno com HNSW
    """)


if __name__ == "__main__":
    main()
