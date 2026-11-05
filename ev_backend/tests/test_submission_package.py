import hashlib
import json
import zipfile
from scripts import package_submission


def test_submission_excludes_local_data_and_verifies_source_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(package_submission,'ROOT',tmp_path)
    for directory in ('ev_backend','ev_frontend','docs','examples','ev_backend/reports/live','ev_backend/reports/submission','ev_backend/logs','ev_backend/.venv'):
        (tmp_path/directory).mkdir(parents=True,exist_ok=True)
    files={
        'README.md':'Setup guide','.gitattributes':'* text=auto',
        'ev_backend/app.py':'print("source")','ev_backend/.env.example':'EV_DB_PATH=',
        'ev_backend/.env':'SECRET=do-not-publish','ev_backend/local.db.backup-123':'private data',
        'ev_backend/server.key':'private key','ev_backend/reports/live/result.json':'runtime data',
        'ev_backend/reports/submission/result.json':'intentional report','ev_backend/.venv/pyvenv.cfg':'local environment'}
    for path,value in files.items():
        (tmp_path/path).write_text(value,encoding='utf-8')
    archive=tmp_path/'submission/final.zip'
    package_submission.package(archive)
    with zipfile.ZipFile(archive) as package:
        names=set(package.namelist())
        assert {'README.md','.gitattributes','ev_backend/app.py','ev_backend/.env.example','ev_backend/reports/submission/result.json'}<=names
        assert not any(path in names for path in files if path.endswith(('.env','.key','backup-123','pyvenv.cfg')) or '/live/' in path)
        manifest=json.loads(package.read('SUBMISSION_MANIFEST.json'))
        assert all(hashlib.sha256(package.read(path)).hexdigest()==value for path,value in manifest['files'].items())
