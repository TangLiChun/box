import base64
import hashlib
import hmac
import json

from flask import request


def get_onlyoffice_callback_secret(get_setting, set_setting):
    secret = get_setting('onlyoffice_callback_secret')
    if secret:
        return secret

    secret = __import__('secrets').token_urlsafe(32)
    set_setting('onlyoffice_callback_secret', secret)
    return secret


def generate_onlyoffice_callback_token(filename, normalize_managed_filename, get_onlyoffice_callback_secret_func):
    safe_name = normalize_managed_filename(filename)
    if not safe_name:
        return None
    return hmac.new(
        get_onlyoffice_callback_secret_func().encode('utf-8'),
        safe_name.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def is_valid_onlyoffice_callback_token(filename, token, generate_onlyoffice_callback_token_func):
    expected_token = generate_onlyoffice_callback_token_func(filename)
    return bool(token and expected_token) and hmac.compare_digest(token, expected_token)


def generate_onlyoffice_download_token(filename, normalize_managed_filename, get_onlyoffice_callback_secret_func):
    safe_name = normalize_managed_filename(filename)
    if not safe_name:
        return None
    token_payload = f"download:{safe_name}"
    return hmac.new(
        get_onlyoffice_callback_secret_func().encode('utf-8'),
        token_payload.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def is_valid_onlyoffice_download_token(filename, token, generate_onlyoffice_download_token_func):
    expected_token = generate_onlyoffice_download_token_func(filename)
    return bool(token and expected_token) and hmac.compare_digest(token, expected_token)


def get_onlyoffice_jwt_secret(get_setting):
    secret = get_setting('onlyoffice_jwt_secret', '')
    return secret.strip() if secret else ''


def encode_onlyoffice_jwt_segment(payload):
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def decode_onlyoffice_jwt_segment(segment):
    padded = segment + ('=' * (-len(segment) % 4))
    decoded = base64.urlsafe_b64decode(padded.encode('ascii'))
    return json.loads(decoded.decode('utf-8'))


def generate_onlyoffice_jwt(payload, get_onlyoffice_jwt_secret_func, secret=None):
    if not isinstance(payload, dict):
        return None

    signing_secret = secret if secret is not None else get_onlyoffice_jwt_secret_func()
    if not signing_secret:
        return None

    header_segment = encode_onlyoffice_jwt_segment({'alg': 'HS256', 'typ': 'JWT'})
    payload_segment = encode_onlyoffice_jwt_segment(payload)
    signing_input = f'{header_segment}.{payload_segment}'.encode('ascii')
    signature = hmac.new(signing_secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
    signature_segment = base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')
    return f'{header_segment}.{payload_segment}.{signature_segment}'


def decode_onlyoffice_jwt(token, get_onlyoffice_jwt_secret_func, secret=None):
    if not token or token.count('.') != 2:
        return None

    signing_secret = secret if secret is not None else get_onlyoffice_jwt_secret_func()
    if not signing_secret:
        return None

    try:
        header_segment, payload_segment, signature_segment = token.split('.')
        header = decode_onlyoffice_jwt_segment(header_segment)
        if not isinstance(header, dict) or header.get('alg') != 'HS256':
            return None

        signing_input = f'{header_segment}.{payload_segment}'.encode('ascii')
        expected_signature = base64.urlsafe_b64encode(
            hmac.new(signing_secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
        ).rstrip(b'=').decode('ascii')
        if not hmac.compare_digest(expected_signature, signature_segment):
            return None

        payload = decode_onlyoffice_jwt_segment(payload_segment)
    except (ValueError, TypeError, json.JSONDecodeError, base64.binascii.Error):
        return None

    return payload if isinstance(payload, dict) else None


def extract_onlyoffice_jwt_token(data=None):
    authorization = request.headers.get('Authorization', '').strip()
    if authorization:
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() in ('bearer', 'jwt') and token.strip():
            return token.strip()

    if isinstance(data, dict):
        token = data.get('token')
        if isinstance(token, str) and token.strip():
            return token.strip()

    return None
