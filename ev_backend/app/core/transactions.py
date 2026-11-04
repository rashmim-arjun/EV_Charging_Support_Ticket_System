"""Serialize read/modify/write workflows; nested calls use SQLite savepoints."""
from functools import wraps
from uuid import uuid4


def atomic(fn):
    @wraps(fn)
    def wrapped(conn, *args, **kwargs):
        outer = not conn.in_transaction
        if outer:
            conn.execute('BEGIN IMMEDIATE')
        name = 'sp_' + uuid4().hex
        conn.execute('SAVEPOINT ' + name)
        try:
            result = fn(conn, *args, **kwargs)
            conn.execute('RELEASE SAVEPOINT ' + name)
            if outer:
                conn.commit()
            return result
        except Exception:
            conn.execute('ROLLBACK TO SAVEPOINT ' + name)
            conn.execute('RELEASE SAVEPOINT ' + name)
            if outer:
                conn.rollback()
            raise
    return wrapped
