# 💬 Chat IA - Sistema de Assistente Inteligente

O sistema de chat IA do SkyNET-I2A2 oferece um assistente inteligente baseado em LLM (Google Gemini) para responder perguntas sobre documentos fiscais e dados CSV processados no sistema.

## 🚀 Funcionalidades

### 🤖 Assistente Inteligente
- **Análise de Documentos Fiscais**: Responde perguntas sobre NFe, NFCe, CTe processados
- **Análise de CSV**: Interpreta e analisa dados de planilhas carregadas
- **Análise Financeira**: Fornece insights sobre valores, impostos e tendências
- **Validação Inteligente**: Identifica problemas e inconsistências nos documentos

### 💾 Cache Inteligente
- **Economia de Tokens**: Respostas são cacheadas para evitar chamadas desnecessárias à API
- **Histórico de Conversas**: Mantém contexto das conversas para respostas mais relevantes
- **Busca Semântica**: Encontra documentos relevantes baseado no conteúdo da pergunta

### 🔧 Gerenciamento de Sessões
- **Múltiplas Sessões**: Crie sessões separadas para diferentes análises
- **Histórico Persistente**: Todas as conversas são salvas no banco de dados
- **Carregamento Rápido**: Recarregue conversas anteriores facilmente

## 🗄️ Estrutura do Banco de Dados

### Tabelas Criadas

#### `chat_sessions`
Armazena sessões de chat com metadados.

```sql
CREATE TABLE chat_sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_name VARCHAR,
  user_id VARCHAR,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  is_active BOOLEAN DEFAULT true
);
```

#### `chat_messages`
Armazena todas as mensagens das conversas.

```sql
CREATE TABLE chat_messages (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
  message_type VARCHAR CHECK (message_type IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);
```

#### `analysis_cache`
Cache de respostas para economizar tokens.

```sql
CREATE TABLE analysis_cache (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  cache_key VARCHAR UNIQUE NOT NULL,
  query_type VARCHAR NOT NULL,
  query_text TEXT NOT NULL,
  context_data JSONB,
  response_content TEXT NOT NULL,
  response_metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ DEFAULT (now() + interval '7 days')
);
```

#### `document_summaries`
Resumos e embeddings de documentos para busca semântica.

```sql
CREATE TABLE document_summaries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  fiscal_document_id UUID REFERENCES fiscal_documents(id) ON DELETE CASCADE,
  summary_text TEXT,
  key_insights JSONB,
  embedding_vector VECTOR(1536),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

#### `analysis_insights`
Insights estruturados extraídos dos documentos.

```sql
CREATE TABLE analysis_insights (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  fiscal_document_id UUID REFERENCES fiscal_documents(id) ON DELETE CASCADE,
  analysis_id UUID REFERENCES analyses(id) ON DELETE SET NULL,
  insight_type VARCHAR NOT NULL,
  insight_category VARCHAR,
  insight_text TEXT NOT NULL,
  confidence_score DECIMAL(3,2),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);
```

## 🛠️ Como Usar

### 1. Aplicar Migrações

Execute as migrações para criar as tabelas necessárias:

```bash
# Para Supabase (usando string de conexão)
python scripts/apply_migrations.py "postgresql://user:pass@host:5432/dbname"

# Para ambiente local (se aplicável)
python scripts/apply_migrations.py "postgresql://localhost:5432/skynet_db"
```

### 2. Configurar Variáveis de Ambiente

Certifique-se que as seguintes variáveis estão configuradas em `.streamlit/secrets.toml`:

```toml
GOOGLE_API_KEY = "your_google_api_key_here"
SUPABASE_URL = "your_supabase_url"
SUPABASE_KEY = "your_supabase_key"
```

### 3. Executar o Sistema

```bash
streamlit run app.py
```

### 4. Acessar o Chat

1. No menu lateral, clique em **"Chat IA"**
2. Clique em **"🆕 Nova Sessão"** para começar
3. Digite suas perguntas sobre documentos fiscais ou dados CSV

## 💡 Exemplos de Perguntas

### Sobre Documentos Fiscais
- "Quais são os documentos processados hoje?"
- "Mostre um resumo financeiro dos últimos 30 dias"
- "Quais documentos têm problemas de validação?"
- "Qual é o valor total das notas fiscais?"
- "Mostre os principais fornecedores por volume"

### Sobre Análise de CSV
- "Qual é a média de vendas por mês?"
- "Quais produtos têm mais outliers?"
- "Mostre a distribuição de valores por categoria"
- "Identifique tendências nos dados"

### Sobre Validação
- "Quais documentos falharam na validação?"
- "Mostre inconsistências encontradas"
- "Verifique se os CNPJs estão válidos"

## 🔧 Desenvolvimento

### Arquivos Principais

#### Backend
- `backend/agents/chat_agent.py` - Agente principal do chat
- `backend/agents/chat_coordinator.py` - Coordenador das funcionalidades
- `backend/tools/chat_tools.py` - Ferramentas de análise

#### Frontend
- `frontend/pages/chat.py` - Interface do usuário no Streamlit

#### Scripts
- `scripts/test_chat_system.py` - Script de teste do sistema

### Testar o Sistema

Execute o script de teste para verificar se tudo está funcionando:

```bash
python scripts/test_chat_system.py
```

### API do Chat

#### Criar Sessão
```python
from backend.agents.chat_coordinator import ChatCoordinator

coordinator = ChatCoordinator(supabase_client)
session_id = await coordinator.initialize_session("Minha Análise")
```

#### Processar Pergunta
```python
response = await coordinator.process_query(
    session_id=session_id,
    query="Quais documentos foram processados?",
    context={'query_type': 'document_analysis'}
)
```

#### Buscar Documentos
```python
results = await coordinator.search_documents(
    "NFe",
    {"document_type": "NFe", "date_from": "2024-01-01"}
)
```

## ⚡ Otimizações

### Cache de Respostas
- Respostas são automaticamente cacheadas por 7 dias
- Chave de cache baseada na query + contexto
- Reduz custos com API do Google Gemini

### Busca Semântica
- Embeddings dos documentos para busca inteligente
- Similaridade vetorial para encontrar documentos relevantes
- Indexação automática de novos documentos

### Gerenciamento de Memória
- Histórico de conversa limitado (últimas 10 mensagens)
- Limpeza automática de cache expirado
- Compressão de metadados

## 🐛 Troubleshooting

### Erro: "pgvector extension not available"
```bash
# No Supabase, execute via SQL Editor:
CREATE EXTENSION IF NOT EXISTS vector;
```

### Erro: "GOOGLE_API_KEY not found"
- Verifique se a chave está em `.streamlit/secrets.toml`
- Certifique-se que a API do Google AI está habilitada

### Erro: "No documents found"
- Faça upload de alguns documentos primeiro
- Execute uma análise de CSV para ter dados

### Performance Lenta
- Verifique se o cache está sendo usado
- Considere aumentar o limite de rate da API do Google
- Otimize queries de busca com filtros específicos

## 📊 Métricas e Monitoramento

O sistema coleta as seguintes métricas:

- **Tokens Utilizados**: Por query e total da sessão
- **Taxa de Cache**: Percentual de respostas do cache
- **Tempo de Resposta**: Latência das queries
- **Tipos de Análise**: Distribuição de tipos de pergunta

Acesse via:
```python
# Ver estatísticas da sessão
history = await coordinator.get_session_history(session_id)
for msg in history:
    if msg.get('metadata'):
        print(f"Tokens: {msg['metadata'].get('tokens_used')}")
```
