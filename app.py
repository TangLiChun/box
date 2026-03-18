import os
import sys
from flask import Flask, current_app, has_app_context, request, redirect, url_for, session, flash, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from nexfile.admin import (
    handle_add_user,
    handle_apply_update,
    handle_change_password,
    handle_delete_user,
    handle_test_onlyoffice_connection,
    handle_update_settings,
    handle_update_status,
    render_admin_dashboard,
)
from nexfile.auth import handle_login, handle_logout
from nexfile.blueprints_main import configure_main_blueprint, main_bp
from nexfile.core import (
    build_unique_name,
    format_size,
    generate_short_id,
    get_initial_admin_password,
    is_runtime_generated_git_path,
    load_secret_key,
    normalize_managed_filename,
    normalize_note_input,
    parse_dirty_paths_from_porcelain,
    resolve_runtime_path,
    secure_filename,
    summarize_update_step,
)
from nexfile.files import (
    handle_analyze_file,
    handle_delete_file,
    handle_download_file,
    handle_index,
)
from nexfile.services import (
    close_connection as services_close_connection,
    delete_trash_metadata as services_delete_trash_metadata,
    get_db as services_get_db,
    get_item_folder as services_get_item_folder,
    get_item_label as services_get_item_label,
    get_setting as services_get_setting,
    get_trash_metadata as services_get_trash_metadata,
    init_db as services_init_db,
    is_admin_password_change_required as services_is_admin_password_change_required,
    move_item_to_trash as services_move_item_to_trash,
    permanently_delete_trash_item as services_permanently_delete_trash_item,
    resolve_item_path as services_resolve_item_path,
    restore_item_from_trash as services_restore_item_from_trash,
    set_setting as services_set_setting,
    store_trash_metadata as services_store_trash_metadata,
)
from nexfile.game import (
    handle_create_game_share,
    handle_game,
    handle_public_game,
    handle_public_share_game,
)
from nexfile.notes import (
    handle_create_note,
    handle_delete_note,
    handle_edit_note,
    handle_notes_index,
    handle_view_note,
)
from nexfile.onlyoffice import handle_onlyoffice_callback, handle_onlyoffice_editor
from nexfile.onlyoffice_tokens import (
    decode_onlyoffice_jwt as tokens_decode_onlyoffice_jwt,
    extract_onlyoffice_jwt_token as tokens_extract_onlyoffice_jwt_token,
    generate_onlyoffice_callback_token as tokens_generate_onlyoffice_callback_token,
    generate_onlyoffice_download_token as tokens_generate_onlyoffice_download_token,
    generate_onlyoffice_jwt as tokens_generate_onlyoffice_jwt,
    get_onlyoffice_callback_secret as tokens_get_onlyoffice_callback_secret,
    get_onlyoffice_jwt_secret as tokens_get_onlyoffice_jwt_secret,
    is_valid_onlyoffice_callback_token as tokens_is_valid_onlyoffice_callback_token,
    is_valid_onlyoffice_download_token as tokens_is_valid_onlyoffice_download_token,
)
from nexfile.preview import handle_render_preview
from nexfile.share import (
    handle_create_share,
    handle_public_share_file,
    handle_public_share_note,
    handle_revoke_share,
)
from nexfile.trash import (
    handle_batch_delete,
    handle_clear_trash,
    handle_permanent_delete_item,
    handle_restore_item,
    handle_view_trash,
)
from nexfile.update import (
    apply_incremental_update as update_apply_incremental_update,
    find_git_repo_root as update_find_git_repo_root,
    inspect_incremental_update_status as update_inspect_incremental_update_status,
    run_update_command as update_run_update_command,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
app = None
UPLOAD_FOLDER = None
NOTES_FOLDER = None
TRASH_FOLDER = None
DATABASE = None
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

def get_active_config():
    if has_app_context():
        return current_app.config
    return app.config if app is not None else {}


def sync_compat_path_globals(config):
    global UPLOAD_FOLDER, NOTES_FOLDER, TRASH_FOLDER, DATABASE
    UPLOAD_FOLDER = config.get('UPLOAD_FOLDER')
    NOTES_FOLDER = config.get('NOTES_FOLDER')
    TRASH_FOLDER = config.get('TRASH_FOLDER')
    DATABASE = config.get('DATABASE')


def build_default_app_config():
    return {
        'UPLOAD_FOLDER': resolve_runtime_path(BASE_DIR, INSTANCE_DIR, 'uploads', prefer_legacy=True),
        'NOTES_FOLDER': resolve_runtime_path(BASE_DIR, INSTANCE_DIR, 'notes', prefer_legacy=True),
        'TRASH_FOLDER': resolve_runtime_path(BASE_DIR, INSTANCE_DIR, 'trash', prefer_legacy=True),
        'DATABASE': resolve_runtime_path(BASE_DIR, INSTANCE_DIR, 'users.db', prefer_legacy=True),
        'MAX_CONTENT_LENGTH': 100 * 1024 * 1024,
    }


def get_db():
    database_path = get_active_config().get('DATABASE', DATABASE)
    return services_get_db(database_path)

def close_connection(exception):
    return services_close_connection(exception)

def init_db(target_app=None):
    target_app = target_app or app
    return services_init_db(
        target_app,
        get_db,
        get_initial_admin_password,
        generate_password_hash,
        target_app.logger,
    )

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
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

def get_setting(key, default=None):
    return services_get_setting(get_db, key, default)

def set_setting(key, value):
    return services_set_setting(get_db, key, value)


def is_admin_password_change_required():
    return services_is_admin_password_change_required(get_setting)

def get_item_folder(item_type):
    return services_get_item_folder(get_active_config(), item_type)

def get_item_label(item_type):
    return services_get_item_label(item_type)

def resolve_item_path(item_type, filename, require_exists=True):
    return services_resolve_item_path(get_active_config(), normalize_managed_filename, item_type, filename, require_exists)

def store_trash_metadata(trash_name, original_name, item_type):
    return services_store_trash_metadata(get_db, trash_name, original_name, item_type)

def get_trash_metadata(trash_name):
    return services_get_trash_metadata(get_db, trash_name)

def delete_trash_metadata(trash_name):
    return services_delete_trash_metadata(get_db, trash_name)

def move_item_to_trash(item_type, filename):
    return services_move_item_to_trash(
        get_active_config(),
        get_db,
        resolve_item_path,
        get_item_label,
        build_unique_name,
        store_trash_metadata,
        item_type,
        filename,
    )

def restore_item_from_trash(trash_name, requested_item_type=None):
    return services_restore_item_from_trash(
        get_active_config(),
        get_db,
        get_trash_metadata,
        delete_trash_metadata,
        normalize_managed_filename,
        build_unique_name,
        get_item_folder,
        trash_name,
        requested_item_type,
    )

def permanently_delete_trash_item(trash_name):
    return services_permanently_delete_trash_item(
        get_active_config(),
        get_db,
        delete_trash_metadata,
        normalize_managed_filename,
        trash_name,
    )

def get_onlyoffice_callback_secret():
    return tokens_get_onlyoffice_callback_secret(get_setting, set_setting)

def generate_onlyoffice_callback_token(filename):
    return tokens_generate_onlyoffice_callback_token(filename, normalize_managed_filename, get_onlyoffice_callback_secret)

def is_valid_onlyoffice_callback_token(filename, token):
    return tokens_is_valid_onlyoffice_callback_token(filename, token, generate_onlyoffice_callback_token)

def generate_onlyoffice_download_token(filename):
    return tokens_generate_onlyoffice_download_token(filename, normalize_managed_filename, get_onlyoffice_callback_secret)

def is_valid_onlyoffice_download_token(filename, token):
    return tokens_is_valid_onlyoffice_download_token(filename, token, generate_onlyoffice_download_token)

def get_onlyoffice_jwt_secret():
    return tokens_get_onlyoffice_jwt_secret(get_setting)

def generate_onlyoffice_jwt(payload, secret=None):
    return tokens_generate_onlyoffice_jwt(payload, get_onlyoffice_jwt_secret, secret)

def decode_onlyoffice_jwt(token, secret=None):
    return tokens_decode_onlyoffice_jwt(token, get_onlyoffice_jwt_secret, secret)

def extract_onlyoffice_jwt_token(data=None):
    return tokens_extract_onlyoffice_jwt_token(data)

def find_git_repo_root(start_dir=None):
    return update_find_git_repo_root(start_dir or BASE_DIR)

def run_update_command(command, cwd, timeout=120):
    return update_run_update_command(command, cwd, timeout)

def inspect_incremental_update_status(run_fetch=True):
    return update_inspect_incremental_update_status(
        BASE_DIR,
        run_update_command,
        find_git_repo_root,
        parse_dirty_paths_from_porcelain,
        is_runtime_generated_git_path,
        summarize_update_step,
        run_fetch,
    )

def apply_incremental_update():
    return update_apply_incremental_update(
        BASE_DIR,
        inspect_incremental_update_status,
        run_update_command,
        summarize_update_step,
        sys.executable,
    )

configure_main_blueprint(
    admin_required=admin_required,
    apply_incremental_update=apply_incremental_update,
    decode_onlyoffice_jwt=decode_onlyoffice_jwt,
    extract_onlyoffice_jwt_token=extract_onlyoffice_jwt_token,
    format_size=format_size,
    generate_onlyoffice_callback_token=generate_onlyoffice_callback_token,
    generate_onlyoffice_download_token=generate_onlyoffice_download_token,
    generate_onlyoffice_jwt=generate_onlyoffice_jwt,
    generate_short_id=generate_short_id,
    get_db=get_db,
    get_item_label=get_item_label,
    get_onlyoffice_jwt_secret=get_onlyoffice_jwt_secret,
    get_setting=get_setting,
    handle_add_user=handle_add_user,
    handle_analyze_file=handle_analyze_file,
    handle_apply_update=handle_apply_update,
    handle_batch_delete=handle_batch_delete,
    handle_change_password=handle_change_password,
    handle_clear_trash=handle_clear_trash,
    handle_create_game_share=handle_create_game_share,
    handle_create_note=handle_create_note,
    handle_create_share=handle_create_share,
    handle_delete_file=handle_delete_file,
    handle_delete_note=handle_delete_note,
    handle_download_file=handle_download_file,
    handle_edit_note=handle_edit_note,
    handle_game=handle_game,
    handle_index=handle_index,
    handle_login=handle_login,
    handle_logout=handle_logout,
    handle_notes_index=handle_notes_index,
    handle_onlyoffice_callback=handle_onlyoffice_callback,
    handle_onlyoffice_editor=handle_onlyoffice_editor,
    handle_permanent_delete_item=handle_permanent_delete_item,
    handle_public_game=handle_public_game,
    handle_public_share_file=handle_public_share_file,
    handle_public_share_game=handle_public_share_game,
    handle_public_share_note=handle_public_share_note,
    handle_render_preview=handle_render_preview,
    handle_restore_item=handle_restore_item,
    handle_revoke_share=handle_revoke_share,
    handle_test_onlyoffice_connection=handle_test_onlyoffice_connection,
    handle_update_settings=handle_update_settings,
    handle_update_status=handle_update_status,
    handle_view_note=handle_view_note,
    handle_view_trash=handle_view_trash,
    inspect_incremental_update_status=inspect_incremental_update_status,
    is_admin_password_change_required=is_admin_password_change_required,
    is_authenticated=is_authenticated,
    is_valid_onlyoffice_callback_token=is_valid_onlyoffice_callback_token,
    is_valid_onlyoffice_download_token=is_valid_onlyoffice_download_token,
    move_item_to_trash=move_item_to_trash,
    normalize_managed_filename=normalize_managed_filename,
    normalize_note_input=normalize_note_input,
    onlyoffice_formats=ONLYOFFICE_FORMATS,
    permanently_delete_trash_item=permanently_delete_trash_item,
    render_admin_dashboard=render_admin_dashboard,
    resolve_item_path=resolve_item_path,
    restore_item_from_trash=restore_item_from_trash,
    secure_filename=secure_filename,
    set_setting=set_setting,
)


def create_app(config_overrides=None):
    global app

    app = Flask(__name__)
    app.secret_key, secret_key_source, secret_key_file = load_secret_key(BASE_DIR)

    if secret_key_source == 'temporary':
        app.logger.warning('WARNING: 使用了临时随机 SECRET_KEY，本次重启后会话将失效。生产环境请配置环境变量 SECRET_KEY。')
    elif secret_key_source == 'file':
        app.logger.info('SECRET_KEY loaded from %s', secret_key_file)

    app.config.update(build_default_app_config())

    if config_overrides:
        app.config.update(config_overrides)

    sync_compat_path_globals(app.config)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['NOTES_FOLDER'], exist_ok=True)
    os.makedirs(app.config['TRASH_FOLDER'], exist_ok=True)

    app.teardown_appcontext(close_connection)
    init_db(app)
    app.register_blueprint(main_bp)
    return app


app = create_app()

if __name__ == '__main__':
    # When deployed in production, use a WSGI server instead of app.run
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes', 'on')
    app.run(host=host, port=port, debug=debug)
