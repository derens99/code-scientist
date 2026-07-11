import base64
import json
from io import BytesIO

import pytest

from code_scientist.coordination import CoordinationError, SQLiteTaskCoordinator
from code_scientist.evidence import EvidenceStore
from code_scientist.vision import VisualInterpretationError, interpret_pdf_visual_evidence


def _figure_pdf(tmp_path):
    import pymupdf
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (500, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.line((40, 200, 450, 40), fill="navy", width=10)
    draw.text((50, 25), "Pass rate", fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    pdf = tmp_path / "visual-paper.pdf"
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_image((70, 100, 470, 292), stream=buffer.getvalue())
    page.insert_text((70, 315), "Figure 1. Pass rate rises with test-time compute.")
    document.save(pdf)
    document.close()
    return pdf


def test_visual_interpretation_renders_bounded_crop_and_preserves_claim_lineage(tmp_path):
    pdf = _figure_pdf(tmp_path)
    parent = next(
        item
        for item in EvidenceStore.from_paths([pdf]).evidence
        if item.kind == "pdf_figure_region"
    )
    calls = []

    class FakeVisionClient:
        def complete_multimodal(self, prompt, images, max_tokens):
            calls.append((prompt, images, max_tokens))
            return json.dumps(
                {
                    "figure_type": "line_chart",
                    "axes": ["x: test-time compute", "y: pass rate"],
                    "legend": [],
                    "qualitative_trends": ["pass rate increases"],
                    "numerical_observations": [],
                    "uncertainties": ["axis ticks are not readable"],
                    "confidence": 0.82,
                }
            )

    coordinator = SQLiteTaskCoordinator(tmp_path / "coordination.sqlite3")
    coordinator.configure_budget("vision_calls", 1)
    interpreted = interpret_pdf_visual_evidence(
        [parent],
        run_dir=tmp_path,
        client=FakeVisionClient(),
        model="fake-vision-model",
        max_regions=1,
        max_tokens=333,
        coordinator=coordinator,
    )

    assert len(interpreted) == 1
    claim = interpreted[0]
    assert claim.kind == "pdf_visual_claim"
    assert claim.metadata["parent_evidence_id"] == parent.id
    assert claim.metadata["bbox"] == parent.metadata["bbox"]
    assert claim.metadata["requires_human_verification"] == "true"
    assert claim.metadata["machine_interpretation"] == "true"
    assert "pass rate increases" in claim.content
    asset = tmp_path / "visual-assets" / f"{claim.metadata['visual_artifact_sha256']}.png"
    assert asset.is_file()
    assert int(claim.metadata["visual_artifact_bytes"]) == asset.stat().st_size
    prompt, images, max_tokens = calls[0]
    assert parent.id in prompt
    assert max_tokens == 333
    assert base64.b64decode(images[0]["data"]) == asset.read_bytes()
    assert coordinator.budget_state("vision_calls") == (1, 1)


def test_visual_interpretation_fails_closed_on_invalid_schema_and_exhausted_budget(tmp_path):
    pdf = _figure_pdf(tmp_path)
    parent = next(
        item
        for item in EvidenceStore.from_paths([pdf]).evidence
        if item.kind == "pdf_figure_region"
    )

    class InvalidClient:
        def complete_multimodal(self, prompt, images, max_tokens):
            return "not-json"

    with pytest.raises(VisualInterpretationError, match="invalid JSON"):
        interpret_pdf_visual_evidence(
            [parent],
            run_dir=tmp_path,
            client=InvalidClient(),
            model="fake",
            max_regions=1,
        )

    coordinator = SQLiteTaskCoordinator(tmp_path / "budget.sqlite3")
    coordinator.configure_budget("vision_calls", 0)
    with pytest.raises(CoordinationError, match="Budget exhausted"):
        interpret_pdf_visual_evidence(
            [parent],
            run_dir=tmp_path,
            client=InvalidClient(),
            model="fake",
            max_regions=1,
            coordinator=coordinator,
        )
