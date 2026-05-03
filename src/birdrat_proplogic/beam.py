from __future__ import annotations

from birdrat_proplogic.config import DEFAULT_CONFIG, ProplogicConfig
from birdrat_proplogic.dproof import DProofParseError, fresh_axiom
from birdrat_proplogic.fitness import total_fitness
from birdrat_proplogic.formula import Formula, is_closed_formula
from birdrat_proplogic.goals import Goal
from birdrat_proplogic.proof import Ax1, Ax2, Ax3, Invalid, Proof, cd_depth, conclusion
from birdrat_proplogic.quality import behavior_descriptor, lemma_schema_score, novelty_score
from birdrat_proplogic.seed import try_make_cd


def cd_beam_search(
    target: Formula,
    regions: tuple[Goal, ...],
    formula_pool: tuple[Formula, ...],
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> tuple[Proof, ...]:
    evolution_config = config.evolution
    if not evolution_config.beam_enabled:
        return ()

    width = max(1, evolution_config.beam_width)
    max_depth = max(0, evolution_config.beam_max_depth)
    seeds = tuple(seeded_axiom_instances(formula_pool, width))
    known: list[Proof] = list(seeds)
    frontier: tuple[Proof, ...] = tuple(known)
    behavior_archive = tuple(behavior_descriptor(proof) for proof in known)

    for _ in range(max_depth):
        new = []
        pair_pool = tuple(_dedupe(list(seeds) + list(known[-width:]) + list(frontier)))
        for major in pair_pool:
            for minor in pair_pool:
                candidate = try_make_cd(major, minor)
                if candidate is None or candidate in known or candidate in new:
                    continue
                new.append(candidate)

        if not new:
            break

        closed, schematic = _partition_valid(new)
        kept_closed = _rank_closed(closed, target, regions, config, width)
        kept_schematic = _rank_schematic(
            schematic,
            target,
            regions,
            behavior_archive,
            config,
            width,
        )
        frontier = kept_closed + kept_schematic
        known.extend(frontier)
        behavior_archive = tuple(
            list(behavior_archive)
            + [behavior_descriptor(proof) for proof in frontier]
        )[-config.evolution.behavior_archive_size :]

    return tuple(_dedupe(known))


def seeded_axiom_instances(formula_pool: tuple[Formula, ...], width: int) -> tuple[Proof, ...]:
    proofs: list[Proof] = []
    leaf_index = 0
    for _ in range(max(3, width // 3)):
        for axiom_number in ("1", "2", "3"):
            leaf_index += 1
            proof = fresh_axiom(axiom_number, leaf_index)
            if not isinstance(proof, DProofParseError):
                proofs.append(proof)
            if len(proofs) >= width:
                return tuple(_dedupe(proofs))

    limited_pool = formula_pool[: max(1, min(len(formula_pool), width))]
    for left in limited_pool:
        for right in limited_pool:
            proofs.append(Ax1(left, right))
            proofs.append(Ax3(left, right))
            if len(proofs) >= width:
                return tuple(_dedupe(proofs))
            for middle in limited_pool[:3]:
                proofs.append(Ax2(left, right, middle))
                if len(proofs) >= width:
                    return tuple(_dedupe(proofs))
    return tuple(_dedupe(proofs))


def _partition_valid(proofs: list[Proof]) -> tuple[tuple[Proof, ...], tuple[Proof, ...]]:
    closed = []
    schematic = []
    for proof in proofs:
        proof_conclusion = conclusion(proof)
        if isinstance(proof_conclusion, Invalid):
            continue
        if is_closed_formula(proof_conclusion):
            closed.append(proof)
        else:
            schematic.append(proof)
    return (tuple(closed), tuple(schematic))


def _rank_closed(
    proofs: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
    width: int,
) -> tuple[Proof, ...]:
    return tuple(
        sorted(
            proofs,
            key=lambda proof: (
                total_fitness(proof, target, regions, config).score,
                -cd_depth(proof),
            ),
            reverse=True,
        )[:width]
    )


def _rank_schematic(
    proofs: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    behavior_archive: tuple,
    config: ProplogicConfig,
    width: int,
) -> tuple[Proof, ...]:
    def score(proof: Proof) -> float:
        fitness = total_fitness(proof, target, regions, config)
        descriptor = behavior_descriptor(proof, fitness.conclusion)
        return lemma_schema_score(fitness, target, regions, descriptor, config) + 50.0 * novelty_score(
            descriptor,
            behavior_archive,
            k=config.evolution.novelty_k,
        )

    ranked = sorted(proofs, key=score, reverse=True)
    selected: list[Proof] = []
    seen_skeletons: set[str] = set()
    for proof in ranked:
        descriptor = behavior_descriptor(proof)
        if descriptor.normalized_skeleton in seen_skeletons:
            continue
        selected.append(proof)
        seen_skeletons.add(descriptor.normalized_skeleton)
        if len(selected) >= width:
            return tuple(selected)
    for proof in ranked:
        if proof in selected:
            continue
        selected.append(proof)
        if len(selected) >= width:
            break
    return tuple(selected)


def _dedupe(proofs: list[Proof]) -> list[Proof]:
    output = []
    seen = set()
    for proof in proofs:
        if proof in seen:
            continue
        output.append(proof)
        seen.add(proof)
    return output
