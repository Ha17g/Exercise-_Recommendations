import requests
import json
import re

# DeepSeek API配置
API_KEY = "sk-1fbc2b1efa1a48acaf0e1cb5048ecb37"
API_URL = "https://api.deepseek.com/v1/chat/completions"

def call_deepseek(prompt, system_prompt="你是一个智能助教。"):
    """
    调用DeepSeek API获取回复
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"DeepSeek API调用失败: {e}")
        return None

def extract_json(text):
    """
    从文本中提取JSON内容（兼容Markdown代码块格式）
    """
    if not text:
        return None
        
    try:
        # 尝试直接解析
        return json.loads(text)
    except:
        # 尝试提取代码块中的JSON
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
        
        # 尝试提取第一个 { 和最后一个 } 之间的内容
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
                
    return None
