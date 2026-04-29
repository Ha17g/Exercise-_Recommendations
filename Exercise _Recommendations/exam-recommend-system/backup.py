import os
import shutil
import json
import datetime
import zipfile
from db_config import db_config

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'backups')


def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def create_backup():
    ensure_backup_dir()
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'backup_{timestamp}'
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    os.makedirs(backup_path, exist_ok=True)

    if db_config.db_type == 'sqlite' and hasattr(db_config, 'db_path'):
        db_path = db_config.db_path
        if os.path.exists(db_path):
            shutil.copy2(db_path, os.path.join(backup_path, 'exam_system.db'))

    vector_store_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vector_store')
    if os.path.exists(vector_store_path):
        for f in os.listdir(vector_store_path):
            src = os.path.join(vector_store_path, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(backup_path, f))

    config_data = {
        'created_at': datetime.datetime.now().isoformat(),
        'db_type': db_config.db_type,
        'version': '2.0'
    }
    with open(os.path.join(backup_path, 'config.json'), 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)

    zip_path = f'{backup_path}.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(backup_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, backup_path)
                zipf.write(file_path, arcname)

    shutil.rmtree(backup_path)

    size_kb = os.path.getsize(zip_path) // 1024

    return {
        'filename': f'{backup_name}.zip',
        'path': zip_path,
        'size': size_kb,
        'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


def list_backups():
    ensure_backup_dir()
    backups = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if f.endswith('.zip'):
            full_path = os.path.join(BACKUP_DIR, f)
            size_kb = os.path.getsize(full_path) // 1024
            created = datetime.datetime.fromtimestamp(os.path.getctime(full_path)).strftime('%Y-%m-%d %H:%M:%S')
            backups.append({
                'filename': f,
                'path': full_path,
                'size': size_kb,
                'created_at': created
            })
    return backups


def restore_backup(filename):
    ensure_backup_dir()
    backup_path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(backup_path):
        return False, '备份文件不存在'

    extract_dir = backup_path + '.extracted'
    try:
        with zipfile.ZipFile(backup_path, 'r') as zipf:
            zipf.extractall(extract_dir)

        found_db_backup = None
        found_vector_files = []
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                if f == 'exam_system.db':
                    found_db_backup = os.path.join(root, f)
                if f.startswith('faiss') or f.endswith('.bin'):
                    found_vector_files.append(os.path.join(root, f))

        if found_db_backup and db_config.db_type == 'sqlite' and hasattr(db_config, 'db_path'):
            db_path = db_config.db_path
            try:
                db_config.close_pool()
            except Exception:
                pass
            shutil.copy2(found_db_backup, db_path)
            try:
                db_config.close_pool()
            except Exception:
                pass

        vector_store_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vector_store')
        os.makedirs(vector_store_path, exist_ok=True)
        for src in found_vector_files:
            dst = os.path.join(vector_store_path, os.path.basename(src))
            shutil.copy2(src, dst)

        return True, '恢复成功'
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)


def delete_backup(filename):
    ensure_backup_dir()
    backup_path = os.path.join(BACKUP_DIR, filename)
    if os.path.exists(backup_path):
        os.remove(backup_path)
        return True
    return False


def get_backup_count():
    ensure_backup_dir()
    return len([f for f in os.listdir(BACKUP_DIR) if f.endswith('.zip')])


def get_latest_backup_time():
    backups = list_backups()
    if backups:
        return backups[0]['created_at']
    return None
