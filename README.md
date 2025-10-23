
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

