from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    output_dir = Path(__file__).with_name("batch_results_zh_v2")
    novels_dir = Path(__file__).parent.parent / "narrative_novels_zh"
    print("book|events|profiles|candidates|character_lines|time_nodes|kg_nodes|kg_edges|bad_event_refs|span_mismatches")
    for path in sorted(output_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = next(novels_dir.glob(path.stem + ".txt")).read_text(encoding="utf-8")
        events = data["world_line"]["events"]
        event_ids = {item["event_id"] for item in events}
        references = [item["world_event_id"] for line in data["character_lines"] for item in line["items"]]
        spans = [item["source_span"] for item in events]
        spans.extend(span for profile in data["character_profiles"] for span in profile["source_spans"])
        span_mismatches = sum(raw[span["start"]:span["end"]] != span["text"] for span in spans)
        print("|".join(map(str, (
            path.stem, len(events), len(data["character_profiles"]),
            len(data["indexes"]["character_candidates"]), len(data["character_lines"]),
            len(data["world_line"]["time_nodes"]), len(data["knowledge_graph"]["nodes"]),
            len(data["knowledge_graph"]["edges"]), sum(ref not in event_ids for ref in references),
            span_mismatches,
        ))))


if __name__ == "__main__":
    main()
