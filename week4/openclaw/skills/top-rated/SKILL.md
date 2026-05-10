# Skill: top-rated

> 根据用户输入的关键字，在知识库中搜索匹配条目并按评分（score）降序返回最高评分项目。

## 触发条件

- 用户消息包含"最高评分""最高分""top rated""best""评分最高"等关键词
- 使用 `/toprated <关键词>` 命令

## 输入

- **keyword**（必填）：搜索关键字，用于匹配 `title`、`summary`、`description`、`tags` 字段
- **top_n**（可选）：返回结果数量，默认 5，最大 20

## 输出

按 `score` 降序排列的匹配条目列表，每条包含：

```json
{
  "title": "文章标题",
  "url": "来源链接",
  "score": 0.85,
  "summary": "中文摘要",
  "tags": ["标签1", "标签2"],
  "source": "github | rss",
  "collected_at": "采集时间"
}
```

## 工作流程

1. **解析输入**：从用户消息中提取搜索关键字和可选的 top_n 参数
2. **扫描知识库**：读取 `knowledge/articles/` 下所有 JSON 文件
3. **关键字匹配**：对每个条目的 `title`、`summary`、`description`、`tags` 做大小写不敏感的子串匹配
4. **排序筛选**：按 `score` 字段降序排序，取前 top_n 条
5. **格式化输出**：以 Markdown 列表格式返回结果

## 搜索脚本

调用方式：

```bash
python skills/top-rated/top-rated.py <keyword> [--top 5]
```

脚本输出 JSON 数组到 stdout，退出码 0 表示成功，1 表示无匹配结果。

## 数据源

- 路径：`knowledge/articles/*.json`（相对于 week4/ 目录）
- 条目格式：每个 JSON 文件包含 `id`、`title`、`url`、`summary`、`description`、`score`、`tags`、`source`、`collected_at` 字段

## 注意事项

- `score` 字段为浮点数（0.0 ~ 1.0 或 0 ~ 10），脚本需统一归一化后排序
- 未经过 LLM 分析的条目 `score` 为 0.0、`analyzed` 为 false，排序时排在最后
- 如果关键字为空，返回所有条目中评分最高的 top_n 条
