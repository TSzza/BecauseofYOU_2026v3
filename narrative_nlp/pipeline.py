from __future__ import annotations

import argparse
import json
import re
import site
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

from .affect import AffectAnalyzer
from .models import CharacterLineItem, EntityMention, EventItem, SourceSpan, TimeMention, to_dict

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    site.addsitedir(user_site)
vendor_dir = str(Path(__file__).resolve().parent / "vendor")
if vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)

try:
    import jieba.posseg as jieba_posseg
except ImportError:  # pragma: no cover - optional dependency fallback
    jieba_posseg = None


SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+(?:[。！？!?；;.]|$)", re.MULTILINE)
TIME_PATTERNS = (
    (re.compile(r"第[一二三四五六七八九十百0-9]+[章节卷]"), "document"),
    (re.compile(r"(?:大约|约)?[0-9一二三四五六七八九十百]+年前"), "relative_year"),
    (re.compile(r"(?:上|下|这|那)(?:个)?(?:周|星期)[一二三四五六七日天]"), "relative_weekday"),
    (re.compile(r"(?:第)?[一二三四五六七八九十百0-9]+天后"), "relative_day"),
    (re.compile(r"(?:次日|翌日|第二天|当天|当晚|清晨|早晨|上午|中午|下午|傍晚|晚上|深夜|放学后|午休)"), "day_part"),
    (re.compile(r"(?:春天|夏天|秋天|冬天|寒假|暑假|开学|月考|期中|期末)"), "school_or_season"),
    (re.compile(r"(?:一|二|三|四|五|六|七|八|九|十|十一|十二)月(?:初|上旬|中旬|下旬|底)?"), "month"),
    (re.compile(r"[0-9]{4}年(?:[0-9]{1,2}月)?(?:[0-9]{1,2}日)?"), "absolute_date"),
    (re.compile(r"\b(?:the )?(?:next|following|previous|last) (?:day|morning|evening|week|month|year)\b", re.IGNORECASE), "relative_english"),
    (re.compile(r"\b(?:yesterday|today|tomorrow|that night|later|years ago|long ago|in the morning|at night)\b", re.IGNORECASE), "relative_english"),
    (re.compile(r"\b(?:spring|summer|autumn|fall|winter|Christmas|Easter)\b", re.IGNORECASE), "season_english"),
    (re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b", re.IGNORECASE), "month_english"),
)
LOCATION_TERMS = (
    "学校", "教室", "宿舍", "图书馆", "操场", "食堂", "办公室", "走廊", "车站",
    "家里", "家中", "客厅", "卧室", "医院", "街道", "公园", "门口", "楼梯", "社团",
)
EN_LOCATION_TERMS = ("school", "classroom", "library", "house", "home", "room", "street", "town", "city", "church", "office", "garden", "ship", "sea", "island", "hotel", "station", "castle", "laboratory")
EVENT_TRIGGERS = (
    "说", "问", "回答", "看", "听", "等", "去", "来", "回", "离开", "遇到", "参加",
    "考试", "月考", "上课", "放学", "回家", "帮助", "拒绝", "接受", "决定", "答应",
    "发现", "记得", "忘记", "担心", "害怕", "喜欢", "讨厌", "争吵", "道歉", "沉默",
    "笑", "哭", "写", "删", "发", "收到", "打开", "关上", "坐", "站", "走进", "离开",
)
EVENT_TRIGGERS += (
    "說", "問", "回答", "聽", "等", "去", "來", "回", "離開", "遇到", "參加", "考試", "上課", "放學",
    "回家", "幫助", "拒絕", "接受", "決定", "答應", "發現", "記得", "忘記", "擔心", "喜歡", "討厭",
    "爭吵", "道歉", "哭", "刪", "收到", "打開", "關上", "站", "走進",
)
EN_EVENT_TRIGGERS = (
    "said", "asked", "replied", "looked", "heard", "waited", "went", "came", "returned", "left", "met", "joined",
    "saw", "found", "remembered", "forgot", "thought", "feared", "hoped", "loved", "hated", "argued", "apologized",
    "laughed", "cried", "wrote", "deleted", "sent", "received", "opened", "closed", "sat", "stood", "entered", "told",
)
PRONOUNS = {"他", "她", "它", "他们", "她们", "自己", "对方", "那人", "这个人"}
ROLE_SUFFIXES = ("老师", "同学", "班主任", "妈妈", "爸爸", "哥哥", "姐姐", "妹妹", "弟弟")
NON_NAME_SUFFIXES = ("说", "說", "道", "问", "問", "答", "喝", "喊", "叫", "写", "寫", "涂", "塗", "看", "听", "聽")
UNNAMED_ROLE_TERMS = (
    "大哥", "哥哥", "姐姐", "妹妹", "弟弟", "父亲", "父親", "母亲", "母親", "老师", "老師",
    "先生", "太太", "夫人", "老爷", "老爺", "医生", "醫生", "掌柜", "掌櫃", "和尚", "道士",
    "father", "mother", "brother", "sister", "teacher", "doctor", "master", "mistress", "servant", "captain",
)
COMMON_SURNAMES = set("赵钱孙李周吴郑王冯陈沈韩杨朱秦许何吕张孔曹金魏姜谢苏潘范彭马方任袁柳史唐薛雷贺倪罗毕郝安于傅齐康伍余顾孟黄萧尹姚邵汪毛米成戴宋庞熊纪舒屈项董梁杜阮蓝季贾江童郭梅林钟徐高夏蔡田胡霍万卢房解宗丁邓单洪包左石崔龚程邢裴陆荣翁甄段巫焦侯仲宫宁武刘龙叶白鄂赖卓蒙池乔谭申冉牛边燕尚温庄柴阎慕连艾向古易戈廖庾都耿满文寇广东欧利师聂晁辛简饶曾沙鞠关查荆红游权盖")
COMMON_SURNAMES.update("趙錢孫吳鄭馮陳瀋韓楊許呂張謝蘇潘範彭馬袁薛賀倪羅畢郝傅齊餘顧黃蕭邵汪龐紀項董藍賈鍾徐蔡萬盧鄧單洪崔龔陸榮甄鄔劉龍葉賴譚申邊燕溫莊閻連廖簡饒曾關遊權蓋")
NAME_STOPWORDS = PRONOUNS | {
    "开学后", "放学后", "第二天", "下午", "上午", "晚上", "参加社团", "是否参加",
    "曾经", "后来", "此前", "之前", "家乡", "回忆", "想起", "那年",
}
ZH_NAME_STOPWORDS = {
    "一个", "一些", "这个", "那个", "自己", "什么", "怎么", "如何", "因为", "所以", "但是", "于是", "后来", "曾经",
    "可以", "不能", "不要", "没有", "不是", "就是", "我们", "你们", "他们", "她们", "大家", "先生", "太太", "小姐",
    "东西", "时候", "地方", "事情", "今日", "明日", "昨日", "天下", "世上", "人家", "众人", "两人", "三人", "有人",
    "说道", "问道", "答道", "笑道", "说道", "只见", "原来", "忽然", "自然", "如此", "不知", "只管", "连忙", "赶忙",
    "已经", "正在", "将要", "不得", "只得", "因此", "如今", "当时", "后来", "以前", "之后", "里面", "外面", "上面", "下面", "明白",
}
NAME_RE = re.compile(r"[A-Z][A-Za-z]{1,14}")
MIXED_NAME_RE = re.compile(r"阿(?:[A-Z]|[Ａ-Ｚ])(?![A-Za-zＡ-Ｚａ-ｚ])")
LOCAL_TIME_BOUNDARY_RE = re.compile(r"(?:第二天|次日|后来|後來|随后|隨後|之后|之後|以前|此前|当晚|當晚|当日|當日|过了几天|過了幾天|多年以后|多年以後)")
EN_NAME_STOPWORDS = {
    "The", "A", "An", "And", "But", "Or", "If", "Then", "When", "Where", "What", "How", "It", "He", "She", "They",
    "Chapter", "Part", "Book", "Vol", "Mr", "Mrs", "Miss", "Dr", "Street", "House", "Lord", "Lady", "Professor",
    "Books", "English", "Information", "Archive", "Foundation", "License", "Literary", "General", "Cousin",
    "Most", "Besides", "Except", "Donations", "As", "At", "By", "For", "From", "In", "My", "Do", "Any", "Agree",
}
CHINESE_NAME_RE = re.compile(r"(?:赵|钱|孙|李|周|吴|郑|王|冯|陈|沈|韩|杨|朱|秦|许|何|吕|张|孔|曹|金|魏|姜|谢|苏|潘|范|彭|马|方|任|袁|柳|史|唐|薛|雷|贺|倪|罗|毕|郝|安|于|傅|齐|康|伍|余|顾|孟|黄|萧|尹|姚|邵|汪|毛|米|成|戴|宋|庞|熊|纪|舒|屈|项|董|梁|杜|阮|蓝|季|贾|江|童|郭|梅|林|钟|徐|高|夏|蔡|田|胡|霍|万|卢|房|解|宗|丁|邓|单|洪|包|左|石|崔|龚|程|邢|裴|陆|荣|翁|甄|段|巫|焦|侯|仲|宫|宁|武|刘|龙|叶|白|鄂|赖|卓|蒙|池|乔|谭|申|冉|牛|边|燕|尚|温|庄|柴|阎|慕|连|艾|向|古|易|戈|廖|庾|都|耿|满|文|寇|广|东|欧|利|师|聂|晁|辛|简|饶|曾|沙|鞠|关|查|荆|红|游|权|盖|司马|上官|欧阳)[\u4e00-\u9fff]{1,2}")


class NovelIndexer:
    """Deterministic Chinese baseline: extract structure first, enrich later with an LLM."""

    def __init__(self, source_id: str = "novel") -> None:
        self.source_id = source_id
        self._entity_by_surface: dict[str, str] = {}
        self._entity_type: dict[str, str] = {}
        self._affect_analyzer = AffectAnalyzer()

    def index_text(self, text: str) -> dict[str, Any]:
        original_character_count = len(text)
        text, source_offset = self._book_body(text)
        sentences = self._sentences(text, source_offset)
        time_mentions = self._extract_times(sentences)
        entity_mentions = self._extract_entities(sentences)
        character_candidates = self._extract_character_candidates(text, entity_mentions)
        events = self._extract_events(sentences, time_mentions, entity_mentions)
        events = self._order_events(events)
        self._link_cross_event_causes(events)
        character_resolution = self._resolve_character_identities(sentences, entity_mentions, events)
        plot_events = self._merge_plot_events(events)
        world_line = self._build_world_line(events, time_mentions, entity_mentions)
        world_line["plot_events"] = plot_events
        world_line["affective_summary"] = self._summarize_world_affect(events)
        character_lines = self._build_character_lines(events, entity_mentions)
        knowledge_graph = self._build_knowledge_graph(
            events, entity_mentions, character_lines, plot_events, character_resolution
        )
        return {
            "schema_version": "nlp-index-0.1",
            "source": {
                "source_id": self.source_id,
                "character_count": original_character_count,
                "indexed_start": source_offset,
                "indexed_end": source_offset + len(text),
            },
            "world_profile": self._world_profile(sentences, entity_mentions),
            "world_line": world_line,
            "character_profiles": self._character_profiles(entity_mentions),
            "character_resolution": character_resolution,
            "character_lines": character_lines,
            "knowledge_graph": knowledge_graph,
            "indexes": {
                "time_mentions": [to_dict(item) for item in time_mentions],
                "entity_mentions": [to_dict(item) for item in entity_mentions],
                "character_candidates": character_candidates,
                "event_count": len(events),
                "unresolved_pronoun_count": sum(1 for event in events if event.event.get("unresolved_pronouns")),
            },
            "handoff": {
                "llm_required_fields": [
                    "event.summary", "event.narrative_function", "event.causes", "character.motivation",
                    "character.emotion", "character.relationship_changes", "adaptation.bridge_content",
                ],
                "designer_preferred_event_layer": "world_line.plot_events",
                "evidence_policy": "Every LLM-filled field must cite source spans and fill_mode.",
            },
        }

    @staticmethod
    def _strip_book_metadata(text: str) -> str:
        body, _ = NovelIndexer._book_body(text)
        return body

    @staticmethod
    def _book_body(text: str) -> tuple[str, int]:
        start = re.search(r"\*\*\*\s*START OF (?:THE )?(?:PROJECT GUTENBERG|THIS PROJECT GUTENBERG)", text, re.IGNORECASE)
        end = re.search(r"\*\*\*\s*END OF (?:THE )?(?:PROJECT GUTENBERG|THIS PROJECT GUTENBERG)", text, re.IGNORECASE)
        if start and end and start.end() < end.start():
            body_start = start.end()
            body_end = end.start()
        else:
            body_start = 0
            body_end = len(text)
        body = text[body_start:body_end]
        annotation = re.search(r"(?:\r?\n)[\u3000 \t]*(?:[注註][释釋]|附[注註])[\u3000 \t]*(?:\r?\n)", body)
        if annotation:
            body = body[:annotation.start()]
        return body, body_start

    def _sentences(self, text: str, source_offset: int = 0) -> list[dict[str, Any]]:
        result = []
        for index, match in enumerate(SENTENCE_RE.finditer(text), start=1):
            value = match.group(0).strip()
            if not value:
                continue
            start = source_offset + match.start() + (len(match.group(0)) - len(match.group(0).lstrip()))
            result.append({"index": index, "text": value, "start": start, "end": start + len(value)})
        return result

    def _extract_times(self, sentences: list[dict[str, Any]]) -> list[TimeMention]:
        mentions: list[TimeMention] = []
        for sentence in sentences:
            found = False
            for pattern, kind in TIME_PATTERNS:
                for match in pattern.finditer(sentence["text"]):
                    mentions.append(TimeMention(match.group(0), f"{kind}:{match.group(0)}", sentence["index"], 0.75))
                    found = True
            for match in LOCAL_TIME_BOUNDARY_RE.finditer(sentence["text"]):
                mentions.append(TimeMention(match.group(0), f"discourse:{match.group(0)}", sentence["index"], 0.7))
                found = True
            if not found:
                mentions.append(TimeMention("", f"sentence:{sentence['index']}", sentence["index"], 0.25))
        return mentions

    def _resolve_character_identities(
        self,
        sentences: list[dict[str, Any]],
        entities: list[EntityMention],
        events: list[EventItem],
    ) -> dict[str, Any]:
        """Build conservative alias candidates and local unnamed-role chains."""
        grouped: dict[str, list[EntityMention]] = defaultdict(list)
        for mention in entities:
            if mention.entity_type == "character":
                grouped[mention.entity_id].append(mention)
        names = {entity_id: mentions[0].text for entity_id, mentions in grouped.items()}
        alias_candidates: list[dict[str, Any]] = []
        canonical_alias_groups: list[dict[str, Any]] = []
        id_by_name = {name: entity_id for entity_id, name in names.items()}
        explicit_alias_re = re.compile(r"(?P<left>[\u4e00-\u9fff]{1,4})(?:又名|又稱|又称|即|本名为|本名為|原名为|原名為)(?P<right>[\u4e00-\u9fff]{1,4})")
        parenthetical_alias_re = re.compile(r"(?P<left>[\u4e00-\u9fff]{1,4})[（(](?P<right>[\u4e00-\u9fff]{1,4})[）)]")
        for sentence in sentences:
            for pattern in (explicit_alias_re, parenthetical_alias_re):
                for match in pattern.finditer(sentence["text"]):
                    left_id, right_id = id_by_name.get(match.group("left")), id_by_name.get(match.group("right"))
                    if left_id and right_id and left_id != right_id:
                        canonical = left_id if len(match.group("left")) >= len(match.group("right")) else right_id
                        canonical_alias_groups.append({
                            "canonical_id": canonical,
                            "member_ids": sorted({left_id, right_id}),
                            "relation": "explicit_alias",
                            "source_span": {
                                "source_id": self.source_id,
                                "start": sentence["start"] + match.start(),
                                "end": sentence["start"] + match.end(),
                                "text": match.group(0),
                            },
                            "fill_mode": "extract", "confidence": 0.92,
                        })
        ids = sorted(names)
        for index, left_id in enumerate(ids):
            for right_id in ids[index + 1:]:
                left, right = names[left_id], names[right_id]
                shorter, longer = sorted((left, right), key=len)
                if len(shorter) != 1 or not longer.startswith(shorter):
                    continue
                left_sentences = {item.sentence_index for item in grouped[left_id]}
                right_sentences = {item.sentence_index for item in grouped[right_id]}
                distance = min(abs(a - b) for a in left_sentences for b in right_sentences)
                if distance <= 12:
                    alias_candidates.append({
                        "left_id": left_id, "right_id": right_id,
                        "relation": "possible_alias", "evidence": "shared_surname_and_local_proximity",
                        "sentence_distance": distance, "confidence": 0.45,
                        "status": "candidate", "requires_review": True,
                    })

        event_by_sentence = {event.time["sentence_index"]: event.event_id for event in events}
        role_mentions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for sentence in sentences:
            for role in UNNAMED_ROLE_TERMS:
                for match in re.finditer(re.escape(role), sentence["text"]):
                    role_mentions[role].append({
                        "sentence_index": sentence["index"],
                        "event_id": event_by_sentence.get(sentence["index"]),
                        "source_span": {
                            "source_id": self.source_id,
                            "start": sentence["start"] + match.start(),
                            "end": sentence["start"] + match.end(),
                            "text": role,
                        },
                    })
        unnamed_entities = []
        for role, mentions in sorted(role_mentions.items()):
            if len(mentions) < 2:
                continue
            unnamed_entities.append({
                "local_entity_id": f"ROLE_{len(unnamed_entities) + 1:03d}",
                "surface": role, "entity_type": "unnamed_character_role",
                "scope": "document_local", "mention_count": len(mentions),
                "mentions": mentions[:100], "status": "coreference_candidate",
                "merge_policy": "Do not merge across scenes until identity continuity is confirmed.",
                "confidence": 0.55,
            })
        return {
            "canonical_alias_groups": canonical_alias_groups,
            "alias_candidates": alias_candidates,
            "unnamed_role_chains": unnamed_entities,
            "policy": "Only explicit equivalence may enter canonical_alias_groups; heuristic matches remain candidates.",
        }

    def _merge_plot_events(self, events: list[EventItem]) -> list[dict[str, Any]]:
        """Merge adjacent sentence events into evidence-preserving plot events."""
        if not events:
            return []
        groups: list[list[EventItem]] = [[events[0]]]
        boundary_reasons: list[str] = []
        for event in events[1:]:
            previous = groups[-1][-1]
            sentence_gap = event.time["sentence_index"] - previous.time["sentence_index"]
            shared_people = set(event.participants) & set(previous.participants)
            shared_places = set(event.space["location_ids"]) & set(previous.space["location_ids"])
            has_new_time = bool(event.time.get("mentions"))
            # Candidate plot grouping is deliberately broader than the old
            # participant-only rule. A one-sentence continuation in the same
            # discourse block is retained for semantic review even when entity
            # recognition missed the repeated subject.
            should_merge = (
                sentence_gap <= 1 and not has_new_time
            ) or (
                sentence_gap <= 3 and not has_new_time and bool(shared_people or shared_places)
            )
            if should_merge:
                groups[-1].append(event)
            else:
                reason = "explicit_time_boundary" if has_new_time else "participant_or_scene_shift"
                boundary_reasons.append(reason)
                groups.append([event])
        result = []
        for index, group in enumerate(groups, start=1):
            spans = [to_dict(item.source_span) for item in group]
            result.append({
                "plot_event_id": f"PLOT_{index:04d}",
                "sequence": index,
                "member_world_event_ids": [item.event_id for item in group],
                "source_spans": spans,
                "start_sentence": group[0].time["sentence_index"],
                "end_sentence": group[-1].time["sentence_index"],
                "participants": sorted({person for item in group for person in item.participants}),
                "location_ids": sorted({place for item in group for place in item.space["location_ids"]}),
                "triggers": sorted({trigger for item in group for trigger in item.event["triggers"]}),
                "raw_text": "".join(item.event["raw_text"] for item in group),
                "summary": None,
                "narrative_function": None,
                "merge_method": "adjacent_shared_participant_or_location",
                "confidence": 0.65 if len(group) > 1 else 0.45,
                "boundary_before": "document_start" if index == 1 else boundary_reasons[index - 2],
                "llm_review_required": len(group) == 1,
                "affective_context": self._aggregate_event_affect(group),
            })
        return result

    @staticmethod
    def _aggregate_event_affect(events: list[EventItem]) -> dict[str, Any] | None:
        states = [event.event.get("affect", {}).get("atmosphere") for event in events]
        states = [state for state in states if state]
        if not states:
            return None
        dimensions = ("valence", "arousal", "dominance")
        vad = {
            dimension: round(sum(state["vad"][dimension] for state in states) / len(states), 4)
            for dimension in dimensions
        }
        emotions: dict[str, float] = defaultdict(float)
        for state in states:
            for label, score in state["emotion_distribution"].items():
                emotions[label] += score
        return {
            "vad": vad,
            "emotion_distribution": {
                label: round(score / len(states), 4)
                for label, score in sorted(emotions.items(), key=lambda pair: -pair[1])
            },
            "evidence_event_ids": [
                event.event_id for event in events
                if event.event.get("affect", {}).get("evidence_count", 0) > 0
            ],
            "fill_mode": "summarize",
            "confidence": round(sum(state["confidence"] for state in states) / len(states), 4),
        }

    def _extract_entities(self, sentences: list[dict[str, Any]]) -> list[EntityMention]:
        mentions: list[EntityMention] = []
        corpus = " ".join(sentence["text"] for sentence in sentences)
        english_counts = defaultdict(int)
        chinese_counts = defaultdict(int)
        for match in NAME_RE.finditer(corpus):
            english_counts[match.group(0)] += 1
        for match in CHINESE_NAME_RE.finditer(corpus):
            chinese_counts[match.group(0)] += 1
        for sentence in sentences:
            text = sentence["text"]
            for term in LOCATION_TERMS:
                if term in text:
                    entity_id = self._entity_id(term, "location")
                    start = text.find(term)
                    mentions.append(EntityMention(term, entity_id, "location", sentence["index"], 0.85, sentence["start"] + max(start, 0), sentence["start"] + max(start, 0) + len(term)))
            for term in EN_LOCATION_TERMS:
                if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
                    entity_id = self._entity_id(term.lower(), "location")
                    start = text.lower().find(term.lower())
                    mentions.append(EntityMention(term, entity_id, "location", sentence["index"], 0.7, sentence["start"] + max(start, 0), sentence["start"] + max(start, 0) + len(term)))
            name_matches = self._contextual_name_matches(text)
            name_matches.extend((m.group(0), m.start(), m.end(), 0.9) for m in MIXED_NAME_RE.finditer(text))
            if jieba_posseg is not None and re.search(r"[\u4e00-\u9fff]", text):
                cursor = 0
                for token in jieba_posseg.cut(text):
                    surface = token.word.strip()
                    if not surface:
                        continue
                    start = text.find(surface, cursor)
                    cursor = max(cursor, start + len(surface))
                    if token.flag in {"nr", "nr1", "nr2", "nrj", "nrf"} and len(surface) >= 2:
                        name_matches.append((surface, start, start + len(surface), 0.55))
            if not name_matches:
                name_matches = [(m.group(0), m.start(), m.end(), 0.45) for m in list(CHINESE_NAME_RE.finditer(text)) + list(NAME_RE.finditer(text))]
            selected_matches = []
            for surface, match_start, match_end, match_confidence in sorted(name_matches, key=lambda item: (item[1], len(item[0]))):
                if any(match_start >= chosen[1] and match_end <= chosen[2] for chosen in selected_matches):
                    continue
                selected_matches.append((surface, match_start, match_end, match_confidence))
            for surface, match_start, match_end, match_confidence in selected_matches:
                if (
                    surface in NAME_STOPWORDS
                    or surface in ZH_NAME_STOPWORDS
                    or surface in LOCATION_TERMS
                    or surface in EVENT_TRIGGERS
                    or len(surface) > 4 and not surface.isascii()
                    or (not surface.isascii() and surface.endswith(NON_NAME_SUFFIXES))
                ):
                    continue
                context = text[max(0, match_start - 8): min(len(text), match_end + 10)]
                context_score = self._character_context_score(context, surface)
                if not surface.isascii() and match_confidence < 0.8 and chinese_counts[surface] < 2 and context_score == 0 and not any(surface.endswith(role) for role in ROLE_SUFFIXES):
                    continue
                if not surface.isascii() and match_confidence < 0.8 and surface[0] not in COMMON_SURNAMES:
                    continue
                if not surface.isascii() and match_confidence < 0.8 and not any(surface.endswith(role) for role in ROLE_SUFFIXES):
                    if context_score == 0:
                        continue
                if surface in EN_NAME_STOPWORDS or surface.lower() in EN_LOCATION_TERMS or surface in EN_EVENT_TRIGGERS:
                    continue
                if surface.isascii() and surface.isupper():
                    continue
                if surface.isascii() and english_counts[surface] < 2:
                    continue
                entity_id = self._entity_id(surface, "character")
                mentions.append(EntityMention(surface, entity_id, "character", sentence["index"], match_confidence, sentence["start"] + match_start, sentence["start"] + match_end))
        character_groups: dict[str, list[EntityMention]] = defaultdict(list)
        for mention in mentions:
            if mention.entity_type == "character":
                character_groups[mention.entity_id].append(mention)
        confirmed_character_ids = {
            entity_id
            for entity_id, group in character_groups.items()
            if len(group) >= 2 or max(item.confidence for item in group) >= 0.8
        }
        return [
            mention for mention in mentions
            if mention.entity_type != "character" or mention.entity_id in confirmed_character_ids
        ]

    def _extract_character_candidates(self, text: str, confirmed: list[EntityMention]) -> list[dict[str, Any]]:
        confirmed_surfaces = {item.text for item in confirmed if item.entity_type == "character"}
        counts = defaultdict(int)
        for match in CHINESE_NAME_RE.finditer(text):
            surface = match.group(0)
            if surface not in NAME_STOPWORDS and surface not in ZH_NAME_STOPWORDS:
                counts[surface] += 1
        candidates = []
        for surface, count in counts.items():
            if surface in confirmed_surfaces or count < 2:
                continue
            candidates.append({
                "surface": surface,
                "mention_count": count,
                "status": "candidate",
                "promotion_required": True,
                "candidate_source": "surname_pattern",
                "evidence_policy": "Promote only after contextual or LLM evidence confirms a person entity.",
            })
        return sorted(candidates, key=lambda item: (-item["mention_count"], item["surface"]))

    @staticmethod
    def _contextual_name_matches(text: str) -> list[tuple[str, int, int, float]]:
        matches: list[tuple[str, int, int, float]] = []
        surname_class = re.escape("".join(sorted(COMMON_SURNAMES)))
        patterns = (
            re.compile(rf"(?:名叫|叫做|称作|稱作|唤作|喚作)(?P<name>[{surname_class}][\u4e00-\u9fff]{{0,3}})"),
            re.compile(rf"姓(?P<name>[{surname_class}])"),
            re.compile(rf"(?P<name>[{surname_class}][\u4e00-\u9fff]{{0,2}})(?=先生|太太|姑娘|公子|大人|老爷|老爺|夫人|将军|將軍|丞相)"),
        )
        for pattern in patterns:
            for match in pattern.finditer(text):
                surface = match.group("name")
                surface = re.sub(r"^(?:那|这|只见|忽见|却见|便见|又见|把|请|請|对|對)", "", surface)
                if len(surface) < 1 or (len(surface) == 1 and surface not in COMMON_SURNAMES):
                    continue
                start = match.start("name") + (len(match.group("name")) - len(surface))
                matches.append((surface, start, start + len(surface), 0.9))
        return matches

    @staticmethod
    def _character_context_score(context: str, surface: str) -> int:
        score = 0
        if re.search(r"(?:说|道|问|答|叫|名叫|称为|告诉|对着|向着|拜见|遇见|看见|认识|姓)[^。！？!?]{0,8}" + re.escape(surface), context):
            score += 2
        if re.search(re.escape(surface) + r"[^。！？!?]{0,8}(?:说|道|问|答|叫|告诉|看见|走进|来到|离开)", context):
            score += 2
        if re.search(r"(?:同|与|與|向|对|對|跟)[^。！？!?]{0,3}" + re.escape(surface), context):
            score += 2
        if re.search(re.escape(surface) + r"(?:的|之)(?:眼色|神情|声音|聲音|话|話|手|脸|臉|家|父|母|兄|弟|妻|夫)", context):
            score += 1
        if re.search(r"(?:先生|太太|小姐|公子|姑娘|大人|老爷|夫人)$", context[: max(0, context.find(surface))]):
            score += 1
        return score

    def _entity_id(self, surface: str, entity_type: str) -> str:
        if surface not in self._entity_by_surface:
            prefix = "CHAR" if entity_type == "character" else "LOC"
            self._entity_by_surface[surface] = f"{prefix}_{len([x for x in self._entity_by_surface if self._entity_type.get(x) == entity_type]) + 1:03d}"
            self._entity_type[surface] = entity_type
        return self._entity_by_surface[surface]

    def _extract_events(self, sentences: list[dict[str, Any]], times: list[TimeMention], entities: list[EntityMention]) -> list[EventItem]:
        events: list[EventItem] = []
        times_by_sentence = defaultdict(list)
        entities_by_sentence = defaultdict(list)
        for item in times:
            if item.raw_text:
                times_by_sentence[item.sentence_index].append(item)
        for item in entities:
            entities_by_sentence[item.sentence_index].append(item)

        for sentence in sentences:
            text = sentence["text"]
            triggers = [term for term in EVENT_TRIGGERS if term in text]
            triggers.extend(term for term in EN_EVENT_TRIGGERS if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE))
            source_span = SourceSpan(self.source_id, sentence["start"], sentence["end"], text)
            people = [item.entity_id for item in entities_by_sentence[sentence["index"]] if item.entity_type == "character"]
            people.extend(self._resolve_pronouns(sentence, entities_by_sentence, sentences, set(people)))
            unresolved_pronouns = [pronoun for pronoun in PRONOUNS if pronoun in text and not self._resolve_pronouns(sentence, entities_by_sentence, sentences, set(people))]
            locations = [item.entity_id for item in entities_by_sentence[sentence["index"]] if item.entity_type == "location"]
            people = sorted(set(people))
            affect = self._affect_analyzer.analyze_event(text, sentence["start"], people)
            self._bind_affect_holders(affect, entities_by_sentence[sentence["index"]], people)
            if not triggers and affect["evidence_count"] == 0:
                continue
            if not triggers:
                triggers = ["affective_expression"]
            event_id = f"EV_{len(events) + 1:04d}"
            events.append(EventItem(
                event_id=event_id,
                sequence=len(events) + 1,
                source_span=source_span,
                time={"mentions": [to_dict(item) for item in times_by_sentence[sentence["index"]]], "sentence_index": sentence["index"]},
                space={"location_ids": locations},
                event={
                    "triggers": triggers, "raw_text": text, "summary": None,
                    "narrative_function": None, "unresolved_pronouns": unresolved_pronouns,
                    "affect": affect,
                },
                participants=people,
                world_state={"before": [], "changes": [], "after": []},
                source={"fill_mode": "extract", "confidence": 0.45, "source_spans": [to_dict(source_span)]},
            ))
        return events

    @staticmethod
    def _link_cross_event_causes(events: list[EventItem]) -> None:
        """Add conservative cross-sentence emotion-cause pairs before LLM review."""
        cause_markers = ("因为", "因為", "由于", "由於", "因此", "所以", "于是", "於是", "because", "therefore", "after")
        for index, event in enumerate(events):
            affect = event.event.get("affect", {})
            if not affect.get("evidence_count"):
                continue
            current_text = event.event["raw_text"].lower()
            candidates = []
            for previous in events[max(0, index - 3):index]:
                if not previous.event.get("raw_text"):
                    continue
                shared_people = bool(set(event.participants) & set(previous.participants))
                explicit_marker = any(marker in current_text for marker in cause_markers)
                if explicit_marker or shared_people:
                    candidates.append({
                        "cause_event_id": previous.event_id,
                        "emotion_event_id": event.event_id,
                        "relation": "possible_emotion_cause",
                        "shared_participant": shared_people,
                        "evidence_policy": "Candidate pair; confirm causal direction with semantic model.",
                        "fill_mode": "infer", "confidence": 0.58 if explicit_marker else 0.38,
                    })
            affect["cross_event_cause_candidates"] = candidates

    @staticmethod
    def _bind_affect_holders(affect: dict[str, Any], mentions: list[EntityMention], people: list[str]) -> None:
        """Prefer the nearest same-sentence named mention; retain ambiguity explicitly."""
        character_mentions = [item for item in mentions if item.entity_type == "character"]
        if len(character_mentions) <= 1:
            return
        for expression in affect.get("expressions", []):
            position = expression["source_span"]["start"]
            distances = sorted(
                (abs(item.start - position), item.entity_id) for item in character_mentions
            )
            if distances and distances[0][0] < distances[1][0] * 0.6:
                expression["holder_candidates"] = [distances[0][1]]
                expression["holder_binding"] = "nearest_same_sentence_mention"
            else:
                expression["holder_binding"] = "ambiguous_same_sentence_mentions"

    def _resolve_pronouns(self, sentence: dict[str, Any], entities_by_sentence: dict[int, list[EntityMention]], sentences: list[dict[str, Any]], current_people: set[str]) -> list[str]:
        """Resolve simple Chinese pronouns to the nearest compatible named character.

        This is deliberately conservative: unresolved pronouns are not attached to a person.
        """
        if not any(pronoun in sentence["text"] for pronoun in PRONOUNS):
            return []
        current = sentence["index"]
        candidates: list[tuple[int, str]] = []
        for distance in range(1, 5):
            for mention in entities_by_sentence.get(current - distance, []):
                if mention.entity_type == "character":
                    candidates.append((distance, mention.entity_id))
        unique_candidates = []
        for distance, entity_id in candidates:
            if entity_id not in current_people and entity_id not in {item[1] for item in unique_candidates}:
                unique_candidates.append((distance, entity_id))
        if not unique_candidates:
            return []
        # Resolve only when one non-current antecedent remains; ambiguity is preserved as unresolved.
        if len(unique_candidates) == 1:
            return [unique_candidates[0][1]]
        return []

    def _order_events(self, events: list[EventItem]) -> list[EventItem]:
        """Order events with temporal constraints, retaining uncertainty explicitly."""
        if not events:
            return events
        edges: dict[str, set[str]] = {event.event_id: set() for event in events}
        indegree = {event.event_id: 0 for event in events}
        relations: list[dict[str, Any]] = []
        for previous, current in zip(events, events[1:]):
            marker = current.source_span.text
            relation = "BEFORE"
            confidence = 0.35
            if re.search(r"回忆|想起|那年|多年以前|曾经", marker):
                relation = "STORY_BEFORE"
                confidence = 0.7
            elif re.search(r"第二天|次日|翌日|后来|之后|随后", marker):
                relation = "BEFORE"
                confidence = 0.8
            elif re.search(r"此前|之前|早些时候", marker):
                relation = "AFTER"
                confidence = 0.7
            if relation == "BEFORE":
                self._add_edge(edges, indegree, previous.event_id, current.event_id)
            elif relation == "AFTER":
                self._add_edge(edges, indegree, current.event_id, previous.event_id)
            elif relation == "STORY_BEFORE":
                # Keep the constraint graph sparse. The adjacent discourse chain
                # propagates this ordering without adding O(n^2) edges for a long
                # flashback block.
                self._add_edge(edges, indegree, current.event_id, previous.event_id)
            relations.append({"from": previous.event_id, "to": current.event_id, "relation": relation, "confidence": confidence})
        by_id = {event.event_id: event for event in events}
        ready = deque(sorted((event_id for event_id, degree in indegree.items() if degree == 0), key=lambda item: by_id[item].source_span.start))
        ordered_ids: list[str] = []
        while ready:
            event_id = ready.popleft()
            ordered_ids.append(event_id)
            for target in sorted(edges[event_id], key=lambda item: by_id[item].source_span.start):
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        # A cycle means contradictory temporal evidence; preserve discourse order for that component.
        if len(ordered_ids) != len(events):
            ordered_ids = [event.event_id for event in events]
            status = "discourse_fallback_cycle"
        else:
            status = "temporal_constraint_topological_order"
        ordered = [by_id[event_id] for event_id in ordered_ids]
        for index, event in enumerate(ordered, start=1):
            event.sequence = index
            event.time["story_sequence"] = index
        self._temporal_relations = relations
        self._temporal_ordering_status = status
        return ordered

    @staticmethod
    def _add_edge(edges: dict[str, set[str]], indegree: dict[str, int], source: str, target: str) -> None:
        if source == target or target in edges[source]:
            return
        edges[source].add(target)
        indegree[target] += 1

    def _build_world_line(self, events: list[EventItem], times: list[TimeMention], entities: list[EntityMention]) -> dict[str, Any]:
        return {
            "world_id": "WORLD_001",
            "time_nodes": [{"time_id": item.normalized, "raw_text": item.raw_text, "sentence_index": item.sentence_index, "confidence": item.confidence} for item in times if item.raw_text],
            "events": [to_dict(item) for item in events],
            "ordering_method": getattr(self, "_temporal_ordering_status", "temporal_constraint_topological_order"),
            "ordering_needs_llm_review": False,
            "temporal_relations": getattr(self, "_temporal_relations", []),
            "ordering_uncertainty": "Unconstrained events retain source order; contradictory constraints are marked in ordering_method.",
            "locations": sorted({item.entity_id for item in entities if item.entity_type == "location"}),
        }

    @staticmethod
    def _summarize_world_affect(events: list[EventItem]) -> dict[str, Any]:
        states = [event.event.get("affect", {}).get("atmosphere") for event in events]
        states = [state for state in states if state]
        if not states:
            return {"status": "insufficient_evidence", "event_coverage": 0.0}
        dimensions = ("valence", "arousal", "dominance")
        means = {
            dimension: round(sum(state["vad"][dimension] for state in states) / len(states), 4)
            for dimension in dimensions
        }
        variability = {
            dimension: round((sum((state["vad"][dimension] - means[dimension]) ** 2 for state in states) / len(states)) ** 0.5, 4)
            for dimension in dimensions
        }
        return {
            "vad_mean": means,
            "vad_variability": variability,
            "event_coverage": round(len(states) / max(1, len(events)), 4),
            "high_arousal_event_ids": [
                event.event_id for event in events
                if (event.event.get("affect", {}).get("atmosphere") or {}).get("vad", {}).get("arousal", 0) >= 0.7
            ],
            "analysis_method": "event_affect_aggregation",
            "fill_mode": "summarize",
        }

    def _build_knowledge_graph(
        self,
        events: list[EventItem],
        entities: list[EntityMention],
        character_lines: list[dict[str, Any]],
        plot_events: list[dict[str, Any]],
        character_resolution: dict[str, Any],
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        seen: set[str] = set()
        for mention in entities:
            if mention.entity_id in seen:
                continue
            seen.add(mention.entity_id)
            nodes.append({
                "node_id": mention.entity_id,
                "node_type": mention.entity_type,
                "label": mention.text,
                "line_anchor": "world_profile",
                "epistemic_status": "explicit",
                "confidence": mention.confidence,
                "source_spans": [{"source_id": self.source_id, "start": mention.start, "end": mention.end, "text": mention.text}],
            })
        for event in events:
            nodes.append({
                "node_id": event.event_id,
                "node_type": "event",
                "label": event.event["raw_text"],
                "line_anchor": "world_line",
                "time_sequence": event.sequence,
                "source_spans": [to_dict(event.source_span)],
                "epistemic_status": "explicit",
                "confidence": event.source["confidence"],
            })
        for plot_event in plot_events:
            nodes.append({
                "node_id": plot_event["plot_event_id"],
                "node_type": "plot_event",
                "label": plot_event["raw_text"],
                "line_anchor": "world_line.plot_events",
                "time_sequence": plot_event["sequence"],
                "source_spans": plot_event["source_spans"],
                "epistemic_status": "derived",
                "confidence": plot_event["confidence"],
            })
        for role in character_resolution["unnamed_role_chains"]:
            nodes.append({
                "node_id": role["local_entity_id"],
                "node_type": "unnamed_character_role",
                "label": role["surface"],
                "line_anchor": "character_resolution.unnamed_role_chains",
                "source_spans": [item["source_span"] for item in role["mentions"]],
                "epistemic_status": "candidate",
                "confidence": role["confidence"],
            })
        edges: list[dict[str, Any]] = []
        for event in events:
            for participant in event.participants:
                edges.append({"from": event.event_id, "relation": "participates", "to": participant, "line_anchor": "world_line", "source_spans": [to_dict(event.source_span)]})
            for cause in event.event.get("affect", {}).get("cross_event_cause_candidates", []):
                edges.append({
                    "from": cause["cause_event_id"], "relation": "possible_emotion_cause",
                    "to": cause["emotion_event_id"], "line_anchor": "world_line",
                    "epistemic_status": "candidate", "confidence": cause["confidence"],
                    "source_spans": [to_dict(event.source_span)],
                })
        for plot_event in plot_events:
            for event_id in plot_event["member_world_event_ids"]:
                edges.append({
                    "from": plot_event["plot_event_id"], "relation": "aggregates", "to": event_id,
                    "line_anchor": "world_line.plot_events", "source_spans": plot_event["source_spans"],
                })
        for role in character_resolution["unnamed_role_chains"]:
            for mention in role["mentions"]:
                if mention["event_id"]:
                    edges.append({
                        "from": mention["event_id"], "relation": "mentions_unnamed_role",
                        "to": role["local_entity_id"], "line_anchor": "character_resolution.unnamed_role_chains",
                        "source_spans": [mention["source_span"]],
                    })
        for alias in character_resolution["alias_candidates"]:
            edges.append({
                "from": alias["left_id"], "relation": "possible_alias", "to": alias["right_id"],
                "line_anchor": "character_resolution.alias_candidates", "confidence": alias["confidence"],
                "epistemic_status": "candidate",
            })
        for relation in getattr(self, "_temporal_relations", []):
            edges.append({**relation, "line_anchor": "world_line"})
        for route in character_lines:
            for item in route["items"]:
                edges.append({
                    "from": route["character_id"], "relation": "experiences", "to": item["world_event_id"],
                    "line_anchor": "character_line", "source_spans": [item["source_span"]],
                    "affect_delta": item.get("psychology", {}).get("affect", {}).get("delta"),
                })
        return {
            "nodes": nodes,
            "edges": edges,
            "anchor_policy": "Every node and edge must point to a world_line or character_line item.",
            "llm_enrichment_allowed": ["summary", "causal_edges", "motivation", "narrative_function", "adapted_bridges"],
        }

    def _character_profiles(self, entities: list[EntityMention]) -> list[dict[str, Any]]:
        grouped: dict[str, list[EntityMention]] = defaultdict(list)
        for item in entities:
            if item.entity_type == "character":
                grouped[item.entity_id].append(item)
        return [
            {
                "character_id": character_id,
                "name": mentions[0].text,
                "surface_forms": sorted({item.text for item in mentions}),
                "mention_count": len(mentions),
                "source_spans": [{"source_id": self.source_id, "start": item.start, "end": item.end, "text": item.text} for item in mentions[:20]],
                "epistemic_status": "explicit",
                "llm_fields": ["goals", "motivation", "arc", "voice"],
            }
            for character_id, mentions in sorted(grouped.items())
        ]

    def _build_character_lines(self, events: list[EventItem], entities: list[EntityMention]) -> list[dict[str, Any]]:
        lines: dict[str, list[CharacterLineItem]] = defaultdict(list)
        states: dict[str, dict[str, float]] = defaultdict(lambda: {"valence": 0.5, "arousal": 0.5, "dominance": 0.5})
        for event in events:
            for character_id in event.participants:
                role = "agent" if event.event["triggers"] else "affected"
                before = dict(states[character_id])
                atmosphere = event.event.get("affect", {}).get("atmosphere")
                during = dict(atmosphere["vad"]) if atmosphere else dict(before)
                after = {
                    dimension: round(before[dimension] * 0.65 + during[dimension] * 0.35, 4)
                    for dimension in before
                }
                delta = {dimension: round(after[dimension] - before[dimension], 4) for dimension in before}
                states[character_id] = after
                affect = {
                    "before": before,
                    "during": during,
                    "after": after,
                    "delta": delta,
                    "emotion_distribution": atmosphere["emotion_distribution"] if atmosphere else {},
                    "appraisal": {
                        "cause_candidates": event.event.get("affect", {}).get("causal_triggers", []),
                        "goal_relevance": None, "goal_congruence": None,
                        "controllability": None, "agency": None,
                        "llm_review_required": True,
                    },
                    "transition_type": self._affect_transition_type(delta),
                    "evidence_event_ids": [event.event_id],
                    "fill_mode": "infer" if atmosphere else "unresolved",
                    "confidence": atmosphere["confidence"] if atmosphere else 0.0,
                    "analysis_method": "event_evidence_exponential_state_update",
                }
                lines[character_id].append(CharacterLineItem(
                    character_id=character_id,
                    sequence=len(lines[character_id]) + 1,
                    world_event_id=event.event_id,
                    role=role,
                    source_span=event.source_span,
                    action=event.event["raw_text"],
                    perception={"known_facts_before": [], "knowledge_gained": [], "interpretation": None},
                    psychology={"goal_before": [], "motivation": None, "affect": affect, "internal_conflict": None},
                    relationships=[],
                    source={"fill_mode": "extract", "confidence": 0.35, "source_spans": [to_dict(event.source_span)]},
                ))
        return [
            {
                "character_id": character_id,
                "items": [to_dict(item) for item in items],
                "affective_summary": self._summarize_character_affect(items),
            }
            for character_id, items in sorted(lines.items())
        ]

    @staticmethod
    def _affect_transition_type(delta: dict[str, float]) -> str:
        if max(abs(value) for value in delta.values()) < 0.02:
            return "stable"
        if delta["valence"] < -0.05 and delta["arousal"] > 0.05:
            return "negative_activation"
        if delta["valence"] > 0.05 and delta["arousal"] < -0.02:
            return "positive_relief"
        if delta["dominance"] < -0.05:
            return "loss_of_control"
        if delta["valence"] > 0.05:
            return "positive_shift"
        if delta["valence"] < -0.05:
            return "negative_shift"
        return "mixed_shift"

    @staticmethod
    def _summarize_character_affect(items: list[CharacterLineItem]) -> dict[str, Any]:
        observed = [item.psychology["affect"] for item in items if item.psychology["affect"]["confidence"] > 0]
        if not observed:
            return {"status": "insufficient_evidence", "event_coverage": 0.0}
        dimensions = ("valence", "arousal", "dominance")
        means = {
            dimension: round(sum(item["after"][dimension] for item in observed) / len(observed), 4)
            for dimension in dimensions
        }
        variability = {
            dimension: round((sum((item["after"][dimension] - means[dimension]) ** 2 for item in observed) / len(observed)) ** 0.5, 4)
            for dimension in dimensions
        }
        return {
            "home_base": means,
            "variability": variability,
            "event_coverage": round(len(observed) / max(1, len(items)), 4),
            "dominant_transition_types": dict(sorted(
                ((kind, sum(item["transition_type"] == kind for item in observed)) for kind in {item["transition_type"] for item in observed}),
                key=lambda pair: -pair[1],
            )),
            "fill_mode": "summarize",
            "analysis_method": "character_event_state_aggregation",
        }

    def _world_profile(self, sentences: list[dict[str, Any]], entities: list[EntityMention]) -> dict[str, Any]:
        return {
            "title": None,
            "genre": None,
            "time_span": None,
            "locations": sorted({item.entity_id for item in entities if item.entity_type == "location"}),
            "organizations": [],
            "rules": [],
            "fixed_facts": [],
            "llm_fields": ["title", "genre", "time_span", "rules", "themes", "background_conflicts"],
        }


def index_novel(text: str, source_id: str = "novel") -> dict[str, Any]:
    return NovelIndexer(source_id=source_id).index_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build World Line and Character Lines from a novel without an LLM.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-id", default="novel")
    args = parser.parse_args()
    text = args.input.read_text(encoding="utf-8")
    result = index_novel(text, args.source_id)
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise SystemExit(
            f"Output directory is not writable: {args.output.parent}. "
            "Choose a writable path with --output."
        ) from exc
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
