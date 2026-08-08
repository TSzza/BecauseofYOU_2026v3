# Narrative NLP v4：双索引知识图谱预处理规范

本文档是当前实现的唯一工程说明。它描述 Designer 之前的确定性 NLP 层：输入一部小说，输出可追溯的 World Line、Character Lines、Plot Events、情绪状态和知识图谱，供 Designer/Controller 二次生成。实现不依赖大模型；需要语义补全的字段通过 `handoff.llm_required_fields` 显式交接


## 1. 总体目标与数据流

```text
原文
 -> _book_body：去 Gutenberg 头尾和注释，记录 source offset
 -> _sentences：句切分、原文 span
 -> _extract_times：时间候选与 discourse boundary
 -> _extract_entities：人物/地点/专名 mention
 -> _extract_events：动作触发词 -> World Event
 -> _order_events：时间约束可用时排序，否则保留篇章顺序
 -> _link_cross_event_causes：跨事件情绪原因候选
 -> _resolve_character_identities：canonical alias / alias candidates / unnamed roles
 -> _merge_plot_events：World Event -> Plot Event 聚合
 -> _build_character_lines：人物状态线，复用 world_event_id
 -> _build_knowledge_graph：节点、索引边和证据边
 -> UTF-8 JSON
```

核心原则：所有抽取和推断都保留 `source_span`、`fill_mode`、`confidence`；候选关系不能冒充原文事实。

## 2. 代码模块

| 文件 | 职责 |
|---|---|
| `pipeline.py` | 主编排、句切分、时间/实体/事件抽取、别名、Plot 聚合、人物线和 KG |
| `affect.py` | 中英文现代/古典情绪词、行为/生理线索、否定、强度、VAD、通道和句内原因 |
| `models.py` | `SourceSpan`、`TimeMention`、`EntityMention`、`EventItem`、`CharacterLineItem` 数据模型 |
| `audit_affect_batch.py` | 批处理结果的结构审计、span/引用/连续性检查和统计汇总 |
| `tests/test_character_extraction.py` | 14 个回归测试，覆盖人物、别名候选、Plot 聚合、情绪和偏移 |
| `batch_results_zh_v4/` | 10 篇中文小说 JSON |
| `batch_results_en_v4/` | 10 篇英文小说 JSON |
| `affect_batch_audit_v4.json` | 20 篇汇总审计结果 |

## 3. 抽取算法详述

### 3.1 文本和时间

句切分保留原始字符位置，`source.indexed_start/indexed_end` 将清理后的正文映射回原文。时间规则覆盖章节、绝对日期、相对日/周/年、昼夜、季节、月份、校园节点及英文对应表达；带有明确时间锚点但没有动作词的句子也会保留为事件，避免闪回和转场被丢弃。`LOCAL_TIME_BOUNDARY_RE` 识别“次日、后来、之后、当晚”等硬边界。事件同时保留 `discourse_sequence` 和 `story_sequence`，并标记 `story_time_status=anchored|candidate`。

### 3.2 实体与人物

中文姓名规则结合姓氏表、关系上下文、jieba 词性和停用词；英文使用大写专名和角色词；地点使用中英文地点词表。每个 mention 包含 `entity_id/entity_type/text/sentence_index/start/end/confidence`。代词不直接建立人物实体，未命名角色只形成文档内链。

### 3.3 World Event

句子含中英文动作触发词、明确时间锚点或情绪证据时生成事件。事件包含：

- `event_id`, `sequence`, `source_span`
- `time`: raw/normalized/kind/confidence
- `space`: location candidates
- `event`: `text`, `trigger`, `summary` 占位、`narrative_function` 占位、`affect`
- `participants`, `world_state`, `source`
- `discourse`: 引语、说话人候选和叙事视角通道

### 3.4 Plot Event 聚合

聚合条件为：相邻句且没有时间边界并满足词汇、触发词或人物连续性，或在 3 句窗口内共享人物/地点且满足语义连续性。时间边界优先级最高。Plot Event 保留 `member_world_event_ids`、首尾 span、参与者、地点和 `affective_context`；KG 为每个成员建立 `aggregates` 边。因此压缩只改变叙事层级，不删除 World Event。

### 3.5 情绪证据与 VAD

`AffectAnalyzer` 使用三层证据：明确情绪词（`fill_mode=extract`）、行为/生理线索（`fill_mode=infer`）和句内因果触发。每条表达记录：

```json
{
  "holder_candidates": ["C001"],
  "channel": "narration|dialogue|internal|action",
  "evidence_type": "emotion_word|behavioral_cue",
  "text": "发抖",
  "emotion": "fear",
  "vad": {"valence": 0.15, "arousal": 0.82, "dominance": 0.17},
  "negated": false,
  "intensity_modifier": 1.0,
  "source_span": {"start": 10, "end": 12, "text": "发抖"},
  "fill_mode": "infer",
  "confidence": 0.66
}
```

否定会反转 valence 并降低置信度；强度词按因子调整 VAD。句内情绪聚合为 `atmosphere.vad`、`emotion_distribution` 和 `confidence`。

### 3.6 情绪主体绑定

先把句内所有人物 mention 作为 `holder_candidates`；若情绪证据到最近人物的距离明显小于第二近人物，则设置 `nearest_same_sentence_mention`；距离接近则保留 `ambiguous_same_sentence_mentions`。省略主语、自由间接引语和长距离共指不强行猜测。

### 3.7 跨事件情绪原因

对每个有情绪证据的事件检查前 3 个事件：显式“因为/由于/看到/得知/because”等标记、共同人物、相邻顺序共同决定候选分数。输出嵌入情绪对象的 `cross_event_cause_candidates`，并在 KG 中建立 `possible_emotion_cause` 边，属性为 `fill_mode=infer`、`requires_review=true`。

### 3.8 别名、称谓和未命名角色

显式等价句式“又名、又称、即、本名为、原名为”和括号等价，且两端实体均被识别时才进入 `canonical_alias_groups`。共享姓氏、单字简称、职衔接近只进入 `alias_candidates`。亲属、职业、身份称谓生成 `unnamed_role_chains`，范围限定在当前文档。

## 4. JSON 生成物结构

顶层字段：

| 字段 | 内容 |
|---|---|
| `schema_version` | 当前为 `nlp-index-0.1` |
| `source` | source_id、原文字符数、索引正文起止偏移 |
| `world_profile` | 人物/地点/时间等世界候选摘要 |
| `world_line` | `events`、`plot_events`、`affective_summary` |
| `character_profiles` | canonical 人物实体及出现统计 |
| `character_resolution` | alias groups、候选、未命名角色链、审核策略 |
| `character_lines` | 每个人物的事件序列和心理状态转移 |
| `knowledge_graph` | nodes 与 edges |
| `indexes` | 时间、实体、事件数量、未解析代词统计 |
| `handoff` | Designer 需要 LLM 补全的字段和证据政策 |

Character Line item 的关键字段是 `character_id`、`world_event_id`、`role`、`source_span`、`action`、`perception`、`psychology.affect.before/during/after/delta`、`relationships` 和 `source`。状态连续性要求上一项 `after` 等于下一项 `before`。

KG 节点类型包括 `world_event`、`plot_event`、`character`、`location` 等；边至少包括 `aggregates`、人物关系、`possible_alias`、`possible_emotion_cause`。所有边都指向已存在节点。

## 5. Designer 交接

NLP 层只负责证据约束的结构化抽取；以下字段留给 Designer/LLM：`event.summary`、`event.narrative_function`、`event.causes`、`character.motivation`、`character.emotion`、`character.relationship_changes`、`adaptation.bridge_content`。LLM 新填字段必须同时给出 `source_span` 和 `fill_mode`（`summarize/adapt/infer/unresolved`）。Designer 应优先读取 `world_line.plot_events`，再沿 `member_world_event_ids` 回查原文。

Controller 可以直接使用确定性锚点生成基础剧情树，但必须把 `candidate`、`infer`、`possible_*` 和 `requires_review` 当作候选而不是事实。开放式文学解释、深层动机、象征/反讽、心理测量映射和游戏分支创作仍交给 Designer/LLM。

## 6. 20 篇实验与审计

`affect_batch_audit_v4.json` 由审计脚本读取 20 个原始文本和 20 个 JSON 重新计算，不是手工填写。

| 指标 | v3 | v4 |
|---|---:|---:|
| World Events | 125,647 | 126,216 |
| Plot Events | 125,254 | 109,884 |
| Plot 合并减少 | 393 | 16,332 |
| 情绪事件 | 9,875 | 10,917 |
| 情绪证据 | 10,373 | 11,450 |
| 中文加权情绪覆盖率 | 4.31% | 5.32% |
| 跨事件情绪原因候选 | 0 | 1,452 |
| 悬空引用 / span 错误 / 状态错误 | 0 / 0 / 0 | 0 / 0 / 0 |

结构审计逐本检查：情绪 schema、Plot 情绪上下文、世界摘要、人物情绪 schema、人物摘要、事件引用、原文 span、状态连续性和 Plot-KG 锚点。运行时 `indexes.consistency_audit` 进一步检查 Plot/Character 对 World Event 的覆盖、时间序列冲突和未引用事件。历史 20/20 结果结构分数为 1.0；当前 17 个单元测试全部通过。当前没有人工 gold set，故不能据此声称文学语义 precision/recall 已达到目标。

## 7. 已知边界

中文古典隐含情绪、无明确主体的情绪、省略主语和自由间接引语仍会漏检或保留候选；canonical alias 仅在显式证据下确认；跨事件原因仍是候选 ECPE。下一阶段应加入中文文学情绪模型、语义角色标注/共指模型、时间约束图、真正的 ECPE 模型和人工 gold set，并将 LLM 作为有证据引用的复核层。

## 8. 运行命令

```powershell
python -m unittest discover -s narrative_nlp\\tests -v
python narrative_nlp\\audit_affect_batch.py
```
