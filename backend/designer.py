from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from backend import config
from backend.model_gateway import ModelGateway
from backend.prompt_loader import PromptRepository

RAG_DIR = config.DESIGN_DIR / "rag"
QUESTIONNAIRE_DIR = config.DESIGN_DIR / "questionnaires"
EVENT_ID_PATTERN = re.compile(r"E\d{2,}")
MONTHS: list[str] = []


class DesignerAgent:
    """Designer creates the whole-game blueprint.

    The Designer may mark a turn as a measurement *candidate*, but the final
    plot/measurement decision is intentionally left to Controller semantic
    judgement after it has generated the concrete question stem.
    """

    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway or ModelGateway()
        self.rag = self._load_rag()
        self.questionnaire = self._load_questionnaire()
        self.prompts = PromptRepository(config.PROMPT_DIR)
        self.last_model_result = None

    @staticmethod
    def _load_rag() -> dict[str, Any]:
        def load(name: str, default: Any) -> Any:
            path = RAG_DIR / name
            if not path.exists():
                return default
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return default

        return {
            "world": load("world.json", []),
            "characters": load("characters.json", []),
            "events": load("events.json", []),
        }

    @staticmethod
    def _load_questionnaire() -> dict[str, Any]:
        path = QUESTIONNAIRE_DIR / "mssmhs.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def design(self, seed: int, preferences: dict[str, Any] | None = None) -> dict[str, Any]:
        preferences = preferences or {}
        if config.MODEL_PROVIDER == "mock":
            return self._local_design(seed, preferences)

        model_design = self._model_design(seed, preferences)
        if model_design and self.validate(model_design):
            model_design["generator"] = "llm"
            return model_design

        reason = self.last_model_result.error if self.last_model_result else "model returned an invalid design"
        if config.MODEL_FAILURE_POLICY == "fallback":
            fallback = self._local_design(seed, preferences)
            fallback["generator"] = "local-designer-rag-fallback"
            fallback["model_error"] = reason
            return fallback
        raise RuntimeError(f"Designer LLM generation failed: {reason}")

    def _model_design(self, seed: int, preferences: dict[str, Any]) -> dict[str, Any] | None:
        self.gateway.require_enabled()
        self.last_model_result = self.gateway.generate_json(
            self.prompts.load("designer"),
            {
                "seed": seed,
                "preferences": preferences,
                "schema": self.schema(),
                "questionnaire": self.questionnaire,
                "rag": self.rag,
            },
        )
        return self.last_model_result.data

    def _local_design(self, seed: int, preferences: dict[str, Any]) -> dict[str, Any]:
        rng = random.Random(seed)
        events = self.rag["events"]
        characters = self.rag["characters"]
        months = self._months()
        turn_bounds = self._turn_bounds()
        questionnaire_items = self._questionnaire_items()

        total_turns = rng.randint(turn_bounds["minimum"], turn_bounds["maximum"])
        chosen = self._expand_events(events, months, total_turns, rng)
        if not chosen:
            raise RuntimeError("local Designer has no eligible RAG events")

        roles = self._semantic_role_plan(chosen, len(questionnaire_items), rng)
        timeline = []
        measurement_index = 0
        for index, event in enumerate(chosen):
            people = [person for person in event.get("people", []) if str(person).startswith("npc_")]
            choices = self._blueprint_choices(event)
            narrative_role = roles[index]
            q_targets: list[dict[str, Any]] = []
            if narrative_role == "measurement_candidate":
                q_targets = self._questionnaire_targets(questionnaire_items, measurement_index)
                measurement_index += 1

            timeline.append(
                {
                    "index": index,
                    "month": event["month"],
                    "period": event.get("period", event.get("time_slot", "")),
                    "title": event["name"],
                    "tone": self._tone_for(event, narrative_role, rng),
                    "event_tags": event.get("tags", []),
                    "narrative_role": narrative_role,
                    "event_id": f"{event['id']}#{event.get('_beat', 1)}",
                    "source_event_id": event["id"],
                    "location": event.get("place", "校园"),
                    "time_slot": event.get("period", event.get("time_slot", "")),
                    "characters": people,
                    "summary": self._beat_summary(event, narrative_role),
                    "trigger": {
                        "required_events": sorted(set(EVENT_ID_PATTERN.findall(str(event.get("trigger", ""))))),
                        "relationship_conditions": [],
                        "source_text": self._trigger_text(event),
                    },
                    "choices": choices,
                    "controller_guidance": self._controller_guidance(narrative_role),
                    "measurement_targets": sorted({key for choice in choices for key in choice.get("signals", {})}),
                    "questionnaire_targets": q_targets,
                    "mandatory": index == len(chosen) - 1,
                }
            )

        npc_ids = {npc_id for event in chosen for npc_id in event.get("people", []) if str(npc_id).startswith("npc_")}
        if len(npc_ids) < 4:
            npc_ids.update(npc["id"] for npc in rng.sample(characters, min(4, len(characters))))
        npcs = [npc for npc in characters if npc["id"] in npc_ids]

        return {
            "schema_version": "1.0",
            "generator": "mock-designer-rag",
            "seed": seed,
            "title": rng.choice(["九月以后", "冬日回声", "因为有你", "放假前的最后一页"]),
            "world_span": {"start": "高一上学期九月", "end": "寒假一月", "months": 5},
            "turn_policy": {
                "decided_by": "designer_agent",
                "total_turns": len(timeline),
                "action_points_per_turn": rng.choice([2, 3, 3, 4]),
                "rationale": (
                    "依据五个月内校园事件的语义密度、人物线索、量表覆盖需求与叙事呼吸空间动态决定；"
                    "测量候选不少于原问卷 60 项，同时把新增回合优先留给 plot/bridge 承接上下文。"
                ),
            },
            "style": {
                "genre": "现实主义校园互动叙事",
                "dramatic_level": "克制",
                "pace": "细水长流",
                "replayability": "稳定骨架与事件抽样结合",
            },
            "phases": [
                {
                    "month": month,
                    "theme": self._month_theme(month),
                    "turn_count": sum(1 for item in timeline if item["month"] == month),
                    "turns": [item for item in timeline if item["month"] == month],
                }
                for month in months
            ],
            "timeline": timeline,
            "npcs": [
                {
                    "id": npc["id"],
                    "name": npc["name"],
                    "role": npc["identity"],
                    "traits": str(npc.get("personality", "")).split("、"),
                    "note": npc.get("semester_arc", ""),
                }
                for npc in npcs
            ],
            "stats": ["学业", "健康", "社交", "共情", "开放", "压力", "心情", "精力"],
            "measurement_dimensions": [
                "计划与责任",
                "坚持倾向",
                "社交主动",
                "关系信任",
                "合作友善",
                "情绪关照",
                "自我调节",
                "压力觉察",
                "开放探索",
                "行动自主",
            ],
            "questionnaire": {
                "id": self.questionnaire.get("id", "MSSMHS"),
                "name": self.questionnaire.get("name", "中学生心理健康量表"),
                "item_count": len(questionnaire_items),
                "factor_count": len(self.questionnaire.get("factors", [])),
                "source_file": self.questionnaire.get("source_file"),
            },
            "preferences": preferences,
        }

    def _expand_events(
        self,
        events: list[dict[str, Any]],
        months: list[str],
        total_turns: int,
        rng: random.Random,
    ) -> list[dict[str, Any]]:
        by_month = {month: [event for event in events if event.get("month") == month] for month in months}
        chosen: list[dict[str, Any]] = []
        used: set[str] = set()

        for month in months:
            pool = list(by_month[month])
            rng.shuffle(pool)
            made_progress = True
            while made_progress:
                made_progress = False
                for event in pool:
                    event_id = event.get("id")
                    if not event_id or event_id in used:
                        continue
                    if month != "一月" and "寒假" in json.dumps(event, ensure_ascii=False):
                        continue
                    deps = set(EVENT_ID_PATTERN.findall(str(event.get("trigger", ""))))
                    if deps and not deps.intersection(used):
                        continue
                    chosen.append(event)
                    used.add(event_id)
                    made_progress = True

        chosen.sort(key=lambda event: (months.index(event["month"]), str(event.get("id", ""))))
        if not chosen:
            return []

        month_targets = self._month_targets(total_turns, rng)
        expanded: list[dict[str, Any]] = []
        for month in months:
            month_events = [event for event in chosen if event.get("month") == month]
            if not month_events:
                month_events = [chosen[0]]
            for offset in range(month_targets[month]):
                source = month_events[offset % len(month_events)]
                expanded.append({**source, "_beat": offset // len(month_events) + 1})
        return expanded[:total_turns]

    def _semantic_role_plan(
        self,
        events: list[dict[str, Any]],
        questionnaire_count: int,
        rng: random.Random,
    ) -> list[str]:
        total = len(events)
        if total == 0:
            return []

        minimum_measurement = min(total, max(60, questionnaire_count))
        desired_measurement = max(minimum_measurement, round(total * rng.uniform(0.48, 0.56)))
        measurement_count = min(total, desired_measurement)
        non_measurement_count = total - measurement_count

        semantic_scores = [
            (index, self._measurement_affinity(event), self._bridge_affinity(event))
            for index, event in enumerate(events)
        ]

        protected_intro = set(range(min(5, total)))
        measurement_candidates = [
            row for row in sorted(semantic_scores, key=lambda item: (-item[1], item[0]))
            if row[0] not in protected_intro
        ]
        if len(measurement_candidates) < measurement_count:
            measurement_candidates = sorted(semantic_scores, key=lambda item: (-item[1], item[0]))

        measurement_indices = {index for index, _, _ in measurement_candidates[:measurement_count]}
        roles = ["measurement_candidate" if index in measurement_indices else "plot" for index in range(total)]

        bridge_target = max(0, min(non_measurement_count, round(total * rng.uniform(0.24, 0.34))))
        bridge_candidates = [
            row for row in sorted(semantic_scores, key=lambda item: (-item[2], item[0]))
            if row[0] not in measurement_indices
        ]
        for index, _, _ in bridge_candidates[:bridge_target]:
            roles[index] = "bridge"

        for index in range(min(5, total)):
            if roles[index] == "measurement_candidate" and total - measurement_count > index:
                replacement = next(
                    (
                        candidate_index
                        for candidate_index in sorted(measurement_indices, reverse=True)
                        if candidate_index >= 5
                    ),
                    None,
                )
                if replacement is not None:
                    roles[replacement] = "plot"
                    measurement_indices.remove(replacement)
                    roles[index] = "bridge" if index in {1, 3} else "plot"

        return roles

    @staticmethod
    def _measurement_affinity(event: dict[str, Any]) -> int:
        text = json.dumps(
            {
                "type": event.get("type", ""),
                "name": event.get("name", ""),
                "summary": event.get("summary", ""),
                "tags": event.get("tags", []),
                "options": event.get("options", []),
            },
            ensure_ascii=False,
        )
        keywords = [
            "考试",
            "作业",
            "成绩",
            "压力",
            "矛盾",
            "犹豫",
            "边界",
            "合作",
            "社交",
            "表达",
            "适应",
            "担心",
            "失眠",
            "拖延",
            "评价",
            "冲突",
            "选择",
            "自责",
            "紧张",
            "求助",
        ]
        return sum(1 for word in keywords if word in text)

    @staticmethod
    def _bridge_affinity(event: dict[str, Any]) -> int:
        text = json.dumps(
            {
                "type": event.get("type", ""),
                "name": event.get("name", ""),
                "summary": event.get("summary", ""),
                "tags": event.get("tags", []),
                "period": event.get("period", ""),
                "place": event.get("place", ""),
            },
            ensure_ascii=False,
        )
        keywords = [
            "相识",
            "日常",
            "宿舍",
            "午休",
            "熄灯",
            "返校",
            "路上",
            "食堂",
            "图书馆",
            "天气",
            "寒假",
            "聊天",
            "观察",
            "整理",
            "班会",
            "社团",
        ]
        return sum(1 for word in keywords if word in text)

    @staticmethod
    def _tone_for(event: dict[str, Any], role: str, rng: random.Random) -> str:
        if role == "bridge":
            return rng.choice(["安静", "温暖", "清淡", "松弛"])
        if role == "plot":
            return rng.choice(["轻快", "清淡", "温暖", "微涩"])
        if DesignerAgent._measurement_affinity(event) >= 3:
            return rng.choice(["微涩", "紧张", "克制"])
        return rng.choice(["清淡", "微涩", "安静"])

    @staticmethod
    def _beat_summary(event: dict[str, Any], role: str) -> str:
        summary = event.get("summary", "")
        beat = event.get("_beat", 1)
        if beat <= 1:
            return summary
        if role == "bridge":
            return f"{summary} 这一回合不急于测量，而是展开前因后果、人物反应与日常细节。"
        if role == "plot":
            return f"{summary} 这一回合主要推进关系与情境，让玩家理解事情为什么会发展到这里。"
        return f"{summary} 这一回合在自然情节中嵌入一个可观察的心理行为候选点。"

    @staticmethod
    def _trigger_text(event: dict[str, Any]) -> str:
        if event.get("_beat", 1) == 1:
            return event.get("trigger", "无")
        return f"延展自 {event['id']} 的第 {event.get('_beat')} 个语义节拍，而非固定旬度切分。"

    @staticmethod
    def _controller_guidance(role: str) -> dict[str, list[str]]:
        common_forbidden = [
            "临床诊断、人格定性、治疗建议。",
            "奇幻、阴谋、极端暴力、救世主叙事。",
            "替玩家追加新的重大决定或改变总回合数。",
        ]
        if role == "measurement_candidate":
            must_preserve = [
                "本回合只是测量候选，Controller 必须先生成题干，再按题干语义判断 plot/measurement。",
                "如果题干没有足够可观察心理行为证据，应降级为 plot。",
                "选项必须像校园情境中的自然反应，不能像量表选项。",
            ]
        elif role == "bridge":
            must_preserve = [
                "本回合优先承担叙事承接、人物余波和生活细节。",
                "默认不要测量，除非 Controller 生成的题干自然出现强行为证据。",
                "选项要帮助玩家表达态度、调整节奏或维系关系。",
            ]
        else:
            must_preserve = [
                "本回合优先推进剧情与人物关系。",
                "保持地点、时间、人物和事件前置。",
                "不要为了覆盖量表而打断场景节奏。",
            ]
        return {
            "must_preserve": must_preserve,
            "may_expand": [
                "补充天气、教室、宿舍、操场、食堂等具体生活细节。",
                "让 NPC 按其 speech 和 semester_arc 给出短反应。",
                "根据玩家自由输入在 choices 边界内做保守解释。",
            ],
            "forbidden": common_forbidden,
        }

    @staticmethod
    def _blueprint_choices(event: dict[str, Any]) -> list[dict[str, Any]]:
        signal_bank = [
            ("conscientiousness", {"academic": 1, "stress": 1}),
            ("social_trust", {"social": 1, "mood": 1}),
            ("self_regulation", {"stress": -1, "energy": 1}),
            ("empathy", {"empathy": 1, "social": 1}),
            ("openness", {"openness": 1, "mood": 1}),
            ("agency", {"openness": 1, "stress": -1}),
        ]
        raw_options = list(event.get("options", []))[:4] or ["先观察局面", "主动开口", "把事情做完"]
        consequences = list(event.get("consequences", []))
        choices = []
        for idx, text in enumerate(raw_options):
            signal, effects = signal_bank[idx % len(signal_bank)]
            choices.append(
                {
                    "id": f"{event.get('id', 'event').lower()}_choice_{idx + 1}",
                    "text": text,
                    "immediate_effect": consequences[idx] if idx < len(consequences) else "留下一个温和、可继续发展的后果。",
                    "effects": effects,
                    "signals": {signal: 1.0},
                    "relationship_effects": {
                        person: 1 for person in event.get("people", []) if str(person).startswith("npc_")
                    }
                    if idx in {1, 3}
                    else {},
                }
            )
        while len(choices) < 3:
            idx = len(choices)
            signal, effects = signal_bank[idx % len(signal_bank)]
            choices.append(
                {
                    "id": f"{event.get('id', 'event').lower()}_choice_{idx + 1}",
                    "text": ["先观察局面", "主动开口", "把事情做完"][idx],
                    "immediate_effect": "让局面继续保持在现实可控的范围内。",
                    "effects": effects,
                    "signals": {signal: 1.0},
                    "relationship_effects": {},
                }
            )
        return choices

    def _questionnaire_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for factor in self.questionnaire.get("factors", []):
            for item in factor.get("items", []):
                items.append(
                    {
                        "factor_id": factor.get("id"),
                        "factor_name": factor.get("name"),
                        "item_id": item.get("id"),
                        "item_text": item.get("text"),
                    }
                )
        return items

    @staticmethod
    def _questionnaire_targets(items: list[dict[str, Any]], index: int) -> list[dict[str, Any]]:
        if not items:
            return []
        primary = items[index % len(items)]
        secondary = items[(index * 7 + 3) % len(items)]
        targets = [primary]
        if secondary.get("item_id") != primary.get("item_id"):
            targets.append(secondary)
        return targets

    @staticmethod
    def validate(design: dict[str, Any]) -> bool:
        try:
            timeline = design["timeline"]
            policy = design["turn_policy"]
            months = {turn["month"] for turn in timeline}
            required = {
                "location",
                "time_slot",
                "characters",
                "summary",
                "trigger",
                "choices",
                "controller_guidance",
                "narrative_role",
            }
            executable = all(
                required.issubset(turn)
                and len(turn.get("choices", [])) >= 3
                and turn.get("narrative_role") in {"plot", "bridge", "measurement_candidate"}
                for turn in timeline
            )
            bounds = DesignerAgent._turn_bounds()
            return (
                isinstance(timeline, list)
                and bounds["minimum"] <= len(timeline) <= bounds["maximum"]
                and policy["total_turns"] == len(timeline)
                and policy["decided_by"] == "designer_agent"
                and set(DesignerAgent._months()).issubset(months)
                and executable
            )
        except (KeyError, TypeError):
            return False

    @staticmethod
    def _month_targets(total: int, rng: random.Random) -> dict[str, int]:
        months = DesignerAgent._months()
        weights = [1.15, 1.05, 1.1, 1.05, 0.65][: len(months)]
        raw = [max(1, round(total * weight / sum(weights))) for weight in weights]
        while sum(raw) < total:
            raw[rng.randrange(len(raw))] += 1
        while sum(raw) > total:
            candidates = [idx for idx, value in enumerate(raw) if value > 1]
            raw[rng.choice(candidates)] -= 1
        return dict(zip(months, raw))

    def _month_theme(self, month: str) -> str:
        for row in self.rag["world"]:
            if row.get("name") == "月份节奏":
                return row.get("content", "五个月校园生活")
        return "五个月校园生活"

    @staticmethod
    def _months() -> list[str]:
        schema = DesignerAgent.schema()
        try:
            return schema["properties"]["timeline"]["items"]["properties"]["month"]["enum"]
        except KeyError:
            return ["九月", "十月", "十一月", "十二月", "一月"]

    @staticmethod
    def _turn_bounds() -> dict[str, int]:
        schema = DesignerAgent.schema()
        try:
            policy = schema["properties"]["turn_policy"]["properties"]["total_turns"]
            return {"minimum": int(policy["minimum"]), "maximum": int(policy["maximum"])}
        except KeyError:
            return {"minimum": 120, "maximum": 150}

    @staticmethod
    def schema() -> dict[str, Any]:
        path = config.DESIGN_DIR / "design.schema.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"required": ["title", "world_span", "turn_policy", "timeline", "npcs"]}


MONTHS = DesignerAgent._months()
