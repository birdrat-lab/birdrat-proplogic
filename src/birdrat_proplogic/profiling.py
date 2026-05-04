from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Iterator


@dataclass(frozen=True)
class RuntimeProfile:
    sections: dict[str, float]
    counters: dict[str, int]


class RuntimeProfiler:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._sections: dict[str, float] = {}
        self._counters: dict[str, int] = {}

    @contextmanager
    def section(self, name: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        started = perf_counter()
        try:
            yield
        finally:
            self._sections[name] = self._sections.get(name, 0.0) + perf_counter() - started

    def increment(self, counter: str, amount: int = 1) -> None:
        if not self.enabled:
            return
        self._counters[counter] = self._counters.get(counter, 0) + amount

    def add_time(self, section: str, seconds: float) -> None:
        if not self.enabled:
            return
        self._sections[section] = self._sections.get(section, 0.0) + seconds

    def snapshot(self) -> RuntimeProfile:
        return RuntimeProfile(sections=dict(self._sections), counters=dict(self._counters))


def compact_runtime_summary(profile: RuntimeProfile) -> list[str]:
    sections = profile.sections
    if not sections:
        return []
    names = (
        ("total", "total"),
        ("beam.total", "beam"),
        ("beam.schema_instantiation", "schema instantiation"),
        ("fitness.total", "fitness"),
        ("evolution.selection", "selection"),
        ("report_writing", "report"),
    )
    lines: list[str] = []
    for key, label in names:
        value = sections.get(key)
        if value is not None:
            lines.append(f"  {label}: {value:.3f}s")
    return lines
