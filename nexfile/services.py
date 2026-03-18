import os
import sqlite3
from datetime import datetime, timezone

from flask import g


def get_db(database_path):
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(database_path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON;')
    return db


def close_connection(_exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db(app, get_db_func, get_initial_admin_password, generate_password_hash, logger):
    with app.app_context():
        db = get_db_func()
        db.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
            '''
        )
        db.execute(
            '''
            CREATE TABLE IF NOT EXISTS shares (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                target_filename TEXT NOT NULL
            )
            '''
        )
        db.execute(
            '''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            '''
        )
        db.execute(
            '''
            CREATE TABLE IF NOT EXISTS trash_items (
                trash_name TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                item_type TEXT NOT NULL,
                deleted_at TEXT NOT NULL
            )
            '''
        )
        if not db.execute('SELECT 1 FROM settings WHERE key = ?', ('onlyoffice_callback_secret',)).fetchone():
            db.execute(
                'INSERT INTO settings (key, value) VALUES (?, ?)',
                ('onlyoffice_callback_secret', __import__('secrets').token_urlsafe(32)),
            )
        db.commit()

        cursor = db.execute('SELECT COUNT(*) FROM users')
        if cursor.fetchone()[0] == 0:
            initial_password, password_source = get_initial_admin_password()
            db.execute(
                'INSERT INTO users (username, password) VALUES (?, ?)',
                ('admin', generate_password_hash(initial_password)),
            )
            db.execute(
                'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                ('admin_password_change_required', '1'),
            )
            db.commit()
            if password_source == 'env':
                logger.warning('Initialized admin user from INITIAL_ADMIN_PASSWORD environment variable.')
            else:
                logger.warning(
                    'Initialized admin user with a one-time generated password. Username: admin Password: %s',
                    initial_password,
                )


def get_setting(get_db_func, key, default=None):
    db = get_db_func()
    row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    return row['value'] if row else default


def set_setting(get_db_func, key, value):
    db = get_db_func()
    db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    db.commit()


def is_admin_password_change_required(get_setting_func):
    return get_setting_func('admin_password_change_required', '0') == '1'


def get_item_folder(app_config, item_type):
    if item_type == 'file':
        return app_config['UPLOAD_FOLDER']
    if item_type == 'note':
        return app_config['NOTES_FOLDER']
    return None


def get_item_label(item_type):
    return '文件' if item_type == 'file' else '笔记'


def resolve_item_path(app_config, normalize_managed_filename, item_type, filename, require_exists=True):
    safe_name = normalize_managed_filename(filename)
    folder = get_item_folder(app_config, item_type)
    if not safe_name or not folder:
        return None, None

    file_path = os.path.join(folder, safe_name)
    if require_exists and not os.path.isfile(file_path):
        return safe_name, None
    return safe_name, file_path


def store_trash_metadata(get_db_func, trash_name, original_name, item_type):
    db = get_db_func()
    db.execute(
        'INSERT OR REPLACE INTO trash_items (trash_name, original_name, item_type, deleted_at) VALUES (?, ?, ?, ?)',
        (trash_name, original_name, item_type, datetime.now(timezone.utc).isoformat()),
    )


def get_trash_metadata(get_db_func, trash_name):
    db = get_db_func()
    return db.execute(
        'SELECT trash_name, original_name, item_type, deleted_at FROM trash_items WHERE trash_name = ?',
        (trash_name,),
    ).fetchone()


def delete_trash_metadata(get_db_func, trash_name):
    db = get_db_func()
    db.execute('DELETE FROM trash_items WHERE trash_name = ?', (trash_name,))


def move_item_to_trash(app_config, get_db_func, resolve_item_path_func, get_item_label_func, build_unique_name, store_trash_metadata_func, item_type, filename):
    safe_name, source_path = resolve_item_path_func(item_type, filename)
    if not safe_name:
        return False, '无效的文件名', 400
    if not source_path:
        return False, f'{get_item_label_func(item_type)}不存在', 404

    trash_name = build_unique_name(app_config['TRASH_FOLDER'], safe_name, 'trash')
    trash_path = os.path.join(app_config['TRASH_FOLDER'], trash_name)
    db = get_db_func()

    try:
        os.rename(source_path, trash_path)
        store_trash_metadata_func(trash_name, safe_name, item_type)
        db.execute('DELETE FROM shares WHERE type = ? AND target_filename = ?', (item_type, safe_name))
        db.commit()
        return True, {'original_name': safe_name, 'trash_name': trash_name}, 200
    except Exception as exc:
        db.rollback()
        return False, str(exc), 500


def restore_item_from_trash(app_config, get_db_func, get_trash_metadata_func, delete_trash_metadata_func, normalize_managed_filename, build_unique_name, get_item_folder_func, trash_name, requested_item_type=None):
    safe_trash_name = normalize_managed_filename(trash_name)
    if not safe_trash_name:
        return False, '无效的文件名', 400
    if requested_item_type is not None and requested_item_type not in ('file', 'note'):
        return False, '无效的恢复类型', 400

    trash_path = os.path.join(app_config['TRASH_FOLDER'], safe_trash_name)
    if not os.path.isfile(trash_path):
        return False, '项目不存在', 404

    metadata = get_trash_metadata_func(safe_trash_name)
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

    target_folder = get_item_folder_func(item_type)
    restored_name = build_unique_name(target_folder, original_name, 'restored')
    destination_path = os.path.join(target_folder, restored_name)
    db = get_db_func()

    try:
        os.rename(trash_path, destination_path)
        delete_trash_metadata_func(safe_trash_name)
        db.commit()
        return True, {'restored_name': restored_name, 'item_type': item_type}, 200
    except Exception as exc:
        db.rollback()
        return False, str(exc), 500


def permanently_delete_trash_item(app_config, get_db_func, delete_trash_metadata_func, normalize_managed_filename, trash_name):
    safe_trash_name = normalize_managed_filename(trash_name)
    if not safe_trash_name:
        return False, '无效的文件名', 400

    trash_path = os.path.join(app_config['TRASH_FOLDER'], safe_trash_name)
    if not os.path.isfile(trash_path):
        return False, '项目不存在', 404

    db = get_db_func()
    try:
        os.remove(trash_path)
        delete_trash_metadata_func(safe_trash_name)
        db.commit()
        return True, '项目已永久删除', 200
    except Exception as exc:
        db.rollback()
        return False, str(exc), 500
