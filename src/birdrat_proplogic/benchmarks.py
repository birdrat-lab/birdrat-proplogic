from __future__ import annotations

from dataclasses import dataclass

from birdrat_proplogic.config import ArchiveConfig, EvolutionConfig, ProplogicConfig
from birdrat_proplogic.parse import ParseError, parse_surface
from birdrat_proplogic.surface import SurfaceFormula


@dataclass(frozen=True)
class SearchBenchmark:
    name: str
    target: SurfaceFormula
    notes: str
    config: ProplogicConfig
    expected_status: str


def small_target_benchmarks() -> tuple[SearchBenchmark, ...]:
    return (
        _benchmark(
            "identity",
            r"p \to p",
            "First non-axiom theorem; confirms CD beam plus evolution can construct a basic Hilbert proof.",
            EvolutionConfig(population_size=20, max_generations=20, beam_width=12, beam_max_depth=2, beam_pair_budget=500),
            "should be found by the current beam/evolution pipeline",
        ),
        _benchmark(
            "syllogism",
            r"(p \to q) \to ((r \to p) \to (r \to q))",
            "Tests composition through Ax2 and implication transport through a context.",
            EvolutionConfig(population_size=60, max_generations=100, beam_width=40, beam_max_depth=3, beam_pair_budget=2500),
            "plausible next target after identity",
        ),
        _benchmark(
            "classical-negation",
            r"\not p \to p \to q",
            "Exercises Ax3 and classical contraposition-style reasoning.",
            EvolutionConfig(population_size=80, max_generations=150, beam_width=50, beam_max_depth=3, beam_pair_budget=3000),
            "may require better target-directed CD pair selection",
        ),
        _benchmark(
            "contraction",
            r"(p \to p \to q) \to p \to q",
            "Tests duplicate antecedent handling without primitive contraction.",
            EvolutionConfig(population_size=80, max_generations=150, beam_width=50, beam_max_depth=4, beam_pair_budget=4000),
            "may require more than the shallow identity configuration",
        ),
        _benchmark(
            "distribution-application",
            r"(p \to q) \to (p \to q \to r) \to p \to r",
            "Tests a deeper Ax2 application pattern.",
            EvolutionConfig(population_size=100, max_generations=200, beam_width=60, beam_max_depth=4, beam_pair_budget=5000),
            "likely requires beam preselection before large beam widths become practical",
        ),
    )


def _benchmark(
    name: str,
    target_text: str,
    notes: str,
    evolution: EvolutionConfig,
    expected_status: str,
) -> SearchBenchmark:
    parsed = parse_surface(target_text)
    if isinstance(parsed, ParseError):
        raise ValueError(parsed.message)
    return SearchBenchmark(
        name=name,
        target=parsed,
        notes=notes,
        config=ProplogicConfig(archive=ArchiveConfig(path=None), evolution=evolution),
        expected_status=expected_status,
    )
