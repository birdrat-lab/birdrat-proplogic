from birdrat_proplogic.config import ArchiveConfig, EvolutionConfig, ProplogicConfig
from birdrat_proplogic.search import make_default_search_phases, search_with_fallback
from birdrat_proplogic.surface import SAtom, SImp


def test_make_default_search_phases_builds_strict_hybrid_and_expanded() -> None:
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=10,
            max_generations=5,
            beam_width=20,
            beam_max_depth=2,
            beam_pair_budget=100,
        ),
    )

    phases = make_default_search_phases(config)

    assert tuple(phase.name for phase in phases) == ("strict-preselected", "hybrid", "expanded-hybrid")
    assert phases[0].prioritized_fraction == 1.0
    assert phases[1].suffix_fraction > 0.0
    assert phases[2].beam_width == 30
    assert phases[2].beam_max_depth == 3
    assert phases[2].beam_pair_budget == 200


def test_search_with_fallback_stops_after_successful_identity_phase() -> None:
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=6,
            max_generations=3,
            beam_width=12,
            beam_max_depth=2,
            beam_pair_budget=100,
        ),
    )

    result = search_with_fallback(SImp(SAtom("p"), SAtom("p")), config, seed=1)

    assert result.found
    assert result.solved_in_phase == "strict-preselected"
    assert len(result.phase_reports) == 1
