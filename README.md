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

技能配置文件位于 `config/skill_config.yml`，支持两种配置方式：

### 方式1：技能目录（推荐）
```yaml
skills:
  - name: bocha_search
    directory: skills/bocha_search
    description: "使用博查搜索引擎获取网上的知识和最新信息"
```

### 方式2：单个工具函数
```yaml
skills:
  - name: custom_tool
    module: skills.custom
    function: custom_function
    description: "自定义工具描述"
```

## 技能目录结构

每个技能是一个目录，必须包含 `SKILL.md` 文件：

```
skills/
└── bocha_search/
    ├── SKILL.md           # 技能描述文件（必需）
    └── bocha_search.py   # 技能实现代码
```

### SKILL.md 格式

SKILL.md 文件包含 YAML frontmatter 和 Markdown 指令：

```markdown
---
name: skill-name
description: 技能描述，告知Agent何时使用此技能
license: Apache-2.0
compatibility: Requires Python 3.10+
metadata:
  author: 作者
  version: "1.0"
---

# 技能名称

## 功能说明
...

## 使用方法
...

## 注意事项
...
```

## 项目结构

```
├── app.py                    # 主服务文件
├── config/
│   └── skill_config.yml      # 技能配置文件
├── skills/
│   └── bocha_search/         # 博查搜索技能目录
│       ├── SKILL.md          # 技能描述文件
│       └── bocha_search.py   # 技能实现代码
├── requirements.txt          # 依赖清单
├── .env.example              # 环境变量示例
└── README.md                 # 项目说明
```