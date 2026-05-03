from birdrat_proplogic.dproof import (
    DProofParseError,
    parse_dproof,
    proves_identity_up_to_renaming,
    render_dproof_verification,
)
from birdrat_proplogic.formula import pretty
from birdrat_proplogic.proof import Invalid, conclusion


def test_parse_dproof_verifies_dd211_identity() -> None:
    proof = parse_dproof("DD211")

    assert not isinstance(proof, DProofParseError)
    assert proves_identity_up_to_renaming(proof)
    proof_conclusion = conclusion(proof)
    assert not isinstance(proof_conclusion, Invalid)
    assert pretty(proof_conclusion) == "?p3 → ?p3"


def test_render_dproof_verification_reports_identity_result() -> None:
    output = render_dproof_verification("DD211")

    assert "conclusion: ?p3 → ?p3" in output
    assert "derives p -> p up to metavariable renaming: yes" in output
