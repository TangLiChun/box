import sqlite3

from flask import jsonify, redirect, render_template, request, session, url_for


def handle_game(is_authenticated, get_setting):
    if not is_authenticated():
        return redirect(url_for('main.login'))
    announcement = get_setting('announcement')
    return render_template('game.html', current_user=session['username'], is_public=False, announcement=announcement)


def handle_public_game(get_setting):
    data = request.args.get('data', '')
    announcement = get_setting('announcement')
    return render_template('game.html', is_public=True, shared_data=data, announcement=announcement)


def handle_create_game_share(is_authenticated, get_db, generate_short_id):
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


def handle_public_share_game(share_id, get_db, get_setting):
    db = get_db()
    share = db.execute('SELECT target_filename FROM shares WHERE id = ? AND type="game"', (share_id,)).fetchone()
    if not share:
        return "此转盘分享链接已失效或不存在。", 404

    announcement = get_setting('announcement')
    return render_template('game.html', is_public=True, shared_data=share['target_filename'], announcement=announcement)
