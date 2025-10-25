++ BEGIN LICENSE
MIT
++ END LICENSE
# SkyNET-I2A2 — Processamento Fiscal (MVP)

Sistema avançado para processamento de documentos fiscais com suporte a extração via OCR, validação de regras fiscais e integração com Supabase.

## 🚀 Visão Geral

SkyNET-I2A2 é uma solução completa para processamento de documentos fiscais que oferece:

- **Extração de Dados**:
  - Parser XML avançado com `lxml`
  - OCR integrado com Tesseract para PDFs e imagens
  - Suporte a múltiplos formatos de documentos fiscais (NFe, NFCe, CTe)

- **Validação Inteligente**:
  - Verificação de CNPJ/CPF
  - Validação de somas e totais
  - Análise de impostos e cálculos fiscais
  - Detecção de anomalias e possíveis fraudes

- **Armazenamento Flexível**:
  - Modo local com JSON para desenvolvimento
  - Integração nativa com Supabase/PostgreSQL
  - Interface unificada para fácil migração entre backends

- **Interface Moderna**:
  - Dashboard interativo com Streamlit
  - Visualização de documentos e histórico
  - Painel de análise e relatórios

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
│   │   ├── classifier.py  # Classificação de documentos
│   │   ├── coordinator.py # Orquestração do fluxo
│   │   ├── extraction.py  # Extração de dados
│   │   └── validator.py   # Validação fiscal
│   │
│   ├── models/            # Modelos de dados
│   │   └── document.py    # Modelo de documento fiscal
│   │
│   ├── tools/             # Ferramentas e utilitários
│   │   ├── ocr_processor.py # Processamento OCR
│   │   ├── fiscal_validator.py # Validações fiscais
│   │   └── ...
│   │
│   ├── storage.py         # Implementação de armazenamento
│   └── storage_interface.py # Interface de armazenamento
│
├── frontend/
│   ├── components/        # Componentes da UI reutilizáveis
│   └── pages/             # Páginas da aplicação
│       ├── home.py        # Página inicial
│       ├── upload.py      # Upload de documentos
│       └── history.py     # Histórico de documentos
│
├── migration/             # Scripts de migração do banco
│   ├── 001-create_tables.sql
│   ├── 002-add_columns.sql
│   └── ...
│
├── .streamlit/
│   ├── config.toml        # Configurações do Streamlit
│   └── secrets.toml       # Chaves e segredos (não versionado)
│
├── tests/                 # Testes automatizados
└── docs/                  # Documentação adicional
```

## 🆕 Melhorias Recentes

### ✨ Nova Interface do Usuário
- **Dashboard Moderno**: Redesenho completo da interface com Streamlit
- **Componentes Avançados**:
  - `streamlit-extras` para UI/UX aprimorada
  - Notificações em tempo real
  - Upload de múltiplos arquivos
  - Visualização de documentos integrada

### 🛠️ Melhorias Técnicas
- **OCR Aprimorado**:
  - Suporte a múltiplos idiomas (Português/Inglês)
  - Fallback automático entre idiomas
  - Tratamento de erros robusto

- **Desempenho**:
  - Cache de resultados de OCR
  - Processamento em lote para múltiplos documentos
  - Otimização de consultas ao banco de dados

- **Segurança**:
  - Validação de entrada aprimorada
  - Tratamento seguro de dados sensíveis
  - Logs detalhados para auditoria

### 📦 Novas Funcionalidades
- **Validação Fiscal**:
  - Verificação de chaves de acesso
  - Validação de assinaturas digitais
  - Cálculo de impostos (ICMS, IPI, PIS, COFINS)

- **Análise Inteligente**:
  - Detecção de anomalias
  - Classificação automática de documentos
  - Extração estruturada de dados

- **Integrações**:
  - Supabase para armazenamento em nuvem
  - Webhooks para notificações
  - API RESTful para integração com outros sistemas

## ⚙️ Configuração

### 📋 Pré-requisitos

- **Sistema Operacional**: Windows 10/11, macOS 10.15+, ou Linux
- **Python**: 3.11 ou superior
- **Banco de Dados**: 
  - SQLite (embutido para desenvolvimento)
  - PostgreSQL 12+ (produção)
- **Serviços Externos**:
  - Conta no [Supabase](https://supabase.com) (opcional)
  - Chave da API do Google (para alguns recursos avançados)

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
   source venv/bin/activate
   ```

3. **Instalar dependências**:
   ```bash
   # Atualizar pip e instalar dependências básicas
   python -m pip install --upgrade pip
   pip install pip-tools
   
   # Instalar dependências do projeto
   pip install -r requirements.txt
   
   # Se encontrar erros com numpy, instale separadamente:
   pip install numpy==2.3.4 --only-binary=:all:
   ```

4. **Configurar variáveis de ambiente**:
   ```bash
   # Copiar arquivo de exemplo
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
- **OCR e PDF**: pytesseract, pdf2image, pypdf
- **IA/ML**: langchain, google-generativeai
- **Web**: fastapi, uvicorn, httpx
- **Banco de Dados**: supabase, sqlalchemy
- **Interface**: streamlit, streamlit-extras

### Solução de Problemas

- **Erro de instalação**: Tente instalar as dependências principais primeiro:
  ```bash
  pip install python-dotenv pydantic fastapi uvicorn python-multipart
  pip install pandas numpy scipy
  pip install -r requirements.txt
  ```

- **Problemas com Tesseract**:
  - Verifique se o Tesseract está instalado e no PATH
  - Confirme o caminho em `TESSERACT_PATH` e `TESSDATA_PREFIX`

## 🚀 Executando o Projeto

### Modo Desenvolvimento

```bash
# Ativar ambiente virtual
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/MacOS

# Iniciar o Streamlit
streamlit run app.py
```

### Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```ini
# Configurações do Supabase
SUPABASE_URL=seu-projeto.supabase.co
SUPABASE_KEY=sua-chave-supabase

# Configurações de Log
LOG_LEVEL=INFO
LOG_FILE=app.log

# Configurações do Tesseract OCR
TESSERACT_PATH=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
TESSDATA_PREFIX=C:\\Program Files\\Tesseract-OCR\\tessdata

# Configurações de API
GOOGLE_API_KEY=sua-chave-google-api

# Configurações de Armazenamento
STORAGE_TYPE=supabase  # ou 'local' para desenvolvimento
```

### Iniciando com Docker (Opcional)

```bash
# Construir a imagem
docker build -t skynet-i2a2 .

# Executar o contêiner
docker run -p 8501:8501 -v $(pwd)/data:/app/data skynet-i2a2
```

Acesse: http://localhost:8501


## ⚙️ Configuração Avançada

### Ordem de Carregamento das Configurações

1. **Variáveis de Ambiente** (`.env` ou variáveis do sistema)
2. **Arquivo de Segredos** (`.streamlit/secrets.toml`)
3. **Configurações Padrão** (`config.py`)

### Exemplo de `secrets.toml`

Crie o arquivo `.streamlit/secrets.toml` com:

```toml
[connections.supabase]
url = "https://seu-projeto.supabase.co"
key = "sua-chave-supabase"

[google]
api_key = "sua-chave-google"

[app]
debug = false
log_level = "INFO"

[ocr]
tesseract_path = "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
tessdata_prefix = "C:\\Program Files\\Tesseract-OCR\\tessdata"

[storage]
type = "supabase"  # ou 'local'
max_file_size = 10485760  # 10MB
allowed_extensions = ["pdf", "jpg", "jpeg", "png", "xml"]
```

### Configurações de Log

Níveis de log disponíveis:
- `DEBUG`: Informações detalhadas para depuração
- `INFO`: Informações gerais de operação
- `WARNING`: Avisos sobre problemas não críticos
- `ERROR`: Erros que não interrompem a execução
- `CRITICAL`: Erros fatais que encerram a aplicação

Configure o nível de log no arquivo `.env`:
```
LOG_LEVEL=INFO
LOG_FILE=app.log
```

CREATE TABLE document_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES fiscal_documents(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID
);

-- Análises realizadas
CREATE TABLE analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES fiscal_documents(id) ON DELETE CASCADE,
    analysis_type VARCHAR(50) NOT NULL,
    result JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);
```

#### Configuração do Supabase

1. **Criar um novo projeto** em [Supabase](https://supabase.com)
2. **Executar migrações**:
   ```bash
   # Instalar a CLI do Supabase
   npm install -g supabase
   
   # Fazer login
   supabase login
   
   # Aplicar migrações
   supabase db push
   ```

3. **Configurar políticas RLS**:
   ```sql
   -- Habilitar RLS nas tabelas
   ALTER TABLE fiscal_documents ENABLE ROW LEVEL SECURITY;
   ALTER TABLE document_history ENABLE ROW LEVEL SECURITY;
   ALTER TABLE analyses ENABLE ROW LEVEL SECURITY;
   
   -- Criar políticas de acesso
   CREATE POLICY "Permitir leitura pública" ON fiscal_documents
   FOR SELECT USING (true);
   
   CREATE POLICY "Permitir inserção autenticada" ON fiscal_documents
   FOR INSERT WITH CHECK (auth.role() = 'authenticated');
   ```

4. **Configurar armazenamento**:
   - Criar um bucket chamado `documents`
   - Configurar políticas de acesso apropriadas

## 🔍 Uso Avançado

### Processamento em Lote

```python
from backend.storage import storage_manager
from backend.agents.coordinator import process_document

# Processar múltiplos documentos
documents = ["doc1.pdf", "doc2.xml", "doc3.jpg"]
for doc_path in documents:
    try:
        result = process_document(doc_path)
        print(f"Processado {doc_path}: {result['status']}")
    except Exception as e:
        print(f"Erro ao processar {doc_path}: {str(e)}")
```

### API REST

O sistema expõe endpoints REST para integração:

```http
# Enviar documento para processamento
POST /api/documents
Content-Type: multipart/form-data

# Obter status de um documento
GET /api/documents/{document_id}

# Listar documentos
GET /api/documents?status=processed&limit=10
```

### Webhooks

Configure webhooks para receber notificações de eventos:

```python
# Exemplo de configuração de webhook
WEBHOOKS = {
    'document_processed': 'https://seu-servidor.com/webhook/processed',
    'validation_failed': 'https://seu-servidor.com/webhook/error'
}
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
   - Confira o caminho do Tesseract no arquivo de configuração

### Logs

Os logs são armazenados em `logs/app.log` por padrão. Níveis de log:

- `DEBUG`: Informações detalhadas para depuração
- `INFO`: Ações importantes do sistema
- `WARNING`: Eventos que podem indicar problemas
- `ERROR`: Erros que não interrompem a execução
- `CRITICAL`: Erros fatais

## 📈 Monitoramento

### Métricas

O sistema expõe métricas no formato Prometheus em `/metrics`:

```
# HELP documents_processed_total Total de documentos processados
# TYPE documents_processed_total counter
documents_processed_total{status="success"} 42
documents_processed_total{status="error"} 3

# HELP processing_duration_seconds Tempo de processamento
# TYPE processing_duration_seconds histogram
processing_duration_seconds_bucket{le="0.5"} 12
processing_duration_seconds_bucket{le="1.0"} 35
processing_duration_seconds_bucket{le="+Inf"} 45
```

### Alertas

Configure alertas para:
- Alta taxa de erros
- Tempo de processamento elevado
- Espaço em disco baixo

## 📚 Documentação Adicional

- [Guia de Estilo de Código](docs/CODING_STANDARDS.md)
- [Guia de Contribuição](docs/CONTRIBUTING.md)
- [Documentação da API](docs/API.md)
- [Perguntas Frequentes](docs/FAQ.md)

## 🤝 Suporte

Para obter suporte, entre em contato:

- E-mail: suporte@empresa.com
- Issues do GitHub: [https://github.com/seu-usuario/skynet-I2A2-nf-final-v2/issues](https://github.com/seu-usuario/skynet-I2A2-nf-final-v2/issues)
- Documentação: [https://docs.empresa.com/skynet-i2a2](https://docs.empresa.com/skynet-i2a2)

## 📄 Licença

Este projeto está licenciado sob a licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

---

Feito com ❤️ pela Equipe SkyNET-I2A2

#### Arquivo de Configuração
Crie um arquivo `.streamlit/secrets.toml` com as seguintes configurações:

```toml
[connections.supabase]
# Configurações de conexão com o Supabase
URL = "https://seu-projeto.supabase.co"
KEY = "sua-chave-anon-ou-service-role"
DATABASE = "postgres"
USER = "postgres.[seu-project-ref]"
PASSWORD = "sua-senha-do-banco"
HOST = "aws-1-regiao.pooler.supabase.com"
PORT = "5432"

# Níveis de log disponíveis: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = "INFO"

# Configurações de armazenamento
STORAGE_TYPE = "supabase"  # Pode ser 'local' ou 'supabase'

# Configurações de API
GOOGLE_API_KEY = "sua-api-key-google"

# Caminho para o executável do Tesseract OCR (necessário para processamento de imagens/PDFs)
TESSERACT_PATH = "C:\\caminho\\para\\tesseract.exe"

# Configurações de paginação
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 1000
```

2. O arquivo `config.py` irá carregar essas configurações e exportá-las para uso em toda a aplicação.

### Gerenciamento de Histórico

O sistema mantém um histórico detalhado de todas as operações realizadas nos documentos fiscais, incluindo:
- Criação de novos documentos
- Atualizações de status
- Análises realizadas
- Eventos do sistema

#### Visualizando o Histórico
O histórico pode ser acessado de duas formas:

1. **Através da API**:
   ```python
   from backend.storage import storage_manager
   
   # Obter histórico de um documento específico
   history = storage_manager.storage.get_document_history(document_id)
   
   # Salvar um novo evento no histórico
   event = {
       'fiscal_document_id': document_id,
       'event_type': 'analysis_completed',
       'event_data': {
           'status': 'success',
           'details': 'Análise concluída com sucesso'
       }
   }
   storage_manager.storage.save_history(event)
   ```

2. **Através da interface web**:
   - Acesse a página de detalhes de um documento
   - A seção "Histórico" exibe todos os eventos relacionados ao documento

#### Políticas de Retenção
- O histórico é mantido indefinidamente por padrão
- Para documentos com muitos eventos, considere implementar uma política de retenção personalizada
- Use o método `cleanup_old_history()` para remover eventos antigos quando necessário

## Sistema de Migrações

O projeto utiliza um sistema de migrações SQL para gerenciar alterações no esquema do banco de dados de forma controlada e reproduzível.

### Estrutura de Arquivos

As migrações ficam no diretório `migration/` e seguem o padrão de nomenclatura:
```
migration/
  001-nome-da-migracao.sql
  002-outra-migracao.sql
  ...
```

### Como Funciona

1. **Execução de Migrações**:
   ```bash
   python scripts/run_migration.py
   ```
   O script irá:
   - Listar todas as migrações disponíveis
   - Pedir confirmação antes de executar
   - Executar cada migração em ordem numérica
   - Manter um log detalhado de cada operação

2. **Criando uma Nova Migração**:
   - Crie um novo arquivo SQL no diretório `migration/`
   - Use o próximo número sequencial (ex: `007-nova-tabela.sql`)
   - Inclua comentários explicativos no início do arquivo
   - Escreva instruções SQL atômicas e idempotentes

3. **Boas Práticas**:
   - Cada migração deve ser independente e auto-contida
   - Sempre use `IF NOT EXISTS` ou `IF EXISTS` para evitar erros
   - Inclua rollback quando possível (em comentários)
   - Teste as migrações em um ambiente de desenvolvimento primeiro

4. **Exemplo de Migração**:
   ```sql
   -- 007-add-user-roles.sql
   -- Adiciona suporte a diferentes tipos de usuários
   
   -- Adiciona a coluna role à tabela users
   ALTER TABLE users 
   ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user';
   
   -- Cria um índice para consultas por role
   CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
   
   -- Opcional: Rollback
   -- ALTER TABLE users DROP COLUMN IF EXISTS role;
   -- DROP INDEX IF EXISTS idx_users_role;
   ```

5. **Dicas de Desenvolvimento**:
   - Sempre faça backup do banco antes de executar migrações em produção
   - Use transações (`BEGIN;` ... `COMMIT;`) para operações críticas
   - Documente alterações quebradoras de compatibilidade
   - Considere o impacto em dados existentes ao modificar esquemas

## Requisitos (Windows)

- Python 3.10+ (recomendado usar `venv`)
- Tesseract OCR — instale o binário para Windows e verifique se `tesseract.exe` está no `PATH`
- Poppler (opcional) — necessário para converter PDFs escaneados em imagens via `pdf2image`
- Biblioteca `toml` para gerenciamento de configurações

Instalação rápida (PowerShell):

```pwsh
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Se não tiver `requirements.txt` atual, instale manualmente pacotes principais:

```pwsh
.\venv\Scripts\Activate.ps1
pip install streamlit pytesseract pillow pypdf lxml pandas numpy
```

> Nota: em Windows alguns pacotes (como `lxml`) podem exigir wheels binários. Use wheels pré-compiladas quando necessário.

## Como executar

1. Ative o venv:

```pwsh
.\venv\Scripts\Activate.ps1
```

2. Execute a aplicação:

```pwsh
streamlit run app.py
```

3. Use a página "Upload de Documento" no Streamlit para enviar XML, PDF ou imagens.

## Resolução de problemas comuns

- `ModuleNotFoundError: No module named 'pypdf'` — instale no venv:

```pwsh
.\venv\Scripts\Activate.ps1
pip install pypdf
```

- Erros ao instalar `lxml` — prefira instalar uma wheel binária compatível com sua versão do Python.

- `pytesseract` não encontra `tesseract.exe` — verifique instalação e `PATH`; o projeto permite configurar caminho via `config.py`.

- PDF escaneado sem texto: instale Poppler e adicione `poppler/bin` ao `PATH` para permitir `pdf2image`.

- Migração `raw_text`: aplique `migration/004-add_raw_text_column.sql` em seu banco (Supabase/Postgres) se usar o backend remoto.

## Testes

```pwsh
.\venv\Scripts\Activate.ps1
pip install pytest
pytest -q
```

## Notas para desenvolvedores

- O parser XML (`backend/tools/xml_parser.py`) retorna um dicionário com campos mínimos: `emitente`, `destinatario`, `itens`, `impostos`, `numero`, `data_emissao`, `total`, `raw_text`.
- Quando o arquivo é processado via OCR, o texto bruto é exposto em `raw_text` e mapeado para campos estruturados por heurísticas no `ocr_text_to_document` (com opção IA).
- `backend/storage_interface.py` define o contrato de storage; `backend/storage.py` contém a implementação local.

## Contribuição

1. Abra uma issue descrevendo o problema ou feature.
2. Crie um branch `feature/...` ou `fix/...` e envie um PR com testes quando aplicável.

## Extras que posso adicionar

- Gerar um `requirements.txt` pinando versões testadas.
- Criar `backend/storage_supabase.py` de exemplo e instruções de deploy para Supabase.
- Script para aplicar migrations automaticamente (opcional).

Diga qual desses extras você prefere e eu adiciono.

---

Licença: MIT

# SkyNET-I2A2 - Sistema de Agentes para Processamento Fiscal (MVP)

Projeto MVP para extração, validação, classificação e análise exploratória de documentos fiscais (NFe/NFCe/CTe).

Instruções rápidas (Windows)
---------------------------

1) Crie e ative um virtualenv (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2) Atualize pip e instale dependências:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

3) Tesseract OCR (required for scanned PDFs)

- Baixe e instale Tesseract para Windows (recomendado: UB Mannheim build):
  https://github.com/UB-Mannheim/tesseract/wiki
- Anote o caminho de instalação (ex: `C:\Program Files\Tesseract-OCR\tesseract.exe`) e defina `TESSERACT_PATH` no seu `.env` ou coloque o diretório no PATH.

4) Poppler (necessário para pdf2image -> imagens)

- Baixe Poppler for Windows (ex.: https://github.com/oschwartz10612/poppler-windows/releases) e extraia.
- Adicione a pasta `poppler-xx/bin` ao `PATH` do Windows ou coloque o caminho em `POPPLER_PATH` se desejar.
- Se Poppler não estiver disponível, a aplicação tentará usar pypdf para extrair texto de PDFs com texto selecionável; para PDFs escaneados Poppler+Tesseract são necessários.

5) Rodar Streamlit

```powershell
streamlit run app.py
```

Persistência local (MVP)
------------------------

- Os documentos processados são salvos localmente em `data/processed_documents.json` via `backend/storage.py`.
- Para limpar o histórico, exclua esse arquivo ou substitua seu conteúdo.
- Para usar Supabase/Postgres (opcional), você pode substituir o backend de armazenamento — eu posso gerar um módulo `backend/storage_supabase.py` + SQL de criação de tabelas se desejar.

Notas sobre LangChain / LLMs
---------------------------

- O `requirements.txt` não força `langchain` por padrão (opcional). Se quiser recursos LLM assistidos, instale manualmente uma versão compatível, por exemplo:

```powershell
pip install "langchain>=0.3.0"
```

Migrations (Supabase/Postgres)
--------------------------------

SQL migration scripts are available in the `migration/` folder in numeric order:

- `001-create_fiscal_documents.sql`
- `002-create_analyses_and_history.sql`
- `003-create_sessions.sql`

To apply them you can either use the Supabase SQL editor (paste each file in order) or run them with psql:

```powershell
psql "postgresql://user:password@host:5432/dbname" -f migration/001-create_fiscal_documents.sql
psql "postgresql://user:password@host:5432/dbname" -f migration/002-create_analyses_and_history.sql
psql "postgresql://user:password@host:5432/dbname" -f migration/003-create_sessions.sql
```

After creating the tables, set `SUPABASE_URL` and `SUPABASE_KEY` in your `.env` (or environment) to let `backend/storage_supabase.py` use the REST API.

Using Supabase from the app
--------------------------

1. Set environment variables (or add to `.env`):

```powershell
$env:SUPABASE_URL = 'https://<project-ref>.supabase.co'
$env:SUPABASE_KEY = '<your-service-role-or-anon-key>'
```

2. Start the Streamlit app. The app will automatically detect the presence of `SUPABASE_URL` and `SUPABASE_KEY` and use Supabase for persistence. Otherwise it falls back to a local JSON file in `data/processed_documents.json`.

3. Example: run the provided example script to insert a document and a history event:

```powershell
python scripts/example_insert_supabase.py
```


Outros
-----

- Exemplos de uso, testes unitários e scripts adicionais estão em `tests/`.
- Licença: MIT

