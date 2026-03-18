import hashlib
import ipaddress
import os
import socket
import tempfile
import urllib.request
from urllib.parse import urlparse, quote as url_quote

from flask import flash, jsonify, redirect, render_template, request, session, url_for


def handle_onlyoffice_editor(
    filename,
    is_authenticated,
    get_setting,
    resolve_item_path,
    onlyoffice_formats,
    generate_onlyoffice_download_token,
    generate_onlyoffice_callback_token,
    get_onlyoffice_jwt_secret,
    generate_onlyoffice_jwt,
):
    if not is_authenticated():
        return redirect(url_for('main.login'))

    onlyoffice_url = get_setting('onlyoffice_url')
    if not onlyoffice_url:
        flash('ONLYOFFICE 未配置')
        return redirect(url_for('main.index'))

    if not onlyoffice_url.endswith('/'):
        onlyoffice_url += '/'

    safe_name, filepath = resolve_item_path('file', filename)
    if not filepath:
        flash('文件不存在')
        return redirect(url_for('main.index'))

    file_ext = os.path.splitext(safe_name)[1].lower()
    document_type = onlyoffice_formats.get(file_ext)
    if not document_type:
        flash(f'不支持编辑 {file_ext} 格式')
        return redirect(url_for('main.index'))

    stat = os.stat(filepath)
    key_seed = f"{safe_name}:{int(stat.st_mtime)}"
    doc_key = f"doc_{hashlib.sha256(key_seed.encode('utf-8')).hexdigest()[:32]}"

    callback_base = get_setting('onlyoffice_callback_base', '').rstrip('/')
    if callback_base:
        dl_token = generate_onlyoffice_download_token(safe_name)
        cb_token = generate_onlyoffice_callback_token(safe_name)
        encoded_name = url_quote(safe_name, safe='')
        document_url = f"{callback_base}/download/{encoded_name}?token={dl_token}"
        callback_url = f"{callback_base}/callback/{encoded_name}?token={cb_token}"
    else:
        document_url = url_for(
            'main.download_file',
            filename=safe_name,
            token=generate_onlyoffice_download_token(safe_name),
            _external=True,
        )
        callback_url = url_for(
            'main.onlyoffice_callback',
            filename=safe_name,
            token=generate_onlyoffice_callback_token(safe_name),
            _external=True,
        )

    config = {
        'document': {
            'fileType': file_ext.replace('.', ''),
            'key': doc_key,
            'title': safe_name,
            'url': document_url,
        },
        'documentType': document_type,
        'editorConfig': {
            'callbackUrl': callback_url,
            'user': {
                'id': str(session.get('user_id')),
                'name': session.get('username'),
            },
            'lang': 'zh-CN',
            'customization': {
                'forcesave': True,
            },
        },
    }

    onlyoffice_jwt_secret = get_onlyoffice_jwt_secret()
    if onlyoffice_jwt_secret:
        config['token'] = generate_onlyoffice_jwt(config, onlyoffice_jwt_secret)

    return render_template(
        'editor_onlyoffice.html',
        config=config,
        onlyoffice_url=onlyoffice_url,
        filename=safe_name,
    )


def handle_onlyoffice_callback(
    filename,
    normalize_managed_filename,
    is_valid_onlyoffice_callback_token,
    get_onlyoffice_jwt_secret,
    extract_onlyoffice_jwt_token,
    decode_onlyoffice_jwt,
    resolve_item_path,
    get_setting,
    app_logger,
):
    safe_name = normalize_managed_filename(filename)
    if not safe_name:
        return jsonify({"error": 1, "message": "Invalid filename"}), 400

    if not is_valid_onlyoffice_callback_token(safe_name, request.args.get('token')):
        return jsonify({"error": 1, "message": "Forbidden"}), 403

    if not request.is_json:
        return jsonify({"error": 1, "message": "Expected JSON body"}), 400

    data = request.get_json(silent=True) or {}
    onlyoffice_jwt_secret = get_onlyoffice_jwt_secret()
    if onlyoffice_jwt_secret:
        onlyoffice_jwt = extract_onlyoffice_jwt_token(data)
        signed_payload = decode_onlyoffice_jwt(onlyoffice_jwt, onlyoffice_jwt_secret)
        if not signed_payload:
            return jsonify({"error": 1, "message": "Invalid ONLYOFFICE token"}), 403

        signed_status = signed_payload.get('status')
        if signed_status is not None and signed_status != data.get('status'):
            return jsonify({"error": 1, "message": "ONLYOFFICE token mismatch"}), 403

        signed_url = signed_payload.get('url')
        if signed_url is not None and data.get('url') and signed_url != data.get('url'):
            return jsonify({"error": 1, "message": "ONLYOFFICE token mismatch"}), 403

    if 'status' not in data:
        return jsonify({"error": 1, "message": "Missing status"}), 400

    status = data.get('status')
    if status in [2, 6]:
        _, filepath = resolve_item_path('file', safe_name)
        if not filepath:
            return jsonify({"error": 1, "message": "Target file not found"}), 404

        download_url = data.get('url')
        if not download_url:
            return jsonify({"error": 1, "message": "Missing download URL"}), 400

        parsed_url = urlparse(download_url)
        if parsed_url.scheme not in ('http', 'https'):
            return jsonify({"error": 1, "message": "Invalid download URL"}), 400

        trusted_hostnames = set()
        configured_oo_url = get_setting('onlyoffice_url', '')
        if configured_oo_url:
            parsed_oo = urlparse(configured_oo_url)
            if parsed_oo.hostname:
                trusted_hostnames.add(parsed_oo.hostname.lower())

        try:
            hostname = parsed_url.hostname
            if not hostname:
                return jsonify({"error": 1, "message": "Invalid URL hostname"})
            is_trusted = hostname.lower() in trusted_hostnames
            if not is_trusted:
                resolved_ips = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
                for ip in resolved_ips:
                    parsed_ip = ipaddress.ip_address(ip)
                    if (
                        parsed_ip.is_private or
                        parsed_ip.is_loopback or
                        parsed_ip.is_link_local or
                        parsed_ip.is_multicast or
                        parsed_ip.is_reserved or
                        parsed_ip.is_unspecified
                    ):
                        app_logger.warning(f"Blocked potential SSRF callback to {download_url} (IP: {ip})")
                        return jsonify({"error": 1, "message": "Invalid download URL"})
        except Exception as exc:
            app_logger.error(f"SSRF validation error: {exc}")
            return jsonify({"error": 1}), 502

        try:
            with urllib.request.urlopen(download_url, timeout=30) as response:
                if response.status != 200:
                    return jsonify({"error": 1, "message": "Download failed"}), 502

                payload = response.read()
                headers = getattr(response, 'headers', {})
                content_type = (headers.get('Content-Type') if hasattr(headers, 'get') else '') or ''
                content_type = str(content_type).lower()
                file_ext = os.path.splitext(safe_name)[1].lower()
                if (
                    'text/html' in content_type or
                    payload.lstrip().startswith(b'<!DOCTYPE html') or
                    payload.lstrip().startswith(b'<html')
                ):
                    app_logger.error(
                        "ONLYOFFICE callback returned HTML instead of file for %s, URL=%s, content_type=%s",
                        safe_name,
                        download_url,
                        content_type,
                    )
                    return jsonify({"error": 1, "message": "Invalid callback payload"}), 502

                if file_ext in {'.docx', '.xlsx', '.pptx'} and not payload.startswith(b'PK'):
                    app_logger.error(
                        "ONLYOFFICE callback returned unexpected binary signature for %s, URL=%s, content_type=%s",
                        safe_name,
                        download_url,
                        content_type,
                    )
                    return jsonify({"error": 1, "message": "Invalid callback payload"}), 502

                dir_name = os.path.dirname(filepath)
                fd, tmp_path = tempfile.mkstemp(dir=dir_name)
                fd_closed = False
                try:
                    os.write(fd, payload)
                    os.close(fd)
                    fd_closed = True
                    os.replace(tmp_path, filepath)
                except Exception:
                    if not fd_closed:
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    raise
                return jsonify({"error": 0})
        except Exception as exc:
            app_logger.error(f"ONLYOFFICE callback save error: {str(exc)}")
            return jsonify({"error": 1}), 502

    return jsonify({"error": 0})
