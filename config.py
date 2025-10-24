"""
Project configuration loader.

Loads values from environment variables first. If not present, tries to read
Streamlit secrets via `streamlit.secrets` (when available). As a final fallback
it will try to parse `.streamlit/secrets.toml` in the project root.

Exports commonly used keys like SUPABASE_URL and SUPABASE_KEY so `app.py` can
import a single source of truth.
"""
from pathlib import Path
import os
from typing import Dict


def _read_secrets_file(path: Path) -> Dict[str, str]:
    """Parse a very small TOML-like KEY=VALUE secrets file used by Streamlit.
    This is intentionally permissive and only supports simple KEY=VALUE lines.
    """
    if not path.exists():
        return {}
    out = {}
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or line.startswith('['):
            continue
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        out[k] = v
    return out


# try to get Streamlit secrets if running under Streamlit
_streamlit_secrets = {}
try:
    import streamlit as _st
    _streamlit_secrets = getattr(_st, 'secrets', {}) or {}
except Exception:
    _streamlit_secrets = {}

# read file fallback
_project_root = Path(__file__).resolve().parent
_secrets_file = _project_root / '.streamlit' / 'secrets.toml'
_file_secrets = _read_secrets_file(_secrets_file)

# Compose final secrets: env vars override Streamlit secrets override file secrets
def _get(key: str, default=None):
    return os.getenv(key) or _streamlit_secrets.get(key) or _file_secrets.get(key) or default


# Common config entries
SUPABASE_URL = _get('SUPABASE_URL')
SUPABASE_KEY = _get('SUPABASE_KEY')

# Database connection settings
DATABASE = _get('DATABASE', 'postgres')
DB_USER = _get('USER')
DB_PASSWORD = _get('PASSWORD')
DB_HOST = _get('HOST')
DB_PORT = _get('PORT', '5432')

# Other settings
GOOGLE_API_KEY = _get('GOOGLE_API_KEY')
TESSERACT_PATH = _get('TESSERACT_PATH')
LOG_LEVEL = _get('LOG_LEVEL', 'INFO')

# Supabase connection details
SUPABASE_CONFIG = {
    'dbname': DATABASE,
    'user': DB_USER,
    'password': DB_PASSWORD,
    'host': DB_HOST,
    'port': DB_PORT,
    'sslmode': 'require'
}
# Tesseract path - try common install locations if not set in env/secrets
TESSERACT_PATH = _get('TESSERACT_PATH') or 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
if not Path(TESSERACT_PATH).exists():
    alt_paths = [
        'C:\\Program Files\\Tesseract-OCR\\tesseract.exe',
        'C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe',
        'D:\\Program Files\\Tesseract-OCR\\tesseract.exe'
    ]
    for p in alt_paths:
        if Path(p).exists():
            TESSERACT_PATH = p
            break

GOOGLE_API_KEY = _get('GOOGLE_API_KEY')
LOG_LEVEL = _get('LOG_LEVEL', 'INFO')


# Expose a dict if callers prefer
ALL = {
    'SUPABASE_URL': SUPABASE_URL,
    'SUPABASE_KEY': SUPABASE_KEY,
    'TESSERACT_PATH': TESSERACT_PATH,
    'GOOGLE_API_KEY': GOOGLE_API_KEY,
    'LOG_LEVEL': LOG_LEVEL,
}
