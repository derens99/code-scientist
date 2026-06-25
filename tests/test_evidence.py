import json

from code_scientist.evidence import EvidenceStore


def test_evidence_store_ingests_local_files_and_returns_cited_snippets(tmp_path):
    source = tmp_path / "agent-findings.md"
    source.write_text(
        "# Agent Findings\n\n"
        "Critic-before-edit assumption decomposition improved pass_rate in local repair tasks.\n\n"
        "Unrelated notes about dashboard polish.\n",
        encoding="utf-8",
    )

    store = EvidenceStore.from_paths([source])
    results = store.search("critic edit pass_rate", limit=1)

    assert len(results) == 1
    assert results[0].source.endswith("agent-findings.md")
    assert "Critic-before-edit" in results[0].content
    assert "lines" in results[0].notes


def test_evidence_store_preserves_markdown_section_citations(tmp_path):
    source = tmp_path / "agent-findings.md"
    source.write_text(
        "# Agent Findings\n\n"
        "General overview.\n\n"
        "## Failure Recovery\n\n"
        "Critic-before-edit assumption decomposition improved pass_rate in local repair tasks.\n",
        encoding="utf-8",
    )

    store = EvidenceStore.from_paths([source])
    result = store.search("critic edit pass_rate", limit=1)[0]

    assert result.metadata["section"] == "Agent Findings > Failure Recovery"
    assert result.metadata["section_level"] == "2"
    assert result.metadata["citation"].endswith(
        "agent-findings.md:Agent Findings > Failure Recovery:lines 7-7"
    )


def test_evidence_store_classifies_code_markdown_and_pdf_sources(tmp_path):
    markdown = tmp_path / "findings.md"
    markdown.write_text("Failure-derived benchmark seeds improved pass_rate on repair tasks.", encoding="utf-8")
    code = tmp_path / "workflow.py"
    code.write_text("def critic_before_edit():\n    return 'tracks assumptions before patching'\n", encoding="utf-8")
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\nLLM coding-agent memory freshness reduced repeated errors.\n%%EOF")

    store = EvidenceStore.from_paths([tmp_path])

    kinds = {item.kind for item in store.evidence}
    assert {"markdown_source", "code_source", "pdf_source"} <= kinds
    assert all(item.metadata["path"].startswith(str(tmp_path)) for item in store.evidence)
    assert all("parser" in item.metadata for item in store.evidence)
    assert store.search("memory freshness repeated errors", limit=1)[0].kind == "pdf_source"


def test_evidence_store_preserves_pdf_page_citations(tmp_path, monkeypatch):
    import pypdf

    class FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class FakeReader:
        def __init__(self, _path: str) -> None:
            self.pages = [
                FakePage("Introductory coding-agent paper text."),
                FakePage("Memory freshness reduced repeated coding-agent repair errors."),
            ]

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF")
    monkeypatch.setattr(pypdf, "PdfReader", FakeReader)

    store = EvidenceStore.from_paths([pdf])
    result = store.search("memory freshness repair errors", limit=1)[0]

    assert result.kind == "pdf_source"
    assert result.metadata["parser"] == "pdf_page_text"
    assert result.metadata["page_number"] == "2"
    assert result.metadata["citation"].endswith("paper.pdf:page 2")


def test_evidence_store_keeps_readable_pdf_pages_when_one_page_fails(tmp_path, monkeypatch):
    import pypdf

    class FakePage:
        def __init__(self, text: str, fail: bool = False) -> None:
            self.text = text
            self.fail = fail

        def extract_text(self) -> str:
            if self.fail:
                raise ValueError("damaged page stream")
            return self.text

    class FakeReader:
        def __init__(self, _path: str) -> None:
            self.pages = [
                FakePage("Introductory coding-agent paper text."),
                FakePage("", fail=True),
                FakePage("Repair traces remain readable after one damaged PDF page."),
            ]

    pdf = tmp_path / "damaged-paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF")
    monkeypatch.setattr(pypdf, "PdfReader", FakeReader)

    store = EvidenceStore.from_paths([pdf])
    page_numbers = {item.metadata["page_number"] for item in store.evidence}
    result = store.search("repair traces readable damaged page", limit=1)[0]

    assert page_numbers == {"1", "3"}
    assert result.metadata["parser"] == "pdf_page_text"
    assert result.metadata["page_number"] == "3"
    assert result.metadata["pdf_failed_pages"] == "2"
    assert result.metadata["citation"].endswith("damaged-paper.pdf:page 3")


def test_evidence_store_records_scanned_pdf_pages_that_need_ocr(tmp_path, monkeypatch):
    import pypdf

    class FakePage:
        def extract_text(self) -> str:
            return ""

    class FakeReader:
        def __init__(self, _path: str) -> None:
            self.pages = [FakePage(), FakePage()]

    pdf = tmp_path / "scanned-paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF")
    monkeypatch.setattr(pypdf, "PdfReader", FakeReader)

    store = EvidenceStore.from_paths([pdf])
    result = store.search("scanned image ocr required", limit=1)[0]

    assert result.kind == "pdf_source"
    assert result.metadata["parser"] == "pdf_ocr_required"
    assert result.metadata["page_number"] == "1"
    assert result.metadata["pdf_empty_pages"] == "1,2"
    assert result.metadata["pdf_empty_page_count"] == "2"
    assert result.metadata["requires_ocr"] == "true"
    assert result.metadata["citation"].endswith("scanned-paper.pdf:page 1")
    assert "OCR is required" in result.content


def test_evidence_store_extracts_benchmark_and_prior_trace_json(tmp_path):
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(
        json.dumps(
            {
                "name": "Seeded repair eval",
                "baseline_metrics": {"pass_rate": 0.42, "regression_count": 4},
                "candidate_metrics": {"pass_rate": 0.67, "regression_count": 2},
                "deltas": {"pass_rate": 0.25, "regression_count": -2},
                "success": True,
                "notes": ["Failure-derived seeds improved repair coverage."],
            }
        ),
        encoding="utf-8",
    )
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "agent_traces": [
                    {
                        "id": "trace-1",
                        "cycle": 1,
                        "agent": "reflection",
                        "action": "deep_verification",
                        "notes": "Novelty review found missing repo-specific failures.",
                        "output_refs": ["rev-1"],
                    }
                ],
                "reviews": [
                    {
                        "id": "rev-1",
                        "hypothesis_id": "hyp-1",
                        "decision": "accept",
                        "findings": ["Local traces support benchmark seed mining."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    store = EvidenceStore.from_paths([benchmark, state])
    bundle = store.retrieve("pass_rate trace benchmark seed mining", limit=4)

    assert any(item.kind == "benchmark_result" for item in bundle.evidence)
    assert any(item.kind == "run_state_trace" for item in bundle.evidence)
    assert any("pass_rate" in item.content for item in bundle.evidence)
    assert bundle.evidence_refs == [item.id for item in bundle.evidence]
    assert bundle.citations


def test_evidence_store_writes_and_reads_reusable_index(tmp_path):
    source = tmp_path / "corpus-note.md"
    source.write_text(
        "Assumption decomposition reduced repeated coding-agent repair failures in the local corpus.",
        encoding="utf-8",
    )
    index = tmp_path / "corpus.index.json"

    store = EvidenceStore.from_paths([source])
    store.write_index(index, name="agent repair corpus")
    loaded = EvidenceStore.from_index(index)

    data = json.loads(index.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["name"] == "agent repair corpus"
    assert data["evidence_count"] == len(store.evidence)
    assert loaded.search("assumption repair failures", limit=1)[0].source == str(source)
    assert loaded.evidence[0].metadata["citation"].endswith("corpus-note.md:lines 1-1")


def test_evidence_store_ranks_repeated_corpus_terms_above_tie_source_order(tmp_path):
    weaker = tmp_path / "a-weaker.md"
    stronger = tmp_path / "b-stronger.md"
    weaker.write_text("pass_rate repair note with a single supporting mention.", encoding="utf-8")
    stronger.write_text(
        "pass_rate pass_rate pass_rate repair repair repair repeated benchmark evidence.",
        encoding="utf-8",
    )

    store = EvidenceStore.from_paths([weaker, stronger])
    result = store.search("pass_rate repair", limit=1)[0]

    assert result.source == str(stronger)


def test_evidence_store_embedding_search_matches_private_corpus_morphology(tmp_path):
    relevant = tmp_path / "maintainer-replay.md"
    distractor = tmp_path / "dashboard.md"
    relevant.write_text(
        "Maintainer replay traces reveal regression pattern clusters for failed code edits.",
        encoding="utf-8",
    )
    distractor.write_text(
        "Dashboard polish notes about spacing, colors, navigation, and status filters.",
        encoding="utf-8",
    )

    store = EvidenceStore.from_paths([relevant, distractor])

    assert store.search("replays regressions", limit=1) == []
    embedding_result = store.search_embedding("replays regressions", limit=1)[0]
    hybrid_bundle = store.retrieve("replays regressions", limit=1, mode="hybrid")

    assert embedding_result.source == str(relevant)
    assert hybrid_bundle.retrieval_method == "hybrid"
    assert hybrid_bundle.evidence_refs == [embedding_result.id]


def test_evidence_store_exposes_local_embedding_similarity_for_proximity():
    related = EvidenceStore.local_embedding_similarity(
        "benchmark seeded repair loop",
        "benchmark-seeded repair loops",
    )
    unrelated = EvidenceStore.local_embedding_similarity(
        "benchmark seeded repair loop",
        "ui layout density scan speed",
    )

    assert related > 0.9
    assert unrelated < related


def test_evidence_index_records_local_embedding_retrieval_metadata(tmp_path):
    source = tmp_path / "private-corpus.md"
    source.write_text(
        "Private corpus traces show maintainer replay regressions in coding-agent repair work.",
        encoding="utf-8",
    )
    index = tmp_path / "private-corpus.index.json"

    EvidenceStore.from_paths([source]).write_index(index, name="private corpus")

    data = json.loads(index.read_text(encoding="utf-8"))
    assert "local_embedding" in data["retrieval_methods"]
    assert data["embedding_model"] == "local-hashed-char-ngram-v1"
    assert data["embedding_dimensions"] > 0
