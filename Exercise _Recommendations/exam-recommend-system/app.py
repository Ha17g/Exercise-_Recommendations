from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
import json
import os
import datetime
import random
import math

from db_config import db_config
from models import UserModel, QuestionModel, UserRecordModel
from auth import generate_token, get_current_user, require_auth, require_role
from admin_routes import admin_bp
from rag.recommend import get_recommendations, analyze_user_status
from rag.vector_db import get_vector_db
from rag.ai_recommend import analyze_user_weakness, generate_recommendation_reason as generate_ai_reason
from rag.question_generator import generate_new_questions
from rag.question_selector import select_questions_from_db
from rag.ai_chat import get_ai_response

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'exam-recommend-system-secret-key-2024')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

app.register_blueprint(admin_bp)


def init_db():
    try:
        db_config.init_database()
    except Exception as e:
        print(f"数据库初始化失败: {e}")


@app.before_request
def before_request():
    if request.endpoint and request.endpoint.startswith('admin.'):
        return
    if request.endpoint and request.endpoint in ('login', 'register', 'static'):
        return
    if request.path.startswith('/api/'):
        return


def get_session_user():
    username = session.get('username')
    if not username:
        return None
    user = UserModel.find_by_username(username)
    return user


def get_db_questions():
    questions = QuestionModel.get_all(limit=10000)
    return questions


def get_db_user_data(username):
    user = UserModel.find_by_username(username)
    if not user:
        return None
    records = UserRecordModel.get_user_records(user['id'], limit=10000)
    stats = UserRecordModel.get_user_stats(user['id'])
    return {
        'records': records,
        'stats': stats,
        'user': user
    }


@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_data = get_db_user_data(username)
    if not user_data:
        session.clear()
        return redirect(url_for('login'))

    records = user_data['records']
    status = analyze_user_status(records)
    stats = user_data['stats']

    status['total_questions'] = stats['total_count']
    status['accuracy'] = stats['accuracy']

    return render_template('index.html', user=username, status=status)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            return render_template('login.html', error="用户名和密码不能为空")

        user = UserModel.find_by_username(username)
        if not user or user.get('password') != password:
            return render_template('login.html', error="用户名或密码错误", username=username)

        session.clear()
        session['username'] = username
        session['user_id'] = user['id']
        session['role'] = user.get('role', 'user')

        if request.args.get('format') == 'json' or request.is_json:
            token = generate_token(user['id'], username, user.get('role', 'user'))
            return jsonify({'code': 200, 'token': token, 'username': username, 'role': user.get('role', 'user')})

        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not username or not password:
            return render_template('register.html', error="用户名和密码不能为空")
        if password != confirm_password:
            return render_template('register.html', error="两次密码输入不一致")
        if len(password) < 6:
            return render_template('register.html', error="密码长度至少6位")

        existing = UserModel.find_by_username(username)
        if existing:
            return render_template('register.html', error="用户名已存在")

        user_id = UserModel.create(username, password, 'user')
        session.clear()
        session['username'] = username
        session['user_id'] = user_id
        session['role'] = 'user'

        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/history')
def history():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_data = get_db_user_data(username)
    if not user_data:
        session.clear()
        return redirect(url_for('login'))

    subject = request.args.get('subject', '全部')
    grade = request.args.get('grade', '全部')
    difficulty = request.args.get('difficulty', '全部')
    search = request.args.get('search', '')

    records = user_data['records']
    history_list = []
    for rec in reversed(records):
        if subject != '全部' and rec.get('subject') != subject:
            continue
        if grade != '全部' and rec.get('grade') != grade:
            continue
        if difficulty != '全部' and rec.get('difficulty') != difficulty:
            continue
        if search:
            q_id_str = str(rec.get('question_id', ''))
            q_text = rec.get('question', '')
            if search not in q_id_str and search not in q_text:
                continue
        item = {
            'id': rec.get('question_id'),
            'question': rec.get('question'),
            'options': rec.get('options', []),
            'answer': rec.get('answer'),
            'knowledge': rec.get('knowledge'),
            'difficulty': rec.get('difficulty'),
            'subject': rec.get('subject'),
            'grade': rec.get('grade'),
            'user_correct': rec.get('correct', False),
            'user_time': rec.get('time')
        }
        history_list.append(item)

    return render_template('history.html',
                          questions=history_list,
                          subject=subject,
                          grade=grade,
                          difficulty=difficulty,
                          search=search)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/question/<int:q_id>')
def question(q_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    q = QuestionModel.find_by_id(q_id)
    if not q:
        return "题目不存在", 404

    from_page = request.args.get('from', 'recommend')
    return render_template('question.html', question=q, from_page=from_page)


@app.route('/submit_answer', methods=['POST'])
def submit_answer():
    if 'username' not in session:
        return jsonify({"error": "未登录"}), 401

    data = request.json
    q_id = data.get('question_id')
    user_answer = data.get('answer')

    q = QuestionModel.find_by_id(q_id)
    if not q:
        return jsonify({"error": "题目不存在"}), 404

    is_correct = (user_answer == q['answer'])
    user_id = session.get('user_id')

    if user_id:
        UserRecordModel.add_record(user_id, q_id, is_correct)

    return jsonify({
        "correct": is_correct,
        "correct_answer": q['answer'],
        "explanation": f"正确答案是：{q['answer']}。该题考察知识点：{q.get('knowledge', '未知')}。"
    })


@app.route('/recommend', methods=['GET', 'POST'])
def recommend():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_data = get_db_user_data(username)
    if not user_data:
        session.clear()
        return redirect(url_for('login'))

    force_refresh = request.args.get('refresh') == 'true'
    selected_subject = request.args.get('subject', '全部')
    selected_grade = request.args.get('grade', '全部')

    if not force_refresh:
        cached = session.get('recommend_cache')
        if cached and cached.get('questions'):
            return render_template('recommend.html',
                                  questions=cached['questions'],
                                  reason=cached['reason'],
                                  base_reason=cached['base_reason'],
                                  current_subject=cached['subject'],
                                  current_grade=cached['grade'])

        return render_template('recommend.html',
                              questions=[],
                              reason='请选择学科和年级，系统将根据您的学习情况智能推荐适合的练习题目。',
                              base_reason='',
                              current_subject=selected_subject,
                              current_grade=selected_grade)

    records = user_data['records']
    ai_analysis, weak_knowledge = analyze_user_weakness(records)

    ai_questions = []
    target_k = "综合知识"

    if selected_subject != '全部':
        target_k = f"{selected_subject}基础与核心知识"
    elif weak_knowledge:
        target_k = random.choice(weak_knowledge)

    try:
        new_qs = generate_new_questions(
            knowledge=target_k,
            difficulty="中等",
            subject=selected_subject if selected_subject != '全部' else '计算机',
            grade=selected_grade if selected_grade != '全部' else '大学',
            count=2
        )
        if new_qs:
            for q in new_qs:
                if 'id' not in q:
                    q_id = QuestionModel.create(
                        question=q['question'],
                        options=q.get('options', []),
                        answer=q['answer'],
                        knowledge=q.get('knowledge'),
                        difficulty=q.get('difficulty'),
                        subject=q.get('subject'),
                        grade=q.get('grade'),
                        created_by=session.get('user_id')
                    )
                    q['id'] = q_id
                q.setdefault('is_ai_generated', True)
            ai_questions.extend(new_qs)
            print(f"AI成功生成 {len(new_qs)} 道新题目")
    except Exception as e:
        print(f"AI生成题目出错: {e}")

    needed_count = 6 - len(ai_questions)
    exclude_ids = {q['id'] for q in ai_questions if 'id' in q}

    done_ids = {r.get('question_id') for r in records if r.get('question_id')}
    exclude_ids.update(done_ids)

    vector_questions = []
    if needed_count > 0:
        try:
            query_parts = []
            if selected_subject != '全部':
                query_parts.append(selected_subject)
            if selected_grade != '全部':
                query_parts.append(selected_grade)
            if weak_knowledge:
                query_parts.extend(weak_knowledge[:5])
            else:
                query_parts.append(target_k)
            query_text = " ".join([p for p in query_parts if p])

            vector_db = get_vector_db()
            candidates = vector_db.search(query_text, k=max(needed_count * 8, 20))
            for q in candidates:
                q_id = q.get('id')
                if not q_id:
                    continue
                if q_id in exclude_ids:
                    continue
                if selected_subject != '全部' and q.get('subject') != selected_subject:
                    continue
                if selected_grade != '全部' and q.get('grade') != selected_grade:
                    continue
                vector_questions.append(q)
                exclude_ids.add(q_id)
                if len(vector_questions) >= needed_count:
                    break
        except Exception as e:
            print(f"向量检索选题出错: {e}")

    remaining_count = needed_count - len(vector_questions)
    db_questions = []
    if remaining_count > 0:
        db_questions = select_questions_from_db(
            k=remaining_count,
            subject=selected_subject if selected_subject != '全部' else None,
            grade=selected_grade if selected_grade != '全部' else None,
            exclude_ids=exclude_ids
        )

    recommended_questions = ai_questions + vector_questions + db_questions
    ai_reason = generate_ai_reason(recommended_questions, ai_analysis)

    session['recommend_cache'] = {
        'questions': recommended_questions,
        'reason': ai_reason,
        'base_reason': ai_analysis,
        'subject': selected_subject,
        'grade': selected_grade
    }

    return render_template('recommend.html',
                          questions=recommended_questions,
                          reason=ai_reason,
                          base_reason=ai_analysis,
                          current_subject=selected_subject,
                          current_grade=selected_grade)


@app.route('/question_bank')
def question_bank():
    if 'username' not in session:
        return redirect(url_for('login'))

    subject = request.args.get('subject', '全部')
    grade = request.args.get('grade', '全部')
    difficulty = request.args.get('difficulty', '全部')
    search = request.args.get('search', '')
    page = max(1, request.args.get('page', 1, type=int))
    page_size = 20

    total = QuestionModel.count(
        subject=subject, grade=grade, difficulty=difficulty, search=search
    )
    skip = (page - 1) * page_size
    questions = QuestionModel.get_all(
        skip=skip, limit=page_size,
        subject=subject, grade=grade, difficulty=difficulty, search=search
    )

    print(f"[DEBUG] 题库查询: subject={subject}, grade={grade}, difficulty={difficulty}, total={total}, 返回={len(questions)}")

    return render_template('question_bank.html',
                          questions=questions,
                          subject=subject,
                          grade=grade,
                          difficulty=difficulty,
                          search=search,
                          page=page,
                          total=total,
                          page_size=page_size)


@app.route('/ai_chat', methods=['GET', 'POST'])
def ai_chat():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_msg = request.json.get('message')
        username = session['username']
        user_data = get_db_user_data(username)

        if user_data:
            status = user_data['stats']
            status['total_questions'] = user_data['stats']['total_count']
            ai_reply = get_ai_response(user_msg, status)
        else:
            ai_reply = "抱歉，无法获取您的学习数据。"

        return jsonify({"reply": ai_reply})

    return render_template('ai_chat.html')


@app.route('/stats')
def stats():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_data = get_db_user_data(username)
    if not user_data:
        session.clear()
        return redirect(url_for('login'))

    status = analyze_user_status(user_data['records'])
    status['total_questions'] = user_data['stats']['total_count']
    status['accuracy'] = user_data['stats']['accuracy']

    return render_template('stats.html', status=status, records=user_data['records'])


@app.route('/reset')
def reset():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session.get('username')
    user = UserModel.find_by_username(username) if username else None
    if user:
        UserRecordModel.delete_user_records(user['id'])
        session['user_id'] = user['id']
        session.pop('recommend_cache', None)

    return redirect(url_for('index'))


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空', 'code': 400}), 400

    user = UserModel.find_by_username(username)
    if not user or user.get('password') != password:
        return jsonify({'error': '用户名或密码错误', 'code': 401}), 401

    token = generate_token(user['id'], username, user.get('role', 'user'))
    return jsonify({
        'code': 200,
        'token': token,
        'username': username,
        'role': user.get('role', 'user'),
        'user_id': user['id']
    })


@app.route('/api/user/profile', methods=['GET'])
def api_profile():
    if 'username' not in session:
        return jsonify({'error': '未登录', 'code': 401}), 401

    username = session['username']
    user = UserModel.find_by_username(username)
    if not user:
        return jsonify({'error': '用户不存在', 'code': 404}), 404

    stats = UserRecordModel.get_user_stats(user['id'])
    return jsonify({
        'code': 200,
        'data': {
            'username': username,
            'role': user.get('role', 'user'),
            'stats': stats
        }
    })


@app.route('/api/questions', methods=['GET'])
def api_questions():
    if 'username' not in session:
        return jsonify({'error': '未登录', 'code': 401}), 401

    subject = request.args.get('subject', '全部')
    grade = request.args.get('grade', '全部')
    difficulty = request.args.get('difficulty', '全部')
    search = request.args.get('search', '')
    page = max(1, request.args.get('page', 1, type=int))
    page_size = min(100, max(1, request.args.get('page_size', 20, type=int)))

    total = QuestionModel.count(
        subject=subject, grade=grade, difficulty=difficulty, search=search
    )
    skip = (page - 1) * page_size
    questions = QuestionModel.get_all(
        skip=skip, limit=page_size,
        subject=subject, grade=grade, difficulty=difficulty, search=search
    )

    return jsonify({
        'code': 200,
        'data': {
            'items': questions,
            'total': total,
            'page': page,
            'page_size': page_size
        }
    })


@app.route('/admin')
def admin():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = UserModel.find_by_username(session['username'])
    if not user or user.get('role') != 'admin':
        return redirect(url_for('index'))
    from models import UserRecordModel
    total_users = UserModel.count()
    total_questions = QuestionModel.count()
    total_records = 0
    avg_accuracy = 0
    hot_questions = []
    recent_logs = []
    try:
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                cursor.execute("SELECT COUNT(*) as cnt FROM user_records")
                total_records = dict(cursor.fetchone())['cnt']
                cursor.execute("SELECT AVG(CAST(correct AS FLOAT)) * 100 as avg_acc FROM user_records")
                result = cursor.fetchone()
                avg_accuracy = round(dict(result)['avg_acc'] or 0, 2) if result else 0

                cursor.execute(
                    """SELECT q.id, q.question, q.subject, q.difficulty, COUNT(ur.id) as times_done
                       FROM user_records ur
                       JOIN questions q ON ur.question_id = q.id
                       GROUP BY q.id
                       ORDER BY times_done DESC, q.id DESC
                       LIMIT 10"""
                )
                for r in cursor.fetchall():
                    d = dict(r)
                    hot_questions.append(d)

                cursor.execute(
                    """SELECT al.id, al.created_at, al.user_id, u.username as username, al.action, al.target_type, al.target_id, al.details, al.ip_address
                       FROM audit_logs al
                       LEFT JOIN users u ON al.user_id = u.id
                       ORDER BY al.id DESC
                       LIMIT 10"""
                )
                for r in cursor.fetchall():
                    d = dict(r)
                    if d.get('created_at') and isinstance(d['created_at'], str) and len(d['created_at']) >= 19:
                        d['created_at'] = d['created_at'][:19].replace('T', ' ')
                    recent_logs.append(d)
            else:
                cursor.execute("SELECT COUNT(*) as cnt FROM user_records")
                total_records = dict(cursor.fetchone())['cnt']
                cursor.execute("SELECT AVG(CASE WHEN correct THEN 100.0 ELSE 0 END) as avg_acc FROM user_records")
                result = cursor.fetchone()
                avg_accuracy = round(dict(result)['avg_acc'] or 0, 2) if result else 0

                cursor.execute(
                    """SELECT q.id, q.question, q.subject, q.difficulty, COUNT(ur.id) as times_done
                       FROM user_records ur
                       JOIN questions q ON ur.question_id = q.id
                       GROUP BY q.id, q.question, q.subject, q.difficulty
                       ORDER BY times_done DESC, q.id DESC
                       LIMIT 10"""
                )
                for r in cursor.fetchall():
                    hot_questions.append(dict(r) if not isinstance(r, dict) else r)

                cursor.execute(
                    """SELECT al.id, al.created_at, al.user_id, u.username as username, al.action, al.target_type, al.target_id, al.details, al.ip_address
                       FROM audit_logs al
                       LEFT JOIN users u ON al.user_id = u.id
                       ORDER BY al.id DESC
                       LIMIT 10"""
                )
                for r in cursor.fetchall():
                    recent_logs.append(dict(r) if not isinstance(r, dict) else r)
    except:
        pass
    return render_template('admin/dashboard.html',
                          active_tab='dashboard',
                          stats={
                              'total_users': total_users,
                              'total_questions': total_questions,
                              'total_records': total_records,
                              'avg_accuracy': avg_accuracy
                          },
                          hot_questions=hot_questions,
                          recent_logs=recent_logs)


@app.route('/admin/users')
def admin_users():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = UserModel.find_by_username(session['username'])
    if not user or user.get('role') != 'admin':
        return redirect(url_for('index'))
    from models import UserRecordModel
    page = max(1, request.args.get('page', 1, type=int))
    page_size = 20
    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role', '').strip()
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    total = UserModel.count(search=search, include_deleted=include_deleted)
    skip = (page - 1) * page_size
    users = UserModel.get_all(skip=skip, limit=page_size, search=search, include_deleted=include_deleted)
    for u in users:
        u.pop('password', None)
        u['stats'] = UserRecordModel.get_user_stats(u['id'])
    if role_filter:
        users = [u for u in users if u.get('role') == role_filter]
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return render_template('admin/users.html',
                          active_tab='users',
                          users=users,
                          page=page,
                          total_pages=total_pages,
                          search=search,
                          role_filter=role_filter,
                          include_deleted=include_deleted)


@app.route('/admin/questions')
def admin_questions():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = UserModel.find_by_username(session['username'])
    if not user or user.get('role') != 'admin':
        return redirect(url_for('index'))
    page = max(1, request.args.get('page', 1, type=int))
    page_size = 20
    search = request.args.get('search', '').strip()
    subject_filter = request.args.get('subject', '').strip()
    grade_filter = request.args.get('grade', '').strip()
    difficulty_filter = request.args.get('difficulty', '').strip()
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    total = QuestionModel.count(
        subject=subject_filter or None,
        grade=grade_filter or None,
        difficulty=difficulty_filter or None,
        search=search,
        include_deleted=include_deleted
    )
    skip = (page - 1) * page_size
    questions = QuestionModel.get_all(
        skip=skip, limit=page_size,
        subject=subject_filter or None,
        grade=grade_filter or None,
        difficulty=difficulty_filter or None,
        search=search,
        include_deleted=include_deleted
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return render_template('admin/questions.html',
                          active_tab='questions',
                          questions=questions,
                          page=page,
                          total_pages=total_pages,
                          search=search,
                          subject_filter=subject_filter,
                          grade_filter=grade_filter,
                          difficulty_filter=difficulty_filter,
                          include_deleted=include_deleted)


@app.route('/admin/audit_logs')
def admin_audit_logs():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = UserModel.find_by_username(session['username'])
    if not user or user.get('role') != 'admin':
        return redirect(url_for('index'))
    from models import AuditLogModel
    page = max(1, request.args.get('page', 1, type=int))
    page_size = 50
    action_filter = request.args.get('action', '').strip()
    user_id_filter = request.args.get('user_id', '').strip()
    skip = (page - 1) * page_size
    user_id_val = int(user_id_filter) if user_id_filter.isdigit() else None
    logs = AuditLogModel.get_logs(skip=skip, limit=page_size, action=action_filter or None, user_id=user_id_val)
    total = AuditLogModel.count(action=action_filter or None, user_id=user_id_val)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return render_template('admin/audit_logs.html',
                          active_tab='logs',
                          logs=logs,
                          page=page,
                          total_pages=total_pages,
                          action_filter=action_filter,
                          user_id_filter=user_id_filter)


@app.route('/admin/backup')
def admin_backup():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = UserModel.find_by_username(session['username'])
    if not user or user.get('role') != 'admin':
        return redirect(url_for('index'))
    from backup import list_backups, get_backup_count, get_latest_backup_time
    backups = list_backups()
    return render_template('admin/backup.html',
                          active_tab='backup',
                          backups=backups,
                          backup_count=get_backup_count(),
                          latest_backup=get_latest_backup_time())


@app.route('/api/admin/backup', methods=['POST'])
def api_create_backup():
    if 'username' not in session:
        return jsonify({'error': '未登录', 'code': 401}), 401
    user = UserModel.find_by_username(session['username'])
    if not user or user.get('role') != 'admin':
        return jsonify({'error': '权限不足', 'code': 403}), 403
    from backup import create_backup
    from models import AuditLogModel
    try:
        result = create_backup()
        AuditLogModel.log(
            user_id=user['id'],
            action='BACKUP',
            target_type='system',
            target_id=None,
            details={'filename': result['filename'], 'size': result['size']},
            ip_address=request.remote_addr
        )
        return jsonify({'code': 200, 'data': result})
    except Exception as e:
        return jsonify({'error': str(e), 'code': 500}), 500


@app.route('/api/admin/backup/<filename>', methods=['POST'])
def api_restore_backup(filename):
    if 'username' not in session:
        return jsonify({'error': '未登录', 'code': 401}), 401
    user = UserModel.find_by_username(session['username'])
    if not user or user.get('role') != 'admin':
        return jsonify({'error': '权限不足', 'code': 403}), 403
    from backup import restore_backup
    from models import AuditLogModel
    success, message = restore_backup(filename)
    AuditLogModel.log(
        user_id=user['id'],
        action='RESTORE',
        target_type='system',
        target_id=None,
        details={'filename': filename, 'result': message},
        ip_address=request.remote_addr
    )
    if success:
        return jsonify({'code': 200, 'message': message})
    else:
        return jsonify({'error': message, 'code': 500}), 500


@app.route('/api/admin/backup/<filename>', methods=['DELETE'])
def api_delete_backup(filename):
    if 'username' not in session:
        return jsonify({'error': '未登录', 'code': 401}), 401
    user = UserModel.find_by_username(session['username'])
    if not user or user.get('role') != 'admin':
        return jsonify({'error': '权限不足', 'code': 403}), 403
    from backup import delete_backup
    success = delete_backup(filename)
    if success:
        return jsonify({'code': 200, 'message': '删除成功'})
    else:
        return jsonify({'error': '删除失败', 'code': 500}), 500


@app.route('/api/admin/backup/download/<filename>')
def api_download_backup(filename):
    if 'username' not in session:
        return redirect(url_for('login'))
    user = UserModel.find_by_username(session['username'])
    if not user or user.get('role') != 'admin':
        return redirect(url_for('index'))
    from backup import BACKUP_DIR
    from flask import send_from_directory
    return send_from_directory(BACKUP_DIR, filename, as_attachment=True)


if __name__ == '__main__':
    init_db()
    print("正在初始化向量数据库...")
    try:
        get_vector_db()
    except Exception as e:
        print(f"向量数据库初始化失败 (可能缺少依赖): {e}")

    app.run(debug=True, port=5000)
