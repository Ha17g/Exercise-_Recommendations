import json
import math
from flask import Blueprint, request, jsonify, g, session
from auth import require_auth, require_role, get_current_user
from models import UserModel, QuestionModel, AuditLogModel, UserRecordModel

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


@admin_bp.before_request
def before_request():
    if request.endpoint and request.endpoint.startswith('admin.'):
        user = get_current_user()
        if not user:
            if 'username' in session and 'user_id' in session:
                g.current_user = {
                    'user_id': session.get('user_id'),
                    'username': session.get('username'),
                    'role': session.get('role', 'user')
                }
                user = g.current_user
        if not user or user.get('role') != 'admin':
            return jsonify({'error': '权限不足', 'code': 403}), 403


@admin_bp.route('/users', methods=['GET'])
@require_auth
@require_role('admin')
def list_users():
    page = max(1, request.args.get('page', 1, type=int))
    page_size = min(100, max(1, request.args.get('page_size', 20, type=int)))
    search = request.args.get('search', '').strip()
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'

    total = UserModel.count(search=search, include_deleted=include_deleted)
    skip = (page - 1) * page_size
    users = UserModel.get_all(skip=skip, limit=page_size, search=search, include_deleted=include_deleted)

    for u in users:
        u.pop('password', None)
        if 'is_deleted' in u and isinstance(u['is_deleted'], (int, bool)):
            u['is_deleted'] = bool(u['is_deleted']) if not isinstance(u['is_deleted'], bool) else u['is_deleted']

    return jsonify({
        'code': 200,
        'data': {
            'items': users,
            'total': total,
            'page': page,
            'page_size': page_size,
            'pages': math.ceil(total / page_size) if total > 0 else 0
        }
    })


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@require_auth
@require_role('admin')
def get_user(user_id):
    user = UserModel.find_by_id(user_id)
    if not user:
        return jsonify({'error': '用户不存在', 'code': 404}), 404
    user.pop('password', None)
    return jsonify({'code': 200, 'data': user})


@admin_bp.route('/users', methods=['POST'])
@require_auth
@require_role('admin')
def create_user():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'user').strip()

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空', 'code': 400}), 400
    if role not in ('admin', 'user'):
        return jsonify({'error': '无效的角色', 'code': 400}), 400

    existing = UserModel.find_by_username(username)
    if existing:
        return jsonify({'error': '用户名已存在', 'code': 409}), 409

    try:
        user_id = UserModel.create(username, password, role)
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 409}), 409
    except Exception as e:
        return jsonify({'error': '创建用户失败: ' + str(e), 'code': 500}), 500
    AuditLogModel.log(
        user_id=g.current_user['user_id'],
        action='CREATE_USER',
        target_type='user',
        target_id=user_id,
        details={'username': username, 'role': role},
        ip_address=request.remote_addr
    )

    return jsonify({'code': 201, 'data': {'id': user_id, 'username': username, 'role': role}}), 201


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@require_auth
@require_role('admin')
def update_user(user_id):
    data = request.json
    current_user = g.current_user

    if user_id == current_user['user_id'] and data.get('role') and data['role'] != current_user['role']:
        return jsonify({'error': '不能修改自己的角色', 'code': 403}), 403

    update_fields = {}
    if 'password' in data and data['password']:
        update_fields['password'] = data['password'].strip()
    if 'role' in data and data['role'] in ('admin', 'user'):
        update_fields['role'] = data['role']

    if not update_fields:
        return jsonify({'error': '没有要更新的字段', 'code': 400}), 400

    success = UserModel.update(user_id, **update_fields)
    if not success:
        return jsonify({'error': '用户不存在', 'code': 404}), 404

    AuditLogModel.log(
        user_id=current_user['user_id'],
        action='UPDATE_USER',
        target_type='user',
        target_id=user_id,
        details=update_fields,
        ip_address=request.remote_addr
    )

    return jsonify({'code': 200, 'message': '更新成功'})


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@require_auth
@require_role('admin')
def delete_user(user_id):
    current_user = g.current_user
    if user_id == current_user['user_id']:
        return jsonify({'error': '不能删除自己', 'code': 403}), 403

    success = UserModel.hard_delete(user_id)
    if not success:
        return jsonify({'error': '用户不存在', 'code': 404}), 404

    AuditLogModel.log(
        user_id=current_user['user_id'],
        action='DELETE_USER',
        target_type='user',
        target_id=user_id,
        details={'hard_delete': True},
        ip_address=request.remote_addr
    )

    return jsonify({'code': 200, 'message': '删除成功'})


@admin_bp.route('/users/batch', methods=['POST'])
@require_auth
@require_role('admin')
def batch_create_users():
    data = request.json
    users_data = data.get('users', [])
    if not users_data:
        return jsonify({'error': '没有要创建的用户数据', 'code': 400}), 400

    results = []
    for u in users_data:
        username = u.get('username', '').strip()
        password = u.get('password', '').strip()
        role = u.get('role', 'user').strip()
        if not username or not password:
            results.append({'username': username, 'success': False, 'error': '用户名或密码为空'})
            continue
        existing = UserModel.find_by_username(username)
        if existing:
            results.append({'username': username, 'success': False, 'error': '用户名已存在'})
            continue
        try:
            user_id = UserModel.create(username, password, role)
            results.append({'username': username, 'success': True, 'id': user_id})
        except Exception as e:
            results.append({'username': username, 'success': False, 'error': str(e)})

    AuditLogModel.log(
        user_id=g.current_user['user_id'],
        action='BATCH_CREATE_USERS',
        target_type='user',
        target_id=None,
        details={'batch_size': len(users_data), 'results': results},
        ip_address=request.remote_addr
    )

    return jsonify({'code': 201, 'data': results})


@admin_bp.route('/users/batch', methods=['DELETE'])
@require_auth
@require_role('admin')
def batch_delete_users():
    data = request.json
    user_ids = data.get('user_ids', [])
    if not user_ids:
        return jsonify({'error': '没有要删除的用户ID', 'code': 400}), 400

    current_user_id = g.current_user['user_id']
    results = []
    for uid in user_ids:
        if uid == current_user_id:
            results.append({'id': uid, 'success': False, 'error': '不能删除自己'})
            continue
        success = UserModel.soft_delete(uid)
        results.append({'id': uid, 'success': success, 'error': None if success else '用户不存在'})

    AuditLogModel.log(
        user_id=current_user_id,
        action='BATCH_DELETE_USERS',
        target_type='user',
        target_id=None,
        details={'user_ids': user_ids, 'results': results},
        ip_address=request.remote_addr
    )

    return jsonify({'code': 200, 'data': results})


@admin_bp.route('/questions', methods=['GET'])
@require_auth
@require_role('admin')
def list_questions():
    page = max(1, request.args.get('page', 1, type=int))
    page_size = min(100, max(1, request.args.get('page_size', 20, type=int)))
    subject = request.args.get('subject', '全部')
    grade = request.args.get('grade', '全部')
    difficulty = request.args.get('difficulty', '全部')
    search = request.args.get('search', '').strip()
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'

    total = QuestionModel.count(
        subject=subject, grade=grade, difficulty=difficulty,
        search=search, include_deleted=include_deleted
    )
    skip = (page - 1) * page_size
    questions = QuestionModel.get_all(
        skip=skip, limit=page_size,
        subject=subject, grade=grade, difficulty=difficulty,
        search=search, include_deleted=include_deleted
    )

    return jsonify({
        'code': 200,
        'data': {
            'items': questions,
            'total': total,
            'page': page,
            'page_size': page_size,
            'pages': math.ceil(total / page_size) if total > 0 else 0
        }
    })


@admin_bp.route('/questions/<int:q_id>', methods=['GET'])
@require_auth
@require_role('admin')
def get_question(q_id):
    question = QuestionModel.find_by_id(q_id)
    if not question:
        return jsonify({'error': '题目不存在', 'code': 404}), 404
    return jsonify({'code': 200, 'data': question})


@admin_bp.route('/questions', methods=['POST'])
@require_auth
@require_role('admin')
def create_question():
    data = request.json
    question_text = data.get('question', '').strip()
    options = data.get('options', [])
    answer = data.get('answer', '').strip()
    knowledge = data.get('knowledge')
    difficulty = data.get('difficulty')
    subject = data.get('subject')
    grade = data.get('grade')

    if not question_text or not answer:
        return jsonify({'error': '题目和答案不能为空', 'code': 400}), 400

    q_id = QuestionModel.create(
        question=question_text, options=options, answer=answer,
        knowledge=knowledge, difficulty=difficulty, subject=subject, grade=grade,
        created_by=g.current_user['user_id']
    )

    AuditLogModel.log(
        user_id=g.current_user['user_id'],
        action='CREATE_QUESTION',
        target_type='question',
        target_id=q_id,
        details={'subject': subject, 'grade': grade, 'difficulty': difficulty},
        ip_address=request.remote_addr
    )

    return jsonify({'code': 201, 'data': {'id': q_id}}), 201


@admin_bp.route('/questions/<int:q_id>', methods=['PUT'])
@require_auth
@require_role('admin')
def update_question(q_id):
    data = request.json
    update_fields = {k: v for k, v in data.items()
                     if k in ('question', 'options', 'answer', 'knowledge', 'difficulty', 'subject', 'grade')}
    if not update_fields:
        return jsonify({'error': '没有要更新的字段', 'code': 400}), 400

    success = QuestionModel.update(q_id, **update_fields)
    if not success:
        return jsonify({'error': '题目不存在', 'code': 404}), 404

    AuditLogModel.log(
        user_id=g.current_user['user_id'],
        action='UPDATE_QUESTION',
        target_type='question',
        target_id=q_id,
        details=update_fields,
        ip_address=request.remote_addr
    )

    return jsonify({'code': 200, 'message': '更新成功'})


@admin_bp.route('/questions/<int:q_id>', methods=['DELETE'])
@require_auth
@require_role('admin')
def delete_question(q_id):
    success = QuestionModel.soft_delete(q_id)
    if not success:
        return jsonify({'error': '题目不存在', 'code': 404}), 404

    AuditLogModel.log(
        user_id=g.current_user['user_id'],
        action='DELETE_QUESTION',
        target_type='question',
        target_id=q_id,
        details={'soft_delete': True},
        ip_address=request.remote_addr
    )

    return jsonify({'code': 200, 'message': '删除成功'})


@admin_bp.route('/questions/batch', methods=['POST'])
@require_auth
@require_role('admin')
def batch_create_questions():
    data = request.json
    questions_data = data.get('questions', [])
    if not questions_data:
        return jsonify({'error': '没有要创建的题目数据', 'code': 400}), 400

    results = []
    for q in questions_data:
        try:
            q_id = QuestionModel.create(
                question=q.get('question', ''),
                options=q.get('options', []),
                answer=q.get('answer', ''),
                knowledge=q.get('knowledge'),
                difficulty=q.get('difficulty'),
                subject=q.get('subject'),
                grade=q.get('grade'),
                created_by=g.current_user['user_id']
            )
            results.append({'question': q.get('question', '')[:30], 'success': True, 'id': q_id})
        except Exception as e:
            results.append({'question': q.get('question', '')[:30], 'success': False, 'error': str(e)})

    AuditLogModel.log(
        user_id=g.current_user['user_id'],
        action='BATCH_CREATE_QUESTIONS',
        target_type='question',
        target_id=None,
        details={'batch_size': len(questions_data), 'results': results},
        ip_address=request.remote_addr
    )

    return jsonify({'code': 201, 'data': results})


@admin_bp.route('/questions/batch', methods=['DELETE'])
@require_auth
@require_role('admin')
def batch_delete_questions():
    data = request.json
    q_ids = data.get('question_ids', [])
    if not q_ids:
        return jsonify({'error': '没有要删除的题目ID', 'code': 400}), 400

    results = []
    for qid in q_ids:
        success = QuestionModel.soft_delete(qid)
        results.append({'id': qid, 'success': success, 'error': None if success else '题目不存在'})

    AuditLogModel.log(
        user_id=g.current_user['user_id'],
        action='BATCH_DELETE_QUESTIONS',
        target_type='question',
        target_id=None,
        details={'question_ids': q_ids, 'results': results},
        ip_address=request.remote_addr
    )

    return jsonify({'code': 200, 'data': results})


@admin_bp.route('/audit_logs', methods=['GET'])
@require_auth
@require_role('admin')
def list_audit_logs():
    page = max(1, request.args.get('page', 1, type=int))
    page_size = min(100, max(1, request.args.get('page_size', 50, type=int)))
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action')

    skip = (page - 1) * page_size
    logs = AuditLogModel.get_logs(skip=skip, limit=page_size, user_id=user_id, action=action)

    return jsonify({
        'code': 200,
        'data': {
            'items': logs,
            'page': page,
            'page_size': page_size
        }
    })


@admin_bp.route('/stats', methods=['GET'])
@require_auth
@require_role('admin')
def get_stats():
    total_users = UserModel.count()
    total_questions = QuestionModel.count()
    total_records = 0
    with __import__('db_config').db_config.get_connection() as conn:
        cursor = conn.cursor()
        if __import__('db_config').db_config.db_type == 'sqlite':
            cursor.execute("SELECT COUNT(*) as cnt FROM user_records")
        else:
            cursor.execute("SELECT COUNT(*) as cnt FROM user_records")
        total_records = dict(cursor.fetchone())['cnt']

    return jsonify({
        'code': 200,
        'data': {
            'total_users': total_users,
            'total_questions': total_questions,
            'total_records': total_records
        }
    })
