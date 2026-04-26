from birdrat_proplogic.formula import pretty
from birdrat_proplogic.run import build_demo_report, render_demo_report
from birdrat_proplogic.surface import surface_pretty


def test_demo_report_contains_section_19_target_and_regions() -> None:
    report = build_demo_report()
    region_theorems = {surface_pretty(region.theorem()) for region in report.regions}

    assert surface_pretty(report.surface_target) == "a ∧ b → b ∧ a"
    assert pretty(report.core_target) == "¬(a → ¬b) → ¬(b → ¬a)"
    assert "a ∧ b → b ∧ a" in region_theorems
    assert "a ∧ b → b" in region_theorems
    assert "a ∧ b → a" in region_theorems


def test_demo_report_has_no_proofs_without_candidates() -> None:
    report = build_demo_report()

    assert not report.exact_proof_found
    assert report.region_proofs_found == ()
    assert report.best_candidate is None


def test_demo_report_rendering_mentions_empty_proof_status() -> None:
    output = render_demo_report(build_demo_report())

    assert "best exact proof:\n  not found" in output
    assert "best candidate:\n  none" in output
