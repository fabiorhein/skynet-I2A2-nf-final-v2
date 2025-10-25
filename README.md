++ BEGIN LICENSE
MIT
++ END LICENSE
# SkyNET-I2A2 — Processamento Fiscal Inteligente (MVP)

Sistema avançado para processamento de documentos fiscais com suporte a extração via OCR, validação de regras fiscais, análise inteligente com IA, e integração com Supabase.

## 🚀 Visão Geral

O SkyNET-I2A2 é uma solução completa e inteligente para processamento de documentos fiscais que oferece:

- **Processamento Inteligente de Documentos**:
  - Parser XML avançado com `lxml`
  - OCR integrado com Tesseract para PDFs e imagens
  - Suporte a múltiplos formatos (NFe, NFCe, CTe, MDFe)
  - Classificação automática de documentos

- **Sistema de Chat IA Avançado**:
  - Assistente inteligente baseado em Google Gemini
  - Análise de documentos fiscais e dados CSV
  - Cache inteligente para economia de tokens
  - Histórico persistente de conversas

- **Validação Fiscal Completa**:
  - Verificação de CNPJ/CPF
  - Validação de somas e totais
  - Análise de impostos (ICMS, IPI, PIS, COFINS)
  - Detecção de anomalias e fraudes

- **Armazenamento Flexível**:
  - Modo local com JSON para desenvolvimento
  - Integração nativa com Supabase/PostgreSQL
  - Interface unificada para migração entre backends

## 💬 Sistema de Chat IA

O SkyNET-I2A2 oferece um assistente inteligente baseado em LLM (Google Gemini) para responder perguntas sobre documentos fiscais e dados CSV processados no sistema.

### 🤖 Funcionalidades do Chat

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

### 🗄️ Banco de Dados do Chat

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

### 📋 Como Usar o Chat

1. **Acesse o Chat**:
   - No menu lateral, clique em **"Chat IA"**

2. **Crie uma Nova Sessão**:
   - Clique em **"🆕 Nova Sessão"** para começar
   - Digite suas perguntas sobre documentos fiscais ou dados CSV

3. **Exemplos de Perguntas**:

   **Sobre Documentos Fiscais:**
   - "Quais são os documentos processados hoje?"
   - "Mostre um resumo financeiro dos últimos 30 dias"
   - "Quais documentos têm problemas de validação?"
   - "Qual é o valor total das notas fiscais?"

   **Sobre Análise de CSV:**
   - "Qual é a média de vendas por mês?"
   - "Quais produtos têm mais outliers?"
   - "Mostre a distribuição de valores por categoria"

   **Sobre Validação:**
   - "Quais documentos falharam na validação?"
   - "Mostre inconsistências encontradas"
   - "Verifique se os CNPJs estão válidos"

### 🧪 Testando o Sistema de Chat

Execute o script de teste para verificar se tudo está funcionando:

```bash
python scripts/test_chat_system.py
```

## 📄 Processador de Documentos Fiscais

O `FiscalDocumentProcessor` é uma classe Python projetada para extrair texto e dados estruturados de documentos fiscais em vários formatos, incluindo PDFs e imagens.

### ⚙️ Funcionalidades

- **Extração de Texto**: OCR com Tesseract para PDFs e imagens
- **Identificação Automática**: Reconhece tipos de documento (NFe, NFCe, CTe, MDFe)
- **Extração Estruturada**: Campos como emitente, destinatário, itens e impostos
- **Suporte a Lote**: Processamento de múltiplos documentos
- **Integração com LLM**: Usa IA para melhorar a precisão da extração

### 📁 Formatos Suportados

- **Imagens**: PNG, JPG, JPEG, TIFF, BMP
- **Documentos**: PDF (com ou sem camada de texto)
- **XML**: NFe, NFCe, CTe, MDFe

### 💻 Uso Básico

```python
from backend.tools.fiscal_document_processor import FiscalDocumentProcessor

# Cria uma instância do processador
processor = FiscalDocumentProcessor()

# Processa um documento
result = processor.process_document("caminho/para/documento.pdf")

# Exibe os resultados
print(f"Tipo de documento: {result.get('document_type')}")
print(f"Número: {result.get('numero')}")
print(f"Emitente: {result.get('emitente', {}).get('razao_social')}")
print(f"Valor Total: R$ {result.get('valor_total', 0):.2f}")
```

## 🏗️ Estrutura do Projeto

```
skynet-I2A2-nf-final-v2/
├── app.py                 # Ponto de entrada da aplicação Streamlit
├── config.py              # Configurações globais e ambiente
├── requirements.in        # Dependências principais
├── requirements.txt       # Dependências travadas
│
├── backend/
│   ├── agents/            # Agentes de processamento
│   │   ├── __init__.py
│   │   ├── analyst.py     # Análise de documentos
│   │   ├── chat_agent.py  # Agente do sistema de chat
│   │   ├── chat_coordinator.py # Coordenador do chat
│   │   ├── classifier.py  # Classificação de documentos
│   │   ├── coordinator.py # Orquestração do fluxo
│   │   ├── extraction.py  # Extração de dados
│   │   └── validator.py   # Validação fiscal
│   │
│   ├── tools/             # Ferramentas e utilitários
│   │   ├── chat_tools.py        # Ferramentas do chat
│   │   ├── eda_analyzer.py      # Análise exploratória
│   │   ├── fiscal_document_processor.py # Processador fiscal
│   │   ├── fiscal_validator.py # Validações fiscais
│   │   ├── llm_ocr_mapper.py    # Mapeador OCR com IA
│   │   ├── ocr_processor.py     # Processamento OCR
│   │   └── xml_parser.py        # Parser XML
│   │
│   ├── storage.py         # Implementação de armazenamento
│   └── storage_interface.py # Interface de armazenamento
│
├── frontend/
│   ├── components/        # Componentes da UI reutilizáveis
│   └── pages/             # Páginas da aplicação
│       ├── chat.py        # Interface do chat IA
│       ├── home.py        # Página inicial
│       ├── upload_csv.py  # Upload e análise de CSV
│       └── history.py     # Histórico de documentos
│
├── migration/             # Scripts de migração do banco
│   ├── 001-create_fiscal_documents.sql
│   ├── 002-create_analyses_and_history.sql
│   ├── 003-create_sessions.sql
│   ├── 004-add_raw_text_column.sql
│   ├── 005-add_uploaded_at_column.sql
│   ├── 006-add_validation_columns.sql
│   ├── 007-add_validation_metadata_column.sql
│   ├── 008-create_chat_system.sql
│   ├── 009-enable_vector_extension.sql
│   └── 010-convert_embedding_to_vector.sql
│
├── examples/              # Scripts de exemplo
│   ├── fiscal_validator_example.py
│   ├── process_document.py
│   └── validate_fiscal_codes.py
│
├── scripts/               # Scripts utilitários
│   ├── apply_migrations.py
│   ├── test_chat_system.py
│   └── verify_chat_system.py
│
├── tests/                 # Testes automatizados
├── .streamlit/           # Configurações do Streamlit
│   ├── config.toml
│   └── secrets.toml       # Chaves e segredos (não versionado)
```

## ⚙️ Configuração

### 📋 Pré-requisitos

- **Sistema Operacional**: Windows 10/11, macOS 10.15+, ou Linux
- **Python**: 3.11 ou superior
- **Banco de Dados**:
  - SQLite (embutido para desenvolvimento)
  - PostgreSQL 12+ (produção)
- **Serviços Externos**:
  - Conta no [Supabase](https://supabase.com) (opcional)
  - Chave da API do Google (para sistema de chat)

### 🔧 Dependências do Sistema

#### Windows
```powershell
# Instalar Tesseract OCR (64-bit)
choco install tesseract --version 5.3.3
choco install poppler

# Ou baixe manualmente:
# Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
# Poppler: https://github.com/oschwartz10612/poppler-windows/releases/
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-por poppler-utils
```

#### macOS
```bash
brew install tesseract tesseract-lang
brew install poppler
```

## 🚀 Instalação Rápida

1. **Clonar o repositório**:
   ```bash
   git clone https://github.com/seu-usuario/skynet-I2A2-nf-final-v2.git
   cd skynet-I2A2-nf-final-v2
   ```

2. **Configurar ambiente virtual**:
   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate

   # Linux/MacOS
   python3 -m venv venv
   cp .env.example .env

   # Editar o arquivo .env com suas credenciais
   # Windows: notepad .env
   # Linux: nano .env
   ```

5. **Configurar Tesseract OCR**:
   - Verifique se o Tesseract está no PATH
   - Configure o caminho no arquivo `.env`:
     ```
     TESSERACT_PATH=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
     TESSDATA_PREFIX=C:\\Program Files\\Tesseract-OCR\\tessdata
     ```

6. **Iniciar a aplicação**:
   ```bash
   streamlit run app.py
   ```

   A aplicação estará disponível em: http://localhost:8501

## 📦 Gerenciamento de Dependências

O projeto utiliza `pip-tools` para gerenciar dependências de forma eficiente e reproduzível.

### Comandos Úteis

| Comando | Descrição |
|---------|-----------|
| `pip-compile --upgrade` | Atualiza `requirements.txt` baseado em `requirements.in` |
| `pip-sync` | Sincroniza o ambiente com `requirements.txt` |
| `pip-compile --upgrade-package <pkg>` | Atualiza um pacote específico |

### Adicionando Novas Dependências

1. Edite `requirements.in`
2. Execute:
   ```bash
   pip-compile --upgrade
   pip-sync
   ```

### Dependências Principais

- **Processamento de Dados**: pandas, numpy, scipy
- **OCR e PDF**: pytesseract, pdf2image, pypdf, lxml
- **IA/ML**: langchain, google-generativeai, sentence-transformers
- **Banco de Dados**: supabase, sqlalchemy, psycopg2-binary
- **Interface**: streamlit, streamlit-extras
- **Utils**: python-dotenv, loguru, pydantic

## 🗄️ Configuração do Banco de Dados

### Migrações

O sistema utiliza um sistema de migrações SQL para gerenciar alterações no esquema do banco de dados:

```bash
# Aplicar todas as migrações
python scripts/run_migration.py

# Ou aplicar apenas as migrações do chat
python scripts/run_chat_migrations_only.py
```

### Supabase (Produção)

1. **Criar um novo projeto** em [Supabase](https://supabase.com)

2. **Configurar variáveis de ambiente**:
   ```bash
   SUPABASE_URL=https://seu-projeto.supabase.co
   SUPABASE_KEY=sua-chave-supabase
   GOOGLE_API_KEY=sua-chave-google-api
   ```

3. **Aplicar migrações**:
   ```bash
   # Usando a CLI do Supabase
   supabase db push

   # Ou via SQL Editor no dashboard
   ```

## 🐛 Solução de Problemas

### Problemas Comuns

1. **Erro ao processar PDFs**
   - Verifique se o Poppler está instalado
   - Confira as permissões de leitura/escrita

2. **Falha na conexão com o Supabase**
   - Verifique as credenciais no arquivo `.env`
   - Confira se o serviço está online

3. **Problemas com OCR**
   - Verifique se o Tesseract está instalado corretamente
   - Configure o caminho correto em `TESSERACT_PATH` e `TESSDATA_PREFIX`

4. **Sistema de Chat não funciona**
   - Verifique se a `GOOGLE_API_KEY` está configurada
   - Teste com `python scripts/test_chat_system.py`

### Logs

Os logs são armazenados em `logs/app.log` por padrão. Configure o nível em `.env`:
```
LOG_LEVEL=INFO
LOG_FILE=app.log
```

## 📚 Documentação Adicional

Toda a documentação foi consolidada neste README.md. Para mais informações sobre:

- **Desenvolvimento**: Consulte os comentários no código e docstrings
- **Contribuição**: Siga as boas práticas descritas no README.md
- **FAQ**: Questões comuns estão na seção de Solução de Problemas acima

## 🤝 Suporte

Para obter suporte, entre em contato:

- E-mail: suporte@empresa.com
- Issues do GitHub: [https://github.com/seu-usuario/skynet-I2A2-nf-final-v2/issues](https://github.com/seu-usuario/skynet-I2A2-nf-final-v2/issues)
- Documentação: [https://docs.empresa.com/skynet-i2a2](https://docs.empresa.com/skynet-i2a2)

## 📄 Licença

Este projeto está licenciado sob a licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

---
Feito com ❤️ pela Equipe SkyNET-I2A2
