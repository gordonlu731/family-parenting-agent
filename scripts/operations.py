"""Local backup and read-only readiness checks. No deployment or cloud access.

Backups are plaintext private files; encrypted off-host storage is a separate
deployment requirement. No command restores over a running database.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import stat
import tempfile

FORMAT = 'family-backup-v1'
PATTERN = re.compile(r'family-backup-\d{8}T\d{6}Z-[0-9a-f]{12}\.sqlite3')
REQUIRED = {'schema_migrations','families','members','profiles','records','menus','audit','sessions','invites'}


class OperationError(Exception):
    pass


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


@contextmanager
def readonly(source):
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise OperationError('database_missing_or_symlink')
    try:
        db = sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)
        try:
            yield db
        finally:
            db.close()
    except sqlite3.Error:
        raise OperationError('database_unreadable_or_invalid') from None


def inspect_database(source):
    with readonly(source) as db:
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise OperationError('database_integrity_failed')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED <= tables:
            raise OperationError('unexpected_database_schema')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise OperationError('database_foreign_keys_failed')
        versions = [r[0] for r in db.execute('SELECT version FROM schema_migrations ORDER BY version')]
        return {'schema_versions': versions}


def private_directory(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = destination.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise OperationError('backup_directory_must_be_owned_and_private_0700')
    return destination


@contextmanager
def backup_lock(destination):
    fd = os.open(destination/'.backup.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_mode & 0o077:
            raise OperationError('backup_lock_permissions_invalid')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OperationError('backup_already_running') from None
        yield
    finally:
        os.close(fd)


def verify_backup(path):
    path = Path(path)
    manifest = path.with_suffix('.json')
    if not PATTERN.fullmatch(path.name) or path.is_symlink() or manifest.is_symlink() or not path.is_file() or not manifest.is_file():
        raise OperationError('backup_pair_missing_or_invalid')
    if manifest.stat().st_size > 16384:
        raise OperationError('backup_manifest_invalid')
    try:
        info = json.loads(manifest.read_text())
        created = datetime.fromisoformat(info['created_at'])
        if info['format'] != FORMAT or info['file'] != path.name or created.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise OperationError('backup_manifest_invalid') from None
    if path.stat().st_mode & 0o077 or manifest.stat().st_mode & 0o077:
        raise OperationError('backup_permissions_invalid')
    if digest(path) != info.get('sha256'):
        raise OperationError('backup_checksum_failed')
    inspect_database(path)
    return info


def backup(source, destination, keep=14):
    if not 2 <= keep <= 365:
        raise OperationError('keep_must_be_between_2_and_365')
    inspect_database(source)
    destination = private_directory(destination)
    with backup_lock(destination):
        stamp = datetime.now(timezone.utc)
        target = destination/('family-backup-'+stamp.strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(6)+'.sqlite3')
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        manifest = target.with_suffix('.json')
        temporary = None
        complete = False
        try:
            with readonly(source) as src, sqlite3.connect(target) as dst:
                src.backup(dst)
            result = inspect_database(target)
            result.update(format=FORMAT, file=target.name, created_at=stamp.isoformat(), sha256=digest(target))
            with tempfile.NamedTemporaryFile(mode='w', dir=destination, prefix='.manifest-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, manifest)
            with target.open('rb') as stream:
                os.fsync(stream.fileno())
            directory_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            complete = True
            # Retention only touches this tool's validated, complete backup pairs.
            valid = []
            for candidate in destination.glob('family-backup-*.sqlite3'):
                try:
                    info = verify_backup(candidate)
                    valid.append((info['created_at'], candidate))
                except OperationError:
                    continue
            valid.sort(key=lambda item: (item[1]==target, item[0]), reverse=True)
            removed = 0
            for _, old in valid[keep:]:
                if old == target:
                    continue
                old.with_suffix('.json').unlink()
                old.unlink()
                removed += 1
            return {'status': 'ok', 'backup': target.name, 'schema_versions': result['schema_versions'], 'pruned_pairs': removed,
                    'encrypted': False, 'off_host': False}
        except BaseException:
            if not complete:
                target.unlink(missing_ok=True)
                manifest.unlink(missing_ok=True)
            if temporary:
                temporary.unlink(missing_ok=True)
            raise


def restore_check(path):
    info = verify_backup(path)
    with tempfile.TemporaryDirectory(prefix='family-restore-check-') as tmp:
        copy = Path(tmp)/'isolated.sqlite3'
        with readonly(path) as src, sqlite3.connect(copy) as dst:
            src.backup(dst)
        result = inspect_database(copy)
    return {'status': 'ok', 'restored_to': 'temporary_isolated_database_only', 'schema_versions': result['schema_versions'], 'sha256': info['sha256']}


def check(source, backup_dir, max_age_hours=36, min_free_mb=256):
    result = {'status': 'ok', 'issues': []}
    try:
        result.update(inspect_database(source))
    except OperationError as exc:
        result['issues'].append(str(exc))
    parent = Path(source).parent
    if not parent.exists() or shutil.disk_usage(parent).free < min_free_mb*1024*1024:
        result['issues'].append('disk_space_low_or_path_missing')
    directory = Path(backup_dir)
    candidates = sorted(directory.glob('family-backup-*.sqlite3'), reverse=True) if directory.is_dir() and not directory.is_symlink() else []
    if not candidates:
        result['issues'].append('backup_missing')
    else:
        try:
            info = verify_backup(candidates[0])
            age = (datetime.now(timezone.utc)-datetime.fromisoformat(info['created_at'])).total_seconds()/3600
            result['backup_age_hours'] = round(age, 2)
            if age < 0 or age > max_age_hours:
                result['issues'].append('backup_stale_or_clock_mismatch')
        except OperationError as exc:
            result['issues'].append(str(exc))
    if result['issues']:
        result['status'] = 'degraded'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    b = commands.add_parser('backup')
    b.add_argument('--source', required=True, type=Path)
    b.add_argument('--destination', required=True, type=Path)
    b.add_argument('--keep', type=int, default=14)
    c = commands.add_parser('check')
    c.add_argument('--source', required=True, type=Path)
    c.add_argument('--backup-dir', required=True, type=Path)
    c.add_argument('--max-age-hours', type=int, default=36, choices=range(1, 721), metavar='1..720')
    c.add_argument('--min-free-mb', type=int, default=256, choices=range(1, 1048577), metavar='1..1048576')
    r = commands.add_parser('restore-check')
    r.add_argument('--backup', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'backup':
            result = backup(args.source, args.destination, args.keep)
        elif args.command == 'check':
            result = check(args.source, args.backup_dir, args.max_age_hours, args.min_free_mb)
        else:
            result = restore_check(args.backup)
    except OperationError as exc:
        result = {'status': 'failed', 'error_code': str(exc)}
    except OSError:
        result = {'status': 'failed', 'error_code': 'filesystem_operation_failed'}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['status']=='ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
