from __future__ import annotations

from pathlib import Path


class PromptRepository:
    """Loads the small block-style YAML prompt files without a YAML dependency."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self, agent: str) -> str:
        path = self.root / f"{agent}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"prompt file not found: {path}")
        lines = path.read_text(encoding="utf-8").splitlines()
        collecting = False
        content: list[str] = []
        for line in lines:
            if line.strip() == "system: |":
                collecting = True
                continue
            if collecting:
                if line.startswith("    "):
                    content.append(line[4:])
                elif not line.strip():
                    content.append("")
                else:
                    break
        prompt = "\n".join(content).strip()
        if not prompt:
            raise ValueError(f"system prompt is empty: {path}")
        return prompt

