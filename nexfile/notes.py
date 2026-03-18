import html
import os
from datetime import datetime

import markdown
from flask import jsonify, redirect, render_template, request, session, url_for


def handle_notes_index(is_authenticated, get_db, get_setting, app_logger, notes_folder):
    if not is_authenticated():
        return redirect(url_for('main.login'))

    notes_list = []
    db = get_db()
    try:
        with os.scandir(notes_folder) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.endswith('.md'):
                    stat = entry.stat()
                    filename = entry.name
                    title = filename[:-3]
                    share = db.execute(
                        'SELECT id FROM shares WHERE type="note" AND target_filename=?',
                        (filename,),
                    ).fetchone()
                    share_id = share['id'] if share else None

                    notes_list.append({
                        'title': title,
                        'filename': filename,
                        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'mtime_raw': stat.st_mtime,
                        'share_id': share_id,
                    })
    except OSError as exc:
        app_logger.error(f"Error listing notes: {exc}")

    notes_list.sort(key=lambda x: x['mtime_raw'], reverse=True)
    announcement = get_setting('announcement')
    return render_template('notes.html', notes=notes_list, current_user=session['username'], announcement=announcement)


def handle_create_note(is_authenticated, normalize_note_input, secure_filename, get_setting, notes_folder):
    if not is_authenticated():
        return redirect(url_for('main.login'))

    if request.method == 'POST':
        title, content, error = normalize_note_input(request.form)
        if error:
            message, status_code = error
            return jsonify({'success': False, 'message': message}), status_code

        filename = secure_filename(title) + '.md'
        filepath = os.path.join(notes_folder, filename)

        if os.path.exists(filepath):
            return jsonify({'success': False, 'message': '已存在同名笔记'})

        with open(filepath, 'w', encoding='utf-8') as handle:
            handle.write(content)

        return jsonify({'success': True, 'redirect': url_for('main.view_note', filename=filename)})

    announcement = get_setting('announcement')
    return render_template('note_edit.html', current_user=session['username'], announcement=announcement)


def handle_edit_note(
    filename,
    is_authenticated,
    resolve_item_path,
    normalize_note_input,
    secure_filename,
    get_db,
    get_setting,
    app_logger,
    notes_folder,
):
    if not is_authenticated():
        return redirect(url_for('main.login'))

    safe_name, filepath = resolve_item_path('note', filename)
    if not filepath:
        return redirect(url_for('main.notes'))

    if request.method == 'POST':
        new_title, content, error = normalize_note_input(request.form, require_content=True)
        if error:
            message, status_code = error
            return jsonify({'success': False, 'message': message}), status_code

        new_filename = secure_filename(new_title) + '.md'
        new_filepath = os.path.join(notes_folder, new_filename)

        if new_filename != safe_name and os.path.exists(new_filepath):
            return jsonify({'success': False, 'message': '已存在同名笔记'})

        if new_filename != safe_name:
            with open(new_filepath, 'w', encoding='utf-8') as handle:
                handle.write(content)
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except OSError as exc:
                app_logger.error(f"Failed to remove old note {safe_name}: {exc}")
                try:
                    os.remove(new_filepath)
                except OSError:
                    pass
                return jsonify({'success': False, 'message': '重命名失败，旧文件无法删除'}), 500

            db = get_db()
            db.execute(
                'UPDATE shares SET target_filename=? WHERE type="note" AND target_filename=?',
                (new_filename, safe_name),
            )
            db.commit()
        else:
            with open(new_filepath, 'w', encoding='utf-8') as handle:
                handle.write(content)

        return jsonify({'success': True, 'redirect': url_for('main.view_note', filename=new_filename)})

    with open(filepath, 'r', encoding='utf-8') as handle:
        content = handle.read()

    announcement = get_setting('announcement')
    return render_template(
        'note_edit.html',
        title=safe_name[:-3],
        content=content,
        is_edit=True,
        original_filename=safe_name,
        current_user=session['username'],
        announcement=announcement,
    )


def handle_view_note(filename, is_authenticated, resolve_item_path, get_setting):
    if not is_authenticated():
        return redirect(url_for('main.login'))

    safe_name, filepath = resolve_item_path('note', filename)
    if not filepath:
        return redirect(url_for('main.notes'))

    with open(filepath, 'r', encoding='utf-8') as handle:
        content = handle.read()

    escaped_content = html.escape(content)
    html_content = markdown.markdown(escaped_content, extensions=['fenced_code', 'tables'])
    announcement = get_setting('announcement')
    return render_template(
        'note_view.html',
        title=safe_name[:-3],
        content=html_content,
        filename=safe_name,
        current_user=session['username'],
        announcement=announcement,
    )


def handle_delete_note(filename, is_authenticated, move_item_to_trash):
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    success, result, status_code = move_item_to_trash('note', filename)
    if success:
        return jsonify({'success': True, 'message': '笔记已移至回收站'}), status_code
    return jsonify({'success': False, 'message': result}), status_code
