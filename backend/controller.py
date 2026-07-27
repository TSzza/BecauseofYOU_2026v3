from __future__ import annotations

import copy
import hashlib
import json
import random
import time
import uuid
from pathlib import Path
from typing import Any

from backend import config
from backend.critic import CriticAgent, clamp
from backend.designer import DesignerAgent
from backend.model_gateway import ModelGateway
from backend.prompt_loader import PromptRepository


class ControllerAgent:
    def __init__(self, session_dir: Path = config.SESSION_DIR) -> None:
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.designer = DesignerAgent()
        self.gateway = ModelGateway()
        self.prompts = PromptRepository(config.PROMPT_DIR)
        self.critic = CriticAgent(self.gateway, self.prompts)

    def create_session(self, seed: int | None = None, name: str | None = None, preferences: dict[str, Any] | None = None) -> dict[str, Any]:
        seed = seed if seed is not None else random.SystemRandom().randint(1, 99999999)
        rng = random.Random(seed)
        design = self.designer.design(seed, preferences)
        profile = {"name": name or rng.choice(["林见夏", "陈听澜", "许朝雨", "周予宁"]), "gender": rng.choice(["女", "男"]), "family": rng.choice(["普通双职工家庭", "与祖辈共同生活", "小城个体经营家庭", "教师家庭"]), "traits": rng.sample(["谨慎", "温和", "好奇", "慢热", "认真", "随和"], 2), "class_name": f"高一（{rng.randint(1, 6)}）班"}
        state = {
            "session_id": uuid.uuid4().hex[:12], "seed": seed, "created_at": time.time(), "turn": 0,
            "ap": design["turn_policy"]["action_points_per_turn"], "finished": False, "design": design, "profile": profile,
            "stats": {"academic": rng.randint(52, 68), "health": rng.randint(68, 82), "social": rng.randint(42, 62), "empathy": rng.randint(50, 70), "openness": rng.randint(45, 68), "stress": 12, "mood": 66, "energy": 76},
            "relationships": {npc["id"]: {"friendship": rng.randint(2, 8), "impression": "刚刚认识"} for npc in design["npcs"]},
            "signals": {key: 0.0 for key in ["conscientiousness", "persistence", "extraversion", "social_trust", "agreeableness", "empathy", "self_regulation", "stress_awareness", "openness", "agency"]},
            "turn_setups": {},
            "history": [],
        }
        self._save(state)
        return self.view(state)

    def load(self, session_id: str) -> dict[str, Any]:
        path = self.session_dir / f"{session_id}.json"
        if not path.exists():
            raise KeyError("session not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        total = state["design"]["turn_policy"]["total_turns"]
        index = min(state["turn"], total - 1)
        scene = copy.deepcopy(state["design"]["timeline"][index])
        setup = self._ensure_turn_setup(state)
        scene["intro"] = setup.get("question") or self._intro(scene)
        scene["turn_setup"] = setup
        scene["progress"] = round(state["turn"] / total * 100)
        return {**state, "scene": scene, "npcs": state["design"]["npcs"], "options": [] if state["finished"] else setup.get("options", []), "critic_preview": self.critic.evaluate(state)}

    def act(self, session_id: str, action_id: str, free_text: str = "", hesitation_ms: int = 0) -> dict[str, Any]:
        state = self.load(session_id)
        if state["finished"]:
            raise ValueError("game already finished")
        setup = self._ensure_turn_setup(state)
        selected = self._resolve(action_id, free_text, setup)
        before = copy.deepcopy(state["stats"])
        rng = random.Random(self._stable_seed(state, selected["id"]))
        npc = rng.choice(state["design"]["npcs"])
        selected["effects"] = self._numeric_map(selected.get("effects", {}))
        selected["signals"] = self._numeric_map(selected.get("signals", {}))
        for key, delta in selected["effects"].items():
            state["stats"][key] = clamp(state["stats"].get(key, 50) + delta)
        for key, delta in selected["signals"].items():
            state["signals"][key] = round(state["signals"].get(key, 0) + delta, 2)
        relation_effects = selected.get("relationship_effects", {})
        if isinstance(relation_effects, dict):
            for npc_id, delta in relation_effects.items():
                if npc_id in state["relationships"] and isinstance(delta, (int, float)):
                    relation = state["relationships"][npc_id]
                    relation["friendship"] = clamp(relation["friendship"] + delta, -100, 100)
                    relation["impression"] = rng.choice(["觉得你很可靠", "愿意和你多说几句", "记住了这次自然的相处"])
        state["ap"] -= 1
        record = {"timestamp": time.time(), "turn": state["turn"], "action_id": selected["id"], "action_label": selected["label"], "free_text": free_text[:300], "hesitation_ms": max(0, hesitation_ms), "effects": selected["effects"], "before": before, "after": copy.deepcopy(state["stats"]), "npc": npc["name"] if selected["source_id"] in {"social", "help"} else None, "question": setup.get("question"), "semantic_judgement": setup.get("semantic_judgement")}
        controller_result = self._controller_result(state, selected, npc, free_text)
        narrative = controller_result.get("narrative") or self._narrative(selected, npc, free_text)
        record["narrative"] = narrative
        state["history"].append(record)
        advanced = False
        if state["ap"] <= 0:
            advanced = True
            state["turn"] += 1
            total = state["design"]["turn_policy"]["total_turns"]
            if state["turn"] >= total:
                state["turn"], state["finished"], state["ap"] = total, True, 0
            else:
                state["ap"] = state["design"]["turn_policy"]["action_points_per_turn"]
                state["stats"]["energy"] = clamp(state["stats"]["energy"] + 2)
        self._save(state)
        result = self.view(state)
        result["last_result"] = {"narrative": narrative, "changes": self._changes(before, record["after"]), "advanced": advanced, "record": record, "llm": controller_result.get("llm")}
        return result

    def report(self, session_id: str) -> dict[str, Any]:
        return self.critic.evaluate(self.load(session_id), detailed=True)

    def _ensure_turn_setup(self, state: dict[str, Any]) -> dict[str, Any]:
        setups = state.setdefault("turn_setups", {})
        key = str(state["turn"])
        if key not in setups:
            setup = self._controller_setup(state)
            setups[key] = setup
            self._save(state)
        return setups[key]

    def _controller_setup(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.gateway.enabled:
            result = self.gateway.generate_json(self.prompts.load("controller"), self._setup_payload(state))
            if result.data:
                setup = self._normalize_setup(result.data, state)
                setup["llm"] = result.diagnostics()
                return setup
            if config.MODEL_FAILURE_POLICY != "fallback":
                raise RuntimeError(f"Controller setup generation failed: {result.error}")
        return self._local_turn_setup(state)

    def _setup_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        total = state["design"]["turn_policy"]["total_turns"]
        scene = state["design"]["timeline"][min(state["turn"], total - 1)]
        return {
            "mode": "turn_setup",
            "task_flow": [
                "generate_question_stem",
                "semantic_judge_plot_or_measurement",
                "generate_options",
            ],
            "scene_blueprint": scene,
            "previous_question": state.get("turn_setups", {}).get(str(state["turn"] - 1)),
            "player": state["profile"],
            "stats": state["stats"],
            "relationships": state["relationships"],
            "recent_history": state["history"][-8:],
            "recent_turn_setups": list(state.get("turn_setups", {}).values())[-3:],
            "continuity_context": self._continuity_context(state),
            "designer_questionnaire_candidates": scene.get("questionnaire_targets", []),
            "questionnaire": state["design"].get("questionnaire", {}),
            "constraints": {
                "do_not_change_total_turns": True,
                "do_not_show_questionnaire_items_to_player": True,
                "decision_values": ["plot", "measurement"],
            },
        }

    def _normalize_setup(self, data: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        question = data.get("question") or data.get("question_stem") or self._intro(state["design"]["timeline"][state["turn"]])
        judgement = data.get("semantic_judgement") or data.get("test_point") or {}
        decision = judgement.get("decision") or ("measurement" if judgement.get("is_test_point") else "plot")
        targets = judgement.get("selected_questionnaire_targets") or data.get("selected_questionnaire_targets") or []
        options = data.get("options") or data.get("next_options") or []
        normalized = []
        for idx, option in enumerate(options[:4]):
            effects = option.get("effects") if isinstance(option, dict) else {}
            signals = option.get("signals") if isinstance(option, dict) else {}
            normalized.append({
                "id": str(option.get("id", f"option_{idx + 1}")),
                "label": option.get("label") or option.get("title") or option.get("text", f"选项{idx + 1}")[:12],
                "description": option.get("description") or option.get("text") or "",
                "effects": effects if isinstance(effects, dict) else {},
                "signals": signals if isinstance(signals, dict) else {},
                "relationship_effects": option.get("relationship_effects", {}) if isinstance(option, dict) else {},
                "source_id": "controller_dynamic",
                "effects_text": self._effect_text(effects if isinstance(effects, dict) else {}),
            })
        if len(normalized) < 3:
            normalized = self._local_turn_setup(state)["options"]
        return {
            "question": question,
            "semantic_judgement": {
                "decision": "measurement" if decision == "measurement" else "plot",
                "is_test_point": decision == "measurement",
                "selected_questionnaire_targets": targets if isinstance(targets, list) else [],
                "reason": judgement.get("reason", ""),
                "confidence": judgement.get("confidence", 0.0),
            },
            "options": normalized,
        }

    def _local_turn_setup(self, state: dict[str, Any]) -> dict[str, Any]:
        total = state["design"]["turn_policy"]["total_turns"]
        scene = state["design"]["timeline"][min(state["turn"], total - 1)]
        question = self._question_stem(scene, state)
        judgement = self._semantic_judge(question, scene, state)
        options = self._semantic_options(scene, judgement)
        return {"question": question, "semantic_judgement": judgement, "options": options}

    def _question_stem(self, scene: dict[str, Any], state: dict[str, Any]) -> str:
        continuity = self._continuity_context(state)
        summary = str(scene.get("summary", scene.get("title", ""))).rstrip("。！？；;")
        lead = f"{scene.get('month')}的{scene.get('time_slot') or scene.get('period')}，{scene.get('location', '校园')}里，{summary}"
        if continuity.get("last_action_label"):
            last_narrative = str(
                continuity.get("last_narrative") or f"你选择了“{continuity['last_action_label']}”，这让局面留下了一点余波"
            ).rstrip("。！？；;")
            lead = (
                f"上一幕里，{last_narrative}。"
                f"时间往前推了一小步，{lead}"
            )
        elif state["turn"] > 0:
            lead = f"前一段校园日常刚刚收束，{lead}"
        role = scene.get("narrative_role")
        if role == "bridge":
            return f"{lead}。这不是一个需要立刻做重大判断的时刻，更像是承接刚才余波的小缝隙；你会怎样让事情自然地继续下去？"
        if role == "plot":
            return f"{lead}。事情的重点暂时不在证明什么，而在于你怎样进入这个场景、理解身边人的反应。此刻你会怎么做？"
        return f"{lead}。你注意到自己和周围人的反应都很细微，此刻你会怎么做？"

    def _semantic_judge(self, question: str, scene: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        text = json.dumps(scene, ensure_ascii=False) + question
        candidates = scene.get("questionnaire_targets", [])
        role = scene.get("narrative_role", "measurement_candidate")
        measurement_keywords = ["紧张", "担心", "压力", "不自在", "适应", "生气", "不公平", "评价", "忽视", "考试", "烦躁", "信任"]
        plot_keywords = ["首次", "展示", "收束", "报名", "合作", "值日", "社团", "运动会", "图书馆", "寝室"]
        measurement_score = sum(word in text for word in measurement_keywords)
        plot_score = sum(word in text for word in plot_keywords)
        threshold = 2 if role in {"plot", "bridge"} else 1
        recent_decisions = [
            setup.get("semantic_judgement", {}).get("decision")
            for setup in list(state.get("turn_setups", {}).values())[-2:]
            if isinstance(setup, dict)
        ]
        if len(recent_decisions) == 2 and all(decision == "measurement" for decision in recent_decisions):
            threshold += 2
        is_test_point = bool(candidates) and measurement_score >= max(threshold, plot_score // 2)
        selected = candidates[:2] if is_test_point else []
        return {
            "decision": "measurement" if is_test_point else "plot",
            "is_test_point": is_test_point,
            "selected_questionnaire_targets": selected,
            "reason": "题干包含可观察的情绪、压力、适应或人际反应线索。" if is_test_point else "题干主要承担事件承接和人物关系推进。",
            "confidence": 0.68 if is_test_point else 0.62,
        }

    def _semantic_options(self, scene: dict[str, Any], judgement: dict[str, Any]) -> list[dict[str, Any]]:
        blueprint_choices = scene.get("choices", [])
        options = []
        for idx, choice in enumerate(blueprint_choices[:4]):
            effects = choice.get("effects", {})
            signals = choice.get("signals", {})
            if isinstance(signals, list):
                signals = {name: 1.0 for name in signals}
            options.append({
                "id": choice.get("id", f"choice_{idx + 1}"),
                "label": choice.get("text", f"选项{idx + 1}")[:12],
                "description": self._option_description(choice, judgement),
                "effects": effects if isinstance(effects, dict) else {},
                "signals": signals if isinstance(signals, dict) else {},
                "relationship_effects": choice.get("relationship_effects", {}),
                "source_id": "designer_choice",
                "measurement_role": "test_point" if judgement["is_test_point"] else "plot_progression",
                "effects_text": self._effect_text(effects if isinstance(effects, dict) else {}),
            })
        while len(options) < 3:
            options.append(self._fallback_option(scene, judgement, len(options) + 1))
        return options

    @staticmethod
    def _option_description(choice: dict[str, Any], judgement: dict[str, Any]) -> str:
        effect = choice.get("immediate_effect", "")
        if judgement["is_test_point"]:
            return f"{effect}。这会作为本题干下的行为证据之一。"
        return f"{effect}。这主要推动当前事件继续发展。"

    def _fallback_option(self, scene: dict[str, Any], judgement: dict[str, Any], index: int) -> dict[str, Any]:
        templates = [
            ("先观察一下", "先不急着行动，观察现场的人和节奏，再决定下一步。", {"stress": -1}, {"self_regulation": 1.0}),
            ("主动问一句", "找一个自然的切口开口，确认自己可以怎样参与。", {"social": 1, "energy": -1}, {"social_trust": 1.0}),
            ("处理手头事", "先把眼前最具体的小事做完，让局面变得清楚一点。", {"academic": 1, "energy": -1}, {"conscientiousness": 1.0}),
        ]
        label, description, effects, signals = templates[(index - 1) % len(templates)]
        return {
            "id": f"{scene.get('event_id', 'scene')}_fallback_{index}",
            "label": label,
            "description": description,
            "effects": effects,
            "signals": signals,
            "relationship_effects": {},
            "source_id": "semantic_fallback",
            "measurement_role": "test_point" if judgement["is_test_point"] else "plot_progression",
            "effects_text": self._effect_text(effects),
        }

    def _options(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return self._ensure_turn_setup(state).get("options", [])

    def _controller_result(self, state: dict[str, Any], action: dict[str, Any], npc: dict[str, Any], free_text: str) -> dict[str, Any]:
        if not self.gateway.enabled:
            return {}
        total = state["design"]["turn_policy"]["total_turns"]
        payload = {
            "scene_blueprint": state["design"]["timeline"][min(state["turn"], total - 1)],
            "player": state["profile"],
            "stats": state["stats"],
            "relationships": state["relationships"],
            "remaining_action_points": state["ap"],
            "recent_history": state["history"][-6:],
            "action": action,
            "free_text": free_text,
            "focus_npc": npc,
        }
        result = self.gateway.generate_json(self.prompts.load("controller"), payload)
        if result.data:
            result.data["llm"] = result.diagnostics()
            return result.data
        if config.MODEL_FAILURE_POLICY == "fallback":
            return {"llm": result.diagnostics()}
        raise RuntimeError(f"Controller LLM generation failed: {result.error}")

    @staticmethod
    def _continuity_context(state: dict[str, Any]) -> dict[str, Any]:
        history = state.get("history", [])
        previous = history[-1] if history else {}
        previous_setup = state.get("turn_setups", {}).get(str(max(0, state.get("turn", 0) - 1)), {})
        recent_questions = [
            setup.get("question")
            for setup in list(state.get("turn_setups", {}).values())[-3:]
            if isinstance(setup, dict) and setup.get("question")
        ]
        return {
            "last_question": previous.get("question") or previous_setup.get("question"),
            "last_action_label": previous.get("action_label"),
            "last_free_text": previous.get("free_text"),
            "last_narrative": previous.get("narrative"),
            "last_semantic_decision": (previous.get("semantic_judgement") or {}).get("decision"),
            "recent_questions": recent_questions,
            "instruction": "下一题题干必须承接上一题的行动或余波；如果换场景，要写清楚时间/地点如何自然过渡。",
        }

    def _resolve(self, action_id: str, free_text: str, setup: dict[str, Any] | None = None) -> dict[str, Any]:
        if setup:
            match = next((copy.deepcopy(item) for item in setup.get("options", []) if item.get("id") == action_id), None)
            if match:
                match.setdefault("effects", {})
                match.setdefault("signals", {})
                match.setdefault("source_id", "controller_dynamic")
                return match
        if action_id != "free":
            fallback = copy.deepcopy((setup or {}).get("options", [{}])[0])
            fallback.update({"id": action_id, "label": fallback.get("label", "继续行动"), "source_id": "unmatched_dynamic"})
            return fallback
        return {"id": "free", "source_id": "free_text", "label": "自由行动", "description": free_text, "effects": {}, "signals": {}}

    @staticmethod
    def _numeric_map(value: Any) -> dict[str, float]:
        if not isinstance(value, dict):
            return {}
        return {key: float(delta) for key, delta in value.items() if isinstance(delta, (int, float))}

    @staticmethod
    def _intro(scene: dict[str, Any]) -> str:
        return f"{scene['month']}的校园进入{scene['period']}。关于“{scene['title']}”的小事正在发生，空气里的情绪是{scene['tone']}的。没有人知道它会不会成为重要回忆。"

    @staticmethod
    def _narrative(action: dict[str, Any], npc: dict[str, Any], free_text: str) -> str:
        text = {
            "study": "你把没弄懂的地方一项项圈出来。进步并不显眼，却足够真实。",
            "social": f"你和{npc['name']}从眼前的小事聊起，下一次见面因此少了一点陌生。",
            "help": f"你自然地帮了{npc['name']}一把。对方没有说很多，只认真道了声谢。",
            "rest": "你暂时合上待办清单，沿操场慢慢走了一圈，拥挤的念头散开了一些。",
            "explore": "你把熟悉的路线拐向另一边，一次小小尝试让今天留下不同的纹理。",
        }
        if action.get("source_id") in text:
            return text[action["source_id"]]
        chosen = free_text.strip() or action.get("label") or action.get("description") or "继续往前走一步"
        consequence = str(action.get("description") or action.get("effects_text") or "事情没有完全照计划发展，但选择确实改变了这段时间。").lstrip("。").rstrip()
        return f"你选择了“{chosen}”。{consequence}"

    def _stable_seed(self, state: dict[str, Any], salt: str) -> int:
        raw = f"{state['seed']}:{state['turn']}:{len(state['history'])}:{salt}"
        return int(hashlib.sha256(raw.encode()).hexdigest()[:12], 16)

    def _save(self, state: dict[str, Any]) -> None:
        (self.session_dir / f"{state['session_id']}.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        if state["history"]:
            (self.session_dir / f"{state['session_id']}.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in state["history"]) + "\n", encoding="utf-8")

    @staticmethod
    def _effect_text(effects: dict[str, float]) -> str:
        names = {"academic": "学业", "stress": "压力", "energy": "精力", "social": "社交", "mood": "心情", "empathy": "共情", "health": "健康", "openness": "开放"}
        return " · ".join(f"{names.get(key, key)} {'+' if value > 0 else ''}{value}" for key, value in effects.items())

    @staticmethod
    def _changes(before: dict[str, float], after: dict[str, float]) -> list[dict[str, Any]]:
        names = {"academic": "学业", "health": "健康", "social": "社交", "empathy": "共情", "openness": "开放", "stress": "压力", "mood": "心情", "energy": "精力"}
        return [{"key": key, "label": names[key], "delta": round(after[key] - value, 1), "value": after[key]} for key, value in before.items() if after[key] != value]
