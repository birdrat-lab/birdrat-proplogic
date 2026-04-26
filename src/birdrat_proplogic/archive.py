from __future__ import annotations

from typing import Iterable, TypeAlias

from birdrat_proplogic.config import DEFAULT_CONFIG, ProplogicConfig
from birdrat_proplogic.fitness import FitnessResult
from birdrat_proplogic.formula import Formula
from birdrat_proplogic.proof import Invalid, Proof, cd_depth, cd_steps, proof_size

ProofArchive: TypeAlias = dict[Formula, tuple[Proof, ...]]


def empty_archive() -> ProofArchive:
    return {}


def record_proof(
    archive: ProofArchive,
    formula: Formula,
    proof: Proof,
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> ProofArchive:
    updated = dict(archive)
    existing = updated.get(formula, ())
    if proof in existing:
        return updated

    proofs = tuple(sorted(existing + (proof,), key=_proof_rank))
    limit = max(1, config.archive.max_proofs_per_formula)
    updated[formula] = proofs[:limit]
    return updated


def update_archive(
    archive: ProofArchive,
    scored: Iterable[tuple[Proof, FitnessResult]],
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> ProofArchive:
    updated = dict(archive)
    for proof, fitness in scored:
        if fitness.exact_region is None:
            continue
        if isinstance(fitness.conclusion, Invalid):
            continue
        updated = record_proof(updated, fitness.exact_region.core_theorem(), proof, config)
    return updated


def archive_size(archive: ProofArchive) -> int:
    return sum(len(proofs) for proofs in archive.values())


def _proof_rank(proof: Proof) -> tuple[int, int, int]:
    return (proof_size(proof), cd_steps(proof), cd_depth(proof))
