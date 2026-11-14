"""Host-side setup and read-only preflight. Python standard library only.

Never prints environment values or provider credentials. Does not install
software, alter cloud resources, or start/stop services.
"""
import argparse
import getpass
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
PROJECT = 'family-parenting-agent'
BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'


def https_url(value, origin=False):
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError('地址中的端口不正确') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or any(c in value for c in "\n\r\t $'\"\\")
            or (origin and parsed.path not in ('', '/')) or (port is not None and not 1 <= port <= 65535)):
        raise ValueError('请输入完整HTTPS地址，不包含账号、密码、查询参数或占位符')
    if '{' in value or '}' in value or '<' in value or '>' in value:
        raise ValueError('请把地址占位符换成真实值')
    if not origin and parsed.path.rstrip('/').endswith('/chat/completions'):
        raise ValueError('Base URL不应包含末尾/chat/completions')
    return value.rstrip('/')


def require_new_config(path):
    if path.exists() or path.is_symlink():
        raise ValueError('配置文件已存在，已保留原文件。请在服务器私下编辑，不要粘贴到聊天。')


def write_config(path, mode, port, *, origin, base, model, key, thinking=None,
                 daily_limit='30', reconfirm_days='7'):
    require_new_config(path)
    if mode not in ('private', 'production'):
        raise ValueError('部署模式不正确')
    if not 1024 <= port <= 65535:
        raise ValueError('端口范围应为1024至65535')
    origin = f'http://127.0.0.1:{port}' if mode == 'private' else https_url(origin, True)
    base = https_url(base)
    if not re.fullmatch(r'[A-Za-z0-9_./:-]{1,160}', model):
        raise ValueError('模型名称格式不正确')
    if key and not re.fullmatch(r'[A-Za-z0-9_.-]{8,512}', key):
        raise ValueError('密钥格式不正确；不要输入引号、空格或整段配置')
    if thinking is None:
        thinking = 'false' if model == 'qwen-plus' and (urlsplit(base).hostname == 'dashscope.aliyuncs.com' or urlsplit(base).hostname.endswith('.maas.aliyuncs.com')) else ''
    if thinking not in ('', 'false', 'true'):
        raise ValueError('思考模式只接受true、false或留空')
    if not re.fullmatch(r'[0-9]{1,4}', str(daily_limit)) or not 1 <= int(daily_limit) <= 1000:
        raise ValueError('每日调用次数范围为1至1000')
    if not re.fullmatch(r'[0-9]{1,2}', str(reconfirm_days)) or not 1 <= int(reconfirm_days) <= 30:
        raise ValueError('食材重确认天数范围为1至30')
    data = {
        'BOOTSTRAP_TOKEN': secrets.token_urlsafe(48), 'APP_DB': '/data/family.sqlite3',
        'APP_PORT': str(port), 'PUBLIC_ORIGIN': origin,
        'COOKIE_SECURE': 'false' if mode == 'private' else 'true', 'DEMO_MODE': 'false',
        'MODEL_API_KEY': key, 'MODEL_BASE_URL': base, 'MODEL_ID': model,
        'MODEL_ENABLE_THINKING': thinking, 'MODEL_DAILY_REQUEST_LIMIT': str(int(daily_limit)),
        'PANTRY_RECONFIRM_DAYS': str(int(reconfirm_days)),
    }
    # O_EXCL prevents concurrent or accidental overwrite, including symlinks.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        file.write(''.join(f'{k}={v}\n' for k, v in data.items()))
    print('已创建仅当前用户可读写的.env；没有发起模型调用或启动服务。')
    if mode == 'private':
        print('当前为SSH隧道内的私人测试配置，不是家人的微信正式入口。')
    return data


def configure(path, mode, port, ask=input, secret=getpass.getpass):
    require_new_config(path)
    if not 1024 <= port <= 65535:
        raise ValueError('端口范围应为1024至65535')
    if secret is getpass.getpass and not sys.stdin.isatty():
        raise ValueError('请在交互式服务器终端运行configure，以便隐藏输入密钥')
    origin = f'http://127.0.0.1:{port}' if mode == 'private' else https_url(ask('正式HTTPS入口（不含页面路径）：').strip(), True)
    print('默认模型：百炼北京地域的 qwen-plus。可使用控制台提供的业务空间专属地址。')
    base = https_url(ask(f'模型 Base URL [回车使用北京兼容地址]：').strip() or BASE_URL)
    model = ask('模型名称 [qwen-plus]：').strip() or 'qwen-plus'
    key = secret('模型 API Key（隐藏输入；回车暂不接入）：').strip()
    return write_config(path, mode, port, origin=origin, base=base, model=model, key=key)


def configure_unattended(path, mode, port, environ=None):
    """Use an explicitly selected process environment; no prompts or secret output.

    This does not source files, discover another project's credentials, contact a
    provider, or connect to a server. Existing configuration is never replaced.
    """
    require_new_config(path)
    env = os.environ if environ is None else environ
    return write_config(
        path, mode, port, origin=env.get('PUBLIC_ORIGIN', '').strip(),
        base=env.get('MODEL_BASE_URL', '').strip() or BASE_URL,
        model=env.get('MODEL_ID', '').strip() or 'qwen-plus',
        key=env.get('MODEL_API_KEY', '').strip(),
        thinking=env.get('MODEL_ENABLE_THINKING'),
        daily_limit=env.get('MODEL_DAILY_REQUEST_LIMIT', '30'),
        reconfirm_days=env.get('PANTRY_RECONFIRM_DAYS', '7'),
    )


def read_env(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('尚无普通.env配置文件，先运行 configure')
    values = {}
    for line in path.read_text().splitlines():
        if line and not line.lstrip().startswith('#'):
            k, sep, v = line.partition('=')
            if not sep or not re.fullmatch(r'[A-Z_]+', k):
                raise ValueError('配置文件格式不正确')
            values[k] = v
    return values


def command_ok(command):
    try:
        # Never echo process output: daemon messages may contain local paths or URLs.
        return subprocess.run(command, cwd=ROOT, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=12, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def preflight(path):
    checks = []
    def add(name, passed, detail):
        checks.append(passed)
        print(f'{"通过" if passed else "待处理"} · {name}：{detail}')
    docker = bool(shutil.which('docker'))
    add('Docker命令', docker, '已发现' if docker else '未安装或不在PATH，暂不能使用容器部署')
    compose = docker and command_ok(['docker', 'compose', 'version'])
    add('Compose', compose, '可调用' if compose else '需要可用的Docker Compose插件')
    daemon = docker and command_ok(['docker', 'info'])
    add('Docker服务', daemon, '当前用户可连接' if daemon else '检查服务状态或当前用户访问权限')
    free = shutil.disk_usage(ROOT).free // (1024**2)
    add('可用磁盘', free >= 2048, f'{free} MiB，部署前至少预留2048 MiB；镜像实际占用另核实')
    try:
        env = read_env(path)
        port = int(env.get('APP_PORT', '18080'))
        if not 1024 <= port <= 65535:
            raise ValueError('APP_PORT不正确')
        if env.get('DEMO_MODE') != 'false' or len(env.get('BOOTSTRAP_TOKEN', '')) < 32:
            raise ValueError('应关闭演示模式并设置有效初始化凭证')
        origin = env.get('PUBLIC_ORIGIN', '')
        private = origin == f'http://127.0.0.1:{port}' and env.get('COOKIE_SECURE') == 'false'
        if not private:
            https_url(origin, True)
            if env.get('COOKIE_SECURE') != 'true':
                raise ValueError('正式入口需要安全Cookie')
        if env.get('MODEL_ENABLE_THINKING', '') not in ('', 'false', 'true'):
            raise ValueError('思考模式只接受true、false或留空')
        limit = int(env.get('MODEL_DAILY_REQUEST_LIMIT', '30'))
        if not 1 <= limit <= 1000:
            raise ValueError('每日调用次数范围为1至1000')
        add('配置权限', path.stat().st_mode & 0o077 == 0, '不会输出任何密钥；.env应仅所有者可读写')
        add('配置内容', True, '私人隧道测试' if private else 'HTTPS正式入口准备，证书及发布条件仍需验证')
        configured = all(env.get(k) for k in ('MODEL_API_KEY', 'MODEL_BASE_URL', 'MODEL_ID'))
        if configured:
            https_url(env['MODEL_BASE_URL'])
        print('提示 · 模型：'+('配置字段齐全，尚未验证真实调用' if configured else '尚未接入，手工记录可用'))
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                free_port = True
            except OSError:
                free_port = False
        add('测试端口', free_port, f'{port}可用' if free_port else f'{port}已占用；可能是本项目已运行，请检查后再操作')
    except (OSError, ValueError):
        add('配置文件', False, '缺失或配置无效，请运行configure或私下核对.env；无需发送文件内容')
    print('检查结束：没有安装软件、调用模型、修改防火墙或启动/停止其他服务。')
    return all(checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    setup = sub.add_parser('configure')
    setup.add_argument('--mode', choices=['private', 'production'], default='private')
    setup.add_argument('--port', type=int, default=18080)
    setup.add_argument('--non-interactive', action='store_true',
                       help='create a new private config from selected environment variables without prompting; never prints secrets')
    sub.add_parser('check')
    args = parser.parse_args()
    try:
        if args.command == 'configure':
            action = configure_unattended if args.non_interactive else configure
            action(ROOT / '.env', args.mode, args.port)
            return 0
        return 0 if preflight(ROOT / '.env') else 1
    except (ValueError, OSError, EOFError, KeyboardInterrupt) as exc:
        # Do not stringify arbitrary OSErrors or input containing secrets.
        print(str(exc) if isinstance(exc, ValueError) else '配置已停止，未启动服务。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
