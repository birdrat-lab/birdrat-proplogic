from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

from birdrat_proplogic.config import DEFAULT_CONFIG, ProplogicConfig
from birdrat_proplogic.dproof import DProofParseError, fresh_axiom
from birdrat_proplogic.fitness import (
    best_consequent_similarity,
    best_directed_similarity,
    implication_spine,
    total_fitness,
    total_formula_size,
)
from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not, formula_size, is_closed_formula, pretty
from birdrat_proplogic.goals import Goal
from birdrat_proplogic.proof import (
    Ax1,
    Ax2,
    Ax3,
    Invalid,
    Proof,
    cd_depth,
    cd_steps,
    conclusion,
    is_vacuous_cd,
    proof_size,
)
from birdrat_proplogic.quality import behavior_descriptor, lemma_schema_score, novelty_score
from birdrat_proplogic.quality import uses_ax1, uses_ax2, uses_ax3
from birdrat_proplogic.seed import try_make_cd
from birdrat_proplogic.unify import UnifyFailure, Substitution, unify


@dataclass(frozen=True)
class BeamLayerStats:
    depth: int
    pair_pool_size: int
    major_candidates: int
    compatible_minor_candidates: int
    pair_attempts: int
    strict_pairs_attempted: int
    suffix_pairs_attempted: int
    exploratory_pairs_attempted: int
    duplicate_pairs_removed: int
    valid_products: int
    closed_products: int
    schematic_products: int
    closed_survivors: int
    schematic_survivors: int
    suffix_survivors_by_suffix: tuple[tuple[str, int], ...]
    exact_target_generated_in_beam: bool
    exact_target_survived_to_population: bool
    generated_ax1_fraction: float
    generated_ax2_fraction: float
    generated_ax3_fraction: float
    kept_ax1_fraction: float
    kept_ax2_fraction: float
    kept_ax3_fraction: float


@dataclass(frozen=True)
class BeamDiagnostics:
    width: int
    max_depth: int
    pair_budget: int
    major_budget: int
    pair_attempts: int = 0
    valid_products: int = 0
    layer_counts: tuple[BeamLayerStats, ...] = ()


@dataclass(frozen=True)
class BeamSearchResult:
    proofs: tuple[Proof, ...]
    diagnostics: BeamDiagnostics


@dataclass(frozen=True)
class PairChannelResult:
    pairs: tuple[tuple[float, Proof, Proof], ...]
    compatible_minor_candidates: int


@dataclass(frozen=True)
class PairSelection:
    pairs: tuple[tuple[float, Proof, Proof], ...]
    compatible_minor_candidates: int
    strict_pairs_attempted: int
    suffix_pairs_attempted: int
    exploratory_pairs_attempted: int
    duplicate_pairs_removed: int


def cd_beam_search(
    target: Formula,
    regions: tuple[Goal, ...],
    formula_pool: tuple[Formula, ...],
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> tuple[Proof, ...]:
    return cd_beam_search_result(target, regions, formula_pool, config).proofs


def cd_beam_search_result(
    target: Formula,
    regions: tuple[Goal, ...],
    formula_pool: tuple[Formula, ...],
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> BeamSearchResult:
    evolution_config = config.evolution
    width = max(1, evolution_config.beam_width)
    max_depth = max(0, evolution_config.beam_max_depth)
    pair_budget = max(0, evolution_config.beam_pair_budget)
    major_budget = max(1, evolution_config.beam_major_budget)
    if not evolution_config.beam_enabled:
        return BeamSearchResult((), BeamDiagnostics(width, max_depth, pair_budget, major_budget))

    seeds = tuple(seeded_axiom_instances(formula_pool, width))
    known: list[Proof] = list(seeds)
    frontier: tuple[Proof, ...] = tuple(known)
    behavior_archive = tuple(behavior_descriptor(proof) for proof in known)
    layers: list[BeamLayerStats] = []

    for depth in range(max_depth):
        pair_pool = tuple(_dedupe(list(seeds) + list(known[-width:]) + list(frontier)))
        new: list[Proof] = []
        pair_selection = candidate_pairs(
            pair_pool,
            target,
            regions,
            config,
            major_budget=major_budget,
            pair_budget=pair_budget,
        )
        pairs = pair_selection.pairs

        for _, major, minor in pairs:
            candidate = try_make_cd(major, minor)
            if candidate is None or candidate in known or candidate in new:
                continue
            new.append(candidate)

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
        layers.append(
            _beam_layer_stats(
                depth,
                pair_pool,
                pairs,
                new,
                closed,
                schematic,
                kept_closed,
                kept_schematic,
                major_budget,
                target,
                pair_selection,
            )
        )
        if not new:
            break

        frontier = kept_closed + kept_schematic
        known.extend(frontier)
        behavior_archive = tuple(
            list(behavior_archive)
            + [behavior_descriptor(proof) for proof in frontier]
        )[-config.evolution.behavior_archive_size :]

    diagnostics = BeamDiagnostics(
        width=width,
        max_depth=max_depth,
        pair_budget=pair_budget,
        major_budget=major_budget,
        pair_attempts=sum(layer.pair_attempts for layer in layers),
        valid_products=sum(layer.valid_products for layer in layers),
        layer_counts=tuple(layers),
    )
    return BeamSearchResult(tuple(_dedupe(known)), diagnostics)


def _beam_layer_stats(
    depth: int,
    pair_pool: tuple[Proof, ...],
    pairs: tuple[tuple[float, Proof, Proof], ...],
    new: list[Proof],
    closed: tuple[Proof, ...],
    schematic: tuple[Proof, ...],
    kept_closed: tuple[Proof, ...],
    kept_schematic: tuple[Proof, ...],
    major_budget: int,
    target: Formula,
    pair_selection: PairSelection,
) -> BeamLayerStats:
    kept = kept_closed + kept_schematic
    generated_fractions = axiom_family_fractions(tuple(new))
    kept_fractions = axiom_family_fractions(kept)
    return BeamLayerStats(
        depth=depth,
        pair_pool_size=len(pair_pool),
        major_candidates=min(major_budget, len([proof for proof in pair_pool if implication_major_parts(proof) is not None])),
        compatible_minor_candidates=pair_selection.compatible_minor_candidates,
        pair_attempts=len(pairs),
        strict_pairs_attempted=pair_selection.strict_pairs_attempted,
        suffix_pairs_attempted=pair_selection.suffix_pairs_attempted,
        exploratory_pairs_attempted=pair_selection.exploratory_pairs_attempted,
        duplicate_pairs_removed=pair_selection.duplicate_pairs_removed,
        valid_products=len(new),
        closed_products=len(closed),
        schematic_products=len(schematic),
        closed_survivors=len(kept_closed),
        schematic_survivors=len(kept_schematic),
        suffix_survivors_by_suffix=_suffix_survivor_counts(kept_closed, target),
        exact_target_generated_in_beam=any(conclusion(proof) == target for proof in new),
        exact_target_survived_to_population=any(conclusion(proof) == target for proof in kept),
        generated_ax1_fraction=generated_fractions[0],
        generated_ax2_fraction=generated_fractions[1],
        generated_ax3_fraction=generated_fractions[2],
        kept_ax1_fraction=kept_fractions[0],
        kept_ax2_fraction=kept_fractions[1],
        kept_ax3_fraction=kept_fractions[2],
    )


def axiom_family_fractions(proofs: tuple[Proof, ...]) -> tuple[float, float, float]:
    if not proofs:
        return (0.0, 0.0, 0.0)
    total = len(proofs)
    return (
        sum(1 for proof in proofs if uses_ax1(proof)) / total,
        sum(1 for proof in proofs if uses_ax2(proof)) / total,
        sum(1 for proof in proofs if uses_ax3(proof)) / total,
    )


def implication_major_parts(proof: Proof) -> tuple[Formula, Formula] | None:
    proof_conclusion = conclusion(proof)
    if not isinstance(proof_conclusion, Imp):
        return None
    return (proof_conclusion.left, proof_conclusion.right)


def major_priority(major: Proof, target: Formula, regions: tuple[Goal, ...]) -> float:
    return major_priority_with_config(major, target, regions, DEFAULT_CONFIG)


def major_priority_with_config(
    major: Proof,
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
) -> float:
    parts = implication_major_parts(major)
    if parts is None:
        return float("-inf")
    antecedent, consequent = parts
    evolution_config = config.evolution
    targets = target_and_regions(target, regions)
    exact = 1.0 if consequent in targets else 0.0
    unifies = 1.0 if _unifies_with_any(consequent, targets) else 0.0
    head_match = 1.0 if _same_final_head_as_any(consequent, targets) else 0.0
    vacuous = 1.0 if is_vacuous_cd(major) else 0.0
    return (
        evolution_config.beam_suffix_match_weight * max(exact, 0.85 * unifies)
        + evolution_config.beam_consequent_similarity_weight * best_consequent_similarity(consequent, target, regions)
        + evolution_config.beam_unification_weight * unifies
        + evolution_config.beam_directed_similarity_weight * best_directed_similarity(consequent, target, regions)
        + evolution_config.beam_head_match_weight * head_match
        - evolution_config.beam_antecedent_size_penalty * formula_size(antecedent)
        - evolution_config.beam_major_proof_size_penalty * proof_size(major)
        - evolution_config.beam_major_cd_step_penalty * cd_steps(major)
        - evolution_config.beam_major_formula_size_penalty * total_formula_size(major)
        - evolution_config.beam_vacuous_penalty * vacuous
    )


def pair_priority(major: Proof, minor: Proof, target: Formula, regions: tuple[Goal, ...]) -> float:
    return pair_priority_with_config(major, minor, target, regions, DEFAULT_CONFIG)


def pair_priority_with_config(
    major: Proof,
    minor: Proof,
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
) -> float:
    parts = implication_major_parts(major)
    if parts is None:
        return float("-inf")
    antecedent, _ = parts
    minor_conclusion = conclusion(minor)
    if isinstance(minor_conclusion, Invalid):
        return float("-inf")
    subst = unify(antecedent, minor_conclusion)
    if isinstance(subst, UnifyFailure):
        return float("-inf")
    evolution_config = config.evolution
    closed_minor_bonus = evolution_config.beam_closed_minor_bonus if is_closed_formula(minor_conclusion) else 0.0
    return (
        major_priority_with_config(major, target, regions, config)
        - evolution_config.beam_minor_proof_size_penalty * proof_size(minor)
        - evolution_config.beam_substitution_size_penalty * substitution_size(subst)
        + closed_minor_bonus
    )


def candidate_pairs(
    proof_pool: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
    *,
    major_budget: int,
    pair_budget: int,
) -> PairSelection:
    budgets = _monotone_channel_budgets(
        pair_budget,
        config.evolution.beam_prioritized_fraction,
        config.evolution.beam_suffix_fraction,
        config.evolution.beam_exploratory_fraction,
    )
    strict_result = prioritized_pairs(
        proof_pool,
        target,
        regions,
        config,
        major_budget=major_budget,
        pair_budget=budgets[0],
    )
    strict_keys = _pair_keys(strict_result.pairs)
    suffix_result = suffix_pairs(
        proof_pool,
        target,
        regions,
        config,
        major_budget=major_budget,
        pair_budget=budgets[1],
        excluded_pairs=strict_keys,
    )
    strict_suffix_keys = strict_keys | _pair_keys(suffix_result.pairs)
    exploratory_result = exploratory_pairs(
        proof_pool,
        target,
        regions,
        config,
        major_budget=major_budget,
        pair_budget=budgets[2],
        excluded_pairs=strict_suffix_keys,
    )
    selected, duplicates = _dedupe_channel_pairs(
        (
            ("strict", strict_result.pairs),
            ("suffix", suffix_result.pairs),
            ("exploratory", exploratory_result.pairs),
        ),
        {"strict": budgets[0], "suffix": budgets[1], "exploratory": budgets[2]},
    )
    return PairSelection(
        pairs=tuple((priority, major, minor) for _channel, priority, major, minor in selected),
        compatible_minor_candidates=(
            strict_result.compatible_minor_candidates
            + suffix_result.compatible_minor_candidates
            + exploratory_result.compatible_minor_candidates
        ),
        strict_pairs_attempted=sum(1 for channel, _priority, _major, _minor in selected if channel == "strict"),
        suffix_pairs_attempted=sum(1 for channel, _priority, _major, _minor in selected if channel == "suffix"),
        exploratory_pairs_attempted=sum(1 for channel, _priority, _major, _minor in selected if channel == "exploratory"),
        duplicate_pairs_removed=duplicates,
    )


def prioritized_candidate_pairs(
    proof_pool: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
    *,
    major_budget: int,
    pair_budget: int,
) -> tuple[tuple[tuple[float, Proof, Proof], ...], int]:
    result = prioritized_pairs(
        proof_pool,
        target,
        regions,
        config,
        major_budget=major_budget,
        pair_budget=pair_budget,
    )
    return (result.pairs, result.compatible_minor_candidates)


def prioritized_pairs(
    proof_pool: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
    *,
    major_budget: int,
    pair_budget: int,
) -> PairChannelResult:
    index = build_minor_shape_index(proof_pool)
    majors = sorted(
        (proof for proof in proof_pool if implication_major_parts(proof) is not None),
        key=lambda proof: major_priority_with_config(proof, target, regions, config),
        reverse=True,
    )[:major_budget]

    pairs: list[tuple[float, Proof, Proof]] = []
    compatible_count = 0
    for major in majors:
        parts = implication_major_parts(major)
        if parts is None:
            continue
        antecedent, _ = parts
        minors = tuple(compatible_minor_candidates(antecedent, proof_pool, index))
        compatible_count += len(minors)
        for minor in minors:
            priority = pair_priority_with_config(major, minor, target, regions, config)
            if isfinite(priority):
                pairs.append((priority, major, minor))

    ranked = sorted(pairs, key=lambda item: item[0], reverse=True)
    if pair_budget <= 0:
        return PairChannelResult((), compatible_count)
    return PairChannelResult(tuple(ranked[:pair_budget]), compatible_count)


def suffix_pairs(
    proof_pool: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
    *,
    major_budget: int,
    pair_budget: int,
    excluded_pairs: set[tuple[Proof, Proof]] | None = None,
) -> PairChannelResult:
    if pair_budget <= 0:
        return PairChannelResult((), 0)
    suffixes = implication_spine_suffixes(target)
    if not suffixes:
        return PairChannelResult((), 0)
    per_suffix = max(1, pair_budget // len(suffixes))
    output: list[tuple[float, Proof, Proof]] = []
    compatible_total = 0
    index = build_minor_shape_index(proof_pool)
    excluded = excluded_pairs or set()
    for suffix in suffixes:
        majors = sorted(
            (proof for proof in proof_pool if implication_major_parts(proof) is not None),
            key=lambda proof: suffix_major_priority(proof, suffix, config),
            reverse=True,
        )[:major_budget]
        suffix_output: list[tuple[float, Proof, Proof]] = []
        for major in majors:
            parts = implication_major_parts(major)
            if parts is None:
                continue
            antecedent, _ = parts
            minors = tuple(compatible_minor_candidates(antecedent, proof_pool, index))
            compatible_total += len(minors)
            for minor in minors:
                if (major, minor) in excluded:
                    continue
                priority = suffix_pair_priority(major, minor, suffix, config)
                if isfinite(priority):
                    suffix_output.append((priority, major, minor))
        output.extend(
            sorted(suffix_output, key=lambda item: item[0], reverse=True)[:per_suffix]
        )
    return PairChannelResult(_dedupe_ranked_pairs(tuple(output), pair_budget), compatible_total)


def exploratory_pairs(
    proof_pool: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
    *,
    major_budget: int,
    pair_budget: int,
    excluded_pairs: set[tuple[Proof, Proof]] | None = None,
) -> PairChannelResult:
    if pair_budget <= 0:
        return PairChannelResult((), 0)
    index = build_minor_shape_index(proof_pool)
    majors = sorted(
        (proof for proof in proof_pool if implication_major_parts(proof) is not None),
        key=lambda proof: (cd_steps(proof), proof_size(proof), total_formula_size(proof)),
    )[:major_budget]
    pairs: list[tuple[float, Proof, Proof]] = []
    compatible_count = 0
    excluded = excluded_pairs or set()
    for major in majors:
        parts = implication_major_parts(major)
        if parts is None:
            continue
        antecedent, _ = parts
        minors = tuple(compatible_minor_candidates(antecedent, proof_pool, index))
        compatible_count += len(minors)
        for minor in minors:
            if (major, minor) in excluded:
                continue
            priority = exploratory_pair_priority(major, minor, config)
            if not isfinite(priority):
                continue
            pairs.append((priority, major, minor))
    return PairChannelResult(_dedupe_ranked_pairs(tuple(pairs), pair_budget), compatible_count)


def suffix_major_priority(major: Proof, suffix: Formula, config: ProplogicConfig) -> float:
    parts = implication_major_parts(major)
    if parts is None:
        return float("-inf")
    antecedent, consequent = parts
    evolution_config = config.evolution
    exact = 1.0 if consequent == suffix else 0.0
    unifies = 1.0 if not isinstance(unify(consequent, suffix), UnifyFailure) else 0.0
    head_match = 1.0 if _same_final_head_as_any(consequent, (suffix,)) else 0.0
    vacuous = 1.0 if is_vacuous_cd(major) else 0.0
    return (
        evolution_config.beam_suffix_match_weight * max(exact, 0.85 * unifies)
        + evolution_config.beam_consequent_similarity_weight * best_directed_similarity(consequent, suffix, ())
        + evolution_config.beam_head_match_weight * head_match
        - evolution_config.beam_antecedent_size_penalty * formula_size(antecedent)
        - evolution_config.beam_major_proof_size_penalty * proof_size(major)
        - evolution_config.beam_major_cd_step_penalty * cd_steps(major)
        - evolution_config.beam_major_formula_size_penalty * total_formula_size(major)
        - evolution_config.beam_vacuous_penalty * vacuous
    )


def suffix_pair_priority(
    major: Proof,
    minor: Proof,
    suffix: Formula,
    config: ProplogicConfig,
) -> float:
    parts = implication_major_parts(major)
    if parts is None:
        return float("-inf")
    antecedent, _ = parts
    minor_conclusion = conclusion(minor)
    if isinstance(minor_conclusion, Invalid):
        return float("-inf")
    subst = unify(antecedent, minor_conclusion)
    if isinstance(subst, UnifyFailure):
        return float("-inf")
    evolution_config = config.evolution
    closed_minor_bonus = evolution_config.beam_closed_minor_bonus if is_closed_formula(minor_conclusion) else 0.0
    return (
        suffix_major_priority(major, suffix, config)
        - evolution_config.beam_minor_proof_size_penalty * proof_size(minor)
        - evolution_config.beam_substitution_size_penalty * substitution_size(subst)
        + closed_minor_bonus
    )


def exploratory_pair_priority(major: Proof, minor: Proof, config: ProplogicConfig) -> float:
    parts = implication_major_parts(major)
    if parts is None:
        return float("-inf")
    antecedent, _ = parts
    minor_conclusion = conclusion(minor)
    if isinstance(minor_conclusion, Invalid):
        return float("-inf")
    subst = unify(antecedent, minor_conclusion)
    if isinstance(subst, UnifyFailure):
        return float("-inf")
    evolution_config = config.evolution
    return -(
        evolution_config.beam_major_proof_size_penalty * proof_size(major)
        + evolution_config.beam_major_cd_step_penalty * cd_steps(major)
        + evolution_config.beam_major_formula_size_penalty * total_formula_size(major)
        + evolution_config.beam_minor_proof_size_penalty * proof_size(minor)
        + evolution_config.beam_substitution_size_penalty * substitution_size(subst)
    )


def _monotone_channel_budgets(
    total: int,
    prioritized_fraction: float,
    suffix_fraction: float,
    exploratory_fraction: float,
) -> tuple[int, int, int]:
    if total <= 0:
        return (0, 0, 0)
    prioritized = int(total * max(0.0, prioritized_fraction))
    suffix = int(total * max(0.0, suffix_fraction))
    exploratory = int(total * max(0.0, exploratory_fraction))
    if prioritized <= 0 and suffix <= 0 and exploratory <= 0:
        prioritized = total
    return (prioritized, suffix, exploratory)


def _dedupe_channel_pairs(
    channel_pairs: tuple[tuple[str, tuple[tuple[float, Proof, Proof], ...]], ...],
    channel_limits: dict[str, int],
) -> tuple[tuple[tuple[str, float, Proof, Proof], ...], int]:
    selected: list[tuple[str, float, Proof, Proof]] = []
    seen: set[tuple[Proof, Proof]] = set()
    duplicate_count = 0
    channel_counts = {channel: 0 for channel in channel_limits}
    for channel, pairs in channel_pairs:
        for priority, major, minor in pairs:
            if channel_counts.get(channel, 0) >= channel_limits.get(channel, 0):
                break
            key = (major, minor)
            if key in seen:
                duplicate_count += 1
                continue
            selected.append((channel, priority, major, minor))
            seen.add(key)
            channel_counts[channel] = channel_counts.get(channel, 0) + 1
    return (tuple(selected), duplicate_count)


def _pair_keys(pairs: tuple[tuple[float, Proof, Proof], ...]) -> set[tuple[Proof, Proof]]:
    return {(major, minor) for _priority, major, minor in pairs}


def _dedupe_ranked_pairs(
    pairs: tuple[tuple[float, Proof, Proof], ...],
    limit: int,
) -> tuple[tuple[float, Proof, Proof], ...]:
    if limit <= 0:
        return ()
    selected: list[tuple[float, Proof, Proof]] = []
    seen: set[tuple[Proof, Proof]] = set()
    for priority, major, minor in sorted(pairs, key=lambda item: item[0], reverse=True):
        key = (major, minor)
        if key in seen:
            continue
        selected.append((priority, major, minor))
        seen.add(key)
        if len(selected) >= limit:
            break
    return tuple(selected)


def build_minor_shape_index(proof_pool: tuple[Proof, ...]) -> dict[str, tuple[Proof, ...]]:
    buckets: dict[str, list[Proof]] = {}
    for proof in proof_pool:
        proof_conclusion = conclusion(proof)
        key = _shape_key(proof_conclusion)
        buckets.setdefault(key, []).append(proof)
        if _is_schematic_or_meta_compatible(proof_conclusion):
            buckets.setdefault("schematic", []).append(proof)
    return {key: tuple(value) for key, value in buckets.items()}


def compatible_minor_candidates(
    antecedent: Formula,
    proof_pool: tuple[Proof, ...],
    index: dict[str, tuple[Proof, ...]],
) -> Iterable[Proof]:
    keys = {_shape_key(antecedent), "schematic"}
    if isinstance(antecedent, Meta):
        keys.update(index)
    selected: list[Proof] = []
    seen: set[Proof] = set()
    for key in keys:
        for proof in index.get(key, ()):
            if proof in seen:
                continue
            selected.append(proof)
            seen.add(proof)
    if not selected and isinstance(antecedent, Meta):
        return proof_pool
    return tuple(selected)


def substitution_size(subst: Substitution) -> int:
    return sum(formula_size(formula) for formula in subst.values())


def implication_spine_suffixes(formula: Formula) -> tuple[Formula, ...]:
    antecedents, head = implication_spine(formula)
    suffixes: list[Formula] = [head]
    current = head
    for antecedent in reversed(antecedents):
        current = Imp(antecedent, current)
        suffixes.append(current)
    return tuple(suffixes)


def target_and_region_suffixes(target: Formula, regions: tuple[Goal, ...]) -> tuple[Formula, ...]:
    suffixes: list[Formula] = []
    seen: set[Formula] = set()
    for formula in (target,) + tuple(region.core_theorem() for region in regions):
        for suffix in implication_spine_suffixes(formula):
            if suffix in seen:
                continue
            seen.add(suffix)
            suffixes.append(suffix)
    return tuple(suffixes)


def target_and_regions(target: Formula, regions: tuple[Goal, ...]) -> tuple[Formula, ...]:
    targets: list[Formula] = [target]
    seen: set[Formula] = {target}
    for region in regions:
        formula = region.core_theorem()
        if formula in seen:
            continue
        seen.add(formula)
        targets.append(formula)
    return tuple(targets)


def suffix_priority(candidate: Formula, target: Formula, regions: tuple[Goal, ...]) -> float:
    suffixes = target_and_region_suffixes(target, regions)
    if candidate in suffixes:
        return 1.0
    if _unifies_with_any(candidate, suffixes):
        return 0.85
    return max(best_directed_similarity(candidate, suffix, ()) for suffix in suffixes)


def seeded_axiom_instances(formula_pool: tuple[Formula, ...], width: int) -> tuple[Proof, ...]:
    proofs: list[Proof] = []
    leaf_index = 0
    fresh_limit = max(3, width // 2)
    for _ in range(max(1, fresh_limit // 3 + 1)):
        for axiom_number in ("1", "2", "3"):
            if len(proofs) >= fresh_limit:
                break
            leaf_index += 1
            proof = fresh_axiom(axiom_number, leaf_index)
            if not isinstance(proof, DProofParseError):
                proofs.append(proof)
        if len(proofs) >= fresh_limit:
            break

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
    ranked = sorted(
        proofs,
        key=lambda proof: (
            total_fitness(proof, target, regions, config).score,
            -cd_depth(proof),
        ),
        reverse=True,
    )
    selected: list[Proof] = []
    for suffix in implication_spine_suffixes(target):
        suffix_candidates = [
            proof
            for proof in ranked
            if proof not in selected and _matches_or_unifies(conclusion(proof), suffix)
        ]
        if suffix_candidates:
            selected.append(suffix_candidates[0])
        if len(selected) >= width:
            return tuple(selected)
    for proof in ranked:
        if proof in selected:
            continue
        selected.append(proof)
        if len(selected) >= width:
            break
    return tuple(selected)


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
        proof_conclusion = conclusion(proof)
        if isinstance(proof_conclusion, Invalid):
            continue
        if not _unifies_with_any(proof_conclusion, target_and_region_suffixes(target, regions)):
            continue
        selected.append(proof)
        seen_skeletons.add(behavior_descriptor(proof).normalized_skeleton)
        if len(selected) >= max(1, width // 4):
            break
    for proof in ranked:
        if proof in selected:
            continue
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


def _shape_key(formula: Formula | Invalid) -> str:
    match formula:
        case Meta():
            return "meta"
        case Atom(name):
            return f"atom:{name}"
        case Not():
            return "not"
        case Imp():
            return "imp"
        case Invalid():
            return "invalid"


def _is_schematic_or_meta_compatible(formula: Formula | Invalid) -> bool:
    match formula:
        case Meta():
            return True
        case Not(body):
            return _is_schematic_or_meta_compatible(body)
        case Imp(left, right):
            return _is_schematic_or_meta_compatible(left) or _is_schematic_or_meta_compatible(right)
        case Atom() | Invalid():
            return False


def _unifies_with_any(formula: Formula, targets: tuple[Formula, ...]) -> bool:
    return any(not isinstance(unify(formula, target), UnifyFailure) for target in targets)


def _matches_or_unifies(formula: Formula | Invalid, target: Formula) -> bool:
    if isinstance(formula, Invalid):
        return False
    return formula == target or not isinstance(unify(formula, target), UnifyFailure)


def _suffix_survivor_counts(proofs: tuple[Proof, ...], target: Formula) -> tuple[tuple[str, int], ...]:
    return tuple(
        (
            pretty(suffix),
            sum(1 for proof in proofs if _matches_or_unifies(conclusion(proof), suffix)),
        )
        for suffix in implication_spine_suffixes(target)
    )


def _same_final_head_as_any(formula: Formula, targets: tuple[Formula, ...]) -> bool:
    _, head = implication_spine(formula)
    return any(head == implication_spine(target)[1] for target in targets)


def _dedupe(proofs: list[Proof]) -> list[Proof]:
    output = []
    seen = set()
    for proof in proofs:
        if proof in seen:
            continue
        output.append(proof)
        seen.add(proof)
    return output
