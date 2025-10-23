"""Simple migration runner: executes SQL files from migration/ in order.

Usage:
  python scripts/apply_migrations.py "postgresql://user:pass@host:5432/dbname"
"""
import sys
import psycopg2
from pathlib import Path
import socket
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def apply_migration(conn, path: Path):
    sql = path.read_text(encoding='utf-8')
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def main():
    if len(sys.argv) < 2:
        print('Usage: python scripts/apply_migrations.py <connection_string>')
        sys.exit(1)
    conn_str = sys.argv[1]

    # Ensure sslmode=require for Supabase
    try:
        parsed = urlparse(conn_str)
        qs = parse_qs(parsed.query)
        if 'sslmode' not in qs:
            qs['sslmode'] = ['require']
            new_query = urlencode(qs, doseq=True)
            parsed = parsed._replace(query=new_query)
            conn_str = urlunparse(parsed)
    except Exception:
        # leave conn_str unchanged if parse fails
        pass

    # Pre-check DNS resolution for host to catch DNS issues early
    try:
        host = urlparse(conn_str).hostname
        if host:
            socket.gethostbyname(host)
    except socket.gaierror:
        print(f"DNS lookup failed for host '{host}'.\nPlease check your network, DNS settings, or that the host name is correct.")
        sys.exit(1)

    conn = psycopg2.connect(conn_str)
    mig_dir = Path('migration')
    files = sorted(mig_dir.glob('*.sql'))
    for f in files:
        print('Applying', f.name)
        apply_migration(conn, f)
    conn.close()
    print('Migrations applied')


if __name__ == '__main__':
    main()
