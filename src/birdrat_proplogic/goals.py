from __future__ import annotations

from dataclasses import dataclass

from birdrat_proplogic.config import DEFAULT_CONFIG, ProplogicConfig, RegionConfig
from birdrat_proplogic.formula import Formula
from birdrat_proplogic.surface import (
    SAnd,
    SIff,
    SImp,
    SOr,
    SurfaceFormula,
    desugar,
    surface_pretty,
)


@dataclass(frozen=True)
class Goal:
    context: tuple[SurfaceFormula, ...]
    target: SurfaceFormula
    name: str = "goal"
    weight: float = 1.0

    def theorem(self) -> SurfaceFormula:
        theorem = self.target
        for hypothesis in reversed(self.context):
            theorem = SImp(hypothesis, theorem)
        return theorem

    def core_theorem(self) -> Formula:
        return desugar(self.theorem())


def extract_goals(
    target: SurfaceFormula,
    config: ProplogicConfig = DEFAULT_CONFIG,
) -> tuple[Goal, ...]:
    region_config = config.regions
    initial = Goal((), target, "whole", region_config.whole_goal_weight)
    seen: set[tuple[tuple[SurfaceFormula, ...], SurfaceFormula]] = set()
    goals: list[Goal] = []
    _extract(initial, seen, goals, region_config)
    return tuple(goals)


def _extract(
    goal: Goal,
    seen: set[tuple[tuple[SurfaceFormula, ...], SurfaceFormula]],
    out: list[Goal],
    config: RegionConfig,
) -> None:
    key = (goal.context, goal.target)
    if key in seen:
        return
    seen.add(key)
    out.append(goal)

    match goal.target:
        case SImp(left, right):
            _extract(
                Goal(
                    goal.context + (left,),
                    right,
                    f"{goal.name}:imp",
                    goal.weight * config.implication_target_weight,
                ),
                seen,
                out,
                config,
            )
        case SAnd(left, right):
            _extract(
                Goal(
                    goal.context,
                    left,
                    f"{goal.name}:left",
                    goal.weight * config.conjunction_target_weight,
                ),
                seen,
                out,
                config,
            )
            _extract(
                Goal(
                    goal.context,
                    right,
                    f"{goal.name}:right",
                    goal.weight * config.conjunction_target_weight,
                ),
                seen,
                out,
                config,
            )
        case SIff(left, right):
            _extract(
                Goal(
                    goal.context,
                    SImp(left, right),
                    f"{goal.name}:forward",
                    goal.weight * config.biconditional_direction_weight,
                ),
                seen,
                out,
                config,
            )
            _extract(
                Goal(
                    goal.context,
                    SImp(right, left),
                    f"{goal.name}:backward",
                    goal.weight * config.biconditional_direction_weight,
                ),
                seen,
                out,
                config,
            )

    for index, hypothesis in enumerate(goal.context):
        prefix = goal.context[:index]
        suffix = goal.context[index + 1 :]
        match hypothesis:
            case SAnd(left, right):
                _extract(
                    Goal(
                        goal.context,
                        left,
                        f"{goal.name}:ctx-left",
                        goal.weight * config.context_conjunction_part_weight,
                    ),
                    seen,
                    out,
                    config,
                )
                _extract(
                    Goal(
                        goal.context,
                        right,
                        f"{goal.name}:ctx-right",
                        goal.weight * config.context_conjunction_part_weight,
                    ),
                    seen,
                    out,
                    config,
                )
                _extract(
                    Goal(
                        prefix + (left, right) + suffix,
                        goal.target,
                        f"{goal.name}:ctx-and",
                        goal.weight * config.context_conjunction_split_weight,
                    ),
                    seen,
                    out,
                    config,
                )
            case SOr(left, right):
                _extract(
                    Goal(
                        prefix + (left,) + suffix,
                        goal.target,
                        f"{goal.name}:case-left",
                        goal.weight * config.context_disjunction_case_weight,
                    ),
                    seen,
                    out,
                    config,
                )
                _extract(
                    Goal(
                        prefix + (right,) + suffix,
                        goal.target,
                        f"{goal.name}:case-right",
                        goal.weight * config.context_disjunction_case_weight,
                    ),
                    seen,
                    out,
                    config,
                )


def goal_label(goal: Goal) -> str:
    if not goal.context:
        return surface_pretty(goal.target)
    context = ", ".join(surface_pretty(item) for item in goal.context)
    return f"{context} ⊢ {surface_pretty(goal.target)}"
