import json
from .deepseek_api import call_deepseek, extract_json
from models import QuestionModel

def analyze_user_weakness(user_records):
    """
    使用AI分析用户的学习薄弱点
    
    参数:
    user_records: list of dict [{"question_id": 1, "correct": False, "time": "..."}]
    
    返回:
    analysis_text: str (分析结果)
    weak_knowledge: list (薄弱知识点列表)
    """
    if not user_records:
        return "暂无做题记录，无法分析。", []

    records_text = ""
    for r in user_records[-10:]: # 取最近10条记录分析
        q_id = r['question_id']
        is_correct = r.get('correct', r.get('is_correct', False))

        knowledge = r.get('knowledge')
        difficulty = r.get('difficulty')
        if knowledge is None or difficulty is None:
            q = QuestionModel.find_by_id(q_id)
            if q:
                knowledge = q.get('knowledge')
                difficulty = q.get('difficulty')

        if knowledge is None and difficulty is None:
            continue

        status = "正确" if is_correct else "错误"
        records_text += f"题目ID：{q_id}，知识点：{knowledge or '未知'}，难度：{difficulty or '未知'}，结果：{status}\n"
            
    if not records_text:
        return "暂无有效做题记录。", []

    prompt = f"""
    以下是学生最近的做题记录：
    {records_text}
    
    请分析该学生可能的知识薄弱点，并给出针对性的建议（100字以内）。
    请按以下JSON格式返回：
    {{
        "analysis": "你的分析建议...",
        "weak_knowledge": ["知识点1", "知识点2"]
    }}
    """
    
    try:
        response = call_deepseek(prompt)
        result = extract_json(response)
        
        if result:
            return result.get("analysis", "AI分析生成失败"), result.get("weak_knowledge", [])
        else:
            return response if response else "AI暂时无法分析", []
            
    except Exception as e:
        print(f"AI分析失败: {e}")
        return "AI服务暂不可用", []

def generate_recommendation_reason(questions, user_status_text):
    """
    生成推荐理由
    
    参数:
    questions: list (推荐的题目列表)
    user_status_text: str (用户的状态描述或薄弱点分析)
    """
    if not questions:
        return "暂无推荐题目。"
        
    q_titles = [f"{q['question']} (知识点: {q['knowledge']})" for q in questions]
    
    prompt = f"""
    学生的学习状态分析如下：
    {user_status_text}
    
    系统为该学生推荐了以下题目：
    {json.dumps(q_titles, ensure_ascii=False)}
    
    请生成一段亲切、鼓励性的推荐语，说明为什么推荐这些题目（50字以内）。
    """
    
    try:
        response = call_deepseek(prompt)
        return response if response else "根据你的学习情况，为你精选了以上习题。"
    except:
        return "根据你的学习情况，为你精选了以上习题。"
