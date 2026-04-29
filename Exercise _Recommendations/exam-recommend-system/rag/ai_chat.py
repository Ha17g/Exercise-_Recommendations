import json
from .deepseek_api import call_deepseek, extract_json

def get_ai_response(user_message, user_status):
    """
    获取AI学习助手的回复
    
    参数:
    user_message: str (用户提问)
    user_status: dict (用户学习状态分析)
    """
    
    # 构建用户状态描述
    status_desc = f"总做题数：{user_status.get('total_questions', 0)}，正确率：{user_status.get('accuracy', 0)}%。"
    
    weak_points = user_status.get('weak_points', [])
    if weak_points:
        weak_desc = "薄弱知识点：" + "、".join([f"{wp['knowledge']}(正确率{int(wp['accuracy']*100)}%)" for wp in weak_points[:3]])
        status_desc += "\n" + weak_desc
    else:
        status_desc += "\n暂无明显薄弱知识点。"
        
    prompt = f"""
    你是一个智能学习助手。
    当前学生的学习情况如下：
    {status_desc}
    
    学生提问：
    {user_message}
    
    请根据学生的学习情况，给出专业、友善且有针对性的建议或回答。
    """
    
    try:
        response = call_deepseek(prompt, system_prompt="你是一位耐心的AI导师。")
        return response if response else "抱歉，我暂时无法思考，请稍后再试。"
    except Exception as e:
        print(f"AI聊天失败: {e}")
        return "系统繁忙，请稍后再试。"
