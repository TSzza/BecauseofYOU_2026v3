from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


# Small, interpretable seed lexicon. It is intentionally evidence-oriented: a later
# model may refine labels, but every score below can be traced to a source span.
EMOTION_LEXICON: dict[str, tuple[str, float, float, float]] = {
    "高兴": ("joy", 0.82, 0.62, 0.64), "高興": ("joy", 0.82, 0.62, 0.64),
    "开心": ("joy", 0.86, 0.66, 0.67), "開心": ("joy", 0.86, 0.66, 0.67),
    "快乐": ("joy", 0.84, 0.58, 0.65), "快樂": ("joy", 0.84, 0.58, 0.65),
    "喜欢": ("liking", 0.77, 0.48, 0.59), "喜歡": ("liking", 0.77, 0.48, 0.59),
    "希望": ("hope", 0.72, 0.52, 0.58), "安心": ("relief", 0.73, 0.28, 0.61),
    "放心": ("relief", 0.72, 0.27, 0.62), "平静": ("calm", 0.61, 0.18, 0.58),
    "平靜": ("calm", 0.61, 0.18, 0.58), "难过": ("sadness", 0.20, 0.43, 0.28),
    "難過": ("sadness", 0.20, 0.43, 0.28), "悲伤": ("sadness", 0.14, 0.45, 0.25),
    "悲傷": ("sadness", 0.14, 0.45, 0.25), "伤心": ("sadness", 0.16, 0.48, 0.24),
    "傷心": ("sadness", 0.16, 0.48, 0.24), "失望": ("disappointment", 0.18, 0.39, 0.27),
    "害怕": ("fear", 0.12, 0.78, 0.18), "恐惧": ("fear", 0.10, 0.82, 0.16),
    "恐懼": ("fear", 0.10, 0.82, 0.16), "担心": ("anxiety", 0.24, 0.67, 0.26),
    "擔心": ("anxiety", 0.24, 0.67, 0.26), "焦虑": ("anxiety", 0.18, 0.74, 0.22),
    "焦慮": ("anxiety", 0.18, 0.74, 0.22), "紧张": ("anxiety", 0.25, 0.76, 0.25),
    "緊張": ("anxiety", 0.25, 0.76, 0.25), "生气": ("anger", 0.18, 0.78, 0.58),
    "生氣": ("anger", 0.18, 0.78, 0.58), "愤怒": ("anger", 0.12, 0.86, 0.66),
    "憤怒": ("anger", 0.12, 0.86, 0.66), "讨厌": ("disgust", 0.16, 0.57, 0.52),
    "討厭": ("disgust", 0.16, 0.57, 0.52), "羞愧": ("shame", 0.17, 0.58, 0.18),
    "惭愧": ("shame", 0.20, 0.52, 0.20), "慚愧": ("shame", 0.20, 0.52, 0.20),
    "内疚": ("guilt", 0.18, 0.55, 0.19), "內疚": ("guilt", 0.18, 0.55, 0.19),
    "孤独": ("loneliness", 0.17, 0.31, 0.21), "孤獨": ("loneliness", 0.17, 0.31, 0.21),
    "惊讶": ("surprise", 0.52, 0.82, 0.45), "驚訝": ("surprise", 0.52, 0.82, 0.45),
}
EMOTION_LEXICON.update({
    "happy": ("joy", 0.84, 0.62, 0.64), "glad": ("joy", 0.82, 0.56, 0.61),
    "joyful": ("joy", 0.90, 0.66, 0.67), "love": ("liking", 0.78, 0.52, 0.62),
    "hope": ("hope", 0.72, 0.52, 0.58), "relieved": ("relief", 0.73, 0.28, 0.61),
    "calm": ("calm", 0.61, 0.18, 0.58), "sad": ("sadness", 0.18, 0.43, 0.26),
    "sorrow": ("sadness", 0.12, 0.45, 0.23), "disappointed": ("disappointment", 0.18, 0.39, 0.27),
    "afraid": ("fear", 0.12, 0.78, 0.18), "fear": ("fear", 0.10, 0.82, 0.16),
    "worried": ("anxiety", 0.24, 0.67, 0.26), "anxious": ("anxiety", 0.18, 0.74, 0.22),
    "nervous": ("anxiety", 0.25, 0.76, 0.25), "angry": ("anger", 0.18, 0.78, 0.58),
    "furious": ("anger", 0.12, 0.86, 0.66), "hate": ("disgust", 0.16, 0.57, 0.52),
    "ashamed": ("shame", 0.17, 0.58, 0.18), "guilty": ("guilt", 0.18, 0.55, 0.19),
    "lonely": ("loneliness", 0.17, 0.31, 0.21), "surprised": ("surprise", 0.52, 0.82, 0.45),
})
EMOTION_LEXICON.update({
    "欢喜": ("joy", 0.78, 0.52, 0.58), "歡喜": ("joy", 0.78, 0.52, 0.58), "喜悦": ("joy", 0.78, 0.45, 0.56), "喜悅": ("joy", 0.78, 0.45, 0.56),
    "悲哀": ("sadness", 0.15, 0.48, 0.22), "哀愁": ("sadness", 0.20, 0.42, 0.24), "忧愁": ("sadness", 0.20, 0.42, 0.24), "憂愁": ("sadness", 0.20, 0.42, 0.24),
    "忧惧": ("anxiety", 0.15, 0.72, 0.20), "憂懼": ("anxiety", 0.15, 0.72, 0.20), "震惊": ("surprise", 0.46, 0.80, 0.40), "震驚": ("surprise", 0.46, 0.80, 0.40),
    "愤怒": ("anger", 0.15, 0.80, 0.60), "憤怒": ("anger", 0.15, 0.80, 0.60), "怨恨": ("resentment", 0.16, 0.66, 0.55), "惶恐": ("fear", 0.12, 0.78, 0.18),
    "惭愧": ("shame", 0.18, 0.56, 0.18), "慚愧": ("shame", 0.18, 0.56, 0.18), "惋惜": ("regret", 0.22, 0.40, 0.25), "不平": ("anger", 0.22, 0.62, 0.48),
})

BEHAVIOR_CUES: dict[str, tuple[str, float, float, float]] = {
    "低下头": ("withdrawal", 0.27, 0.42, 0.25), "低下頭": ("withdrawal", 0.27, 0.42, 0.25),
    "发抖": ("fear", 0.15, 0.82, 0.17), "發抖": ("fear", 0.15, 0.82, 0.17),
    "颤抖": ("fear", 0.14, 0.84, 0.16), "顫抖": ("fear", 0.14, 0.84, 0.16),
    "哭": ("sadness", 0.14, 0.70, 0.19), "流泪": ("sadness", 0.16, 0.58, 0.20),
    "流淚": ("sadness", 0.16, 0.58, 0.20), "叹气": ("sadness", 0.25, 0.31, 0.28),
    "嘆氣": ("sadness", 0.25, 0.31, 0.28), "大笑": ("joy", 0.78, 0.78, 0.65),
    "微笑": ("joy", 0.72, 0.42, 0.59), "冷笑": ("contempt", 0.24, 0.55, 0.61),
    "沉默": ("suppression", 0.35, 0.31, 0.34), "回避": ("avoidance", 0.27, 0.46, 0.24),
    "躲开": ("avoidance", 0.24, 0.55, 0.21), "躲開": ("avoidance", 0.24, 0.55, 0.21),
}
BEHAVIOR_CUES.update({
    "lowered his head": ("withdrawal", 0.27, 0.42, 0.25), "trembled": ("fear", 0.15, 0.82, 0.17),
    "shook": ("fear", 0.15, 0.78, 0.17), "cried": ("sadness", 0.14, 0.70, 0.19),
    "wept": ("sadness", 0.14, 0.68, 0.19), "sighed": ("sadness", 0.25, 0.31, 0.28),
    "laughed": ("joy", 0.78, 0.78, 0.65), "smiled": ("joy", 0.72, 0.42, 0.59),
    "silence": ("suppression", 0.35, 0.31, 0.34), "avoided": ("avoidance", 0.27, 0.46, 0.24),
})
BEHAVIOR_CUES.update({
    "面如土色": ("fear", 0.12, 0.78, 0.18), "面色惨白": ("fear", 0.13, 0.74, 0.18), "面色慘白": ("fear", 0.13, 0.74, 0.18),
    "战战兢兢": ("fear", 0.12, 0.82, 0.16), "戰戰兢兢": ("fear", 0.12, 0.82, 0.16), "泪流满面": ("sadness", 0.12, 0.64, 0.18), "淚流滿面": ("sadness", 0.12, 0.64, 0.18),
    "怒目而视": ("anger", 0.16, 0.80, 0.62), "怒目而視": ("anger", 0.16, 0.80, 0.62), "长叹": ("sadness", 0.23, 0.38, 0.25), "長歎": ("sadness", 0.23, 0.38, 0.25),
})

NEGATIONS = ("不", "没", "沒", "未", "无", "無", "并非", "並非", "not", "never", "no")
INTENSIFIERS = {"很": 1.15, "非常": 1.3, "十分": 1.25, "极": 1.3, "極": 1.3, "太": 1.2, "有点": 0.75, "有點": 0.75, "略": 0.75, "very": 1.25, "extremely": 1.3, "slightly": 0.75}
CAUSE_RE = re.compile(r"(?:因为|因為|由于|由於|因|看到|听到|聽到|得知|because|after seeing|after hearing|learning that)(?P<cause>[^。！？!?；;]{1,36})", re.IGNORECASE)


class AffectAnalyzer:
    def analyze_event(self, text: str, absolute_start: int, character_ids: list[str]) -> dict[str, Any]:
        evidence: list[dict[str, Any]] = []
        for lexicon, evidence_type, base_confidence in (
            (EMOTION_LEXICON, "emotion_word", 0.86),
            (BEHAVIOR_CUES, "behavioral_cue", 0.66),
        ):
            for term, (label, valence, arousal, dominance) in lexicon.items():
                pattern = rf"\b{re.escape(term)}\b" if term.isascii() else re.escape(term)
                for match in re.finditer(pattern, text, re.IGNORECASE if term.isascii() else 0):
                    local_valence, local_arousal, local_dominance = valence, arousal, dominance
                    prefix = text[max(0, match.start() - 10):match.start()].lower().rstrip()
                    negated = any(prefix.endswith(item.lower()) for item in NEGATIONS)
                    intensity = 1.0
                    for marker, factor in INTENSIFIERS.items():
                        if prefix.endswith(marker):
                            intensity = factor
                            break
                    if negated:
                        local_valence = 1.0 - local_valence
                    vad = {
                        "valence": round(self._scale(local_valence, intensity), 4),
                        "arousal": round(self._scale(local_arousal, intensity), 4),
                        "dominance": round(self._scale(local_dominance, intensity), 4),
                    }
                    evidence.append({
                        "holder_candidates": character_ids,
                        "channel": self._channel(text, match.start(), evidence_type),
                        "evidence_type": evidence_type,
                        "text": match.group(0), "emotion": label,
                        "vad": vad, "negated": negated, "intensity_modifier": intensity,
                        "source_span": {
                            "start": absolute_start + match.start(),
                            "end": absolute_start + match.end(), "text": match.group(0),
                        },
                        "fill_mode": "extract" if evidence_type == "emotion_word" else "infer",
                        "confidence": base_confidence - (0.12 if negated else 0.0),
                    })
        aggregate = self._aggregate(evidence)
        causes = []
        for match in CAUSE_RE.finditer(text):
            causes.append({
                "text": match.group("cause"),
                "affected_character_ids": character_ids,
                "source_span": {
                    "start": absolute_start + match.start("cause"),
                    "end": absolute_start + match.end("cause"), "text": match.group("cause"),
                },
                "fill_mode": "extract", "confidence": 0.62,
            })
        return {
            "atmosphere": aggregate,
            "expressions": evidence,
            "causal_triggers": causes,
            "evidence_count": len(evidence),
            "analysis_method": "lexicon_negation_intensity_behavior_hybrid",
        }

    @staticmethod
    def _scale(value: float, intensity: float) -> float:
        return max(0.0, min(1.0, 0.5 + (value - 0.5) * intensity))

    @staticmethod
    def _channel(text: str, position: int, evidence_type: str) -> str:
        if evidence_type == "behavioral_cue":
            return "action"
        before = text[:position]
        if before.count("“") > before.count("”") or before.count("『") > before.count("』") or before.count("「") > before.count("」"):
            return "dialogue"
        if before.count('"') % 2 == 1 or before.count("'") % 2 == 1:
            return "dialogue"
        if any(term in text[max(0, position - 12):position + 12].lower() for term in ("想", "觉得", "覺得", "心里", "心裡", "意识", "意識", "thought", "felt", "realized")):
            return "internal"
        return "narration"

    @staticmethod
    def _aggregate(evidence: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not evidence:
            return None
        totals = defaultdict(float)
        emotions = defaultdict(float)
        weight_sum = 0.0
        for item in evidence:
            weight = item["confidence"]
            weight_sum += weight
            for dimension, value in item["vad"].items():
                totals[dimension] += value * weight
            emotions[item["emotion"]] += weight
        return {
            "vad": {key: round(value / weight_sum, 4) for key, value in totals.items()},
            "emotion_distribution": {
                key: round(value / weight_sum, 4)
                for key, value in sorted(emotions.items(), key=lambda pair: -pair[1])
            },
            "confidence": round(min(0.9, weight_sum / max(1, len(evidence))), 4),
        }
