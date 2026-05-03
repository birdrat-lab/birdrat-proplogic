from birdrat_proplogic.beam import cd_beam_search
from birdrat_proplogic.config import ArchiveConfig, EvolutionConfig, ProplogicConfig
from birdrat_proplogic.dproof import proves_identity_up_to_renaming
from birdrat_proplogic.evolution import evolve
from birdrat_proplogic.formula import Imp, Meta
from birdrat_proplogic.surface import SAtom, SImp


def test_cd_beam_rediscovers_identity_shape_without_hardcoded_proof() -> None:
    target = Imp(Meta("?x"), Meta("?x"))
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(beam_width=12, beam_max_depth=2),
    )

    proofs = cd_beam_search(target, (), (target,), config)

    assert any(proves_identity_up_to_renaming(proof) for proof in proofs)


def test_beam_mixed_evolution_finds_closed_identity_target() -> None:
    config = ProplogicConfig(
        archive=ArchiveConfig(path=None),
        evolution=EvolutionConfig(
            population_size=6,
            max_generations=3,
            beam_width=12,
            beam_max_depth=2,
        ),
    )

    result = evolve(SImp(SAtom("a"), SAtom("a")), config, seed=1)

    assert result.best.fitness.exact_target
    assert result.history[-1].beam_pool_size > 0
