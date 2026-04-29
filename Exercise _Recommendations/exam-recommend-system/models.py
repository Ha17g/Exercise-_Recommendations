import json
import datetime
from db_config import db_config, sanitize_value


def now_str():
    return datetime.datetime.now().replace(microsecond=0).strftime('%Y-%m-%d %H:%M:%S')


def normalize_time_str(val):
    if val is None:
        return None
    if not isinstance(val, str):
        return val
    s = val.replace('T', ' ')
    if len(s) >= 19:
        return s[:19]
    return s


def normalize_dt_fields(d, fields):
    for f in fields:
        if f in d and d[f] is not None:
            d[f] = normalize_time_str(d[f])
    return d


def json_loads_default(val):
    if val is None:
        return []
    if isinstance(val, str):
        try:
            return json.loads(val)
        except:
            return []
    return val


def json_dumps_default(val):
    if val is None:
        return "[]"
    if isinstance(val, (list, dict)):
        return json.dumps(val, ensure_ascii=False)
    return val


class UserModel:
    @staticmethod
    def find_by_username(username):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                cursor.execute(
                    "SELECT * FROM users WHERE username = ? AND is_deleted = 0",
                    (username,)
                )
            else:
                cursor.execute(
                    "SELECT * FROM users WHERE username = %s AND is_deleted = FALSE",
                    (username,)
                )
            row = cursor.fetchone()
            if row:
                return dict(row) if not isinstance(row, dict) else row
            return None

    @staticmethod
    def find_by_id(user_id):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                cursor.execute(
                    "SELECT * FROM users WHERE id = ? AND is_deleted = 0",
                    (user_id,)
                )
            else:
                cursor.execute(
                    "SELECT * FROM users WHERE id = %s AND is_deleted = FALSE",
                    (user_id,)
                )
            row = cursor.fetchone()
            if row:
                return dict(row) if not isinstance(row, dict) else row
            return None

    @staticmethod
    def create(username, password, role='user'):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            else:
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            existing = cursor.fetchone()
            if existing:
                raise ValueError(f"用户名 '{username}' 已存在（已被使用）")
            now = now_str()
            if db_config.db_type == 'sqlite':
                cursor.execute(
                    "INSERT INTO users (username, password, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (username, password, role, now, now)
                )
            else:
                cursor.execute(
                    "INSERT INTO users (username, password, role, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
                    (username, password, role, now, now)
                )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def get_all(skip=0, limit=20, search='', include_deleted=False):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                if include_deleted:
                    query = "SELECT * FROM users WHERE 1=1"
                else:
                    query = "SELECT * FROM users WHERE is_deleted = 0"
                params = []
                if search:
                    query += " AND username LIKE ?"
                    params.append(f"%{search}%")
                query += " ORDER BY id LIMIT ? OFFSET ?"
                params.extend([limit, skip])
                cursor.execute(query, params)
            else:
                if include_deleted:
                    query = "SELECT * FROM users WHERE 1=1"
                else:
                    query = "SELECT * FROM users WHERE is_deleted = FALSE"
                params = []
                if search:
                    query += " AND username LIKE %s"
                    params.append(f"%{search}%")
                query += " ORDER BY id LIMIT %s OFFSET %s"
                params.extend([limit, skip])
                cursor.execute(query, params)
            rows = cursor.fetchall()
            results = []
            for row in rows:
                r = dict(row) if not isinstance(row, dict) else row
                results.append(normalize_dt_fields(r, ['created_at', 'updated_at']))
            return results

    @staticmethod
    def count(search='', include_deleted=False):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                if include_deleted:
                    query = "SELECT COUNT(*) as cnt FROM users"
                else:
                    query = "SELECT COUNT(*) as cnt FROM users WHERE is_deleted = 0"
                params = []
                if search:
                    query += " AND username LIKE ?"
                    params.append(f"%{search}%")
                cursor.execute(query, params)
            else:
                if include_deleted:
                    query = "SELECT COUNT(*) as cnt FROM users"
                else:
                    query = "SELECT COUNT(*) as cnt FROM users WHERE is_deleted = FALSE"
                params = []
                if search:
                    query += " AND username LIKE %s"
                    params.append(f"%{search}%")
                cursor.execute(query, params)
            row = cursor.fetchone()
            return row['cnt'] if isinstance(row, dict) else dict(row)['cnt']

    @staticmethod
    def update(user_id, **kwargs):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            kwargs['updated_at'] = now_str()
            if db_config.db_type == 'sqlite':
                sets = ', '.join([f"{k} = ?" for k in kwargs.keys()])
                values = list(kwargs.values()) + [user_id]
                cursor.execute(f"UPDATE users SET {sets} WHERE id = ?", values)
            else:
                sets = ', '.join([f"{k} = %s" for k in kwargs.keys()])
                values = list(kwargs.values()) + [user_id]
                cursor.execute(f"UPDATE users SET {sets} WHERE id = %s", values)
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def soft_delete(user_id):
        return UserModel.update(user_id, is_deleted=1 if db_config.db_type == 'sqlite' else True)

    @staticmethod
    def hard_delete(user_id):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            else:
                cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            return cursor.rowcount > 0


class QuestionModel:
    @staticmethod
    def find_by_id(q_id):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                cursor.execute("SELECT * FROM questions WHERE id = ? AND is_deleted = 0", (q_id,))
            else:
                cursor.execute("SELECT * FROM questions WHERE id = %s AND is_deleted = FALSE", (q_id,))
            row = cursor.fetchone()
            if row:
                result = dict(row) if not isinstance(row, dict) else row
                if 'options' in result:
                    result['options'] = json_loads_default(result['options'])
                return result
            return None

    @staticmethod
    def get_all(skip=0, limit=20, subject=None, grade=None, difficulty=None, search='',
                include_deleted=False, created_by=None):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                if include_deleted:
                    query = "SELECT * FROM questions WHERE 1=1"
                else:
                    query = "SELECT * FROM questions WHERE is_deleted = 0"
                params = []
                if subject and subject != '全部':
                    query += " AND subject = ?"
                    params.append(subject)
                if grade and grade != '全部':
                    query += " AND grade = ?"
                    params.append(grade)
                if difficulty and difficulty != '全部':
                    query += " AND difficulty = ?"
                    params.append(difficulty)
                if search:
                    query += " AND (question LIKE ? OR CAST(id AS TEXT) LIKE ?)"
                    params.extend([f"%{search}%", f"%{search}%"])
                if created_by:
                    query += " AND created_by = ?"
                    params.append(created_by)
                query += " ORDER BY id LIMIT ? OFFSET ?"
                params.extend([limit, skip])
                cursor.execute(query, params)
            else:
                if include_deleted:
                    query = "SELECT * FROM questions WHERE 1=1"
                else:
                    query = "SELECT * FROM questions WHERE is_deleted = FALSE"
                params = []
                if subject and subject != '全部':
                    query += " AND subject = %s"
                    params.append(subject)
                if grade and grade != '全部':
                    query += " AND grade = %s"
                    params.append(grade)
                if difficulty and difficulty != '全部':
                    query += " AND difficulty = %s"
                    params.append(difficulty)
                if search:
                    query += " AND (question LIKE %s OR CAST(id AS TEXT) LIKE %s)"
                    params.extend([f"%{search}%", f"%{search}%"])
                if created_by:
                    query += " AND created_by = %s"
                    params.append(created_by)
                query += " ORDER BY id LIMIT %s OFFSET %s"
                params.extend([limit, skip])
                cursor.execute(query, params)
            rows = cursor.fetchall()
            results = []
            for row in rows:
                result = dict(row) if not isinstance(row, dict) else row
                if 'options' in result:
                    result['options'] = json_loads_default(result['options'])
                normalize_dt_fields(result, ['created_at', 'updated_at'])
                results.append(result)
            return results

    @staticmethod
    def count(subject=None, grade=None, difficulty=None, search='', include_deleted=False, created_by=None):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                if include_deleted:
                    query = "SELECT COUNT(*) as cnt FROM questions WHERE 1=1"
                else:
                    query = "SELECT COUNT(*) as cnt FROM questions WHERE is_deleted = 0"
                params = []
                if subject and subject != '全部':
                    query += " AND subject = ?"
                    params.append(subject)
                if grade and grade != '全部':
                    query += " AND grade = ?"
                    params.append(grade)
                if difficulty and difficulty != '全部':
                    query += " AND difficulty = ?"
                    params.append(difficulty)
                if search:
                    query += " AND (question LIKE ? OR CAST(id AS TEXT) LIKE ?)"
                    params.extend([f"%{search}%", f"%{search}%"])
                if created_by:
                    query += " AND created_by = ?"
                    params.append(created_by)
                cursor.execute(query, params)
            else:
                if include_deleted:
                    query = "SELECT COUNT(*) as cnt FROM questions WHERE 1=1"
                else:
                    query = "SELECT COUNT(*) as cnt FROM questions WHERE is_deleted = FALSE"
                params = []
                if subject and subject != '全部':
                    query += " AND subject = %s"
                    params.append(subject)
                if grade and grade != '全部':
                    query += " AND grade = %s"
                    params.append(grade)
                if difficulty and difficulty != '全部':
                    query += " AND difficulty = %s"
                    params.append(difficulty)
                if search:
                    query += " AND (question LIKE %s OR CAST(id AS TEXT) LIKE %s)"
                    params.extend([f"%{search}%", f"%{search}%"])
                if created_by:
                    query += " AND created_by = %s"
                    params.append(created_by)
                cursor.execute(query, params)
            row = cursor.fetchone()
            return row['cnt'] if isinstance(row, dict) else dict(row)['cnt']

    @staticmethod
    def create(question, options, answer, knowledge=None, difficulty=None, subject=None, grade=None, created_by=None):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            now = now_str()
            options_json = json_dumps_default(options)
            if db_config.db_type == 'sqlite':
                cursor.execute(
                    """INSERT INTO questions (question, options, answer, knowledge, difficulty, subject, grade, created_at, updated_at, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (question, options_json, answer, knowledge, difficulty, subject, grade, now, now, created_by)
                )
            else:
                cursor.execute(
                    """INSERT INTO questions (question, options, answer, knowledge, difficulty, subject, grade, created_at, updated_at, created_by)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (question, options_json, answer, knowledge, difficulty, subject, grade, now, now, created_by)
                )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def update(q_id, **kwargs):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            kwargs['updated_at'] = now_str()
            if 'options' in kwargs:
                kwargs['options'] = json_dumps_default(kwargs['options'])
            if db_config.db_type == 'sqlite':
                sets = ', '.join([f"{k} = ?" for k in kwargs.keys()])
                values = list(kwargs.values()) + [q_id]
                cursor.execute(f"UPDATE questions SET {sets} WHERE id = ?", values)
            else:
                sets = ', '.join([f"{k} = %s" for k in kwargs.keys()])
                values = list(kwargs.values()) + [q_id]
                cursor.execute(f"UPDATE questions SET {sets} WHERE id = %s", values)
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def soft_delete(q_id):
        return QuestionModel.update(q_id, is_deleted=1 if db_config.db_type == 'sqlite' else True)

    @staticmethod
    def hard_delete(q_id):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                cursor.execute("DELETE FROM questions WHERE id = ?", (q_id,))
            else:
                cursor.execute("DELETE FROM questions WHERE id = %s", (q_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def batch_create(questions_data, created_by=None):
        results = []
        for q in questions_data:
            q_id = QuestionModel.create(
                question=q['question'],
                options=q.get('options', []),
                answer=q['answer'],
                knowledge=q.get('knowledge'),
                difficulty=q.get('difficulty'),
                subject=q.get('subject'),
                grade=q.get('grade'),
                created_by=created_by
            )
            results.append(q_id)
        return results


class UserRecordModel:
    @staticmethod
    def get_user_records(user_id, skip=0, limit=100):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                cursor.execute(
                    """SELECT ur.*, q.question, q.answer, q.options, q.knowledge, q.difficulty, q.subject, q.grade
                       FROM user_records ur
                       LEFT JOIN questions q ON ur.question_id = q.id
                       WHERE ur.user_id = ?
                       ORDER BY ur.time DESC
                       LIMIT ? OFFSET ?""",
                    (user_id, limit, skip)
                )
            else:
                cursor.execute(
                    """SELECT ur.*, q.question, q.answer, q.options::text, q.knowledge, q.difficulty, q.subject, q.grade
                       FROM user_records ur
                       LEFT JOIN questions q ON ur.question_id = q.id
                       WHERE ur.user_id = %s
                       ORDER BY ur.time DESC
                       LIMIT %s OFFSET %s""",
                    (user_id, limit, skip)
                )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                result = dict(row) if not isinstance(row, dict) else row
                if 'options' in result:
                    result['options'] = json_loads_default(result['options'])
                normalize_dt_fields(result, ['time', 'created_at'])
                results.append(result)
            return results

    @staticmethod
    def add_record(user_id, question_id, correct, time_str=None):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if time_str is None:
                time_str = now_str()
            else:
                time_str = normalize_time_str(time_str)
            correct_val = 1 if correct else 0
            if db_config.db_type == 'sqlite':
                cursor.execute(
                    "INSERT INTO user_records (user_id, question_id, correct, time) VALUES (?, ?, ?, ?)",
                    (user_id, question_id, correct_val, time_str)
                )
            else:
                cursor.execute(
                    "INSERT INTO user_records (user_id, question_id, correct, time) VALUES (%s, %s, %s, %s)",
                    (user_id, question_id, correct_val, time_str)
                )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def delete_user_records(user_id):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                cursor.execute("DELETE FROM user_records WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("DELETE FROM user_records WHERE user_id = %s", (user_id,))
            conn.commit()
            return cursor.rowcount

    @staticmethod
    def get_user_stats(user_id):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                cursor.execute(
                    """SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct_count
                       FROM user_records WHERE user_id = ?""",
                    (user_id,)
                )
            else:
                cursor.execute(
                    """SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN correct = TRUE THEN 1 ELSE 0 END) as correct_count
                       FROM user_records WHERE user_id = %s""",
                    (user_id,)
                )
            row = cursor.fetchone()
            result = dict(row) if not isinstance(row, dict) else row
            total = result.get('total', 0) or 0
            correct = result.get('correct_count', 0) or 0
            return {
                'total_count': total,
                'correct_count': correct,
                'accuracy': round((correct / total * 100), 2) if total > 0 else 0
            }


class AuditLogModel:
    @staticmethod
    def log(user_id, action, target_type=None, target_id=None, details=None, ip_address=None):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            details_json = json_dumps_default(details) if details else None
            now = now_str()
            if db_config.db_type == 'sqlite':
                cursor.execute(
                    """INSERT INTO audit_logs (user_id, action, target_type, target_id, details, ip_address, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, action, target_type, target_id, details_json, ip_address, now)
                )
            else:
                cursor.execute(
                    """INSERT INTO audit_logs (user_id, action, target_type, target_id, details, ip_address, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (user_id, action, target_type, target_id, details_json, ip_address, now)
                )
            conn.commit()
            return cursor.lastrowid

    @staticmethod
    def get_logs(skip=0, limit=50, user_id=None, action=None):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                query = "SELECT * FROM audit_logs WHERE 1=1"
                params = []
                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)
                if action:
                    query += " AND action = ?"
                    params.append(action)
                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, skip])
                cursor.execute(query, params)
            else:
                query = "SELECT * FROM audit_logs WHERE 1=1"
                params = []
                if user_id:
                    query += " AND user_id = %s"
                    params.append(user_id)
                if action:
                    query += " AND action = %s"
                    params.append(action)
                query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, skip])
                cursor.execute(query, params)
            rows = cursor.fetchall()
            results = []
            for row in rows:
                r = dict(row) if not isinstance(row, dict) else row
                results.append(normalize_dt_fields(r, ['created_at']))
            return results

    @staticmethod
    def count(user_id=None, action=None):
        with db_config.get_connection() as conn:
            cursor = conn.cursor()
            if db_config.db_type == 'sqlite':
                query = "SELECT COUNT(*) as cnt FROM audit_logs WHERE 1=1"
                params = []
                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)
                if action:
                    query += " AND action = ?"
                    params.append(action)
                cursor.execute(query, params)
            else:
                query = "SELECT COUNT(*) as cnt FROM audit_logs WHERE 1=1"
                params = []
                if user_id:
                    query += " AND user_id = %s"
                    params.append(user_id)
                if action:
                    query += " AND action = %s"
                    params.append(action)
                cursor.execute(query, params)
            row = cursor.fetchone()
            return row['cnt'] if isinstance(row, dict) else dict(row)['cnt']
