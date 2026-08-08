from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parent.parent
SPECS = (
    ("en", ROOT / "narrative_novels", Path(__file__).with_name("batch_results_en_v4")),
    ("zh", ROOT / "narrative_novels_zh", Path(__file__).with_name("batch_results_zh_v4")),
)


def audit_file(language: str, novel_path: Path, result_path: Path) -> dict:
    raw = novel_path.read_text(encoding="utf-8")
    data = json.loads(result_path.read_text(encoding="utf-8"))
    events = data["world_line"]["events"]
    plots = data["world_line"]["plot_events"]
    routes = data["character_lines"]
    event_ids = {event["event_id"] for event in events}
    affective_events = [event for event in events if event["event"]["affect"]["evidence_count"] > 0]
    evidence = [item for event in events for item in event["event"]["affect"]["expressions"]]
    span_mismatches = sum(
        raw[item["source_span"]["start"]:item["source_span"]["end"]] != item["source_span"]["text"]
        for item in evidence
    )
    bad_event_refs = sum(
        item["world_event_id"] not in event_ids
        for route in routes for item in route["items"]
    )
    continuity_errors = 0
    character_affect_items = 0
    evidenced_character_items = 0
    for route in routes:
        items = route["items"]
        for previous, current in zip(items, items[1:]):
            if previous["psychology"]["affect"]["after"] != current["psychology"]["affect"]["before"]:
                continuity_errors += 1
        character_affect_items += len(items)
        evidenced_character_items += sum(item["psychology"]["affect"]["confidence"] > 0 for item in items)
    aggregate_targets = {
        edge["to"] for edge in data["knowledge_graph"]["edges"] if edge["relation"] == "aggregates"
    }
    structural_checks = {
        "event_affect_schema": all("affect" in event["event"] for event in events),
        "plot_affect_schema": all("affective_context" in plot for plot in plots),
        "world_summary": "affective_summary" in data["world_line"],
        "character_affect_schema": all("affect" in item["psychology"] for route in routes for item in route["items"]),
        "character_summaries": all("affective_summary" in route for route in routes),
        "event_references": bad_event_refs == 0,
        "affect_spans": span_mismatches == 0,
        "state_continuity": continuity_errors == 0,
        "plot_kg_anchors": aggregate_targets == event_ids,
    }
    return {
        "language": language, "book": novel_path.stem,
        "events": len(events), "plot_events": len(plots),
        "merged_plot_events": sum(len(plot["member_world_event_ids"]) > 1 for plot in plots),
        "characters": len(data["character_profiles"]), "character_lines": len(routes),
        "alias_candidates": len(data["character_resolution"]["alias_candidates"]),
        "canonical_alias_groups": len(data["character_resolution"]["canonical_alias_groups"]),
        "unnamed_role_chains": len(data["character_resolution"]["unnamed_role_chains"]),
        "cross_event_cause_candidates": sum(
            len(event["event"]["affect"].get("cross_event_cause_candidates", [])) for event in events
        ),
        "affective_events": len(affective_events), "affect_evidence": len(evidence),
        "event_affect_coverage": round(len(affective_events) / max(1, len(events)), 4),
        "character_affect_coverage": round(evidenced_character_items / max(1, character_affect_items), 4),
        "kg_nodes": len(data["knowledge_graph"]["nodes"]),
        "kg_edges": len(data["knowledge_graph"]["edges"]),
        "bad_event_refs": bad_event_refs, "span_mismatches": span_mismatches,
        "continuity_errors": continuity_errors,
        "structural_score": round(sum(structural_checks.values()) / len(structural_checks), 4),
        "structural_checks": structural_checks,
    }


def main() -> None:
    rows = []
    for language, novels_dir, results_dir in SPECS:
        for novel_path in sorted(novels_dir.glob("*.txt")):
            rows.append(audit_file(language, novel_path, results_dir / f"{novel_path.stem}.json"))
    report = {
        "documents": len(rows),
        "rows": rows,
        "aggregate": {
            "events": sum(row["events"] for row in rows),
            "plot_events": sum(row["plot_events"] for row in rows),
            "affective_events": sum(row["affective_events"] for row in rows),
            "affect_evidence": sum(row["affect_evidence"] for row in rows),
            "bad_event_refs": sum(row["bad_event_refs"] for row in rows),
            "span_mismatches": sum(row["span_mismatches"] for row in rows),
            "continuity_errors": sum(row["continuity_errors"] for row in rows),
        },
    }
    output = Path(__file__).with_name("affect_batch_audit_v4.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("lang|book|events|plots|chars|lines|affect_events|evidence|event_cov|char_cov|aliases|roles|struct")
    for row in rows:
        print("|".join(map(str, (
            row["language"], row["book"], row["events"], row["plot_events"], row["characters"],
            row["character_lines"], row["affective_events"], row["affect_evidence"],
            row["event_affect_coverage"], row["character_affect_coverage"], row["alias_candidates"],
            row["unnamed_role_chains"], row["structural_score"],
        ))))
    print(json.dumps(report["aggregate"], ensure_ascii=False))


if __name__ == "__main__":
    main()
