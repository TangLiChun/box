import mimetypes
import os
import hashlib
import math
from datetime import datetime

from flask import abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for


def handle_index(
    is_authenticated,
    secure_filename,
    get_db,
    format_size,
    get_setting,
    app_logger,
    upload_folder,
    office_extensions,
):
    if not is_authenticated():
        return redirect(url_for('main.login'))

    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未找到文件部分'})

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'})

        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(upload_folder, filename)

            counter = 1
            name, ext = os.path.splitext(filename)
            while os.path.exists(file_path):
                filename = f"{name}_{counter}{ext}"
                file_path = os.path.join(upload_folder, filename)
                counter += 1

            file.save(file_path)
            return jsonify({'success': True, 'message': f'文件 {filename} 上传成功。'})

    files = []
    db = get_db()
    try:
        with os.scandir(upload_folder) as entries:
            for entry in entries:
                if entry.is_file():
                    stat = entry.stat()
                    filename = entry.name
                    share = db.execute(
                        'SELECT id FROM shares WHERE type="file" AND target_filename=?',
                        (filename,),
                    ).fetchone()
                    share_id = share['id'] if share else None
                    files.append({
                        'name': filename,
                        'size_raw': stat.st_size,
                        'size': format_size(stat.st_size),
                        'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                        'share_id': share_id,
                    })
    except OSError as exc:
        app_logger.error(f"Error listing uploads: {exc}")

    files.sort(key=lambda x: x['size_raw'], reverse=True)
    return render_template(
        'index.html',
        files=files,
        current_user=session['username'],
        onlyoffice_url=get_setting('onlyoffice_url'),
        office_extensions=office_extensions,
        announcement=get_setting('announcement'),
    )


def handle_download_file(filename, resolve_item_path, is_authenticated, is_valid_onlyoffice_download_token, upload_folder):
    safe_name, filepath = resolve_item_path('file', filename)
    if not safe_name or not filepath:
        abort(404)

    if not is_authenticated():
        token = request.args.get('token')
        if token:
            if not is_valid_onlyoffice_download_token(safe_name, token):
                return jsonify({'success': False, 'message': '无效下载令牌'}), 403
        else:
            return redirect(url_for('main.login'))

    return send_from_directory(upload_folder, safe_name, as_attachment=True)


def handle_delete_file(filename, is_authenticated, move_item_to_trash):
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    success, result, status_code = move_item_to_trash('file', filename)
    if success:
        return jsonify({'success': True, 'message': f'文件 {result["original_name"]} 已移至回收站'}), status_code
    return jsonify({'success': False, 'message': result}), status_code


def handle_analyze_file(filename, is_authenticated, resolve_item_path):
    if not is_authenticated():
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    safe_name, filepath = resolve_item_path('file', filename)
    if not safe_name:
        return jsonify({'success': False, 'message': '无效的文件名'}), 400
    if not filepath:
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    stat = os.stat(filepath)
    size_bytes = stat.st_size
    mime_type, _encoding = mimetypes.guess_type(filepath)
    if mime_type is None:
        mime_type = 'application/octet-stream'

    created = datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
    modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

    def format_size_value(size):
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        value = float(size)
        unit_index = 0
        while value >= 1024 and unit_index < len(units) - 1:
            value /= 1024
            unit_index += 1
        if unit_index == 0:
            return f'{int(value)} {units[unit_index]}'
        return f'{value:.2f} {units[unit_index]}'

    hex_header = ''
    md5_hash = hashlib.md5()
    sha256_hash = hashlib.sha256()
    byte_frequencies = [0] * 256
    total_bytes = 0
    try:
        with open(filepath, 'rb') as handle:
            header = handle.read(16)
            hex_header = ' '.join(f'{header_byte:02x}' for header_byte in header)
            md5_hash.update(header)
            sha256_hash.update(header)
            total_bytes += len(header)
            for header_byte in header:
                byte_frequencies[header_byte] += 1

            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                md5_hash.update(chunk)
                sha256_hash.update(chunk)
                total_bytes += len(chunk)
                for chunk_byte in chunk:
                    byte_frequencies[chunk_byte] += 1
    except Exception:
        hex_header = '无法读取文件十六进制数据'

    entropy = 0.0
    if total_bytes:
        for count in byte_frequencies:
            if count:
                probability = count / total_bytes
                entropy -= probability * math.log2(probability)

    analysis = {
        'filename': safe_name,
        'size_bytes': size_bytes,
        'size': format_size_value(size_bytes),
        'mime_type': mime_type,
        'mime': mime_type,
        'type': os.path.splitext(safe_name)[1].lstrip('.').upper() or '未知',
        'created_at': created,
        'modified_at': modified,
        'hex_header_preview': hex_header.upper(),
        'hex_header': hex_header.upper(),
        'md5': md5_hash.hexdigest().upper() if total_bytes else '无法计算',
        'sha256': sha256_hash.hexdigest().upper() if total_bytes else '无法计算',
        'entropy': f'{entropy:.4f} bits/byte' if total_bytes else '无法计算',
    }
    return jsonify({'success': True, 'analysis': analysis, **analysis})
