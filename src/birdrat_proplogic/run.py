from __future__ import annotations

from dataclasses import dataclass

from birdrat_proplogic.formula import Formula, pretty
from birdrat_proplogic.goals import Goal, extract_goals
from birdrat_proplogic.proof import Invalid, Proof, cd_depth, cd_steps, conclusion, proof_size
from birdrat_proplogic.surface import SAnd, SAtom, SImp, SurfaceFormula, desugar, surface_pretty


@dataclass(frozen=True)
class CandidateSummary:
    conclusion: Formula | Invalid
    exact_target: bool
    region: Goal | None
    cd_steps: int
    cd_depth: int
    proof_size: int


@dataclass(frozen=True)
class DemoReport:
    surface_target: SurfaceFormula
    core_target: Formula
    regions: tuple[Goal, ...]
    exact_proof_found: bool
    region_proofs_found: tuple[Goal, ...]
    best_candidate: CandidateSummary | None


def conjunction_commutativity_target() -> SurfaceFormula:
    a = SAtom("a")
    b = SAtom("b")
    return SImp(SAnd(a, b), SAnd(b, a))


def build_demo_report(candidates: tuple[Proof, ...] = ()) -> DemoReport:
    target = conjunction_commutativity_target()
    core_target = desugar(target)
    regions = extract_goals(target)
    candidate_summaries = tuple(_summarize_candidate(candidate, core_target, regions) for candidate in candidates)
    region_proofs = tuple(
        region
        for region in regions
        if any(summary.region == region for summary in candidate_summaries)
    )

    return DemoReport(
        surface_target=target,
        core_target=core_target,
        regions=regions,
        exact_proof_found=any(summary.exact_target for summary in candidate_summaries),
        region_proofs_found=region_proofs,
        best_candidate=_best_candidate(candidate_summaries),
    )


def render_demo_report(report: DemoReport) -> str:
    display_regions = _unique_regions_by_theorem(report.regions)
    lines = [
        "surface target:",
        f"  {surface_pretty(report.surface_target)}",
        "",
        "core target:",
        f"  {pretty(report.core_target)}",
        "",
        "generated regions:",
    ]
    lines.extend(f"  {surface_pretty(region.theorem())}" for region in display_regions)
    lines.extend(
        [
            "",
            "best exact proof:",
            f"  {_found_text(report.exact_proof_found)}",
            "",
            "best region proofs:",
        ]
    )
    lines.extend(
        f"  {surface_pretty(region.theorem())} : {_found_text(region in report.region_proofs_found)}"
        for region in display_regions
    )
    lines.extend(["", "best candidate:"])
    if report.best_candidate is None:
        lines.append("  none")
    else:
        lines.extend(_render_candidate(report.best_candidate))
    return "\n".join(lines)


def main() -> None:
    print(render_demo_report(build_demo_report()))


def _summarize_candidate(candidate: Proof, core_target: Formula, regions: tuple[Goal, ...]) -> CandidateSummary:
    candidate_conclusion = conclusion(candidate)
    exact_target = candidate_conclusion == core_target
    matching_region = next(
        (
            region
            for region in regions
            if candidate_conclusion == region.core_theorem()
        ),
        None,
    )
    return CandidateSummary(
        conclusion=candidate_conclusion,
        exact_target=exact_target,
        region=matching_region,
        cd_steps=cd_steps(candidate),
        cd_depth=cd_depth(candidate),
        proof_size=proof_size(candidate),
    )


def _best_candidate(candidates: tuple[CandidateSummary, ...]) -> CandidateSummary | None:
    if not candidates:
        return None
    return max(candidates, key=_candidate_rank)


def _unique_regions_by_theorem(regions: tuple[Goal, ...]) -> tuple[Goal, ...]:
    seen: set[SurfaceFormula] = set()
    unique: list[Goal] = []
    for region in regions:
        theorem = region.theorem()
        if theorem in seen:
            continue
        seen.add(theorem)
        unique.append(region)
    return tuple(unique)


def _candidate_rank(candidate: CandidateSummary) -> tuple[int, int, int, int]:
    valid = not isinstance(candidate.conclusion, Invalid)
    return (
        int(candidate.exact_target),
        int(candidate.region is not None),
        int(valid),
        -candidate.proof_size,
    )


def _render_candidate(candidate: CandidateSummary) -> list[str]:
    if isinstance(candidate.conclusion, Invalid):
        conclusion_text = f"invalid: {candidate.conclusion.reason}"
    else:
        conclusion_text = pretty(candidate.conclusion)
    return [
        f"  conclusion: {conclusion_text}",
        f"  exact target: {_found_text(candidate.exact_target)}",
        f"  region: {surface_pretty(candidate.region.theorem()) if candidate.region else 'none'}",
        f"  cd_steps: {candidate.cd_steps}",
        f"  cd_depth: {candidate.cd_depth}",
        f"  proof_size: {candidate.proof_size}",
    ]


def _found_text(found: bool) -> str:
    if found:
        return "found"
    return "not found"


if __name__ == "__main__":
    main()
