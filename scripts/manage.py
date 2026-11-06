"""Operator-only commands. Run inside the application container.

backup TARGET creates a consistent SQLite snapshot. invite-owner emits a secret
single-use recovery path; deliver it privately to the owner, not in server logs.
"""
import argparse
import os
import secrets
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app import database, digest, migrate, now

parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest='command', required=True)
backup = sub.add_parser('backup')
backup.add_argument('target')
sub.add_parser('invite-owner')
args = parser.parse_args()
migrate()
if args.command == 'backup':
    target = Path(args.target)
    source = Path(os.getenv('APP_DB', str(Path(__file__).resolve().parent.parent / 'data/family.sqlite3')))
    if target.exists() or target.resolve() == source.resolve():
        parser.error('Backup target must be a new path different from source')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity failed')
        target.chmod(0o600)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    print('Consistent backup created.')
else:
    token = secrets.token_urlsafe(48)
    with database(True) as db:
        owners = db.execute("SELECT id,family_id FROM members WHERE role='owner' AND active=1").fetchall()
        if len(owners) != 1:
            parser.error('Expected exactly one active family owner')
        owner = owners[0]
        db.execute('INSERT INTO invites VALUES (?,?,?,?,NULL,?)', (digest(token), owner['family_id'], owner['id'], int(time.time()) + 86400, owner['id']))
    print('/#invite=' + token)
