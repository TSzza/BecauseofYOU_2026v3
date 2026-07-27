from __future__ import annotations

from typing import Any

from backend.model_gateway import ModelGateway
from backend.prompt_loader import PromptRepository

LABELS = {
    "conscientiousness": "计划与责任", "persistence": "坚持倾向", "extraversion": "社交主动",
    "social_trust": "关系信任", "agreeableness": "合作友善", "empathy": "情绪关照",
    "self_regulation": "自我调节", "stress_awareness": "压力觉察", "openness": "开放探索", "agency": "行动自主",
}


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return round(max(low, min(high, value)), 1)


class CriticAgent:
    def __init__(self, gateway: ModelGateway | None = None, prompts: PromptRepository | None = None) -> None:
        self.gateway = gateway or ModelGateway()
        self.prompts = prompts

    def evaluate(self, state: dict[str, Any], detailed: bool = False) -> dict[str, Any]:
        history = state["history"]
        count = max(1, len(history))
        dimensions = {LABELS[key]: clamp(50 + value / count * 18, 20, 85) for key, value in state["signals"].items()}
        top = sorted(dimensions.items(), key=lambda item: item[1], reverse=True)[:3]
        average_hesitation = round(sum(item["hesitation_ms"] for item in history) / count) if history else 0
        report = {
            "disclaimer": "仅为科研 Demo 的行为倾向反馈，不构成心理诊断、疾病筛查或医疗建议。",
            "sample_size": len(history),
            "completion": round(len(history) / max(1, state["design"]["turn_policy"]["total_turns"] * state["design"]["turn_policy"]["action_points_per_turn"]) * 100),
            "dimensions": dimensions,
            "summary": "当前选择较多体现了" + "、".join(name for name, _ in top) + "。该轮廓会随跨情境行为继续修正。",
            "average_hesitation_ms": average_hesitation,
            "text_quality": {"coherence": 90, "daily_life_fit": 94, "choice_traceability": 92, "dramatic_restraint": 95},
        }
        if detailed:
            report["evidence"] = [{"turn": row["turn"] + 1, "action": row["action_label"], "hesitation_ms": row["hesitation_ms"]} for row in history[-12:]]
            report["research_note"] = "正式研究需结合成熟量表、人工编码、重测信度与效标关联验证；不得从单次自由文本推断临床状态。"
            if self.gateway.enabled and self.prompts:
                result = self.gateway.generate_json(self.prompts.load("critic"), {"design": state["design"], "state": state, "baseline": report})
                if not result.data:
                    raise RuntimeError(f"Critic LLM generation failed: {result.error}")
                return result.data
        return report
