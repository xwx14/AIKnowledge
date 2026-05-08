---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

## 使用场景

- 对已采集的 GitHub 热门项目进行深度技术分析与价值评估
- 从大量开源项目中提炼技术趋势和核心洞察
- 为技术决策和学习方向提供结构化参考

## 执行步骤

1. **读取源数据**：读取 `knowledge/raw/` 目录下最新的采集文件（如 `github-trending-YYYY-MM-DD.json`）
2. **逐条深度分析**：对每个项目执行以下分析：
   - **精简摘要**：用不超过 50 字概括项目核心
   - **技术亮点**：列出 2-3 个具体亮点，用事实和数据说话，避免空泛描述
   - **评分**：按评分标准给出 1-10 分，并附具体理由
   - **标签建议**：补充或优化项目的技术标签
3. **趋势发现**：分析项目间的共同主题、技术栈共性、新兴概念或模式
4. **输出分析结果**：将完整分析结果输出为 JSON 文件

## 注意事项

- 摘要必须精炼，严格控制在 50 字以内
- 技术亮点需基于项目 README、文档或实际代码，用事实支撑
- 评分必须严格遵守约束：15 个项目中 9-10 分不超过 2 个
- 趋势发现应聚焦可验证的模式，而非主观推测
- 输出文件命名：`knowledge/analysis/tech-summary-YYYY-MM-DD.json`

## 评分标准

| 分数 | 标准 | 说明 |
|------|------|------|
| 9-10 | 改变格局 | 开创性技术，可能重塑行业方向 |
| 7-8  | 直接有帮助 | 解决实际问题，可立即应用到工作中 |
| 5-6  | 值得了解 | 有参考价值，但非紧迫需求 |
| 1-4  | 可略过 | 成熟技术重复实现，或价值有限 |

## 输出格式

```json
{
  "source": "tech-summary",
  "skill": "tech-summary",
  "analyzed_at": "YYYY-MM-DDTHH:mm:ssZ",
  "source_file": "github-trending-YYYY-MM-DD.json",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "50字以内的核心摘要",
      "highlights": ["亮点1：具体事实或数据", "亮点2：具体事实或数据"],
      "score": 8,
      "score_reason": "评分理由",
      "tags": ["llm", "agent", "framework"]
    }
  ],
  "trends": {
    "common_themes": ["主题1", "主题2"],
    "emerging_concepts": ["新概念1", "新概念2"],
    "summary": "整体趋势分析总结"
  }
}
```
