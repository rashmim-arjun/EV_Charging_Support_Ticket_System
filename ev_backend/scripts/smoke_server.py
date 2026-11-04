"""Start a disposable seeded backend for browser tests; never opens the user's DB."""
import os
import sys
import tempfile
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--ui-port', type=int, default=5173)
    args = parser.parse_args()
    import uvicorn
    import logging
    with tempfile.TemporaryDirectory(prefix='ev-browser-') as folder:
        os.environ['EV_DB_PATH'] = str(Path(folder) / 'smoke.db')
        os.environ['EV_REPORT_DIR'] = str(Path(folder) / 'reports')
        from app.evaluation.evaluation import _fresh_conn
        from app.core.settings import settings_raw
        settings_raw()['cors_origins'] = [f'http://localhost:{args.ui_port}']
        from app.data.synthetic_generator import SyntheticDataset
        conn = _fresh_conn(os.environ['EV_DB_PATH'])
        from app.core.logging_setup import setup_logging
        setup_logging()
        logging.getLogger('app').setLevel(logging.WARNING)
        SyntheticDataset(seed=42, n_per_template=2).write(conn)
        conn.close()
        uvicorn.run('app.main:app', host='127.0.0.1', port=args.port, log_level='warning')
