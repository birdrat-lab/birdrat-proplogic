from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegionConfig:
    whole_goal_weight: float = 1.0
    implication_target_weight: float = 0.8
    conjunction_target_weight: float = 0.7
    biconditional_direction_weight: float = 0.8
    context_conjunction_part_weight: float = 0.5
    context_conjunction_split_weight: float = 0.6
    context_disjunction_case_weight: float = 0.6


@dataclass(frozen=True)
class FitnessConfig:
    exact_target_bonus: float = 1_000_000.0
    exact_region_bonus: float = 50_000.0
    symbolic_similarity_weight: float = 1_000.0
    cd_step_penalty: float = 5.0
    proof_size_penalty: float = 1.0
    formula_size_penalty: float = 0.1
    invalid_proof_penalty: float = 100_000.0
    adaptive_cd_depth_threshold: int = 8
    depth_penalty_limit: float = 100.0
    depth_penalty_steepness: float = 1.5
    exact_success_base: float = 10_000_000.0


@dataclass(frozen=True)
class MutationConfig:
    atom_names: tuple[str, ...] = ("a", "b", "c")
    meta_names: tuple[str, ...] = ("?p", "?q", "?r")
    max_formula_size: int = 32
    random_formula_depth: int = 3
    random_proof_depth: int = 2


@dataclass(frozen=True)
class ProplogicConfig:
    regions: RegionConfig = field(default_factory=RegionConfig)
    fitness: FitnessConfig = field(default_factory=FitnessConfig)
    mutation: MutationConfig = field(default_factory=MutationConfig)


DEFAULT_CONFIG = ProplogicConfig()
