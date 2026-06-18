from code_scientist.paper import seed_paper_evidence


def test_seed_paper_evidence_contains_core_loop():
    evidence = seed_paper_evidence()
    contents = " ".join(item.content for item in evidence)

    assert len(evidence) >= 5
    assert "generate, debate, and evolve" in contents
    assert "Elo" in contents
    assert "safety" in contents.lower()
