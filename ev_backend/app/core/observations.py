"""Read-only observation capability: no annotation tables/columns or source handle.

An allowlisted in-memory snapshot is deliberately separate from the working DB.
This is a Python application boundary, not a sandbox against hostile Python code.
"""
import sqlite3
from dataclasses import replace

TABLES = {
    'charging_sessions', 'session_events', 'payment_records', 'charger_status_log',
    'knowledge_rules', 'tool_priors', 'cases', 'resolutions',
    'communication_sessions', 'communication_events',
}
PRIVATE = {'scenario_id', 'ground_truth_category', 'run_id', 'config_json', 'template_id', 'split', 'annotations_json'}


def observation_complaint(complaint):
    return replace(complaint, ground_truth_category=None, scenario_id=None)


class ObservationReader:
    def __init__(self, source):
        # FastAPI worker-thread objects may be finalized on another thread.
        self.__db = sqlite3.connect(':memory:', check_same_thread=False)
        self.__db.row_factory = sqlite3.Row
        for table in sorted(TABLES):
            schema = source.execute(f'PRAGMA table_info({table})').fetchall()
            columns = [(r['name'], r['type'] or 'TEXT') for r in schema if r['name'] not in PRIVATE]
            if not columns:
                continue
            definition = ','.join(f'"{name}" {kind}' for name, kind in columns)
            self.__db.execute(f'CREATE TABLE "{table}" ({definition})')
            names = ','.join(f'"{name}"' for name, _ in columns)
            rows = source.execute(f'SELECT {names} FROM "{table}"').fetchall()
            self.__db.executemany(f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in columns)})', [tuple(r) for r in rows])
        self.__db.commit()
        self.__db.execute('PRAGMA query_only=ON')
        def authorize(action, first, second, database, trigger):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ and first in TABLES:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and second not in ('load_extension', 'writefile', 'readfile'):
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        self.__db.set_authorizer(authorize)

    def execute(self, sql, parameters=()):
        return self.__db.execute(sql, parameters)

    def close(self):
        self.__db.close()

    def __del__(self):
        self.__db.close()


def observations(conn):
    return conn if isinstance(conn, ObservationReader) else ObservationReader(conn)
