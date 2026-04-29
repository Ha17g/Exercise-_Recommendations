from .vector_db import get_vector_db

def analyze_user_status(user_records):
    """
    分析用户的学习状态：正确率、薄弱知识点、学科掌握情况
    user_records: list of dict, e.g. [{"question_id": 1, "correct": True, "time": "...", "subject": "...", "grade": "..."}]
    """
    if not user_records:
        return {
            "accuracy": 0,
            "weak_points": [],
            "subject_stats": [],
            "total_questions": 0
        }

    total = len(user_records)
    correct_count = sum(1 for r in user_records if r.get('correct', r.get('is_correct', False)))
    accuracy = (correct_count / total) * 100 if total > 0 else 0

    knowledge_stats = {}
    subject_stats_map = {}

    all_subjects = set()

    for record in user_records:
        s = record.get('subject', '其他')
        g = record.get('grade', '其他')
        k = record.get('knowledge', '未知')
        all_subjects.add(s)

        if s not in subject_stats_map:
            subject_stats_map[s] = {'correct': 0, 'total': 0}
        subject_stats_map[s]['total'] += 1
        if record.get('correct', record.get('is_correct', False)):
            subject_stats_map[s]['correct'] += 1

        if k and k != s:
            if k not in knowledge_stats:
                knowledge_stats[k] = {'correct': 0, 'total': 0}
            knowledge_stats[k]['total'] += 1
            if record.get('correct', record.get('is_correct', False)):
                knowledge_stats[k]['correct'] += 1

    weak_points = []
    for k, stats in knowledge_stats.items():
        if k in all_subjects:
            continue
        if stats['total'] > 0:
            acc = stats['correct'] / stats['total']
        else:
            acc = 0
        weak_points.append({
            "knowledge": k,
            "accuracy": acc,
            "count": stats['total']
        })

    subject_stats_list = []
    for s, stats in subject_stats_map.items():
        if stats['total'] > 0:
            acc = stats['correct'] / stats['total']
        else:
            acc = 0
        subject_stats_list.append({
            "subject": s,
            "accuracy": acc,
            "count": stats['total']
        })

    weak_points.sort(key=lambda x: x['accuracy'])
    subject_stats_list.sort(key=lambda x: x['accuracy'])

    return {
        "accuracy": round(accuracy, 2),
        "weak_points": weak_points,
        "subject_stats": subject_stats_list,
        "total_questions": total
    }


def get_recommendations(user_data, k=3):
    """
    获取推荐题目
    user_data: dict, e.g. { "records": [...], "answered_questions": [...] }
    """
    if isinstance(user_data, dict):
        user_records = user_data.get('records', [])
        done_ids = set(user_data.get('answered_questions', []))
    else:
        user_records = user_data if isinstance(user_data, list) else []
        done_ids = {r['question_id'] for r in user_records}

    status = analyze_user_status(user_records)
    weak_points = status['weak_points']

    if not weak_points:
        return [], status

    top_weak = weak_points[:k]
    query_text = " ".join([wp.get('knowledge', '') for wp in top_weak if wp.get('knowledge')])

    try:
        vector_db = get_vector_db()
        if vector_db is None:
            return [], status
        candidates = vector_db.search(query_text, k=max(k * 4, 10))
        picked = []
        for q in candidates:
            q_id = q.get('id')
            if not q_id:
                continue
            if q_id in done_ids:
                continue
            picked.append(q)
            if len(picked) >= k:
                break
        return picked, status
    except Exception as e:
        print(f"向量检索失败: {e}")
        return [], status
