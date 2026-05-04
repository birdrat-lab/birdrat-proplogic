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
            EvolutionConfig(population_size=40, max_generations=40, beam_width=40, beam_max_depth=3, beam_pair_budget=2500),
            "plausible next target after identity",
        ),
        _benchmark(
            "classical-negation",
            r"\not p \to p \to q",
            "Exercises Ax3 and classical contraposition-style reasoning.",
            EvolutionConfig(population_size=40, max_generations=40, beam_width=50, beam_max_depth=3, beam_pair_budget=3000),
            "may require better target-directed CD pair selection",
        ),
        _benchmark(
            "contraction",
            r"(p \to p \to q) \to p \to q",
            "Tests duplicate antecedent handling without primitive contraction.",
            EvolutionConfig(population_size=40, max_generations=40, beam_width=50, beam_max_depth=4, beam_pair_budget=4000),
            "may require more than the shallow identity configuration",
        ),
        _benchmark(
            "distribution-application",
            r"(p \to q) \to (p \to q \to r) \to p \to r",
            "Tests a deeper Ax2 application pattern.",
            EvolutionConfig(population_size=40, max_generations=40, beam_width=60, beam_max_depth=4, beam_pair_budget=5000),
            "likely requires beam preselection before large beam widths become practical",
        ),
    )


def regression_benchmarks() -> tuple[SearchBenchmark, ...]:
    return small_target_benchmarks()


def expanded_target_benchmarks() -> tuple[SearchBenchmark, ...]:
    return (
        _benchmark(
            "double-negation-intro",
            r"p |- \not \not p",
            "Checks whether a simple classical target is reachable without adding a surface-level rule.",
            EvolutionConfig(
                population_size=80,
                max_generations=150,
                diagnostics_interval=1,
                beam_width=240,
                beam_max_depth=7,
                beam_major_budget=10_000,
                beam_pair_budget=100_000,
                beam_stop_on_exact=True,
            ),
            "diagnostic expanded target; failure should be reported without failing the suite unless --strict is used",
        ),
        _benchmark(
            "contrapositive",
            r"p \to q, \not q |- \not p",
            "Diagnostic target for implication plus negation interaction.",
            EvolutionConfig(
                population_size=100,
                max_generations=250,
                diagnostics_interval=1,
                beam_width=320,
                beam_max_depth=8,
                beam_major_budget=20_000,
                beam_pair_budget=200_000,
                beam_stop_on_exact=True,
            ),
            "diagnostic expanded target; failure should be reported without failing the suite unless --strict is used",
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
