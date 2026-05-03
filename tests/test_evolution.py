from birdrat_proplogic.config import ArchiveConfig, EvolutionConfig, ProplogicConfig
from birdrat_proplogic.evolution import evolve
from birdrat_proplogic.proof import Proof
from birdrat_proplogic.surface import SAtom, SImp


def test_evolve_returns_population_and_history() -> None:
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=6,
            max_generations=3,
            elite_count=2,
            tournament_size=2,
            beam_enabled=False,
        )
    )

    result = evolve(SImp(SAtom("a"), SAtom("a")), config, seed=1)

    assert len(result.population) == 6
    assert len(result.history) == 3
    assert isinstance(result.archive, dict)
    assert isinstance(result.best.proof, Proof)
    assert result.history[0].valid_fraction > 0.0
    assert result.history[0].best_conclusion


def test_evolve_is_deterministic_with_seed() -> None:
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=5,
            max_generations=2,
            elite_count=1,
            tournament_size=2,
            beam_enabled=False,
        )
    )
    target = SImp(SAtom("a"), SAtom("a"))

    first = evolve(target, config, seed=42)
    second = evolve(target, config, seed=42)

    assert first.population == second.population
    assert first.best == second.best
    assert first.history == second.history


def test_iterative_deepening_updates_active_depth() -> None:
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=4,
            max_generations=5,
            elite_count=1,
            tournament_size=2,
            initial_proof_depth=1,
            max_proof_depth=3,
            iterative_deepening_budget=2,
            iterative_deepening_scale=1.0,
            diagnostics_interval=2,
            beam_enabled=False,
        )
    )

    result = evolve(SImp(SAtom("a"), SAtom("a")), config, seed=3)

    assert tuple(item.active_proof_depth for item in result.history) == (1, 1, 2, 2, 3)


def test_iterative_deepening_budget_scales_with_depth() -> None:
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=4,
            max_generations=8,
            elite_count=1,
            tournament_size=2,
            initial_proof_depth=1,
            max_proof_depth=4,
            iterative_deepening_budget=2,
            iterative_deepening_scale=2.0,
            beam_enabled=False,
        )
    )

    result = evolve(SImp(SAtom("a"), SAtom("a")), config, seed=3)

    assert tuple(item.active_proof_depth for item in result.history) == (1, 1, 2, 2, 2, 2, 3, 3)


def test_evolve_handles_elite_count_larger_than_population() -> None:
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=3,
            max_generations=1,
            elite_count=10,
            beam_enabled=False,
        )
    )

    result = evolve(SImp(SAtom("a"), SAtom("a")), config, seed=4)

    assert len(result.population) == 3


def test_evolve_saves_archive_to_configured_path(tmp_path) -> None:
    path = tmp_path / "archive.json"
    config = ProplogicConfig(
        archive=ArchiveConfig(path=str(path), load_on_start=True, save_on_finish=True),
        evolution=EvolutionConfig(
            population_size=4,
            max_generations=1,
            elite_count=1,
            beam_enabled=False,
        ),
    )

    evolve(SImp(SAtom("a"), SAtom("a")), config, seed=4)

    assert path.exists()
