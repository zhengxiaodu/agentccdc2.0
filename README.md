# AI问答系统

基于AgentScope 2.0构建的AI问答系统，支持流式返回和技能调用。

## 功能特性

- 基于AgentScope 2.0的AI Agent服务
- 流式响应返回
- 技能配置文件管理
- 博查搜索技能集成

## 环境要求

- Python >= 3.11
- OpenAI API Key

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置环境变量

```bash
cp .env.example .env
# 修改 .env 文件，添加你的 API Key
```

## 启动服务

```bash
python app.py
```

## API接口

### 1. 健康检查

```
GET /health
```

### 2. 列出技能

```
GET /skills
```

### 3. 聊天接口（流式）

```
POST /chat
Content-Type: application/json

{
    "messages": [
        {
            "role": "user",
            "content": "今天天气怎么样？"
        }
    ],
    "session_id": "optional-session-id",
    "user_id": "optional-user-id"
}
```

## 技能配置

技能配置文件位于 `config/skill_config.yml`，格式如下：

```yaml
skills:
  - name: skill_name
    module: module.path
    function: function_name
    description: "技能描述"
```

## 项目结构

```
├── app.py                    # 主服务文件
├── config/
│   └── skill_config.yml      # 技能配置文件
├── skills/
│   └── bocha_search.py       # 博查搜索技能
├── requirements.txt          # 依赖清单
├── .env.example              # 环境变量示例
└── README.md                 # 项目说明
```