import os
import secrets
import string
import time


def resolve_runtime_path(base_dir, instance_dir, *parts, prefer_legacy=False):
    instance_path = os.path.join(instance_dir, *parts)
    legacy_path = os.path.join(base_dir, *parts)

    if prefer_legacy and os.path.exists(legacy_path) and not os.path.exists(instance_path):
        return legacy_path
    return instance_path


def load_secret_key(base_dir):
    env_secret = os.getenv('SECRET_KEY')
    if env_secret:
        return env_secret, 'env', None

    instance_dir = os.path.join(base_dir, 'instance')
    secret_file = os.path.join(instance_dir, 'secret_key')

    def read_file_secret():
        with open(secret_file, 'r', encoding='utf-8') as handle:
            saved_secret = handle.read().strip()
        return saved_secret or None

    try:
        os.makedirs(instance_dir, exist_ok=True)

        try:
            file_secret = read_file_secret()
            if file_secret:
                return file_secret, 'file', secret_file
        except FileNotFoundError:
            pass

        generated_secret = secrets.token_hex(32)
        try:
            fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(generated_secret)
                handle.flush()
                os.fsync(handle.fileno())
            return generated_secret, 'file', secret_file
        except FileExistsError:
            for _ in range(5):
                try:
                    file_secret = read_file_secret()
                    if file_secret:
                        return file_secret, 'file', secret_file
                except FileNotFoundError:
                    pass
                time.sleep(0.05)
            raise OSError('secret key file exists but could not be read')
    except OSError:
        return secrets.token_hex(32), 'temporary', None


def secure_filename(filename):
    if not filename:
        return 'unnamed'
    filename = os.path.basename(filename)
    filename = filename.replace('/', '').replace('\\', '').replace('..', '')
    for ch in '<>:"|?*':
        filename = filename.replace(ch, '_')
    filename = ''.join(c for c in filename if ord(c) > 31)
    filename = filename.strip('. ')
    if not filename:
        return 'unnamed'
    return filename


def get_initial_admin_password():
    configured = os.getenv('INITIAL_ADMIN_PASSWORD')
    if configured:
        return configured, 'env'
    return secrets.token_urlsafe(16), 'generated'


def generate_short_id(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))


def format_size(size_bytes):
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def normalize_managed_filename(filename):
    if not isinstance(filename, str) or not filename:
        return None
    if any(sep in filename for sep in ('/', '\\')) or '..' in filename:
        return None
    safe_name = secure_filename(filename)
    if safe_name != filename:
        return None
    return safe_name


def normalize_note_input(form, require_content=False):
    title = form.get('title', '')
    if not isinstance(title, str):
        return None, None, ('标题格式不正确', 400)

    title = title.strip()
    if not title:
        return None, None, ('标题不能为空', 400)

    content = form.get('content')
    if content is None:
        if require_content:
            return None, None, ('内容不能为空', 400)
        content = ''
    elif not isinstance(content, str):
        content = str(content)

    return title, content, None


def build_unique_name(directory, filename, suffix):
    candidate = filename
    name, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{name}_{suffix}_{int(time.time())}_{counter}{ext}"
        counter += 1
    return candidate


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
    ignored_prefixes = ('instance/', 'uploads/', 'notes/', 'trash/', '__pycache__/')

    if normalized in ignored_exact:
        return True
    if normalized.startswith(ignored_prefixes):
        return True
    if normalized.endswith('.pyc'):
        return True
    return False
