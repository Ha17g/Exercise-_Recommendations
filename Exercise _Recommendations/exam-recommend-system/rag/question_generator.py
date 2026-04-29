import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.deepseek_api import call_deepseek, extract_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def generate_new_questions(knowledge="综合知识", difficulty="中等", subject="计算机", grade="大学", count=2):
    """
    生成多道新题目

    参数:
    knowledge: str (知识点)
    difficulty: str (难度)
    subject: str (学科)
    grade: str (年级)
    count: int (生成数量)

    返回:
    new_questions: list (新题目列表)
    """

    prompt = f"""
    请生成 {count} 道关于【{subject}】学科，【{grade}】年级的选择题。
    重点知识点：{knowledge}。

    要求：
    1. 难度等级必须为：简单 / 中等 / 困难 之一。
    2. 包含四个选项（A, B, C, D）。
    3. 给出正确答案（选项内容）。
    4. 题目描述清晰，准确无误。
    5. 学科字段(subject)必须准确，例如：语文、数学、英语、物理、化学、生物、历史、地理、政治、计算机。

    请严格按以下JSON数组格式输出（不要包含其他文字）：
    [
      {{
        "question": "题目内容1",
        "options": ["选项1", "选项2", "选项3", "选项4"],
        "answer": "正确选项内容",
        "knowledge": "{knowledge}",
        "difficulty": "简单/中等/困难",
        "subject": "{subject}",
        "grade": "{grade}"
      }},
      ...
    ]
    """

    try:
        response = call_deepseek(prompt, system_prompt="你是一位出题专家。")
        if not response:
            return []

        new_qs = extract_json(response)
        if not new_qs or not isinstance(new_qs, list):
            return []

        saved_questions = []
        for q_data in new_qs:
            required_keys = ["question", "options", "answer", "knowledge", "difficulty", "subject", "grade"]
            if all(k in q_data for k in required_keys):
                if not q_data.get('subject') or (q_data['subject'] == '操作系统' and subject != '计算机'):
                    q_data['subject'] = subject

                try:
                    from models import QuestionModel
                    q_id = QuestionModel.create(
                        question=q_data['question'],
                        options=q_data['options'],
                        answer=q_data['answer'],
                        knowledge=q_data.get('knowledge'),
                        difficulty=q_data.get('difficulty'),
                        subject=q_data.get('subject'),
                        grade=q_data.get('grade')
                    )
                    q_data['id'] = q_id
                    q_data['is_ai_generated'] = True
                    saved_questions.append(q_data)
                    print(f"[AI] 保存题目到数据库: id={q_id}, subject={q_data.get('subject')}, grade={q_data.get('grade')}")
                except Exception as e:
                    import traceback
                    print(f"[AI] 保存题目失败: {e}")
                    traceback.print_exc()

        return saved_questions

    except Exception as e:
        print(f"批量生成题目失败: {e}")
        return []
