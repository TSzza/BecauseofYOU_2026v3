from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SourceSpan:
    source_id: str
    start: int
    end: int
    text: str


@dataclass
class TimeMention:
    raw_text: str
    normalized: str
    sentence_index: int
    confidence: float = 0.6


@dataclass
class EntityMention:
    text: str
    entity_id: str
    entity_type: str
    sentence_index: int
    confidence: float = 0.5
    start: int = 0
    end: int = 0


@dataclass
class EventItem:
    event_id: str
    sequence: int
    source_span: SourceSpan
    time: dict[str, Any]
    space: dict[str, Any]
    event: dict[str, Any]
    participants: list[str] = field(default_factory=list)
    world_state: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)


@dataclass
class CharacterLineItem:
    character_id: str
    sequence: int
    world_event_id: str
    role: str
    source_span: SourceSpan
    action: str
    perception: dict[str, Any] = field(default_factory=dict)
    psychology: dict[str, Any] = field(default_factory=dict)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value
