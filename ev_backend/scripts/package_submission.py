"""Create a clean EV support submission ZIP without altering the working tree/DB."""
import argparse,hashlib,json,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
EXCLUDED={'node_modules','.venv','.venv-clean','__pycache__','.pytest_cache','.tmp','dist','test-results','playwright-report','coverage','logs','.git','.codex','.agents'}
ROOT_FILES={'README.md','.gitignore','.gitattributes','LICENSE','LICENSE.md'}

def package(output):
    output=output.resolve()
    if not output.is_relative_to(ROOT):raise ValueError('Submission output must stay inside this project')
    files=[]
    for entry in ('ev_backend','ev_frontend','docs','examples'):
        for p in (ROOT/entry).rglob('*'):
            relative=p.relative_to(ROOT)
            if not p.is_file() or not p.resolve().is_relative_to(ROOT):continue
            if any(part in EXCLUDED or part.startswith('.venv') for part in relative.parts):continue
            if relative.parts[:3]==('ev_backend','reports','live'):continue
            if p.name.startswith('.env') and p.name!='.env.example':continue
            if p.suffix in ('.db','.log','.pyc','.zip') or p.name.endswith(('.db-wal','.db-shm','.log.1')):continue
            if '.db.backup-' in p.name or p.suffix in ('.pem','.key'):continue
            if p.name in ('.coverage','Thumbs.db','.DS_Store'):continue
            files.append(p)
    files.extend(ROOT/name for name in ROOT_FILES if (ROOT/name).is_file())
    files=sorted(set(files))
    manifest={'scope':'EV support application; source, lockfiles, tests, configuration and intentional reports.',
        'database':'Working SQLite database excluded and untouched. Regenerate using documented seed/generation commands.',
        'excluded':'Environments, dependencies, builds, caches, temporary databases, logs, browser traces, unrelated applications.',
        'files':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in files:archive.write(p,p.relative_to(ROOT).as_posix())
        archive.writestr('SUBMISSION_MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():raise RuntimeError('ZIP integrity verification failed')
    print(json.dumps({'zip':str(output),'files':len(files)+1,'bytes':output.stat().st_size,
        'sha256':hashlib.sha256(output.read_bytes()).hexdigest()},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'submission/EV_Support_Submission.zip')
    package(parser.parse_args().output)
