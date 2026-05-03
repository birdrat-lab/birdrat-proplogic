from birdrat_proplogic.config import ArchiveConfig, EvolutionConfig, ProplogicConfig
from birdrat_proplogic.evolution import ScoredProof, evolve
from birdrat_proplogic.fitness import total_fitness
from birdrat_proplogic.formula import Atom, Imp, Meta, is_closed_formula
from birdrat_proplogic.proof import Ax1, conclusion
from birdrat_proplogic.quality import (
    behavior_descriptor,
    behavior_distance,
    promote_schematic_candidates,
)
from birdrat_proplogic.surface import SAtom, SImp


def test_behavior_descriptor_distinguishes_closed_and_schematic_candidates() -> None:
    closed = Ax1(Atom("a"), Atom("b"))
    schematic = Ax1(Meta("?p"), Atom("b"))

    closed_descriptor = behavior_descriptor(closed)
    schematic_descriptor = behavior_descriptor(schematic)

    assert closed_descriptor.closed
    assert not schematic_descriptor.closed
    assert schematic_descriptor.meta_count == 1
    assert behavior_distance(closed_descriptor, schematic_descriptor) > 0.0


def test_promote_schematic_candidate_instantiates_to_closed_target() -> None:
    target = Imp(Atom("a"), Imp(Atom("b"), Atom("a")))
    proof = Ax1(Meta("?p"), Meta("?q"))
    fitness = total_fitness(proof, target)

    promoted = promote_schematic_candidates(
        (ScoredProof(proof, fitness),),
        target,
        (),
        ProplogicConfig(archive=ArchiveConfig(path=None)),
    )

    assert len(promoted) == 1
    assert promoted[0].fitness.exact_target
    assert is_closed_formula(promoted[0].fitness.conclusion)
    assert conclusion(promoted[0].proof) == target


def test_evolution_reports_quality_diversity_diagnostics() -> None:
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=6,
            max_generations=2,
            elite_count=2,
            tournament_size=2,
        ),
    )

    result = evolve(SImp(SAtom("a"), SAtom("a")), config, seed=7)

    assert len(result.population) == 6
    assert result.behavior_archive_size > 0
    assert result.history[-1].unique_behavior_count > 0
    assert result.history[-1].random_immigrant_count > 0
