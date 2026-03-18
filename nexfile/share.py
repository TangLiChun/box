import html
import sqlite3

import markdown
from flask import current_app, jsonify, render_template, request, send_from_directory


def handle_create_share(is_authenticated, resolve_item_path, get_item_label, get_db, generate_short_id):
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
    existing = db.execute(
        'SELECT id FROM shares WHERE type=? AND target_filename=?',
        (item_type, safe_name),
    ).fetchone()
    if existing:
        return jsonify({'success': True, 'share_id': existing['id']})

    for _ in range(5):
        share_id = generate_short_id()
        try:
            db.execute(
                'INSERT INTO shares (id, type, target_filename) VALUES (?, ?, ?)',
                (share_id, item_type, safe_name),
            )
            db.commit()
            return jsonify({'success': True, 'share_id': share_id})
        except sqlite3.IntegrityError:
            continue

    return jsonify({'success': False, 'message': '生成分享链接失败，请重试'}), 500


def handle_revoke_share(is_authenticated, get_db):
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    if not request.is_json:
        return jsonify({'success': False, 'message': '请求必须为 JSON'}), 400

    data = request.get_json(silent=True) or {}
    share_id = data.get('share_id')
    if not share_id:
        return jsonify({'success': False, 'message': '缺少 share_id'}), 400

    db = get_db()
    db.execute('DELETE FROM shares WHERE id = ?', (share_id,))
    db.commit()
    return jsonify({'success': True})


def handle_public_share_file(share_id, get_db, resolve_item_path):
    db = get_db()
    share = db.execute(
        'SELECT target_filename FROM shares WHERE id = ? AND type="file"',
        (share_id,),
    ).fetchone()
    if not share:
        return "此分享链接已失效或不存在。", 404

    filename, filepath = resolve_item_path('file', share['target_filename'])
    if not filepath:
        return "文件已被删除。", 404

    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=True)


def handle_public_share_note(share_id, get_db, resolve_item_path, get_setting):
    db = get_db()
    share = db.execute(
        'SELECT target_filename FROM shares WHERE id = ? AND type="note"',
        (share_id,),
    ).fetchone()
    if not share:
        return "此分享链接已失效或不存在。", 404

    filename, filepath = resolve_item_path('note', share['target_filename'])
    if not filepath:
        return "笔记已被删除。", 404

    with open(filepath, 'r', encoding='utf-8') as handle:
        content = handle.read()

    escaped_content = html.escape(content)
    html_content = markdown.markdown(escaped_content, extensions=['fenced_code', 'tables'])
    announcement = get_setting('announcement')
    return render_template('share_view.html', title=filename[:-3], content=html_content, announcement=announcement)
