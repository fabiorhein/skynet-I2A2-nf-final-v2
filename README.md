++ BEGIN LICENSE
MIT
++ END LICENSE
# SkyNET-I2A2 — Processamento Fiscal (MVP)

Projeto MVP para extração, validação e classificação de documentos fiscais eletrônicos (NFe/NFCe/CTe).

## Visão geral

- Extrai dados de arquivos XML (parser pragmático usando `lxml`) ou via OCR (Tesseract + `pytesseract`) para PDFs/imagens.
- Valida regras fiscais básicas (CNPJ, somas de itens vs total, impostos) e classifica documentos.
- Armazenamento local via JSON ou integração com Supabase/Postgres (implementação compatível via `StorageInterface`).

## Estrutura do projeto

- `app.py` — ponto de entrada (Streamlit).
- `frontend/pages/` — páginas da UI (upload, histórico, home, etc.).
- `backend/agents/` — agentes: `extraction`, `classifier`, `analyst` e `coordinator`.
- `backend/tools/` — utilitários (parser XML, OCR, validação fiscal, etc.).
- `backend/storage.py` — implementação local JSON; há uma interface em `backend/storage_interface.py` para adaptar outros backends.
- `migration/` — scripts SQL de migração (ex.: `004-add_raw_text_column.sql`).

## Alterações recentes

- `raw_text`: coluna/migração adicionada (`migration/004-add_raw_text_column.sql`) para unificar texto bruto extraído de XML e OCR.
- Refatoração da integração LLM (preparado para chamadas diretas a API; LangChain é opcional).
- Melhorias no parser XML para retorno consistente (`raw_text`, `emitente`, `itens`, `impostos`, etc.).

## Configuração

### Arquivo de Configuração

O projeto usa um arquivo `config.py` como fonte central de configuração. As configurações são carregadas na seguinte ordem de prioridade:

1. Variáveis de ambiente
2. Configurações do Streamlit (se disponível)
3. Arquivo `.streamlit/secrets.toml`

### Configuração do Banco de Dados

1. Crie um arquivo `.streamlit/secrets.toml` com as seguintes configurações:

```toml
[connections.supabase]
URL = "https://seu-projeto.supabase.co"
KEY = "sua-chave-anon-ou-service-role"
DATABASE = "postgres"
USER = "postgres.[seu-project-ref]"
PASSWORD = "sua-senha-do-banco"
HOST = "aws-1-regiao.pooler.supabase.com"
PORT = "5432"

# Outras configurações
GOOGLE_API_KEY = "sua-api-key-google"
TESSERACT_PATH = "C:\\caminho\\para\\tesseract.exe"
LOG_LEVEL = "INFO"
```

2. O arquivo `config.py` irá carregar essas configurações e exportá-las para uso em toda a aplicação.

### Configuração do Supabase

1. No painel do Supabase, vá para "Database" > "Settings" > "Connection Info"
2. Use as credenciais fornecidas para configurar o `secrets.toml`
3. Certifique-se de adicionar seu IP à lista de permissões em "Database" > "Settings" > "Allowed IPs"

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
pip install streamlit pytesseract pillow PyPDF2 lxml pandas numpy
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

- `ModuleNotFoundError: No module named 'PyPDF2'` — instale no venv:

```pwsh
.\venv\Scripts\Activate.ps1
pip install PyPDF2
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
- Se Poppler não estiver disponível, a aplicação tentará usar PyPDF2 para extrair texto de PDFs com texto selecionável; para PDFs escaneados Poppler+Tesseract são necessários.

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

