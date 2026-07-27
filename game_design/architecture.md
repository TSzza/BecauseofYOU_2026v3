# 线性多 Agent 架构

```text
需求与研究约束
      |
Designer Agent -- 每局生成动态设计、时间线、NPC、测量覆盖
      |
结构化设计 JSON / RAG 索引
      |
Controller Agent -- 读取设计 + 当前状态 + 最近记忆，生成回合并记录行为
      |
session JSON + append-only JSONL 行为轨迹
      |
Critic Agent -- 文本质量检查 + 行为证据聚合 + 非诊断性反馈
```

Controller 不修改 Designer 的总回合数，只在设计时间线内推进。Critic 不直接控制剧情，避免测评目标污染玩家选择。

