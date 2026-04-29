import faiss
import numpy as np
import os
from .embedding import get_embedding, get_dimension
from models import QuestionModel

# 获取项目根目录 (rag 目录的父目录)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class VectorDB:
    def __init__(self, 
                 index_path=os.path.join(BASE_DIR, "vector_store", "faiss_index.bin"),
                 data_path=None,
                 max_questions=20000):
        self.index_path = index_path
        self.data_path = data_path
        self.max_questions = max_questions
        self.dimension = get_dimension()
        self.index = None
        self.questions = []
        self._load_or_create_index()

    def _load_questions_from_db(self):
        try:
            self.questions = QuestionModel.get_all(limit=self.max_questions)
        except Exception:
            self.questions = []

    def _load_or_create_index(self):
        self._load_questions_from_db()

        # 尝试加载现有索引
        if os.path.exists(self.index_path):
            try:
                self.index = faiss.read_index(self.index_path)
                if self.index.ntotal == len(self.questions):
                    print(f"成功加载向量索引，包含 {self.index.ntotal} 条数据")
                    return
                print("向量索引与题库数据不一致，将重新构建")
            except Exception as e:
                print(f"加载索引失败: {e}，将重新构建")

        # 如果没有索引或加载失败，重新构建
        self.build_index()

    def build_index(self):
        """构建FAISS索引"""
        print("开始构建向量索引...")
        # 初始化索引 (L2距离)
        self.index = faiss.IndexFlatL2(self.dimension)
        if not self.questions:
            print("没有数据，无法构建索引")
            return
        
        vectors = []
        
        for q in self.questions:
            # 组合题目文本和知识点进行向量化
            text = f"{q.get('question', '')} {q.get('knowledge', '')}"
            vec = get_embedding(text)
            vectors.append(vec)
            
        if vectors:
            vectors_np = np.array(vectors).astype('float32')
            self.index.add(vectors_np)
            
            # 保存索引
            if not os.path.exists(os.path.dirname(self.index_path)):
                os.makedirs(os.path.dirname(self.index_path))
            faiss.write_index(self.index, self.index_path)
            print(f"索引构建完成并保存，共 {self.index.ntotal} 条数据")

    def search(self, query_text, k=5):
        """
        根据文本搜索相似题目
        返回: (distances, indices) -> indices 对应 questions 列表的下标
        """
        if not self.index or self.index.ntotal == 0:
            return [], []

        if isinstance(query_text, (list, tuple)):
            query_text = " ".join([str(x) for x in query_text if x is not None])
            
        query_vec = get_embedding(query_text)
        query_vec_np = np.array([query_vec]).astype('float32')
        
        distances, indices = self.index.search(query_vec_np, k)
        
        # 转换结果为题目列表
        results = []
        for idx in indices[0]:
            if 0 <= idx < len(self.questions):
                results.append(self.questions[idx])
                
        return results

    def refresh(self):
        self._load_questions_from_db()
        self.build_index()

# 单例模式，方便外部调用
_db_instance = None

def get_vector_db():
    global _db_instance
    if _db_instance is None:
        _db_instance = VectorDB()
    return _db_instance
