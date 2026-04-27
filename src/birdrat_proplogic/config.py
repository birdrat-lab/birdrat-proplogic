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
    enable_context_conjunction_split: bool = False


@dataclass(frozen=True)
class FitnessConfig:
    exact_target_bonus: float = 1_000_000.0
    exact_region_bonus: float = 50_000.0
    symbolic_similarity_weight: float = 1_000.0
    cd_step_penalty: float = 5.0
    proof_size_penalty: float = 1.0
    formula_size_penalty: float = 0.1
    invalid_proof_penalty: float = 100_000.0
    axiom_only_similarity_cap: float = 50.0
    cd_existence_bonus: float = 250.0
    cd_progress_bonus: float = 500.0
    projection_penalty: float = 250.0
    projection_similarity_cap: float = 0.15
    weakening_wrapper_penalty: float = 300.0
    consequent_match_threshold: float = 0.75
    consequent_mismatch_similarity_cap: float = 0.20
    directed_similarity_weight: float = 0.85
    auxiliary_similarity_weight: float = 0.15
    assumption_debt_penalty: float = 100.0
    extra_antecedent_penalty: float = 1.0
    extra_antecedent_size_penalty: float = 0.05
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
class EvolutionConfig:
    population_size: int = 50
    max_generations: int = 100
    elite_count: int = 4
    tournament_size: int = 3
    crossover_rate: float = 0.7
    mutation_rate: float = 0.9
    initial_proof_depth: int = 1
    max_proof_depth: int = 8
    iterative_deepening_budget: int = 10
    iterative_deepening_scale: float = 1.5
    diagnostics_interval: int = 10
    stop_on_exact: bool = True


@dataclass(frozen=True)
class ArchiveConfig:
    max_proofs_per_formula: int = 5
    path: str | None = ".birdrat/archive.json"
    load_on_start: bool = True
    save_on_finish: bool = True


@dataclass(frozen=True)
class ProplogicConfig:
    regions: RegionConfig = field(default_factory=RegionConfig)
    fitness: FitnessConfig = field(default_factory=FitnessConfig)
    mutation: MutationConfig = field(default_factory=MutationConfig)
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)


DEFAULT_CONFIG = ProplogicConfig()
