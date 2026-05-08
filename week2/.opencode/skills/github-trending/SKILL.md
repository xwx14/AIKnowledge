---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

## 使用场景

- 定期采集 GitHub 热门开源项目，构建 AI/LLM/Agent 领域知识库
- 发现新兴技术趋势和值得关注的开源项目
- 为知识管理系统提供原始数据源

## 执行步骤

1. **搜索热门仓库**：通过 GitHub API 或 WebFetch 访问 GitHub Trending 页面，获取当前热门仓库列表
2. **提取信息**：从返回结果中提取仓库名称、URL、Star 数、主要编程语言、Topics/标签等关键信息
3. **过滤**：
   - ✅ 纳入：AI、LLM、Agent、Machine Learning、RAG 等相关项目
   - ❌ 排除：Awesome 列表、curated 集合类、个人博客/笔记类项目
4. **去重**：检查已有数据文件，去除已收录的重复仓库
5. **撰写中文摘要**：按公式 `项目名 + 做什么 + 为什么值得关注` 为每个项目编写一段简明的中文摘要
6. **排序取 Top15**：按 Star 数和近期增长趋势综合排序，选取前 15 个项目
7. **输出 JSON**：将结果写入 `knowledge/raw/github-trending-YYYY-MM-DD.json`

## 注意事项

- GitHub Trending 页面可能有反爬限制，建议设置合理的 User-Agent
- 过滤时需仔细判断项目是否真正属于 AI/LLM/Agent 领域
- 摘要应突出项目的独特价值，避免泛泛而谈
- 日期格式统一为 `YYYY-MM-DD`
- 若 API 调用失败，可降级使用 WebFetch 抓取页面内容

## 输出格式

```json
{
  "source": "github-trending",
  "skill": "github-trending",
  "collected_at": "YYYY-MM-DDTHH:mm:ssZ",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "项目名 + 做什么 + 为什么值得关注",
      "stars": 12345,
      "language": "Python",
      "topics": ["llm", "agent", "rag"]
    }
  ]
}
```
