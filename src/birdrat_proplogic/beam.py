from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import isfinite
from typing import Iterable

from birdrat_proplogic.config import DEFAULT_CONFIG, ProplogicConfig
from birdrat_proplogic.dproof import DProofParseError, fresh_axiom
from birdrat_proplogic.fitness import (
    antecedent_coverage_score,
    assumption_debt,
    best_antecedent_coverage,
    best_consequent_similarity,
    best_directed_similarity,
    implication_spine,
    total_fitness,
    total_formula_size,
)
from birdrat_proplogic.formula import Atom, Formula, Imp, Meta, Not, formula_size, is_closed_formula, metas, pretty, subformulas
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
from birdrat_proplogic.quality import apply_proof_subst, behavior_descriptor, lemma_schema_score, novelty_score
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
    suffix_candidates_seen_by_suffix: tuple[tuple[str, int], ...]
    suffix_closed_candidates_seen_by_suffix: tuple[tuple[str, int], ...]
    suffix_schematic_candidates_seen_by_suffix: tuple[tuple[str, int], ...]
    suffix_survivors_by_suffix: tuple[tuple[str, int], ...]
    best_candidate_by_suffix: tuple[tuple[str, str], ...]
    schema_instantiation_attempts: int
    schema_instantiation_valid: int
    schema_instantiation_closed: int
    schema_instantiation_schematic: int
    schema_instantiation_exact_target: int
    schema_instantiation_exact_region: int
    schema_instantiation_exact_suffix: int
    best_instantiated_candidate: str | None
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


@dataclass(frozen=True)
class SuffixRetentionDiagnostics:
    candidates_seen_by_suffix: tuple[tuple[str, int], ...]
    closed_candidates_seen_by_suffix: tuple[tuple[str, int], ...]
    schematic_candidates_seen_by_suffix: tuple[tuple[str, int], ...]
    survivors_by_suffix: tuple[tuple[str, int], ...]
    best_candidate_by_suffix: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SchemaInstantiationDiagnostics:
    attempts: int = 0
    valid: int = 0
    closed: int = 0
    schematic: int = 0
    exact_target: int = 0
    exact_region: int = 0
    exact_suffix: int = 0
    best_candidate: str | None = None


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
        instantiated, schema_diagnostics = _instantiate_schematic_candidates(
            schematic,
            target,
            regions,
            formula_pool,
            config,
            width,
        )
        for proof in instantiated:
            if proof not in known and proof not in new:
                new.append(proof)
        closed, schematic = _partition_valid(new)
        global_closed = _rank_closed(closed, target, regions, config, width)
        global_schematic = _rank_schematic(
            schematic,
            target,
            regions,
            behavior_archive,
            config,
            width,
        )
        kept_closed, kept_schematic, suffix_diagnostics = _retain_with_suffix_buckets(
            closed,
            schematic,
            global_closed,
            global_schematic,
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
                suffix_diagnostics,
                schema_diagnostics,
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
    suffix_diagnostics: SuffixRetentionDiagnostics,
    schema_diagnostics: SchemaInstantiationDiagnostics,
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
        suffix_candidates_seen_by_suffix=suffix_diagnostics.candidates_seen_by_suffix,
        suffix_closed_candidates_seen_by_suffix=suffix_diagnostics.closed_candidates_seen_by_suffix,
        suffix_schematic_candidates_seen_by_suffix=suffix_diagnostics.schematic_candidates_seen_by_suffix,
        suffix_survivors_by_suffix=suffix_diagnostics.survivors_by_suffix,
        best_candidate_by_suffix=suffix_diagnostics.best_candidate_by_suffix,
        schema_instantiation_attempts=schema_diagnostics.attempts,
        schema_instantiation_valid=schema_diagnostics.valid,
        schema_instantiation_closed=schema_diagnostics.closed,
        schema_instantiation_schematic=schema_diagnostics.schematic,
        schema_instantiation_exact_target=schema_diagnostics.exact_target,
        schema_instantiation_exact_region=schema_diagnostics.exact_region,
        schema_instantiation_exact_suffix=schema_diagnostics.exact_suffix,
        best_instantiated_candidate=schema_diagnostics.best_candidate,
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
        + 250.0 * best_antecedent_coverage(consequent, target, regions)
        + evolution_config.beam_head_match_weight * head_match
        - 50.0 * min(10.0, assumption_debt(consequent, target, config.fitness))
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
        + 250.0 * antecedent_coverage_score(consequent, suffix)
        - 50.0 * min(10.0, assumption_debt(consequent, suffix, config.fitness))
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


def _instantiate_schematic_candidates(
    schematic: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    formula_pool: tuple[Formula, ...],
    config: ProplogicConfig,
    width: int,
) -> tuple[tuple[Proof, ...], SchemaInstantiationDiagnostics]:
    evolution_config = config.evolution
    if not schematic:
        return ((), SchemaInstantiationDiagnostics())
    instantiation_pool = _schema_instantiation_formula_pool(target, regions, formula_pool, evolution_config.schema_instantiation_pool_size)
    schema_candidates = sorted(
        schematic,
        key=lambda proof: _schema_instantiation_candidate_score(proof, target, regions, config),
        reverse=True,
    )[: max(1, width)]
    products: list[Proof] = []
    attempts = valid = closed_count = schematic_count = exact_target = exact_region = exact_suffix = 0
    suffixes = target_and_region_suffixes(target, regions)
    seen: set[Proof] = set()
    for proof in schema_candidates:
        proof_conclusion = conclusion(proof)
        if isinstance(proof_conclusion, Invalid):
            continue
        proof_metas = tuple(sorted(metas(proof_conclusion), key=lambda item: item.name))
        if not proof_metas or len(proof_metas) > evolution_config.schema_instantiation_max_metas:
            continue
        substitutions = _direct_schema_substitutions(proof_conclusion, suffixes)
        substitutions += _pool_schema_substitutions(
            proof_metas,
            instantiation_pool,
            max(0, evolution_config.schema_instantiation_max_attempts_per_proof - len(substitutions)),
        )
        for subst in substitutions[: evolution_config.schema_instantiation_max_attempts_per_proof]:
            attempts += 1
            instantiated = apply_proof_subst(proof, subst)
            instantiated_conclusion = conclusion(instantiated)
            if isinstance(instantiated_conclusion, Invalid):
                continue
            valid += 1
            if is_closed_formula(instantiated_conclusion):
                closed_count += 1
            else:
                schematic_count += 1
            if instantiated_conclusion == target:
                exact_target += 1
            if any(instantiated_conclusion == region.core_theorem() for region in regions):
                exact_region += 1
            if instantiated_conclusion in suffixes:
                exact_suffix += 1
            if instantiated not in seen:
                products.append(instantiated)
                seen.add(instantiated)
    ranked = tuple(
        sorted(
            products,
            key=lambda proof: total_fitness(proof, target, regions, config).score,
            reverse=True,
        )[:width]
    )
    best_candidate = None
    if ranked:
        best_conclusion = conclusion(ranked[0])
        best_candidate = "invalid" if isinstance(best_conclusion, Invalid) else pretty(best_conclusion)
    return (
        ranked,
        SchemaInstantiationDiagnostics(
            attempts=attempts,
            valid=valid,
            closed=closed_count,
            schematic=schematic_count,
            exact_target=exact_target,
            exact_region=exact_region,
            exact_suffix=exact_suffix,
            best_candidate=best_candidate,
        ),
    )


def _schema_instantiation_candidate_score(
    proof: Proof,
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
) -> float:
    proof_conclusion = conclusion(proof)
    if isinstance(proof_conclusion, Invalid):
        return float("-inf")
    return (
        best_directed_similarity(proof_conclusion, target, regions)
        + best_antecedent_coverage(proof_conclusion, target, regions)
        - 0.01 * proof_size(proof)
        - 0.001 * total_formula_size(proof)
    )


def _schema_instantiation_formula_pool(
    target: Formula,
    regions: tuple[Goal, ...],
    formula_pool: tuple[Formula, ...],
    limit: int,
) -> tuple[Formula, ...]:
    formulas: list[Formula] = []
    base = (target,) + tuple(region.core_theorem() for region in regions)
    for formula in base:
        formulas.extend(implication_spine_suffixes(formula))
        antecedents, head = implication_spine(formula)
        formulas.extend(antecedents)
        formulas.append(head)
        formulas.extend(subformulas(formula))
    formulas.extend(formula_pool)
    seed = tuple(_dedupe_formulas(formulas))
    expanded: list[Formula] = list(seed)
    for formula in seed[: max(1, min(10, len(seed)))]:
        expanded.append(Not(formula))
    for left in seed[:6]:
        for right in seed[:6]:
            expanded.append(Imp(left, right))
            if len(expanded) >= max(limit * 2, limit):
                break
        if len(expanded) >= max(limit * 2, limit):
            break
    return tuple(_dedupe_formulas(expanded)[: max(1, limit)])


def _direct_schema_substitutions(schema: Formula, targets: tuple[Formula, ...]) -> list[Substitution]:
    substitutions: list[Substitution] = []
    seen: set[tuple[tuple[str, Formula], ...]] = set()
    for target in targets:
        subst = unify(schema, target)
        if isinstance(subst, UnifyFailure):
            continue
        key = tuple(sorted(subst.items(), key=lambda item: item[0]))
        if key in seen:
            continue
        substitutions.append(subst)
        seen.add(key)
    return substitutions


def _pool_schema_substitutions(
    proof_metas: tuple[Meta, ...],
    formula_pool: tuple[Formula, ...],
    limit: int,
) -> list[Substitution]:
    if limit <= 0:
        return []
    substitutions: list[Substitution] = []
    for replacements in product(formula_pool, repeat=len(proof_metas)):
        substitutions.append({meta.name: replacement for meta, replacement in zip(proof_metas, replacements)})
        if len(substitutions) >= limit:
            break
    return substitutions


def _dedupe_formulas(formulas: list[Formula]) -> list[Formula]:
    output: list[Formula] = []
    seen: set[Formula] = set()
    for formula in formulas:
        if formula in seen:
            continue
        output.append(formula)
        seen.add(formula)
    return output


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


def _retain_with_suffix_buckets(
    closed: tuple[Proof, ...],
    schematic: tuple[Proof, ...],
    global_closed: tuple[Proof, ...],
    global_schematic: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    behavior_archive: tuple,
    config: ProplogicConfig,
    width: int,
) -> tuple[tuple[Proof, ...], tuple[Proof, ...], SuffixRetentionDiagnostics]:
    suffixes = implication_spine_suffixes(target)
    closed_suffix = _suffix_bucket_proofs(
        closed,
        suffixes,
        config.evolution.suffix_closed_keep_per_suffix,
        lambda proof, suffix: _suffix_closed_score(proof, suffix, config),
    )
    schematic_suffix = _suffix_bucket_proofs(
        schematic,
        suffixes,
        config.evolution.suffix_schematic_keep_per_suffix,
        lambda proof, suffix: _suffix_schematic_score(proof, suffix, target, regions, behavior_archive, config),
    )
    kept_closed = tuple(_dedupe_by_conclusion_best(
        list(global_closed) + list(closed_suffix),
        lambda proof: _closed_score(proof, target, regions, config),
    )[:width])
    kept_schematic = tuple(_dedupe_by_conclusion_best(
        list(global_schematic) + list(schematic_suffix),
        lambda proof: _schematic_score(proof, target, regions, behavior_archive, config),
    )[:width])
    kept = kept_closed + kept_schematic
    return (kept_closed, kept_schematic, _suffix_retention_diagnostics(closed, schematic, kept, target))


def _suffix_bucket_proofs(
    proofs: tuple[Proof, ...],
    suffixes: tuple[Formula, ...],
    keep_per_suffix: int,
    score,
) -> tuple[Proof, ...]:
    if keep_per_suffix <= 0:
        return ()
    selected: list[Proof] = []
    for suffix in suffixes:
        candidates = [
            proof
            for proof in proofs
            if _suffix_candidate_score(conclusion(proof), suffix) > 0.0
        ]
        selected.extend(
            sorted(candidates, key=lambda proof: score(proof, suffix), reverse=True)[:keep_per_suffix]
        )
    return tuple(_dedupe_by_conclusion_best(selected, lambda proof: max(score(proof, suffix) for suffix in suffixes)))


def _rank_closed(
    proofs: tuple[Proof, ...],
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
    width: int,
) -> tuple[Proof, ...]:
    ranked = sorted(
        proofs,
        key=lambda proof: _closed_score(proof, target, regions, config),
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
        return _schematic_score(proof, target, regions, behavior_archive, config)

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


def _closed_score(
    proof: Proof,
    target: Formula,
    regions: tuple[Goal, ...],
    config: ProplogicConfig,
) -> tuple[float, float, int, int, int]:
    proof_conclusion = conclusion(proof)
    if isinstance(proof_conclusion, Invalid):
        return (float("-inf"), 0.0, 0, 0, 0)
    return (
        total_fitness(proof, target, regions, config).score,
        best_antecedent_coverage(proof_conclusion, target, regions),
        -cd_depth(proof),
        -proof_size(proof),
        -total_formula_size(proof),
    )


def _schematic_score(
    proof: Proof,
    target: Formula,
    regions: tuple[Goal, ...],
    behavior_archive: tuple,
    config: ProplogicConfig,
) -> float:
    fitness = total_fitness(proof, target, regions, config)
    descriptor = behavior_descriptor(proof, fitness.conclusion)
    coverage = 0.0 if isinstance(fitness.conclusion, Invalid) else best_antecedent_coverage(fitness.conclusion, target, regions)
    return (
        lemma_schema_score(fitness, target, regions, descriptor, config)
        + 100.0 * coverage
        + 50.0 * novelty_score(descriptor, behavior_archive, k=config.evolution.novelty_k)
    )


def _suffix_closed_score(proof: Proof, suffix: Formula, config: ProplogicConfig) -> tuple[float, float, float, int, int, int]:
    proof_conclusion = conclusion(proof)
    if isinstance(proof_conclusion, Invalid):
        return (float("-inf"), 0.0, 0.0, 0, 0, 0)
    return (
        _suffix_candidate_score(proof_conclusion, suffix),
        antecedent_coverage_score(proof_conclusion, suffix),
        -assumption_debt(proof_conclusion, suffix, config.fitness),
        -proof_size(proof),
        -total_formula_size(proof),
        -cd_steps(proof),
    )


def _suffix_schematic_score(
    proof: Proof,
    suffix: Formula,
    target: Formula,
    regions: tuple[Goal, ...],
    behavior_archive: tuple,
    config: ProplogicConfig,
) -> tuple[float, float, float, float, int, int]:
    proof_conclusion = conclusion(proof)
    if isinstance(proof_conclusion, Invalid):
        return (float("-inf"), 0.0, 0.0, 0.0, 0, 0)
    return (
        _suffix_candidate_score(proof_conclusion, suffix),
        antecedent_coverage_score(proof_conclusion, suffix),
        _schematic_score(proof, target, regions, behavior_archive, config),
        -assumption_debt(proof_conclusion, suffix, config.fitness),
        -proof_size(proof),
        -total_formula_size(proof),
    )


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


def _suffix_candidate_score(formula: Formula | Invalid, suffix: Formula) -> float:
    if isinstance(formula, Invalid):
        return 0.0
    if formula == suffix:
        return 1.0
    if not isinstance(unify(formula, suffix), UnifyFailure):
        return 0.90
    return best_directed_similarity(formula, suffix, ())


def _dedupe_by_conclusion_best(proofs: list[Proof], score) -> tuple[Proof, ...]:
    best_by_conclusion: dict[Formula | Invalid, Proof] = {}
    for proof in proofs:
        proof_conclusion = conclusion(proof)
        current = best_by_conclusion.get(proof_conclusion)
        if current is None or score(proof) > score(current):
            best_by_conclusion[proof_conclusion] = proof
    return tuple(sorted(best_by_conclusion.values(), key=score, reverse=True))


def _suffix_retention_diagnostics(
    closed: tuple[Proof, ...],
    schematic: tuple[Proof, ...],
    kept: tuple[Proof, ...],
    target: Formula,
) -> SuffixRetentionDiagnostics:
    suffixes = implication_spine_suffixes(target)
    all_candidates = closed + schematic
    return SuffixRetentionDiagnostics(
        candidates_seen_by_suffix=_suffix_counts(all_candidates, suffixes),
        closed_candidates_seen_by_suffix=_suffix_counts(closed, suffixes),
        schematic_candidates_seen_by_suffix=_suffix_counts(schematic, suffixes),
        survivors_by_suffix=_suffix_counts(kept, suffixes),
        best_candidate_by_suffix=_best_candidate_by_suffix(all_candidates, suffixes),
    )


def _suffix_counts(proofs: tuple[Proof, ...], suffixes: tuple[Formula, ...]) -> tuple[tuple[str, int], ...]:
    return tuple(
        (
            pretty(suffix),
            sum(1 for proof in proofs if _suffix_candidate_score(conclusion(proof), suffix) > 0.0),
        )
        for suffix in suffixes
    )


def _best_candidate_by_suffix(proofs: tuple[Proof, ...], suffixes: tuple[Formula, ...]) -> tuple[tuple[str, str], ...]:
    output: list[tuple[str, str]] = []
    for suffix in suffixes:
        candidates = [proof for proof in proofs if _suffix_candidate_score(conclusion(proof), suffix) > 0.0]
        if not candidates:
            output.append((pretty(suffix), "none"))
            continue
        best = max(candidates, key=lambda proof: _suffix_candidate_score(conclusion(proof), suffix))
        proof_conclusion = conclusion(best)
        output.append((pretty(suffix), "invalid" if isinstance(proof_conclusion, Invalid) else pretty(proof_conclusion)))
    return tuple(output)


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
