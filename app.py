import os
import sqlite3
import string
import random
import mimetypes
import time
import secrets
import hmac
import hashlib
import ipaddress
import json
import base64
import subprocess
import sys
import html
import socket
import tempfile
from urllib.parse import urlparse, quote as url_quote
import urllib.request
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash, jsonify, g, abort
from werkzeug.security import generate_password_hash, check_password_hash
import markdown

def secure_filename(filename):
    if not filename:
        return 'unnamed'
    # 使用 os.path.basename 防止通过任何路径分隔符进行的目录遍历
    filename = os.path.basename(filename)
    # 若还是有反斜杠等，再进行一层替换
    filename = filename.replace('/', '').replace('\\', '').replace('..', '')
    # 去除 Windows 非法文件名字符
    for ch in '<>:"|?*':
        filename = filename.replace(ch, '_')
    # 去除控制字符 (ASCII 0-31)
    filename = ''.join(c for c in filename if ord(c) > 31)
    filename = filename.strip('. ')
    if not filename:
        return 'unnamed'
    return filename

app = Flask(__name__)
# Generate a secret key for session management
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
NOTES_FOLDER = os.path.join(BASE_DIR, 'notes')
TRASH_FOLDER = os.path.join(BASE_DIR, 'trash')
DATABASE = os.path.join(BASE_DIR, 'users.db')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(NOTES_FOLDER, exist_ok=True)
os.makedirs(TRASH_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['NOTES_FOLDER'] = NOTES_FOLDER
app.config['TRASH_FOLDER'] = TRASH_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max limit

# ONLYOFFICE supported formats and their document types
ONLYOFFICE_FORMATS = {
    # Word
    '.docx': 'word', '.doc': 'word', '.odt': 'word', '.rtf': 'word', '.txt': 'word',
    # Cell
    '.xlsx': 'cell', '.xls': 'cell', '.ods': 'cell', '.csv': 'cell',
    # Slide
    '.pptx': 'slide', '.ppt': 'slide', '.odp': 'slide',
    # PDF (usually read-only in ONLYOFFICE Document Server)
    '.pdf': 'pdf'
}

# --- Database helpers ---

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        # Enable foreign key constraints
        db.execute('PRAGMA foreign_keys = ON;')
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        # Create users table
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        # Create share links table
        db.execute('''
            CREATE TABLE IF NOT EXISTS shares (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                target_filename TEXT NOT NULL
            )
        ''')
        # Create settings table
        db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS trash_items (
                trash_name TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                item_type TEXT NOT NULL,
                deleted_at TEXT NOT NULL
            )
        ''')
        if not db.execute('SELECT 1 FROM settings WHERE key = ?', ('onlyoffice_callback_secret',)).fetchone():
            db.execute(
                'INSERT INTO settings (key, value) VALUES (?, ?)',
                ('onlyoffice_callback_secret', secrets.token_urlsafe(32))
            )
        db.commit()
        
        # Create default admin if no users exist
        cursor = db.execute('SELECT COUNT(*) FROM users')
        if cursor.fetchone()[0] == 0:
            db.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                      ('admin', generate_password_hash('password123')))
            db.commit()

# Initialize database
init_db()

# --- Auth Helpers ---

def is_authenticated():
    return session.get('user_id') is not None

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated() or session.get('username') != 'admin':
            if request.is_json:
                return jsonify({'success': False, 'message': '仅限管理员访问'}), 403
            flash('此操作需要管理员权限')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def generate_short_id(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def format_size(size_bytes):
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def get_setting(key, default=None):
    db = get_db()
    row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    return row['value'] if row else default

def set_setting(key, value):
    db = get_db()
    db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    db.commit()

def normalize_managed_filename(filename):
    if not isinstance(filename, str) or not filename:
        return None
    if any(sep in filename for sep in ('/', '\\')) or '..' in filename:
        return None
    safe_name = secure_filename(filename)
    if safe_name != filename:
        return None
    return safe_name

def normalize_note_input(form):
    title = form.get('title', '')
    if not isinstance(title, str):
        return None, None, ('标题格式不正确', 400)

    title = title.strip()
    if not title:
        return None, None, ('标题不能为空', 400)

    content = form.get('content', '')
    if content is None:
        content = ''
    elif not isinstance(content, str):
        content = str(content)

    return title, content, None

def get_item_folder(item_type):
    if item_type == 'file':
        return app.config['UPLOAD_FOLDER']
    if item_type == 'note':
        return app.config['NOTES_FOLDER']
    return None

def get_item_label(item_type):
    return '文件' if item_type == 'file' else '笔记'

def resolve_item_path(item_type, filename, require_exists=True):
    safe_name = normalize_managed_filename(filename)
    folder = get_item_folder(item_type)
    if not safe_name or not folder:
        return None, None

    file_path = os.path.join(folder, safe_name)
    if require_exists and not os.path.isfile(file_path):
        return safe_name, None
    return safe_name, file_path

def build_unique_name(directory, filename, suffix):
    candidate = filename
    name, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{name}_{suffix}_{int(time.time())}_{counter}{ext}"
        counter += 1
    return candidate

def store_trash_metadata(trash_name, original_name, item_type):
    db = get_db()
    db.execute(
        'INSERT OR REPLACE INTO trash_items (trash_name, original_name, item_type, deleted_at) VALUES (?, ?, ?, ?)',
        (trash_name, original_name, item_type, datetime.now(timezone.utc).isoformat())
    )

def get_trash_metadata(trash_name):
    db = get_db()
    return db.execute(
        'SELECT trash_name, original_name, item_type, deleted_at FROM trash_items WHERE trash_name = ?',
        (trash_name,)
    ).fetchone()

def delete_trash_metadata(trash_name):
    db = get_db()
    db.execute('DELETE FROM trash_items WHERE trash_name = ?', (trash_name,))

def move_item_to_trash(item_type, filename):
    safe_name, source_path = resolve_item_path(item_type, filename)
    if not safe_name:
        return False, '无效的文件名', 400
    if not source_path:
        return False, f'{get_item_label(item_type)}不存在', 404

    trash_name = build_unique_name(app.config['TRASH_FOLDER'], safe_name, 'trash')
    trash_path = os.path.join(app.config['TRASH_FOLDER'], trash_name)
    db = get_db()

    try:
        os.rename(source_path, trash_path)
        store_trash_metadata(trash_name, safe_name, item_type)
        db.execute('DELETE FROM shares WHERE type = ? AND target_filename = ?', (item_type, safe_name))
        db.commit()
        return True, {'original_name': safe_name, 'trash_name': trash_name}, 200
    except Exception as e:
        db.rollback()
        return False, str(e), 500

def restore_item_from_trash(trash_name, requested_item_type=None):
    safe_trash_name = normalize_managed_filename(trash_name)
    if not safe_trash_name:
        return False, '无效的文件名', 400
    if requested_item_type is not None and requested_item_type not in ('file', 'note'):
        return False, '无效的恢复类型', 400

    trash_path = os.path.join(app.config['TRASH_FOLDER'], safe_trash_name)
    if not os.path.isfile(trash_path):
        return False, '项目不存在', 404

    metadata = get_trash_metadata(safe_trash_name)
    if metadata:
        original_name = normalize_managed_filename(metadata['original_name'])
        item_type = metadata['item_type']
        if not original_name or item_type not in ('file', 'note'):
            return False, '回收站元数据无效', 500
        if requested_item_type and requested_item_type != item_type:
            return False, '恢复类型与回收站记录不一致', 400
    else:
        original_name = safe_trash_name
        if requested_item_type:
            item_type = requested_item_type
        elif safe_trash_name.endswith('.md'):
            return False, '旧回收站中的 Markdown 条目缺少来源信息，请选择恢复为文件或笔记', 409
        else:
            item_type = 'file'

    target_folder = get_item_folder(item_type)
    restored_name = build_unique_name(target_folder, original_name, 'restored')
    destination_path = os.path.join(target_folder, restored_name)
    db = get_db()

    try:
        os.rename(trash_path, destination_path)
        delete_trash_metadata(safe_trash_name)
        db.commit()
        return True, {'restored_name': restored_name, 'item_type': item_type}, 200
    except Exception as e:
        db.rollback()
        return False, str(e), 500

def permanently_delete_trash_item(trash_name):
    safe_trash_name = normalize_managed_filename(trash_name)
    if not safe_trash_name:
        return False, '无效的文件名', 400

    trash_path = os.path.join(app.config['TRASH_FOLDER'], safe_trash_name)
    if not os.path.isfile(trash_path):
        return False, '项目不存在', 404

    db = get_db()
    try:
        os.remove(trash_path)
        delete_trash_metadata(safe_trash_name)
        db.commit()
        return True, '项目已永久删除', 200
    except Exception as e:
        db.rollback()
        return False, str(e), 500

def get_onlyoffice_callback_secret():
    secret = get_setting('onlyoffice_callback_secret')
    if secret:
        return secret

    secret = secrets.token_urlsafe(32)
    set_setting('onlyoffice_callback_secret', secret)
    return secret

def generate_onlyoffice_callback_token(filename):
    safe_name = normalize_managed_filename(filename)
    if not safe_name:
        return None
    return hmac.new(
        get_onlyoffice_callback_secret().encode('utf-8'),
        safe_name.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def is_valid_onlyoffice_callback_token(filename, token):
    expected_token = generate_onlyoffice_callback_token(filename)
    return bool(token and expected_token) and hmac.compare_digest(token, expected_token)

def generate_onlyoffice_download_token(filename):
    safe_name = normalize_managed_filename(filename)
    if not safe_name:
        return None
    token_payload = f"download:{safe_name}"
    return hmac.new(
        get_onlyoffice_callback_secret().encode('utf-8'),
        token_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def is_valid_onlyoffice_download_token(filename, token):
    expected_token = generate_onlyoffice_download_token(filename)
    return bool(token and expected_token) and hmac.compare_digest(token, expected_token)

def get_onlyoffice_jwt_secret():
    secret = get_setting('onlyoffice_jwt_secret', '')
    return secret.strip() if secret else ''

def _encode_onlyoffice_jwt_segment(payload):
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')

def _decode_onlyoffice_jwt_segment(segment):
    padded = segment + ('=' * (-len(segment) % 4))
    decoded = base64.urlsafe_b64decode(padded.encode('ascii'))
    return json.loads(decoded.decode('utf-8'))

def generate_onlyoffice_jwt(payload, secret=None):
    if not isinstance(payload, dict):
        return None

    signing_secret = secret if secret is not None else get_onlyoffice_jwt_secret()
    if not signing_secret:
        return None

    header_segment = _encode_onlyoffice_jwt_segment({'alg': 'HS256', 'typ': 'JWT'})
    payload_segment = _encode_onlyoffice_jwt_segment(payload)
    signing_input = f'{header_segment}.{payload_segment}'.encode('ascii')
    signature = hmac.new(signing_secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
    signature_segment = base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')
    return f'{header_segment}.{payload_segment}.{signature_segment}'

def decode_onlyoffice_jwt(token, secret=None):
    if not token or token.count('.') != 2:
        return None

    signing_secret = secret if secret is not None else get_onlyoffice_jwt_secret()
    if not signing_secret:
        return None

    try:
        header_segment, payload_segment, signature_segment = token.split('.')
        header = _decode_onlyoffice_jwt_segment(header_segment)
        if not isinstance(header, dict) or header.get('alg') != 'HS256':
            return None

        signing_input = f'{header_segment}.{payload_segment}'.encode('ascii')
        expected_signature = base64.urlsafe_b64encode(
            hmac.new(signing_secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
        ).rstrip(b'=').decode('ascii')
        if not hmac.compare_digest(expected_signature, signature_segment):
            return None

        payload = _decode_onlyoffice_jwt_segment(payload_segment)
    except (ValueError, TypeError, json.JSONDecodeError, base64.binascii.Error):
        return None

    return payload if isinstance(payload, dict) else None

def extract_onlyoffice_jwt_token(data=None):
    authorization = request.headers.get('Authorization', '').strip()
    if authorization:
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() in ('bearer', 'jwt') and token.strip():
            return token.strip()

    if isinstance(data, dict):
        token = data.get('token')
        if isinstance(token, str) and token.strip():
            return token.strip()

    return None

def find_git_repo_root(start_dir=None):
    current = os.path.abspath(start_dir or BASE_DIR)
    while True:
        if os.path.isdir(os.path.join(current, '.git')):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent

def run_update_command(command, cwd, timeout=120):
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
    except subprocess.TimeoutExpired:
        return {
            'ok': False,
            'command': ' '.join(command),
            'stdout': '',
            'stderr': 'Command timed out',
            'returncode': None
        }
    except OSError as exc:
        return {
            'ok': False,
            'command': ' '.join(command),
            'stdout': '',
            'stderr': str(exc),
            'returncode': None
        }

    return {
        'ok': completed.returncode == 0,
        'command': ' '.join(command),
        'stdout': completed.stdout.strip(),
        'stderr': completed.stderr.strip(),
        'returncode': completed.returncode
    }

def summarize_update_step(result):
    lines = [f"$ {result['command']}"]
    if result.get('stdout'):
        lines.append(result['stdout'])
    if result.get('stderr'):
        lines.append(result['stderr'])
    if not result.get('stdout') and not result.get('stderr'):
        lines.append('(no output)')
    return '\n'.join(lines)


def parse_dirty_paths_from_porcelain(porcelain_output):
    dirty_paths = []
    for raw_line in (porcelain_output or '').splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        path = line[3:]
        if ' -> ' in path:
            path = path.split(' -> ', 1)[1]
        dirty_paths.append(path.strip())
    return dirty_paths


def is_runtime_generated_git_path(path):
    if not path:
        return False

    normalized = path.replace('\\', '/').lstrip('./')
    ignored_exact = {'users.db'}
    ignored_prefixes = ('uploads/', 'notes/', 'trash/', '__pycache__/')

    if normalized in ignored_exact:
        return True
    if normalized.startswith(ignored_prefixes):
        return True
    if normalized.endswith('.pyc'):
        return True
    return False


def inspect_incremental_update_status(run_fetch=True):
    repo_root = find_git_repo_root(BASE_DIR)
    requirements_path = os.path.join(BASE_DIR, 'requirements.txt')
    status = {
        'supported': False,
        'repo_detected': bool(repo_root),
        'repo_root': repo_root,
        'requirements_path': requirements_path if os.path.isfile(requirements_path) else None,
        'branch': None,
        'current_commit': None,
        'upstream': None,
        'remote_commit': None,
        'ahead': 0,
        'behind': 0,
        'has_updates': False,
        'dirty': False,
        'dirty_files': [],
        'ignored_dirty_files': [],
        'message': ''
    }

    if not repo_root:
        status['message'] = '当前部署目录不是 Git 仓库，无法执行增量更新。'
        return status

    branch_result = run_update_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], repo_root)
    commit_result = run_update_command(['git', 'rev-parse', '--short', 'HEAD'], repo_root)
    dirty_result = run_update_command(['git', 'status', '--porcelain'], repo_root)
    upstream_result = run_update_command(
        ['git', 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'],
        repo_root
    )

    if branch_result['ok']:
        status['branch'] = branch_result['stdout']
    if commit_result['ok']:
        status['current_commit'] = commit_result['stdout']

    if dirty_result['ok']:
        dirty_paths = parse_dirty_paths_from_porcelain(dirty_result['stdout'])
        status['ignored_dirty_files'] = [path for path in dirty_paths if is_runtime_generated_git_path(path)]
        status['dirty_files'] = [path for path in dirty_paths if not is_runtime_generated_git_path(path)]
        status['dirty'] = bool(status['dirty_files'])
    else:
        status['dirty'] = False

    if not upstream_result['ok'] or not upstream_result['stdout']:
        status['message'] = '检测到 Git 仓库，但当前分支没有配置上游，无法执行增量更新。'
        return status

    status['upstream'] = upstream_result['stdout']
    remote_name = upstream_result['stdout'].split('/')[0]

    if run_fetch:
        fetch_result = run_update_command(['git', 'fetch', '--quiet', remote_name], repo_root, timeout=180)
        if not fetch_result['ok']:
            status['message'] = '获取远端更新失败，请检查网络或 Git 访问权限。'
            status['last_error'] = summarize_update_step(fetch_result)
            return status

    divergence_result = run_update_command(
        ['git', 'rev-list', '--left-right', '--count', 'HEAD...@{u}'],
        repo_root
    )
    remote_commit_result = run_update_command(['git', 'rev-parse', '--short', '@{u}'], repo_root)

    if divergence_result['ok'] and divergence_result['stdout']:
        try:
            ahead_str, behind_str = divergence_result['stdout'].split()
            status['ahead'] = int(ahead_str)
            status['behind'] = int(behind_str)
        except (ValueError, TypeError):
            pass

    if remote_commit_result['ok']:
        status['remote_commit'] = remote_commit_result['stdout']

    status['has_updates'] = status['behind'] > 0
    status['supported'] = True

    if status['dirty']:
        status['message'] = '检测到本地未提交改动，已禁用自动升级。请先备份或提交本地修改。'
    elif status['has_updates']:
        status['message'] = f"检测到 {status['behind']} 个远端更新，可以执行增量升级。"
        if status['ignored_dirty_files']:
            status['message'] += '（已自动忽略运行时文件变更）'
    else:
        status['message'] = '当前已经是最新版本。'

    return status

def apply_incremental_update():
    status = inspect_incremental_update_status(run_fetch=True)
    if not status['supported']:
        return False, status, 400

    if status['dirty']:
        return False, status, 409

    if not status['has_updates']:
        status['message'] = '当前已经是最新版本，无需升级。'
        return True, status, 200

    repo_root = status['repo_root']
    steps = []

    pull_result = run_update_command(['git', 'pull', '--ff-only'], repo_root, timeout=240)
    steps.append(summarize_update_step(pull_result))
    if not pull_result['ok']:
        status['message'] = '增量升级失败，Git 拉取未完成。'
        status['output'] = '\n\n'.join(steps)
        return False, status, 500

    if status.get('requirements_path'):
        pip_result = run_update_command(
            [sys.executable, '-m', 'pip', 'install', '-r', status['requirements_path']],
            BASE_DIR,
            timeout=600
        )
        steps.append(summarize_update_step(pip_result))
        if not pip_result['ok']:
            status['message'] = '代码已更新，但依赖安装失败，请检查输出日志。'
            status['output'] = '\n\n'.join(steps)
            return False, status, 500

    refreshed_status = inspect_incremental_update_status(run_fetch=False)
    refreshed_status['supported'] = status['supported']
    refreshed_status['message'] = '升级完成，请重启应用以加载最新代码。'
    refreshed_status['output'] = '\n\n'.join(steps)
    refreshed_status['restart_required'] = True
    return True, refreshed_status, 200

# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_authenticated():
        return redirect(url_for('index'))
        
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            error = '账号或密码错误。请重试。'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
def index():
    if not is_authenticated():
        return redirect(url_for('login'))
        
    # Handle file upload
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未找到文件部分'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'})
            
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # check if file already exists
            counter = 1
            name, ext = os.path.splitext(filename)
            while os.path.exists(file_path):
                filename = f"{name}_{counter}{ext}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                counter += 1
                
            file.save(file_path)
            return jsonify({'success': True, 'message': f'文件 {filename} 上传成功。'})

    # List all files for GET request
    files = []
    db = get_db()
    try:
        with os.scandir(app.config['UPLOAD_FOLDER']) as entries:
            for entry in entries:
                if entry.is_file():
                    stat = entry.stat()
                    filename = entry.name
                    
                    # check sharing status
                    share = db.execute('SELECT id FROM shares WHERE type="file" AND target_filename=?', (filename,)).fetchone()
                    share_id = share['id'] if share else None
                    
                    files.append({
                        'name': filename,
                        'size_raw': stat.st_size,
                        'size': format_size(stat.st_size),
                        'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                        'share_id': share_id
                    })
    except OSError as e:
        app.logger.error(f"Error listing uploads: {e}")

    files.sort(key=lambda x: x['size_raw'], reverse=True)
    onlyoffice_url = get_setting('onlyoffice_url')
    announcement = get_setting('announcement')
    return render_template('index.html', 
                          files=files, 
                          current_user=session['username'], 
                          onlyoffice_url=onlyoffice_url,
                          office_extensions=tuple(ONLYOFFICE_FORMATS.keys()),
                          announcement=announcement)

@app.route('/download/<filename>')
def download_file(filename):
    safe_name, filepath = resolve_item_path('file', filename)
    if not safe_name or not filepath:
        abort(404)

    if not is_authenticated():
        token = request.args.get('token')
        if token:
            if not is_valid_onlyoffice_download_token(safe_name, token):
                return jsonify({'success': False, 'message': '无效下载令牌'}), 403
        else:
            return redirect(url_for('login'))

    return send_from_directory(app.config['UPLOAD_FOLDER'], safe_name, as_attachment=True)

@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    success, result, status_code = move_item_to_trash('file', filename)
    if success:
        return jsonify({'success': True, 'message': f'文件 {result["original_name"]} 已移至回收站'}), status_code
    return jsonify({'success': False, 'message': result}), status_code

@app.route('/analyze/<filename>')
def analyze_file(filename):
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    safe_name, filepath = resolve_item_path('file', filename)
    if not safe_name:
        return jsonify({'success': False, 'message': '无效的文件名'}), 400
    if not filepath:
        return jsonify({'success': False, 'message': '文件不存在'}), 404
        
    stat = os.stat(filepath)
    size_bytes = stat.st_size
    mime_type, encoding = mimetypes.guess_type(filepath)
    if mime_type is None:
        mime_type = 'application/octet-stream'
        
    created = datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
    modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    
    hex_header = ""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(16)
            hex_header = ' '.join(f'{header_byte:02x}' for header_byte in header)
    except Exception:
        hex_header = '无法读取文件十六进制数据'
        
    analysis = {
        'filename': safe_name,
        'size_bytes': size_bytes,
        'mime_type': mime_type,
        'created_at': created,
        'modified_at': modified,
        'hex_header_preview': hex_header.upper()
    }
    return jsonify({'success': True, 'analysis': analysis})

# ----------------- GAME FEATURE -----------------

@app.route('/game')
def game():
    if not is_authenticated():
        return redirect(url_for('login'))
    announcement = get_setting('announcement')
    return render_template('game.html', current_user=session['username'], is_public=False, announcement=announcement)

@app.route('/public/game')
def public_game():
    data = request.args.get('data', '')
    announcement = get_setting('announcement')
    return render_template('game.html', is_public=True, shared_data=data, announcement=announcement)

@app.route('/game/share', methods=['POST'])
def create_game_share():
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    if not request.is_json:
        return jsonify({'success': False, 'message': '请求必须为 JSON'}), 400

    data = request.get_json(silent=True) or {}
    wheel_data = data.get('data', '').strip()
    if not wheel_data:
        return jsonify({'success': False, 'message': '分享内容不能为空'}), 400

    db = get_db()
    existing = db.execute('SELECT id FROM shares WHERE type="game" AND target_filename=?', (wheel_data,)).fetchone()
    if existing:
        return jsonify({'success': True, 'share_id': existing['id']})

    for _ in range(5):
        share_id = generate_short_id()
        try:
            db.execute('INSERT INTO shares (id, type, target_filename) VALUES (?, ?, ?)', (share_id, 'game', wheel_data))
            db.commit()
            return jsonify({'success': True, 'share_id': share_id})
        except sqlite3.IntegrityError:
            continue

    return jsonify({'success': False, 'message': '生成分享链接失败，请重试'}), 500

@app.route('/g/<share_id>')
def public_share_game(share_id):
    db = get_db()
    share = db.execute('SELECT target_filename FROM shares WHERE id = ? AND type="game"', (share_id,)).fetchone()
    if not share:
        return "此转盘分享链接已失效或不存在。", 404

    announcement = get_setting('announcement')
    return render_template('game.html', is_public=True, shared_data=share['target_filename'], announcement=announcement)

# ----------------- NOTES FEATURE -----------------

@app.route('/notes')
def notes():
    if not is_authenticated():
        return redirect(url_for('login'))
        
    notes_list = []
    db = get_db()
    try:
        with os.scandir(app.config['NOTES_FOLDER']) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.endswith('.md'):
                    stat = entry.stat()
                    filename = entry.name
                    title = filename[:-3]
                    
                    # check sharing status
                    share = db.execute('SELECT id FROM shares WHERE type="note" AND target_filename=?', (filename,)).fetchone()
                    share_id = share['id'] if share else None
                    
                    notes_list.append({
                        'title': title,
                        'filename': filename,
                        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'mtime_raw': stat.st_mtime,
                        'share_id': share_id
                    })
    except OSError as e:
        app.logger.error(f"Error listing notes: {e}")
            
    notes_list.sort(key=lambda x: x['mtime_raw'], reverse=True)
    announcement = get_setting('announcement')
    return render_template('notes.html', notes=notes_list, current_user=session['username'], announcement=announcement)

@app.route('/notes/create', methods=['GET', 'POST'])
def create_note():
    if not is_authenticated():
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        title, content, error = normalize_note_input(request.form)
        if error:
            message, status_code = error
            return jsonify({'success': False, 'message': message}), status_code
            
        filename = secure_filename(title) + '.md'
        filepath = os.path.join(app.config['NOTES_FOLDER'], filename)
        
        if os.path.exists(filepath):
            return jsonify({'success': False, 'message': '已存在同名笔记'})
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
            
        # Return success with JSON for fetch API
        return jsonify({'success': True, 'redirect': url_for('view_note', filename=filename)})
        
    announcement = get_setting('announcement')
    return render_template('note_edit.html', current_user=session['username'], announcement=announcement)

@app.route('/notes/edit/<filename>', methods=['GET', 'POST'])
def edit_note(filename):
    if not is_authenticated():
        return redirect(url_for('login'))

    safe_name, filepath = resolve_item_path('note', filename)
    if not filepath:
        return redirect(url_for('notes'))
        
    if request.method == 'POST':
        new_title, content, error = normalize_note_input(request.form)
        if error:
             message, status_code = error
             return jsonify({'success': False, 'message': message}), status_code
            
        new_filename = secure_filename(new_title) + '.md'
        new_filepath = os.path.join(app.config['NOTES_FOLDER'], new_filename)
        
        if new_filename != safe_name and os.path.exists(new_filepath):
             return jsonify({'success': False, 'message': '已存在同名笔记'})
             
        if new_filename != safe_name:
            # 先写入新的文件
            with open(new_filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            # 再尝试删除旧文件
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except OSError as e:
                # 旧文件删除失败时，回滚：删除新文件，保留旧文件
                app.logger.error(f"Failed to remove old note {safe_name}: {e}")
                try:
                    os.remove(new_filepath)
                except OSError:
                    pass
                return jsonify({'success': False, 'message': '重命名失败，旧文件无法删除'}), 500
            # update share links
            db = get_db()
            db.execute('UPDATE shares SET target_filename=? WHERE type="note" AND target_filename=?', (new_filename, safe_name))
            db.commit()
        else:
            # 文件名不变，直接覆盖写入
            with open(new_filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
        return jsonify({'success': True, 'redirect': url_for('view_note', filename=new_filename)})
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    announcement = get_setting('announcement')
    return render_template('note_edit.html', title=safe_name[:-3], content=content, is_edit=True, original_filename=safe_name, current_user=session['username'], announcement=announcement)

@app.route('/notes/view/<filename>')
def view_note(filename):
    if not is_authenticated():
        return redirect(url_for('login'))

    safe_name, filepath = resolve_item_path('note', filename)
    if not filepath:
        return redirect(url_for('notes'))
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Basic XSS protection: escape HTML tags before markdown rendering
    escaped_content = html.escape(content)
    html_content = markdown.markdown(escaped_content, extensions=['fenced_code', 'tables'])
    announcement = get_setting('announcement')
    return render_template('note_view.html', title=safe_name[:-3], content=html_content, filename=safe_name, current_user=session['username'], announcement=announcement)

@app.route('/notes/delete/<filename>', methods=['POST'])
def delete_note(filename):
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    success, result, status_code = move_item_to_trash('note', filename)
    if success:
        return jsonify({'success': True, 'message': '笔记已移至回收站'}), status_code
    return jsonify({'success': False, 'message': result}), status_code

# ----------------- ADMIN SYSTEM -----------------

@app.route('/admin')
@admin_required
def admin():
    db = get_db()
    users = db.execute('SELECT id, username FROM users').fetchall()
    onlyoffice_url = get_setting('onlyoffice_url', '')
    onlyoffice_jwt_secret = get_onlyoffice_jwt_secret()
    onlyoffice_callback_base = get_setting('onlyoffice_callback_base', '')
    announcement = get_setting('announcement')
    return render_template('admin.html', 
                          users=users, 
                          current_user=session['username'],
                          onlyoffice_url=get_setting('onlyoffice_url'),
                          onlyoffice_jwt_secret=get_setting('onlyoffice_jwt_secret'),
                          onlyoffice_callback_base=get_setting('onlyoffice_callback_base'),
                          announcement=announcement)

@app.route('/admin/settings', methods=['POST'])
@admin_required
def update_settings():
    onlyoffice_url = request.form.get('onlyoffice_url', '').strip()
    onlyoffice_jwt_secret = request.form.get('onlyoffice_jwt_secret', '').strip()
    onlyoffice_callback_base = request.form.get('onlyoffice_callback_base', '').strip()
    if onlyoffice_url and not onlyoffice_url.startswith(('http://', 'https://')):
        return jsonify({'success': False, 'message': '请输入有效的 URL (以 http:// 或 https:// 开头)'})
    if onlyoffice_callback_base and not onlyoffice_callback_base.startswith(('http://', 'https://')):
        return jsonify({'success': False, 'message': '回调地址必须以 http:// 或 https:// 开头'})
    
    set_setting('onlyoffice_url', onlyoffice_url)
    set_setting('onlyoffice_jwt_secret', onlyoffice_jwt_secret)
    set_setting('onlyoffice_callback_base', onlyoffice_callback_base)
    return jsonify({'success': True, 'message': '设置已更新'})

@app.route('/admin/onlyoffice/test')
@admin_required
def test_onlyoffice_connection():
    onlyoffice_url = get_setting('onlyoffice_url', '')
    if not onlyoffice_url:
        return jsonify({'success': False, 'message': 'ONLYOFFICE 地址未配置'})
    
    test_url = onlyoffice_url.rstrip('/') + '/healthcheck'
    try:
        req = urllib.request.Request(test_url, method='GET')
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode('utf-8', errors='replace').strip()
            if resp.status == 200 and body.lower() == 'true':
                return jsonify({'success': True, 'message': f'连接成功 ✓ ({test_url})'})
            return jsonify({'success': False, 'message': f'服务器返回异常: HTTP {resp.status}, body={body[:200]}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'连接失败: {str(e)}'})

@app.route('/admin/update/status')
@admin_required
def admin_update_status():
    status = inspect_incremental_update_status(run_fetch=True)
    return jsonify({'success': True, **status})

@app.route('/admin/update/apply', methods=['POST'])
@admin_required
def admin_apply_update():
    success, result, status_code = apply_incremental_update()
    payload = {'success': success, **result}
    return jsonify(payload), status_code

@app.route('/admin/users/add', methods=['POST'])
@admin_required
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})
        
    db = get_db()
    # Check if exists
    if db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
        return jsonify({'success': False, 'message': '用户名已存在'})
        
    db.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
              (username, generate_password_hash(password)))
    db.commit()
    return jsonify({'success': True, 'message': f'用户 {username} 添加成功'})

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        return jsonify({'success': False, 'message': '不能删除当前登录用户'})
        
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    return jsonify({'success': True, 'message': '用户删除成功'})
    
@app.route('/admin/password', methods=['POST'])
def change_password():
    if not is_authenticated():
         return jsonify({'success': False, 'message': '未授权访问'}), 401
         
    user_id = request.form.get('user_id')
    new_password = request.form.get('new_password')
    
    # Security: Non-admin can only change their own password
    if session.get('username') != 'admin' and str(user_id) != str(session.get('user_id')):
         return jsonify({'success': False, 'message': '未授权的操作'}), 403
         
    if not new_password:
        return jsonify({'success': False, 'message': '新密码不能为空'})
        
    db = get_db()
    db.execute('UPDATE users SET password = ? WHERE id = ?', (generate_password_hash(new_password), user_id))
    db.commit()
    return jsonify({'success': True, 'message': '密码修改成功'})

# ----------------- SHARING SYSTEM -----------------
@app.route('/share/create', methods=['POST'])
def create_share():
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    if not request.is_json:
        return jsonify({'success': False, 'message': '请求必须为 JSON'}), 400

    data = request.get_json(silent=True) or {}
    item_type = data.get('type')
    filename = data.get('filename')

    if item_type not in ('file', 'note'):
        return jsonify({'success': False, 'message': '不支持的分享类型'}), 400

    safe_name, item_path = resolve_item_path(item_type, filename)
    if not safe_name:
        return jsonify({'success': False, 'message': '无效的文件名'}), 400
    if not item_path:
        return jsonify({'success': False, 'message': f'{get_item_label(item_type)}不存在'}), 404

    db = get_db()
    # check if already shared
    existing = db.execute('SELECT id FROM shares WHERE type=? AND target_filename=?', (item_type, safe_name)).fetchone()
    if existing:
        return jsonify({'success': True, 'share_id': existing['id']})

    for _ in range(5):
        share_id = generate_short_id()
        try:
            db.execute('INSERT INTO shares (id, type, target_filename) VALUES (?, ?, ?)', (share_id, item_type, safe_name))
            db.commit()
            return jsonify({'success': True, 'share_id': share_id})
        except sqlite3.IntegrityError:
            continue

    return jsonify({'success': False, 'message': '生成分享链接失败，请重试'}), 500

@app.route('/share/revoke', methods=['POST'])
def revoke_share():
    if not is_authenticated():
         return jsonify({'success': False, 'message': '未授权访问'}), 401

    if not request.is_json:
        return jsonify({'success': False, 'message': '请求必须为 JSON'}), 400

    data = request.get_json(silent=True) or {}
    share_id = data.get('share_id')
    if share_id:
        db = get_db()
        db.execute('DELETE FROM shares WHERE id = ?', (share_id,))
        db.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '缺少 share_id'}), 400

@app.route('/s/f/<share_id>')
def public_share_file(share_id):
    db = get_db()
    share = db.execute('SELECT target_filename FROM shares WHERE id = ? AND type="file"', (share_id,)).fetchone()
    if not share:
        return "此分享链接已失效或不存在。", 404

    filename, filepath = resolve_item_path('file', share['target_filename'])
    if not filepath:
         return "文件已被删除。", 404

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    
@app.route('/s/n/<share_id>')
def public_share_note(share_id):
    db = get_db()
    share = db.execute('SELECT target_filename FROM shares WHERE id = ? AND type="note"', (share_id,)).fetchone()
    if not share:
         return "此分享链接已失效或不存在。", 404

    filename, filepath = resolve_item_path('note', share['target_filename'])
    if not filepath:
         return "笔记已被删除。", 404

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Basic XSS protection: escape HTML tags before markdown rendering
    escaped_content = html.escape(content)
    html_content = markdown.markdown(escaped_content, extensions=['fenced_code', 'tables'])
    # Serve a clean public viewing template
    announcement = get_setting('announcement')
    return render_template('share_view.html', title=filename[:-3], content=html_content, announcement=announcement)

# ----------------- TRASH SYSTEM -----------------
def auto_cleanup_trash():
    """Automatically delete files in trash that are older than 3 days."""
    try:
        if not os.path.exists(TRASH_FOLDER):
            return
        
        days_limit = 3
        now = time.time()
        cleanup_threshold = days_limit * 86400
        
        removed_names = []
        for filename in os.listdir(TRASH_FOLDER):
            file_path = os.path.join(TRASH_FOLDER, filename)
            if os.path.isfile(file_path):
                file_age = now - os.path.getmtime(file_path)
                if file_age > cleanup_threshold:
                    os.remove(file_path)
                    removed_names.append(filename)
        if removed_names:
            db = get_db()
            db.executemany('DELETE FROM trash_items WHERE trash_name = ?', [(name,) for name in removed_names])
            db.commit()
    except Exception as e:
        print(f"Trash cleanup error: {str(e)}")

@app.route('/api/batch-delete', methods=['POST'])
def batch_delete():
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权'}), 401

    if not request.is_json:
        return jsonify({'success': False, 'message': '请求必须为 JSON'}), 400

    try:
        data = request.get_json(silent=True) or {}
        if not data or 'filenames' not in data:
            return jsonify({'success': False, 'message': '无效的请求'}), 400

        filenames = data['filenames']
        if not isinstance(filenames, list):
            return jsonify({'success': False, 'message': 'filenames 必须为数组'}), 400

        success_count = 0
        failures = []

        for filename in filenames:
            success, result, _ = move_item_to_trash('file', filename)
            if success:
                success_count += 1
            else:
                failures.append({'filename': filename, 'message': result})

        if success_count == 0:
            return jsonify({
                'success': False,
                'message': failures[0]['message'] if failures else '没有可处理的文件',
                'failures': failures
            }), 400

        message = f'成功将 {success_count} 个文件移至回收站'
        if failures:
            message += f'，另有 {len(failures)} 个文件未处理'
        return jsonify({'success': True, 'message': message, 'failures': failures})
    except Exception as e:
        return jsonify({'success': False, 'message': f'操作失败: {str(e)}'}), 500

@app.route('/trash')
def view_trash():
    if not is_authenticated():
        return redirect(url_for('login'))
    
    # Trigger auto cleanup
    auto_cleanup_trash()
    
    trash_items = []
    db = get_db()
    metadata_rows = db.execute('SELECT trash_name, original_name, item_type FROM trash_items').fetchall()
    metadata_by_name = {row['trash_name']: row for row in metadata_rows}
    try:
        with os.scandir(app.config['TRASH_FOLDER']) as entries:
            for entry in entries:
                if entry.is_file():
                    stat = entry.stat()
                    metadata = metadata_by_name.get(entry.name)
                    display_name = metadata['original_name'] if metadata else entry.name
                    item_type = metadata['item_type'] if metadata else ('unknown' if entry.name.endswith('.md') else 'file')
                    trash_items.append({
                        'name': display_name,
                        'trash_name': entry.name,
                        'item_type': item_type,
                        'size': format_size(stat.st_size),
                        'deleted_at': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'mtime_raw': stat.st_mtime
                    })
    except OSError as e:
        app.logger.error(f"Error listing trash: {e}")
        
    trash_items.sort(key=lambda x: x['mtime_raw'], reverse=True)
    announcement = get_setting('announcement')
    return render_template('trash.html', items=trash_items, current_user=session['username'], announcement=announcement)

@app.route('/trash/restore/<filename>', methods=['POST'])
def restore_item(filename):
    if not is_authenticated():
        return jsonify({'success': False}), 401

    requested_item_type = None
    if request.is_json:
        data = request.get_json(silent=True) or {}
        requested_item_type = data.get('item_type')
    elif (request.content_length or 0) > 0:
        return jsonify({'success': False, 'message': '请求必须为 JSON'}), 400

    success, result, status_code = restore_item_from_trash(filename, requested_item_type=requested_item_type)
    if success:
        return jsonify({'success': True, 'message': '项目已还原', 'filename': result['restored_name']}), status_code
    return jsonify({'success': False, 'message': result}), status_code

@app.route('/trash/delete/<filename>', methods=['POST'])
def permanent_delete_item(filename):
    if not is_authenticated():
        return jsonify({'success': False}), 401

    success, result, status_code = permanently_delete_trash_item(filename)
    if success:
        return jsonify({'success': True, 'message': result}), status_code
    return jsonify({'success': False, 'message': result}), status_code

@app.route('/trash/clear', methods=['POST'])
def clear_trash():
    if not is_authenticated():
        return jsonify({'success': False}), 401
        
    try:
        for filename in os.listdir(app.config['TRASH_FOLDER']):
            file_path = os.path.join(app.config['TRASH_FOLDER'], filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
        db = get_db()
        db.execute('DELETE FROM trash_items')
        db.commit()
        return jsonify({'success': True, 'message': '回收站已清空'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ONLYOFFICE Editor Route
@app.route('/editor/<filename>')
def onlyoffice_editor(filename):
    if not is_authenticated():
        return redirect(url_for('login'))
    
    onlyoffice_url = get_setting('onlyoffice_url')
    if not onlyoffice_url:
        flash('ONLYOFFICE 未配置')
        return redirect(url_for('index'))
    
    # Ensure URL ends with /
    if not onlyoffice_url.endswith('/'):
        onlyoffice_url += '/'
        
    safe_name, filepath = resolve_item_path('file', filename)
    if not filepath:
        flash('文件不存在')
        return redirect(url_for('index'))

    file_ext = os.path.splitext(safe_name)[1].lower()
    
    # Determine document type for ONLYOFFICE
    document_type = ONLYOFFICE_FORMATS.get(file_ext)
    if not document_type:
        flash(f'不支持编辑 {file_ext} 格式')
        return redirect(url_for('index'))
        
    # Generate a stable key with restricted characters and bounded length.
    # Include filename and mtime so key rotates when the file is updated.
    stat = os.stat(filepath)
    key_seed = f"{safe_name}:{int(stat.st_mtime)}"
    doc_key = f"doc_{hashlib.sha256(key_seed.encode('utf-8')).hexdigest()[:32]}"
    
    # Build document_url and callback_url.
    # If a callback_base is configured, use it so ONLYOFFICE can reach our app
    # through NAT/reverse-proxy. Otherwise, fall back to url_for(_external).
    callback_base = get_setting('onlyoffice_callback_base', '').rstrip('/')
    if callback_base:
        dl_token = generate_onlyoffice_download_token(safe_name)
        cb_token = generate_onlyoffice_callback_token(safe_name)
        encoded_name = url_quote(safe_name, safe='')
        document_url = f"{callback_base}/download/{encoded_name}?token={dl_token}"
        callback_url = f"{callback_base}/callback/{encoded_name}?token={cb_token}"
    else:
        document_url = url_for(
            'download_file',
            filename=safe_name,
            token=generate_onlyoffice_download_token(safe_name),
            _external=True
        )
        callback_url = url_for(
            'onlyoffice_callback',
            filename=safe_name,
            token=generate_onlyoffice_callback_token(safe_name),
            _external=True
        )
    
    config = {
        'document': {
            'fileType': file_ext.replace('.', ''),
            'key': doc_key,
            'title': safe_name,
            'url': document_url,
        },
        'documentType': document_type,
        'editorConfig': {
            'callbackUrl': callback_url,
            'user': {
                'id': str(session.get('user_id')),
                'name': session.get('username')
            },
            'lang': 'zh-CN',
            'customization': {
                'forcesave': True
            }
        }
    }

    onlyoffice_jwt_secret = get_onlyoffice_jwt_secret()
    if onlyoffice_jwt_secret:
        config['token'] = generate_onlyoffice_jwt(config, onlyoffice_jwt_secret)
    
    return render_template('editor_onlyoffice.html', 
                           config=config, 
                           onlyoffice_url=onlyoffice_url,
                           filename=safe_name)

@app.route('/callback/<filename>', methods=['POST'])
def onlyoffice_callback(filename):
    safe_name = normalize_managed_filename(filename)
    if not safe_name:
        return jsonify({"error": 1, "message": "Invalid filename"}), 400

    if not is_valid_onlyoffice_callback_token(safe_name, request.args.get('token')):
        return jsonify({"error": 1, "message": "Forbidden"}), 403

    if not request.is_json:
        return jsonify({"error": 1, "message": "Expected JSON body"}), 400

    # ONLYOFFICE sends status in the body
    data = request.get_json(silent=True) or {}
    onlyoffice_jwt_secret = get_onlyoffice_jwt_secret()
    if onlyoffice_jwt_secret:
        onlyoffice_jwt = extract_onlyoffice_jwt_token(data)
        signed_payload = decode_onlyoffice_jwt(onlyoffice_jwt, onlyoffice_jwt_secret)
        if not signed_payload:
            return jsonify({"error": 1, "message": "Invalid ONLYOFFICE token"}), 403

        signed_status = signed_payload.get('status')
        if signed_status is not None and signed_status != data.get('status'):
            return jsonify({"error": 1, "message": "ONLYOFFICE token mismatch"}), 403

        signed_url = signed_payload.get('url')
        if signed_url is not None and data.get('url') and signed_url != data.get('url'):
            return jsonify({"error": 1, "message": "ONLYOFFICE token mismatch"}), 403

    if 'status' not in data:
        return jsonify({"error": 1, "message": "Missing status"}), 400

    status = data.get('status')
    
    # Status 2: Document is ready for saving
    # Status 6: Document is being edited but forcesave is triggered
    if status in [2, 6]:
        _, filepath = resolve_item_path('file', safe_name)
        if not filepath:
            return jsonify({"error": 1, "message": "Target file not found"}), 404

        download_url = data.get('url')
        if not download_url:
            return jsonify({"error": 1, "message": "Missing download URL"}), 400

        # SSRF Protection: Validate URL, but whitelist the configured ONLYOFFICE server
        parsed_url = urlparse(download_url)
        if parsed_url.scheme not in ('http', 'https'):
            return jsonify({"error": 1, "message": "Invalid download URL"}), 400

        # Build set of trusted hostnames from ONLYOFFICE server configuration
        trusted_hostnames = set()
        configured_oo_url = get_setting('onlyoffice_url', '')
        if configured_oo_url:
            parsed_oo = urlparse(configured_oo_url)
            if parsed_oo.hostname:
                trusted_hostnames.add(parsed_oo.hostname.lower())

        try:
            hostname = parsed_url.hostname
            if not hostname:
                 return jsonify({"error": 1, "message": "Invalid URL hostname"})
            # Skip SSRF check if the download URL points to the configured ONLYOFFICE server
            is_trusted = hostname.lower() in trusted_hostnames
            if not is_trusted:
                resolved_ips = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
                for ip in resolved_ips:
                    parsed_ip = ipaddress.ip_address(ip)
                    if (
                        parsed_ip.is_private or
                        parsed_ip.is_loopback or
                        parsed_ip.is_link_local or
                        parsed_ip.is_multicast or
                        parsed_ip.is_reserved or
                        parsed_ip.is_unspecified
                    ):
                        app.logger.warning(f"Blocked potential SSRF callback to {download_url} (IP: {ip})")
                        return jsonify({"error": 1, "message": "Invalid download URL"})
        except Exception as e:
            app.logger.error(f"SSRF validation error: {e}")
            return jsonify({"error": 1}), 502

        try:
            with urllib.request.urlopen(download_url, timeout=30) as response:
                if response.status == 200:
                    payload = response.read()
                    headers = getattr(response, 'headers', {})
                    content_type = (headers.get('Content-Type') if hasattr(headers, 'get') else '') or ''
                    content_type = str(content_type).lower()
                    file_ext = os.path.splitext(safe_name)[1].lower()
                    if (
                        'text/html' in content_type or
                        payload.lstrip().startswith(b'<!DOCTYPE html') or
                        payload.lstrip().startswith(b'<html')
                    ):
                        app.logger.error(
                            "ONLYOFFICE callback returned HTML instead of file for %s, URL=%s, content_type=%s",
                            safe_name,
                            download_url,
                            content_type,
                        )
                        return jsonify({"error": 1, "message": "Invalid callback payload"}), 502

                    if file_ext in {'.docx', '.xlsx', '.pptx'} and not payload.startswith(b'PK'):
                        app.logger.error(
                            "ONLYOFFICE callback returned unexpected binary signature for %s, URL=%s, content_type=%s",
                            safe_name,
                            download_url,
                            content_type,
                        )
                        return jsonify({"error": 1, "message": "Invalid callback payload"}), 502

                    # Atomic write: write to temp file, then replace
                    dir_name = os.path.dirname(filepath)
                    fd, tmp_path = tempfile.mkstemp(dir=dir_name)
                    fd_closed = False
                    try:
                        os.write(fd, payload)
                        os.close(fd)
                        fd_closed = True
                        os.replace(tmp_path, filepath)
                    except Exception:
                        if not fd_closed:
                            try:
                                os.close(fd)
                            except OSError:
                                pass
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                        raise
                    return jsonify({"error": 0})
                return jsonify({"error": 1, "message": "Download failed"}), 502
        except Exception as e:
            app.logger.error(f"ONLYOFFICE callback save error: {str(e)}")
            return jsonify({"error": 1}), 502
    
    return jsonify({"error": 0})

# API Endpoint for Markdown Preview
@app.route('/api/preview', methods=['POST'])
def render_preview():
    if not is_authenticated():
        return jsonify({'success': False}), 401

    if not request.is_json:
        return jsonify({'success': False, 'message': '请求必须为 JSON'}), 400

    data = request.get_json(silent=True) or {}
    content = data.get('content', '')
    if not isinstance(content, str):
        content = '' if content is None else str(content)
    escaped_content = html.escape(content)
    html_content = markdown.markdown(escaped_content, extensions=['fenced_code', 'tables'])
    return jsonify({'success': True, 'html': html_content})

if __name__ == '__main__':
    # When deployed in production, use a WSGI server instead of app.run
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('FLASK_DEBUG', '1').lower() in ('1', 'true', 'yes', 'on')
    app.run(host=host, port=port, debug=debug)
