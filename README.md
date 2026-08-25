# 基于大模型的智能习题推荐系统

这是一个基于 Flask + 向量检索（FAISS）+ DeepSeek 大模型的智能习题推荐系统。系统会基于用户做题记录生成学习画像（正确率、薄弱知识点、学科掌握情况），并支持题库筛选、AI 出题入库、AI 学习助手对话、管理后台与数据备份。

## 核心功能

- 智能推荐：基于薄弱知识点与检索结果生成推荐题单，并给出推荐理由
- AI 出题：调用 DeepSeek 生成新题并写入题库
- 题库与做题：题库筛选/搜索、答题与判题、错题回顾与历史记录
- 学习分析：仪表盘与统计页展示正确率、学科/知识点掌握情况
- 管理后台：用户/题库管理、审计日志、备份与恢复（需要管理员权限）

## 快速开始

### 1) 环境准备

- Python 3.8+

```bash
cd exam-recommend-system
pip install -r requirements.txt
```

### 2) 配置 DeepSeek（启用AI功能时必需）

当前版本通过代码文件读取 DeepSeek 配置，请打开 `rag/deepseek_api.py`：

- 将 `API_KEY` 替换为你自己的 DeepSeek API Key
- 当前默认模型为 `deepseek-v4-flash`（如需切换，可修改 `model` 字段）

### 3) 运行

```bash
python app.py
```

访问：<http://127.0.0.1:5000>

说明：

- 首次启动可能会下载 sentence-transformers 模型（用于向量化），需要联网
- 系统默认使用 SQLite 数据库文件存储数据（见下文“数据库与配置”）
- 未配置/不可用 DeepSeek Key 时，AI 出题/推荐理由/学习助手等能力会返回空结果或失败，但题库、做题、历史与统计等功能可正常使用

## 数据库与配置

### 环境变量

- Flask
  - `SECRET_KEY`：会话密钥（不设置则使用默认值）
- JWT（用于接口鉴权，主要用于 `/api/...`）
  - `JWT_SECRET`：JWT 密钥
  - `JWT_EXPIRE_HOURS`：过期小时数
- 数据库（见 `db_config.py`）
  - `DB_TYPE`：`sqlite`（默认）/ `postgresql` / `mysql`
  - SQLite：`DB_PATH`（可选，指定 DB 文件路径；不设置时默认 `data/exam_system.db`）
  - PostgreSQL / MySQL：
    - `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD`

### 默认数据库与表

- 默认 SQLite 文件：`exam-recommend-system/data/exam_system.db`
- 兼容旧路径：如果存在 `../data/exam_system.db`，系统会自动比较并优先选择数据更完整的那一个（见 `db_config.py` 的兼容逻辑）
- 主要表：`users`、`questions`、`user_records`、`audit_logs`

### 管理员账号

管理员账号:admin
密码：password123

注册的新用户默认 `role=user`。如需使用管理后台，可将某个用户提升为管理员：

- SQLite 示例：

```sql
UPDATE users SET role='admin' WHERE username='你的用户名';
```

## 向量索引（FAISS）

- 索引文件默认保存：`vector_store/faiss_index.bin`
- 当前向量库实现从数据库 `questions` 表读取题目构建索引（见 `rag/vector_db.py`）
  - 若题库为空，索引会是空索引，向量检索将返回空结果

## 备份

- 备份文件默认目录：`data/backups/`
- 管理后台提供备份/恢复/下载/删除入口（需要管理员权限），备份内容包含数据库与 `vector_store/` 索引文件

## 项目结构

```
exam-recommend-system
├─ app.py                 # Web 入口（页面路由 + 部分管理端备份接口）
├─ admin_routes.py        # 管理后台 API（/api/admin/...）
├─ auth.py                # JWT 与鉴权装饰器
├─ db_config.py           # 数据库连接/建表/连接池
├─ models.py              # 数据访问层（users/questions/user_records/audit_logs）
├─ backup.py              # 备份与恢复逻辑
├─ rag/                   # RAG 与 AI 能力（DeepSeek、Embedding、推荐、出题、对话）
├─ templates/             # Jinja2 模板（含 templates/admin/）
├─ static/                # 静态资源
├─ data/                  # SQLite DB 与备份目录（data/backups/）
└─ vector_store/          # FAISS 索引文件
```

## 注意事项

- 不要在仓库中提交真实的 API Key；当前版本需要直接修改 `rag/deepseek_api.py`，建议自行改造为环境变量读取
- MySQL 支持依赖 `pymysql`，属于可选能力；PostgreSQL 支持依赖 `psycopg2-binary`（requirements 已包含）

