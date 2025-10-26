"""
Página RAG (Retrieval-Augmented Generation) para o SkyNET-I2A2.

Esta página demonstra o sistema RAG implementado, permitindo:
1. Consultas semânticas em documentos fiscais
2. Visualização de estatísticas do sistema RAG
3. Processamento de documentos para embeddings
4. Validação de documentos usando contexto
"""
import streamlit as st
import asyncio
import logging
from datetime import datetime
import pandas as pd
from typing import Dict, Any, List

# Backend imports
from backend.services import RAGService

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_rag_service():
    """Inicializa o serviço RAG se ainda não estiver inicializado."""
    if 'rag_service' not in st.session_state:
        try:
            st.session_state.rag_service = RAGService()
            logger.info("RAG service initialized")
        except Exception as e:
            st.error(f"Erro ao inicializar serviço RAG: {str(e)}")
            return False
    return True


def show_rag_statistics():
    """Exibe estatísticas do sistema RAG."""
    st.subheader("📊 Estatísticas do Sistema RAG")

    if not initialize_rag_service():
        return

    try:
        with st.spinner("Carregando estatísticas..."):
            stats = st.session_state.rag_service.get_embedding_statistics()

        if 'error' not in stats:
            # Métricas principais
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total de Chunks", f"{stats.get('total_chunks', 0):,}")
            with col2:
                st.metric("Documentos com Embeddings", f"{stats.get('documents_with_embeddings', 0):,}")
            with col3:
                st.metric("Total de Insights", f"{stats.get('total_insights', 0):,}")
            with col4:
                st.metric("Dimensão dos Vetores", stats.get('vector_dimension', 768))

            # Status dos embeddings
            status_dist = stats.get('embedding_status_distribution', {})
            if status_dist:
                st.subheader("Status dos Embeddings")
                status_df = pd.DataFrame(
                    list(status_dist.items()),
                    columns=['Status', 'Quantidade']
                )
                st.bar_chart(status_df.set_index('Status'))

        else:
            st.error(f"Erro ao carregar estatísticas: {stats['error']}")

    except Exception as e:
        st.error(f"Erro ao carregar estatísticas: {str(e)}")


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
    if st.button("🔍 Buscar", type="primary", use_container_width=True):
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

        submitted = st.form_submit_button("🚀 Processar Documento", type="primary", use_container_width=True)

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

        validate_submitted = st.form_submit_button("🔍 Validar Documento", type="primary", use_container_width=True)

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
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔍 Busca Semântica",
        "📝 Processar Documento",
        "✅ Validação",
        "📊 Estatísticas",
        "💡 Exemplos"
    ])

    with tab1:
        show_semantic_search()

    with tab2:
        show_document_processing()

    with tab3:
        show_document_validation()

    with tab4:
        show_rag_statistics()

    with tab5:
        show_rag_examples()

    # Rodapé com informações técnicas
    st.divider()
    st.caption("""
    **Sistema RAG - SkyNET-I2A2**

    - **Embeddings:** Google Gemini (768 dimensões)
    - **Vector Store:** Supabase com pgvector
    - **LLM:** Google Gemini Flash
    - **Busca:** Similaridade de cosseno com HNSW
    """)


if __name__ == "__main__":
    main()
