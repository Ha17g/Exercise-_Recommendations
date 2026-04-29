import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import QuestionModel

def select_questions_from_db(k=4, subject=None, grade=None, exclude_ids=None):
    """
    从数据库题库中选择题目

    参数:
    k: int (需要的题目数量)
    subject: str (学科筛选)
    grade: str (年级筛选)
    exclude_ids: set (排除的题目ID)

    返回:
    selected_questions: list (选中的题目)
    """
    try:
        all_questions = QuestionModel.get_all(limit=10000, subject=subject, grade=grade)
    except Exception as e:
        print(f"从数据库获取题目失败: {e}")
        return []

    if not all_questions:
        return []

    candidates = []
    for q in all_questions:
        if exclude_ids and q.get('id') in exclude_ids:
            continue
        candidates.append(q)

    if len(candidates) <= k:
        return candidates
    else:
        return random.sample(candidates, k)
