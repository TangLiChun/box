import urllib.request

from flask import jsonify, render_template, request, session
from werkzeug.security import generate_password_hash


def render_admin_dashboard(get_db, get_setting, is_admin_password_change_required):
    db = get_db()
    users = db.execute('SELECT id, username FROM users').fetchall()
    announcement = get_setting('announcement')
    return render_template(
        'admin.html',
        users=users,
        current_user=session['username'],
        onlyoffice_url=get_setting('onlyoffice_url'),
        onlyoffice_jwt_secret=get_setting('onlyoffice_jwt_secret'),
        onlyoffice_callback_base=get_setting('onlyoffice_callback_base'),
        announcement=announcement,
        admin_password_change_required=is_admin_password_change_required(),
    )


def handle_update_settings(set_setting):
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


def handle_test_onlyoffice_connection(get_setting):
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
    except Exception as exc:
        return jsonify({'success': False, 'message': f'连接失败: {str(exc)}'})


def handle_update_status(inspect_incremental_update_status):
    status = inspect_incremental_update_status(run_fetch=True)
    return jsonify({'success': True, **status})


def handle_apply_update(apply_incremental_update):
    success, result, status_code = apply_incremental_update()
    payload = {'success': success, **result}
    return jsonify(payload), status_code


def handle_add_user(get_db):
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})

    db = get_db()
    if db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
        return jsonify({'success': False, 'message': '用户名已存在'})

    db.execute(
        'INSERT INTO users (username, password) VALUES (?, ?)',
        (username, generate_password_hash(password)),
    )
    db.commit()
    return jsonify({'success': True, 'message': f'用户 {username} 添加成功'})


def handle_delete_user(user_id, get_db):
    if user_id == session['user_id']:
        return jsonify({'success': False, 'message': '不能删除当前登录用户'})

    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    return jsonify({'success': True, 'message': '用户删除成功'})


def handle_change_password(is_authenticated, get_db):
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    user_id = request.form.get('user_id')
    new_password = request.form.get('new_password')

    if session.get('username') != 'admin' and str(user_id) != str(session.get('user_id')):
        return jsonify({'success': False, 'message': '未授权的操作'}), 403

    if not new_password:
        return jsonify({'success': False, 'message': '新密码不能为空'})

    db = get_db()
    db.execute('UPDATE users SET password = ? WHERE id = ?', (generate_password_hash(new_password), user_id))
    if str(user_id) == str(session.get('user_id')) and session.get('username') == 'admin':
        db.execute(
            'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
            ('admin_password_change_required', '0'),
        )
    db.commit()
    return jsonify({'success': True, 'message': '密码修改成功'})
