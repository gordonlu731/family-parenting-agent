"""Start the local demo only; not a production launch command."""
import os
import secrets
import signal
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
env = os.environ.copy()
env.setdefault('DEMO_MODE', 'true')
env.setdefault('COOKIE_SECURE', 'false')
env.setdefault('APP_DB', str(root / 'data/demo.sqlite3'))
env.setdefault('BOOTSTRAP_TOKEN', secrets.token_urlsafe(48))
children = []


def shutdown(*_):
    for child in children:
        child.terminate()
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)
try:
    children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log'], cwd=root, env=env))
    children.append(subprocess.Popen(['npm', 'exec', '--', 'vite', '--host', '0.0.0.0', '--port', '3000'], cwd=root, env=env))
    while all(child.poll() is None for child in children):
        try:
            children[0].wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
finally:
    shutdown()
