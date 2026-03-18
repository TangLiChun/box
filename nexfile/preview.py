import html

import markdown
from flask import jsonify, request


def handle_render_preview(is_authenticated):
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
