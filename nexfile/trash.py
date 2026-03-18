import os
import time
from datetime import datetime

from flask import jsonify, redirect, render_template, request, session, url_for


def auto_cleanup_trash(trash_folder, get_db, app_logger):
    try:
        if not os.path.exists(trash_folder):
            return

        cleanup_threshold = 3 * 86400
        now = time.time()
        removed_names = []
        for filename in os.listdir(trash_folder):
            file_path = os.path.join(trash_folder, filename)
            if os.path.isfile(file_path):
                file_age = now - os.path.getmtime(file_path)
                if file_age > cleanup_threshold:
                    os.remove(file_path)
                    removed_names.append(filename)

        if removed_names:
            db = get_db()
            db.executemany('DELETE FROM trash_items WHERE trash_name = ?', [(name,) for name in removed_names])
            db.commit()
    except Exception as exc:
        app_logger.error(f"Trash cleanup error: {exc}")


def handle_batch_delete(is_authenticated, move_item_to_trash):
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
                'failures': failures,
            }), 400

        message = f'成功将 {success_count} 个文件移至回收站'
        if failures:
            message += f'，另有 {len(failures)} 个文件未处理'
        return jsonify({'success': True, 'message': message, 'failures': failures})
    except Exception as exc:
        return jsonify({'success': False, 'message': f'操作失败: {str(exc)}'}), 500


def handle_view_trash(is_authenticated, get_db, format_size, get_setting, app_logger, trash_folder):
    if not is_authenticated():
        return redirect(url_for('main.login'))

    auto_cleanup_trash(trash_folder, get_db, app_logger)

    trash_items = []
    db = get_db()
    metadata_rows = db.execute('SELECT trash_name, original_name, item_type FROM trash_items').fetchall()
    metadata_by_name = {row['trash_name']: row for row in metadata_rows}
    try:
        with os.scandir(trash_folder) as entries:
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
                        'mtime_raw': stat.st_mtime,
                    })
    except OSError as exc:
        app_logger.error(f"Error listing trash: {exc}")

    trash_items.sort(key=lambda x: x['mtime_raw'], reverse=True)
    return render_template(
        'trash.html',
        items=trash_items,
        current_user=session['username'],
        announcement=get_setting('announcement'),
    )


def handle_restore_item(filename, is_authenticated, restore_item_from_trash):
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


def handle_permanent_delete_item(filename, is_authenticated, permanently_delete_trash_item):
    if not is_authenticated():
        return jsonify({'success': False}), 401

    success, result, status_code = permanently_delete_trash_item(filename)
    if success:
        return jsonify({'success': True, 'message': result}), status_code
    return jsonify({'success': False, 'message': result}), status_code


def handle_clear_trash(is_authenticated, get_db, trash_folder):
    if not is_authenticated():
        return jsonify({'success': False}), 401

    try:
        for filename in os.listdir(trash_folder):
            file_path = os.path.join(trash_folder, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
        db = get_db()
        db.execute('DELETE FROM trash_items')
        db.commit()
        return jsonify({'success': True, 'message': '回收站已清空'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 500
