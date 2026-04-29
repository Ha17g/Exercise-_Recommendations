import numpy as np
import os

# 尝试导入 sentence_transformers
try:
    from sentence_transformers import SentenceTransformer
    HAS_TRANSFORMERS = True
    try:
        # 使用轻量级模型，第一次运行会自动下载
        model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        print("Embedding模型加载成功")
    except Exception as e:
        print(f"Embedding模型加载失败: {e}")
        print("将使用随机向量代替。")
        HAS_TRANSFORMERS = False
except ImportError:
    HAS_TRANSFORMERS = False
    print("警告：未检测到 sentence_transformers 库，将使用随机向量代替。请运行 pip install sentence-transformers")

def get_embedding(text):
    """
    获取文本的向量表示
    """
    if not text:
        return np.zeros(384).astype('float32')
        
    if HAS_TRANSFORMERS:
        try:
            # 编码文本，返回numpy数组
            embedding = model.encode(text)
            return embedding.astype('float32')
        except Exception as e:
            print(f"Embedding生成出错: {e}")
            return np.random.rand(384).astype('float32')
    else:
        # 模拟 384 维向量 (MiniLM输出维度)
        return np.random.rand(384).astype('float32')

def get_dimension():
    """
    返回向量维度
    """
    return 384
