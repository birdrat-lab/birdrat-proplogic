from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from birdrat_proplogic.formula import Formula, pretty
from birdrat_proplogic.proof import Invalid, Proof, proof_pretty


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def write_report(
    payload: dict[str, Any],
    *,
    report_dir: str | Path,
    stem: str,
    report_format: str = "json",
) -> tuple[Path, ...]:
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if report_format in ("json", "both"):
        path = directory / f"{stem}.json"
        path.write_text(json.dumps(to_report_data(payload), indent=2, sort_keys=True) + "\n")
        written.append(path)
    if report_format in ("md", "both"):
        path = directory / f"{stem}.md"
        path.write_text(markdown_report(payload))
        written.append(path)
    return tuple(written)


def to_report_data(value: Any) -> Any:
    if isinstance(value, Invalid):
        return {"invalid": value.reason}
    if _is_formula(value):
        return pretty(value)
    if _is_proof(value):
        return proof_pretty(value)
    if is_dataclass(value):
        return {field.name: to_report_data(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): to_report_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_report_data(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def markdown_report(payload: dict[str, Any]) -> str:
    data = to_report_data(payload)
    lines = [f"# {data.get('title', 'birdrat-proplogic report')}", ""]
    summary = data.get("summary")
    if summary is not None:
        lines.extend(["## Summary", "", "```json", json.dumps(summary, indent=2, sort_keys=True), "```", ""])
    lines.extend(["## Full Data", "", "```json", json.dumps(data, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)


def _is_formula(value: Any) -> bool:
    return value.__class__.__module__ == "birdrat_proplogic.formula" and value.__class__.__name__ in {
        "Atom",
        "Meta",
        "Not",
        "Imp",
    }


def _is_proof(value: Any) -> bool:
    return value.__class__.__module__ == "birdrat_proplogic.proof" and value.__class__.__name__ in {
        "Ax1",
        "Ax2",
        "Ax3",
        "CD",
    }
