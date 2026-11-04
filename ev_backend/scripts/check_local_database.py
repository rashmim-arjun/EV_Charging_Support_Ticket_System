"""Inspect, back up, and optionally migrate the configured local database."""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.db import connect, get_db_path, init_db


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair', action='store_true', help='Back up before applying migrations')
    args = parser.parse_args()
    path = Path(get_db_path())
    if not path.exists():
        parser.error(f'Database does not exist: {path}')
    conn = (connect(str(path)) if args.repair else
            sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True))
    conn.row_factory = sqlite3.Row
    try:
        print('Database:', path)
        print('Integrity:', conn.execute('PRAGMA integrity_check').fetchone()[0])
        print('Versions:', [r[0] for r in conn.execute('SELECT version FROM schema_version')])
        for table in ('communication_events', 'case_checks', 'case_evidence', 'resolutions'):
            print(table, [r['name'] for r in conn.execute(f'PRAGMA table_info({table})')])
        print('Resolution indexes:', [dict(r) for r in conn.execute('PRAGMA index_list(resolutions)')])
        if args.repair:
            backup = path.with_name(path.name + datetime.now().strftime('.backup-%Y%m%d-%H%M%S-%f'))
            target = sqlite3.connect(str(backup))
            try:
                conn.backup(target)
            finally:
                target.close()
            print('Backup:', backup)
            init_db(conn)
            print('Migrated to:', conn.execute('SELECT MAX(version) FROM schema_version').fetchone()[0])
        print('Foreign key violations:', len(conn.execute('PRAGMA foreign_key_check').fetchall()))
        print('Cases:', conn.execute('SELECT COUNT(*) FROM cases').fetchone()[0])
    finally:
        conn.close()
