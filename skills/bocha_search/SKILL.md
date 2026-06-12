---
name: bocha_search
description: 使用博查搜索引擎获取网上的知识和最新信息。当用户询问最新消息、实时信息、网络搜索相关内容时使用此技能。
license: Apache-2.0
compatibility: Requires curl installed
metadata:
  author: AI Assistant
  version: "1.0"
  tags:
    - search
    - web
    - news
    - information
---

# 博查搜索技能

## 功能说明

本技能通过博查搜索API获取互联网上的最新知识和信息。

## 使用方法

当用户需要获取实时信息时，使用 bash 工具执行以下 curl 命令：

```bash
curl -s -X POST https://api.bocha.com/v1/search \
  -H "Authorization: Bearer sk-b2456820150d48a68c15a0f76ded1eef" \
  -H "Content-Type: application/json" \
  -d '{"query": "搜索关键词", "limit": 5}'
```

### 参数说明

| 参数 | 说明 |
|------|------|
| query | 用户的搜索关键词 |
| limit | 返回结果数量，建议 5-10 |

### 输出示例

```json
{
  "results": [
    {
      "title": "文章标题",
      "summary": "文章摘要",
      "url": "来源链接"
    }
  ]
}
```

## 使用示例

### 示例1：搜索科技新闻
```
用户: 今天有什么科技新闻？
Agent: 使用 bash 工具执行：
curl -s -X POST https://api.bocha.com/v1/search \
  -H "Authorization: Bearer sk-b2456820150d48a68c15a0f76ded1eef" \
  -H "Content-Type: application/json" \
  -d '{"query": "科技新闻", "limit": 5}'
```

### 示例2：查询实时信息
```
用户: 比特币现在价格多少？
Agent: 使用 bash 工具执行：
curl -s -X POST https://api.bocha.com/v1/search \
  -H "Authorization: Bearer sk-b2456820150d48a68c15a0f76ded1eef" \
  -H "Content-Type: application/json" \
  -d '{"query": "比特币价格", "limit": 3}'
```

## 注意事项

1. 查询词应简洁明了
2. 返回结果包含 JSON 格式数据，需要解析后用自然语言回复用户
3. 如果网络错误，应向用户说明情况
