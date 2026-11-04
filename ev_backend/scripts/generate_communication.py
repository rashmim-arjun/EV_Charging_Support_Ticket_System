"""Generate/persist a coordinated charging dataset and optionally export annotated JSON."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.communication.schema import GenerateRequest
from app.communication.simulator import generate_dataset
from app.communication.storage import persist_dataset
from app.core import db
from app.data.seed_rules import seed_rules_if_empty


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--per-template', type=int, default=2)
    p.add_argument('--split', choices=['train', 'validation', 'test', 'all'], default='all')
    p.add_argument('--scenario', action='append', help='Repeat to select scenario families; default is all')
    p.add_argument('--config', type=Path, help='JSON GenerateRequest configuration, including optional injections')
    p.add_argument('--export', type=Path, help='Annotated dataset JSON; includes ground truth for offline evaluation')
    args = p.parse_args()
    request = json.loads(args.config.read_text(encoding='utf-8')) if args.config else dict(seed=args.seed, per_template=args.per_template, split=args.split, scenarios=args.scenario)
    dataset = generate_dataset(GenerateRequest.model_validate(request))
    conn = db.ensure_schema(args.db)
    try:
        db.sync_config_tables(conn)
        seed_rules_if_empty(conn)
        print(json.dumps(persist_dataset(conn, dataset), indent=2))
        print('Synthetic semantic communication simulation; no protocol compliance claim.')
    finally:
        conn.close()
    if args.export:
        args.export.parent.mkdir(parents=True, exist_ok=True)
        args.export.write_text(json.dumps(dataset, indent=2) + '\n', encoding='utf-8')
        print('Annotated export:', args.export)


if __name__ == '__main__':
    main()
