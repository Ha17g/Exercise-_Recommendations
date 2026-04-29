import os
import jwt
import datetime
from functools import wraps
from flask import request, jsonify, g

SECRET_KEY = os.getenv('JWT_SECRET', 'exam-recommend-system-secret-key-2024')
ALGORITHM = 'HS256'
TOKEN_EXPIRE_HOURS = int(os.getenv('JWT_EXPIRE_HOURS', '24'))


def generate_token(user_id, username, role):
    payload = {
        'user_id': user_id,
        'username': username,
        'role': role,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRE_HOURS),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_token_from_header():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import session
        token = get_token_from_header()
        if not token:
            if 'username' not in session:
                if request.is_json:
                    return jsonify({'error': '未登录', 'code': 401}), 401
                return redirect(url_for('login'))
        else:
            payload = decode_token(token)
            if not payload:
                if request.is_json:
                    return jsonify({'error': '无效或已过期的令牌', 'code': 401}), 401
                session.clear()
                return redirect(url_for('login'))

            g.current_user = {
                'user_id': payload['user_id'],
                'username': payload['username'],
                'role': payload['role']
            }

        if not hasattr(g, 'current_user') or not g.current_user:
            if 'username' in session:
                g.current_user = {
                    'user_id': session.get('user_id'),
                    'username': session.get('username'),
                    'role': session.get('role', 'user')
                }

        return f(*args, **kwargs)
    return decorated


def require_role(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from flask import session
            if not hasattr(g, 'current_user') or not g.current_user:
                token = get_token_from_header()
                if token:
                    payload = decode_token(token)
                    if payload:
                        g.current_user = {
                            'user_id': payload['user_id'],
                            'username': payload['username'],
                            'role': payload['role']
                        }
                if not hasattr(g, 'current_user') or not g.current_user:
                    if 'username' in session:
                        g.current_user = {
                            'user_id': session.get('user_id'),
                            'username': session.get('username'),
                            'role': session.get('role', 'user')
                        }

            if not hasattr(g, 'current_user') or not g.current_user:
                if request.is_json:
                    return jsonify({'error': '未登录', 'code': 401}), 401
                return redirect(url_for('login'))

            if g.current_user.get('role') not in allowed_roles:
                if request.is_json:
                    return jsonify({'error': '权限不足，需要以下角色: ' + ', '.join(allowed_roles), 'code': 403}), 403
                from flask import abort
                abort(403)

            return f(*args, **kwargs)
        return decorated
    return decorator


def get_current_user():
    from flask import session
    if hasattr(g, 'current_user') and g.current_user:
        return g.current_user
    token = get_token_from_header()
    if token:
        payload = decode_token(token)
        if payload:
            g.current_user = {
                'user_id': payload['user_id'],
                'username': payload['username'],
                'role': payload['role']
            }
            return g.current_user
    if 'username' in session and 'user_id' in session:
        g.current_user = {
            'user_id': session.get('user_id'),
            'username': session.get('username'),
            'role': session.get('role', 'user')
        }
        return g.current_user
    return None
