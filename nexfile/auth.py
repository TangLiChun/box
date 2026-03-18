from flask import redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash


def handle_login(is_authenticated, get_db):
    if is_authenticated():
        return redirect(url_for('main.index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('main.index'))

        error = '账号或密码错误。请重试。'

    return render_template('login.html', error=error)


def handle_logout():
    session.clear()
    return redirect(url_for('main.login'))
