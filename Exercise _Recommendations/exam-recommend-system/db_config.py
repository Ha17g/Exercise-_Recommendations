import os
import time
import logging
from contextlib import contextmanager
from datetime import timedelta
from urllib.parse import urlparse
import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseConfig:
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.db_type = os.getenv('DB_TYPE', 'sqlite').lower()
        self.max_connections = int(os.getenv('DB_MAX_CONNECTIONS', '20'))
        self.min_connections = int(os.getenv('DB_MIN_CONNECTIONS', '2'))
        self.retry_times = int(os.getenv('DB_RETRY_TIMES', '3'))
        self.retry_delay = float(os.getenv('DB_RETRY_DELAY', '1.0'))
        self.slow_query_threshold = float(os.getenv('DB_SLOW_QUERY_THRESHOLD', '1.0'))
        self.slow_query_logger = logging.getLogger('slow_query')

        if self.db_type == 'postgresql':
            self.connection_params = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': os.getenv('DB_PORT', '5432'),
                'database': os.getenv('DB_NAME', 'exam_system'),
                'user': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', ''),
            }
        elif self.db_type == 'mysql':
            self.connection_params = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': int(os.getenv('DB_PORT', '3306')),
                'database': os.getenv('DB_NAME', 'exam_system'),
                'user': os.getenv('DB_USER', 'root'),
                'password': os.getenv('DB_PASSWORD', ''),
                'charset': 'utf8mb4',
            }
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_dir = os.path.join(base_dir, 'data')
            os.makedirs(db_dir, exist_ok=True)
            env_db_path = os.getenv('DB_PATH')
            if env_db_path:
                self.db_path = env_db_path if os.path.isabs(env_db_path) else os.path.join(base_dir, env_db_path)
            else:
                default_path = os.path.join(db_dir, 'exam_system.db')
                legacy_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                legacy_path = os.path.join(legacy_base_dir, 'data', 'exam_system.db')
                def _sqlite_db_score(path):
                    if not os.path.exists(path):
                        return None
                    try:
                        conn = sqlite3.connect(path)
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tables = {r[0] for r in cursor.fetchall()}
                        score = 0
                        for t in ('users', 'questions', 'user_records', 'audit_logs'):
                            if t in tables:
                                cursor.execute(f"SELECT COUNT(*) FROM {t}")
                                score += int(cursor.fetchone()[0] or 0)
                        conn.close()
                        return score
                    except Exception:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        return None

                if not os.path.exists(default_path) and os.path.exists(legacy_path):
                    self.db_path = legacy_path
                elif os.path.exists(default_path) and os.path.exists(legacy_path):
                    default_score = _sqlite_db_score(default_path)
                    legacy_score = _sqlite_db_score(legacy_path)
                    if (default_score is None and legacy_score is not None) or (default_score == 0 and (legacy_score or 0) > 0):
                        self.db_path = legacy_path
                    else:
                        self.db_path = default_path
                else:
                    self.db_path = default_path

    def _create_sqlite_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA journal_mode = WAL')
        conn.execute('PRAGMA busy_timeout = 5000')
        return conn

    def _create_pg_connection(self):
        return psycopg2.connect(**self.connection_params, cursor_factory=RealDictCursor)

    def _create_mysql_connection(self):
        import pymysql
        return pymysql.connect(**self.connection_params, cursor=pymysql.cursors.DictCursor)

    def _create_connection(self):
        for attempt in range(self.retry_times):
            try:
                if self.db_type == 'postgresql':
                    return self._create_pg_connection()
                elif self.db_type == 'mysql':
                    return self._create_mysql_connection()
                else:
                    return self._create_sqlite_connection()
            except Exception as e:
                logger.warning(f"连接数据库失败 (尝试 {attempt + 1}/{self.retry_times}): {e}")
                if attempt < self.retry_times - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise

    def init_pool(self):
        if self._pool is None:
            if self.db_type == 'sqlite':
                self._pool = SimpleConnectionPool(1, self.max_connections, self._create_sqlite_connection)
            elif self.db_type == 'postgresql':
                self._pool = pool.ThreadedConnectionPool(
                    self.min_connections, self.max_connections, **self.connection_params
                )
            elif self.db_type == 'mysql':
                import pymysql
                self._pool = pool.ThreadedConnectionPool(
                    self.min_connections, self.max_connections,
                    cursorclass=pymysql.cursors.DictCursor, **self.connection_params
                )
        return self._pool

    def get_pool(self):
        if self._pool is None:
            self.init_pool()
        return self._pool

    def close_pool(self):
        if self._pool is None:
            return
        try:
            if self.db_type == 'sqlite':
                if hasattr(self._pool, 'closeall'):
                    self._pool.closeall()
            else:
                if hasattr(self._pool, 'closeall'):
                    self._pool.closeall()
        finally:
            self._pool = None

    @contextmanager
    def get_connection(self):
        pool = self.get_pool()
        conn = None
        try:
            if self.db_type == 'sqlite':
                conn = pool.get_connection()
            else:
                conn = pool.getconn()
            conn.autocommit = False
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                if self.db_type == 'sqlite':
                    conn.close()
                else:
                    pool.putconn(conn)

    def init_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'sqlite':
                cursor.executescript('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        role TEXT DEFAULT 'user' CHECK(role IN ('admin', 'user')),
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now')),
                        is_deleted INTEGER DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS questions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question TEXT NOT NULL,
                        options TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        knowledge TEXT,
                        difficulty TEXT,
                        subject TEXT,
                        grade TEXT,
                        is_deleted INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now')),
                        created_by INTEGER REFERENCES users(id)
                    );

                    CREATE TABLE IF NOT EXISTS user_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        question_id INTEGER NOT NULL REFERENCES questions(id),
                        correct INTEGER NOT NULL,
                        time TEXT NOT NULL,
                        created_at TEXT DEFAULT (datetime('now'))
                    );

                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER REFERENCES users(id),
                        action TEXT NOT NULL,
                        target_type TEXT,
                        target_id INTEGER,
                        details TEXT,
                        ip_address TEXT,
                        created_at TEXT DEFAULT (datetime('now'))
                    );

                    CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                    CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                    CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject);
                    CREATE INDEX IF NOT EXISTS idx_questions_grade ON questions(grade);
                    CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);
                    CREATE INDEX IF NOT EXISTS idx_user_records_user_id ON user_records(user_id);
                    CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
                ''')
            elif self.db_type == 'postgresql':
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(100) UNIQUE NOT NULL,
                        password VARCHAR(255) NOT NULL,
                        role VARCHAR(20) DEFAULT 'user' CHECK(role IN ('admin', 'user')),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_deleted BOOLEAN DEFAULT FALSE
                    );

                    CREATE TABLE IF NOT EXISTS questions (
                        id SERIAL PRIMARY KEY,
                        question TEXT NOT NULL,
                        options JSONB NOT NULL,
                        answer TEXT NOT NULL,
                        knowledge VARCHAR(100),
                        difficulty VARCHAR(20),
                        subject VARCHAR(50),
                        grade VARCHAR(50),
                        is_deleted BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_by INTEGER REFERENCES users(id)
                    );

                    CREATE TABLE IF NOT EXISTS user_records (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        question_id INTEGER NOT NULL REFERENCES questions(id),
                        correct BOOLEAN NOT NULL,
                        time TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id),
                        action VARCHAR(100) NOT NULL,
                        target_type VARCHAR(50),
                        target_id INTEGER,
                        details JSONB,
                        ip_address VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                    CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                    CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject);
                    CREATE INDEX IF NOT EXISTS idx_questions_grade ON questions(grade);
                    CREATE INDEX IF NOT EXISTS idx_user_records_user_id ON user_records(user_id);
                ''')
            conn.commit()


class SimpleConnectionPool:
    def __init__(self, min_conn, max_conn, factory):
        self.min_conn = min_conn
        self.max_conn = max_conn
        self.factory = factory
        self._pool = []
        self._lock = __import__('threading').Lock()
        for _ in range(min_conn):
            self._pool.append(factory())

    def get_connection(self):
        with self._lock:
            if self._pool:
                return self._pool.pop()
            if len(self._pool) < self.max_conn:
                return self.factory()
            raise Exception("连接池已满")

    def put_connection(self, conn):
        with self._lock:
            if len(self._pool) < self.max_conn:
                self._pool.append(conn)
            else:
                conn.close()

    def closeall(self):
        with self._lock:
            while self._pool:
                conn = self._pool.pop()
                try:
                    conn.close()
                except Exception:
                    pass


def sanitize_identifier(identifier):
    if not identifier.replace('_', '').isalnum():
        raise ValueError(f"无效的标识符: {identifier}")
    return identifier


def sanitize_value(value):
    if isinstance(value, str):
        return value.replace('\x00', '')
    return value


db_config = DatabaseConfig()
