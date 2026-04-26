from birdrat_proplogic.archive import archive_size, empty_archive, record_proof, update_archive
from birdrat_proplogic.config import ArchiveConfig, ProplogicConfig
from birdrat_proplogic.fitness import total_fitness
from birdrat_proplogic.formula import Atom, Imp
from birdrat_proplogic.goals import extract_goals
from birdrat_proplogic.proof import Ax1, CD
from birdrat_proplogic.surface import SAtom, SImp


def test_record_proof_stores_proof_under_formula() -> None:
    formula = Imp(Atom("a"), Atom("a"))
    proof = Ax1(Atom("a"), Atom("a"))

    archive = record_proof(empty_archive(), formula, proof)

    assert archive[formula] == (proof,)


def test_record_proof_deduplicates_same_proof() -> None:
    formula = Imp(Atom("a"), Atom("a"))
    proof = Ax1(Atom("a"), Atom("a"))

    archive = record_proof(empty_archive(), formula, proof)
    archive = record_proof(archive, formula, proof)

    assert archive[formula] == (proof,)
    assert archive_size(archive) == 1


def test_record_proof_keeps_shorter_proofs_first_and_respects_limit() -> None:
    formula = Imp(Atom("a"), Imp(Atom("a"), Atom("a")))
    short = Ax1(Atom("a"), Atom("a"))
    long = CD(Ax1(Atom("a"), Atom("a")), Ax1(Atom("a"), Atom("a")))
    config = ProplogicConfig(archive=ArchiveConfig(max_proofs_per_formula=1))

    archive = record_proof(empty_archive(), formula, long, config)
    archive = record_proof(archive, formula, short, config)

    assert archive[formula] == (short,)


def test_update_archive_records_exact_region_proofs() -> None:
    proof = Ax1(Atom("a"), Atom("a"))
    target = Imp(Atom("b"), Atom("b"))
    regions = extract_goals(SImp(SAtom("a"), SImp(SAtom("a"), SAtom("a"))))
    fitness = total_fitness(proof, target, regions)

    archive = update_archive(empty_archive(), ((proof, fitness),))

    assert fitness.exact_region is not None
    assert archive[fitness.exact_region.core_theorem()] == (proof,)


def test_update_archive_ignores_non_region_proofs() -> None:
    proof = Ax1(Atom("a"), Atom("a"))
    fitness = total_fitness(proof, Imp(Atom("b"), Atom("b")), ())

    archive = update_archive(empty_archive(), ((proof, fitness),))

    assert archive == {}
