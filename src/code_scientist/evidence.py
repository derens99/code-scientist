from __future__ import annotations

import json
import math
import threading
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from hashlib import sha1
from pathlib import Path

from code_scientist.models import Evidence, Hypothesis, RetrievalMemoryRecord, stable_id


TEXT_EXTENSIONS = {
    ".csv",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
PDF_EXTENSIONS = {".pdf"}
SKIP_DIRS = {".git", ".next", ".venv", "__pycache__", "node_modules"}
LOCAL_EMBEDDING_MODEL = "local-hashed-char-ngram-v1"
LOCAL_EMBEDDING_DIMENSIONS = 256


@dataclass(frozen=True)
class EvidenceBundle:
    query: str
    evidence: list[Evidence]
    retrieval_method: str = "bm25"

    @property
    def evidence_refs(self) -> list[str]:
        return [item.id for item in self.evidence]

    @property
    def citations(self) -> list[str]:
        return [
            item.metadata.get("citation", f"{item.source} ({item.notes})")
            for item in self.evidence
        ]


class EvidenceStore:
    def __init__(self, evidence: Iterable[Evidence] = ()) -> None:
        self.evidence = list(evidence)
        self._retrieval_local = threading.local()

    def _retrieval_buffer(self) -> list[RetrievalMemoryRecord]:
        buffer = getattr(self._retrieval_local, "records", None)
        if buffer is None:
            buffer = []
            self._retrieval_local.records = buffer
        return buffer

    @classmethod
    def from_paths(cls, paths: Iterable[str | Path]) -> EvidenceStore:
        store = cls()
        for path in paths:
            store.ingest_path(path)
        return store

    @classmethod
    def from_index(cls, path: str | Path) -> EvidenceStore:
        source = Path(path)
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Evidence index must be a JSON object: {source}")
        raw_evidence = data.get("evidence", [])
        if not isinstance(raw_evidence, list):
            raise ValueError(f"Evidence index has invalid evidence list: {source}")
        index_id = str(data.get("id", ""))
        index_name = str(data.get("name", ""))
        schema_version = str(data.get("schema_version", ""))
        evidence: list[Evidence] = []
        for raw_item in raw_evidence:
            if not isinstance(raw_item, dict):
                continue
            item = Evidence.from_dict(raw_item)
            metadata = {
                **item.metadata,
                "index_path": str(source),
                "index_id": index_id,
                "index_name": index_name,
                "index_schema_version": schema_version,
            }
            evidence.append(
                Evidence(
                    id=item.id,
                    kind=item.kind,
                    source=item.source,
                    content=item.content,
                    notes=item.notes,
                    metadata=metadata,
                )
            )
        return cls(evidence)

    @classmethod
    def from_indexes(cls, paths: Iterable[str | Path]) -> EvidenceStore:
        store = cls()
        for path in paths:
            store.evidence.extend(cls.from_index(path).evidence)
        store.evidence = _unique_evidence(store.evidence)
        return store

    def to_index(self, name: str = "") -> dict[str, object]:
        index_name = name.strip() or "local evidence index"
        evidence_ids = ",".join(item.id for item in self.evidence)
        index_id = stable_id("evidx", f"{index_name}:{evidence_ids}")
        return {
            "schema_version": 1,
            "id": index_id,
            "name": index_name,
            "evidence_count": len(self.evidence),
            "retrieval_methods": ["bm25", "local_embedding", "hybrid"],
            "embedding_model": LOCAL_EMBEDDING_MODEL,
            "embedding_dimensions": LOCAL_EMBEDDING_DIMENSIONS,
            "evidence": [item.to_dict() for item in self.evidence],
        }

    def write_index(self, path: str | Path, name: str = "") -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(self.to_index(name=name), indent=2), encoding="utf-8")

    def ingest_path(self, path: str | Path) -> None:
        source = Path(path)
        if source.is_dir():
            for file_path in sorted(source.rglob("*")):
                if _should_read(file_path):
                    self._ingest_file(file_path)
            return
        if _should_read(source):
            self._ingest_file(source)

    def _ingest_file(self, path: Path) -> None:
        if path.suffix.lower() == ".json":
            self.evidence.extend(_evidence_from_json(path))
            return
        if path.suffix.lower() in PDF_EXTENSIONS:
            self.evidence.extend(_evidence_from_pdf(path))
            return
        if path.suffix.lower() == ".md":
            text = _read_text(path)
            for start_line, end_line, content, section, section_level in _markdown_chunks(text):
                self.evidence.append(
                    _evidence_for_chunk(
                        path,
                        start_line,
                        end_line,
                        content,
                        citation=_section_citation(path, section, start_line, end_line),
                        metadata_extra={
                            "section": section,
                            "section_level": str(section_level),
                        }
                        if section
                        else {},
                    )
                )
            return
        text = _read_text(path)
        for start_line, end_line, content in _ingestible_chunks(text):
            self.evidence.append(_evidence_for_chunk(path, start_line, end_line, content))

    def search(self, query: str, limit: int = 5) -> list[Evidence]:
        return [item for _score, item in self._bm25_ranked(query, limit)]

    def search_embedding(self, query: str, limit: int = 5) -> list[Evidence]:
        if limit <= 0:
            return []
        query_vector = _local_embedding_vector(query)
        if not query_vector:
            return []

        ranked: list[tuple[float, str, Evidence]] = []
        for item in self.evidence:
            item_vector = _local_embedding_vector(" ".join([item.content, item.notes, item.source]))
            score = _cosine_similarity(query_vector, item_vector)
            if score > 0:
                ranked.append((score, item.source, item))

        ranked.sort(key=lambda entry: (-entry[0], entry[1], entry[2].id))
        return [item for _score, _source, item in ranked[:limit]]

    @staticmethod
    def local_embedding_similarity(left: str, right: str) -> float:
        return _cosine_similarity(_local_embedding_vector(left), _local_embedding_vector(right))

    def search_hybrid(self, query: str, limit: int = 5) -> list[Evidence]:
        if limit <= 0:
            return []
        bm25_ranked = self._bm25_ranked(query, limit=max(limit, len(self.evidence)))
        embedding_ranked = self._embedding_ranked(query, limit=max(limit, len(self.evidence)))
        scores: dict[str, float] = {}
        items_by_id: dict[str, Evidence] = {}
        for score, item in bm25_ranked:
            items_by_id[item.id] = item
            scores[item.id] = max(scores.get(item.id, 0.0), _bounded_score(score))
        for score, item in embedding_ranked:
            items_by_id[item.id] = item
            scores[item.id] = scores.get(item.id, 0.0) + score

        ranked = [
            (score, items_by_id[item_id].source, items_by_id[item_id])
            for item_id, score in scores.items()
            if score > 0
        ]
        ranked.sort(key=lambda entry: (-entry[0], entry[1], entry[2].id))
        return [item for _score, _source, item in ranked[:limit]]

    def _bm25_ranked(self, query: str, limit: int) -> list[tuple[float, Evidence]]:
        query_tokens = _tokens(query)
        if not query_tokens or limit <= 0:
            return []
        corpus_counts: list[tuple[Evidence, Counter[str]]] = [
            (item, Counter(_tokens(" ".join([item.content, item.notes, item.source]))))
            for item in self.evidence
        ]
        document_frequency: Counter[str] = Counter()
        for _item, token_counts in corpus_counts:
            document_frequency.update(token_counts.keys())
        average_document_length = (
            sum(sum(token_counts.values()) for _item, token_counts in corpus_counts) / len(corpus_counts)
            if corpus_counts
            else 1.0
        )

        ranked: list[tuple[float, str, Evidence]] = []
        for item, token_counts in corpus_counts:
            score = _bm25_score(
                query_tokens=query_tokens,
                token_counts=token_counts,
                document_frequency=document_frequency,
                document_count=len(corpus_counts),
                average_document_length=average_document_length,
            )
            if score > 0:
                ranked.append((score, item.source, item))

        ranked.sort(key=lambda entry: (-entry[0], entry[1], entry[2].id))
        return [(_score, item) for _score, _source, item in ranked[:limit]]

    def _embedding_ranked(self, query: str, limit: int) -> list[tuple[float, Evidence]]:
        if limit <= 0:
            return []
        query_vector = _local_embedding_vector(query)
        if not query_vector:
            return []

        ranked: list[tuple[float, str, Evidence]] = []
        for item in self.evidence:
            item_vector = _local_embedding_vector(" ".join([item.content, item.notes, item.source]))
            score = _cosine_similarity(query_vector, item_vector)
            if score > 0:
                ranked.append((score, item.source, item))

        ranked.sort(key=lambda entry: (-entry[0], entry[1], entry[2].id))
        return [(_score, item) for _score, _source, item in ranked[:limit]]

    def search_hypothesis(self, hypothesis: Hypothesis, limit: int = 5) -> list[Evidence]:
        query = " ".join(
            [
                hypothesis.title,
                hypothesis.claim,
                hypothesis.rationale,
                *hypothesis.assumptions,
                *hypothesis.risks,
            ]
        )
        return self.search(query, limit=limit)

    def retrieve(self, query: str, limit: int = 5, mode: str = "hybrid") -> EvidenceBundle:
        if mode == "bm25":
            evidence = self.search(query, limit=limit)
        elif mode in {"embedding", "local_embedding"}:
            evidence = self.search_embedding(query, limit=limit)
            mode = "local_embedding"
        elif mode == "hybrid":
            evidence = self.search_hybrid(query, limit=limit)
        else:
            raise ValueError(f"Unknown evidence retrieval mode: {mode}")
        bundle = EvidenceBundle(query=query, evidence=evidence, retrieval_method=mode)
        buffer = self._retrieval_buffer()
        buffer.append(
            RetrievalMemoryRecord(
                id=stable_id(
                    "retrieval",
                    f"{len(buffer)}:{query}:{mode}:{','.join(bundle.evidence_refs)}",
                ),
                query=query,
                retrieval_method=mode,
                evidence_refs=bundle.evidence_refs,
                citations=bundle.citations,
                reason="evidence_store.retrieve",
            )
        )
        return bundle

    def consume_retrieval_memory(
        self,
        *,
        cycle: int,
        agent: str,
        task_id: str,
        reason: str = "",
    ) -> list[RetrievalMemoryRecord]:
        buffer = self._retrieval_buffer()
        records = [
            replace(
                record,
                id=stable_id(
                    "retrieval",
                    (
                        f"{cycle}:{agent}:{task_id}:{index}:{record.query}:"
                        f"{record.retrieval_method}:{','.join(record.evidence_refs)}"
                    ),
                ),
                cycle=cycle,
                agent=agent,
                task_id=task_id,
                reason=reason or record.reason,
            )
            for index, record in enumerate(buffer)
        ]
        buffer.clear()
        return records

    def add(self, evidence: Evidence) -> None:
        if evidence.id not in {item.id for item in self.evidence}:
            self.evidence.append(evidence)


def read_document_text(path: str | Path) -> str:
    source = Path(path)
    if source.suffix.lower() in PDF_EXTENSIONS:
        return _read_pdf_text(source)
    return _read_text(source)


def _should_read(path: Path) -> bool:
    if not path.is_file():
        return False
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS or path.suffix.lower() in PDF_EXTENSIONS


def _ingestible_chunks(text: str) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    current: list[str] = []
    start_line = 1
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if line:
            if not current:
                start_line = line_number
            current.append(line)
            continue
        if current:
            chunks.append((start_line, line_number - 1, " ".join(current)))
            current = []
    if current:
        chunks.append((start_line, start_line + len(current) - 1, " ".join(current)))
    return chunks


def _markdown_chunks(text: str) -> list[tuple[int, int, str, str, int]]:
    chunks: list[tuple[int, int, str, str, int]] = []
    current: list[str] = []
    current_section = ""
    current_section_level = 0
    start_line = 1
    heading_stack: list[tuple[int, str]] = []

    def flush(end_line: int) -> None:
        nonlocal current
        if current:
            chunks.append(
                (
                    start_line,
                    end_line,
                    " ".join(current),
                    current_section,
                    current_section_level,
                )
            )
            current = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        heading = _markdown_heading(line)
        if heading:
            flush(line_number - 1)
            level, title = heading
            heading_stack = [item for item in heading_stack if item[0] < level]
            heading_stack.append((level, title))
            current_section = " > ".join(title for _level, title in heading_stack)
            current_section_level = level
            continue
        if line:
            if not current:
                start_line = line_number
            current.append(line)
            continue
        flush(line_number - 1)
    flush(start_line + len(current) - 1)
    return chunks


def _markdown_heading(line: str) -> tuple[int, str] | None:
    if not line.startswith("#"):
        return None
    level = len(line) - len(line.lstrip("#"))
    if level > 6 or len(line) <= level or line[level] != " ":
        return None
    title = line[level:].strip()
    if not title:
        return None
    return level, title.strip("#").strip()


def _tokens(text: str) -> list[str]:
    return [
        token.strip(".,:;()[]{}'\"").lower()
        for token in text.replace("_", " ").replace("-", " ").split()
        if len(token.strip(".,:;()[]{}'\"")) > 2
    ]


def _bm25_score(
    query_tokens: list[str],
    token_counts: Counter[str],
    document_frequency: Counter[str],
    document_count: int,
    average_document_length: float,
) -> float:
    if not token_counts or not document_count:
        return 0.0
    k1 = 1.5
    b = 0.75
    document_length = max(sum(token_counts.values()), 1)
    length_ratio = document_length / average_document_length if average_document_length else 1.0
    normalizer = k1 * (1 - b + b * length_ratio)
    score = 0.0
    for token in set(query_tokens):
        frequency = token_counts.get(token, 0)
        if not frequency:
            continue
        term_document_frequency = document_frequency.get(token, 0)
        idf = math.log(1 + (document_count - term_document_frequency + 0.5) / (term_document_frequency + 0.5))
        score += idf * ((frequency * (k1 + 1)) / (frequency + normalizer))
    return score


def _local_embedding_vector(text: str) -> Counter[int]:
    vector: Counter[int] = Counter()
    for token in _tokens(text):
        padded = f"^{token}$"
        for size in (3, 4, 5):
            if len(padded) < size:
                continue
            for index in range(0, len(padded) - size + 1):
                gram = padded[index : index + size]
                bucket = int(sha1(gram.encode("utf-8")).hexdigest()[:8], 16) % LOCAL_EMBEDDING_DIMENSIONS
                vector[bucket] += 1
    return vector


def _cosine_similarity(left: Counter[int], right: Counter[int]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(value * right.get(key, 0) for key, value in left.items())
    if not numerator:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _bounded_score(score: float) -> float:
    if score <= 0:
        return 0.0
    return score / (score + 1.0)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _read_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(str(path))
        page_texts: list[str] = []
        for page in reader.pages:
            try:
                page_texts.append(page.extract_text() or "")
            except Exception:
                continue
        if page_texts:
            return "\n".join(page_texts)
    except Exception:
        pass
    return path.read_bytes().decode("utf-8", errors="ignore")


def _evidence_from_pdf(path: Path) -> list[Evidence]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(str(path))
        evidence: list[Evidence] = []
        failed_pages: list[str] = []
        empty_pages: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:
                failed_pages.append(str(page_number))
                continue
            if not page_text.strip():
                empty_pages.append(str(page_number))
                continue
            for start_line, end_line, content in _ingestible_chunks(page_text):
                evidence.append(
                    _evidence_for_chunk(
                        path,
                        start_line,
                        end_line,
                        content,
                        citation=f"{_source_for(path)}:page {page_number}",
                        notes=f"page {page_number} lines {start_line}-{end_line}",
                        parser="pdf_page_text",
                        metadata_extra={
                            "page_number": str(page_number),
                            "page_start_line": str(start_line),
                            "page_end_line": str(end_line),
                        },
                    )
                )
        if empty_pages:
            evidence.append(_pdf_ocr_required_evidence(path, empty_pages))
        if evidence:
            if empty_pages:
                empty_page_text = ",".join(empty_pages)
                empty_page_count = str(len(empty_pages))
                evidence = [
                    replace(
                        item,
                        metadata={
                            **item.metadata,
                            "pdf_empty_pages": empty_page_text,
                            "pdf_empty_page_count": empty_page_count,
                        },
                    )
                    for item in evidence
                ]
            if failed_pages:
                failed_page_text = ",".join(failed_pages)
                failed_page_count = str(len(failed_pages))
                evidence = [
                    replace(
                        item,
                        metadata={
                            **item.metadata,
                            "pdf_failed_pages": failed_page_text,
                            "pdf_failed_page_count": failed_page_count,
                        },
                    )
                    for item in evidence
                ]
            return evidence
    except Exception:
        pass

    text = _read_pdf_text(path)
    return [
        _evidence_for_chunk(path, start_line, end_line, content)
        for start_line, end_line, content in _ingestible_chunks(text)
    ]


def _pdf_ocr_required_evidence(path: Path, empty_pages: list[str]) -> Evidence:
    source = _source_for(path)
    page_number = empty_pages[0]
    page_list = ",".join(empty_pages)
    content = (
        f"PDF page {page_number} in {path.name} has no extractable text. "
        f"The PDF page is likely scanned or image-only; OCR is required before "
        f"pages {page_list} can ground scientific claims."
    )
    citation = f"{source}:page {page_number}"
    return Evidence(
        id=stable_id("ev", f"{source}:pdf_ocr_required:{page_list}"),
        kind=_kind_for_path(path),
        source=source,
        content=content,
        notes=f"page {page_number} has no extractable text; OCR required",
        metadata={
            "path": source,
            "extension": path.suffix.lower(),
            "parser": "pdf_ocr_required",
            "page_number": page_number,
            "citation": citation,
            "requires_ocr": "true",
        },
    )


def _source_for(path: Path) -> str:
    return str(path)


def _kind_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".rst"}:
        return "markdown_source"
    if suffix in {".py", ".ts", ".tsx"}:
        return "code_source"
    if suffix == ".pdf":
        return "pdf_source"
    if suffix == ".json":
        return "json_source"
    return "local_source"


def _parser_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf_text"
    return "text"


def _section_citation(path: Path, section: str, start_line: int, end_line: int) -> str:
    if not section:
        return f"{_source_for(path)}:lines {start_line}-{end_line}"
    return f"{_source_for(path)}:{section}:lines {start_line}-{end_line}"


def _evidence_for_chunk(
    path: Path,
    start_line: int,
    end_line: int,
    content: str,
    citation: str | None = None,
    notes: str | None = None,
    parser: str | None = None,
    metadata_extra: dict[str, str] | None = None,
) -> Evidence:
    source = _source_for(path)
    citation = citation or f"{source}:lines {start_line}-{end_line}"
    metadata = {
        "path": source,
        "extension": path.suffix.lower(),
        "parser": parser or _parser_for_path(path),
        "start_line": str(start_line),
        "end_line": str(end_line),
        "citation": citation,
    }
    metadata.update(metadata_extra or {})
    return Evidence(
        id=stable_id("ev", f"{source}:{citation}:{start_line}:{end_line}:{content}"),
        kind=_kind_for_path(path),
        source=source,
        content=content,
        notes=notes or f"lines {start_line}-{end_line}",
        metadata=metadata,
    )


def _evidence_from_json(path: Path) -> list[Evidence]:
    text = _read_text(path)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [
            _evidence_for_chunk(path, start_line, end_line, content)
            for start_line, end_line, content in _ingestible_chunks(text)
        ]

    if _looks_like_benchmark(data):
        return [_benchmark_evidence(path, data)]
    if isinstance(data, dict) and any(key in data for key in ("agent_traces", "reviews", "hypotheses")):
        return _run_state_evidence(path, data)
    return [_json_summary_evidence(path, data)]


def _looks_like_benchmark(data: object) -> bool:
    return isinstance(data, dict) and (
        {"baseline_metrics", "candidate_metrics"} <= set(data)
        or {"name", "deltas"} <= set(data)
    )


def _benchmark_evidence(path: Path, data: dict[str, object]) -> Evidence:
    source = _source_for(path)
    name = str(data.get("name", path.stem))
    fragments = [f"Benchmark {name}."]
    for label in ("baseline_metrics", "candidate_metrics", "deltas"):
        metrics = data.get(label, {})
        if isinstance(metrics, dict):
            rendered = ", ".join(f"{key}={value}" for key, value in sorted(metrics.items()))
            if rendered:
                fragments.append(f"{label}: {rendered}.")
    if "success" in data:
        fragments.append(f"success={data['success']}.")
    notes = data.get("notes", [])
    if isinstance(notes, list):
        fragments.extend(str(note) for note in notes)
    elif notes:
        fragments.append(str(notes))
    content = " ".join(fragments)
    return Evidence(
        id=stable_id("ev", f"{source}:benchmark:{content}"),
        kind="benchmark_result",
        source=source,
        content=content,
        notes="structured benchmark result",
        metadata={
            "path": source,
            "extension": ".json",
            "parser": "benchmark_json",
            "citation": f"{source}:benchmark",
        },
    )


def _run_state_evidence(path: Path, data: dict[str, object]) -> list[Evidence]:
    source = _source_for(path)
    evidence: list[Evidence] = []
    traces = data.get("agent_traces", [])
    if isinstance(traces, list):
        for index, trace in enumerate(traces, start=1):
            if not isinstance(trace, dict):
                continue
            trace_id = str(trace.get("id", f"trace-{index}"))
            content = " ".join(
                str(part)
                for part in [
                    trace.get("agent", ""),
                    trace.get("action", ""),
                    trace.get("notes", ""),
                    " ".join(str(item) for item in trace.get("output_refs", []) or []),
                ]
                if part
            )
            if content:
                evidence.append(
                    Evidence(
                        id=stable_id("ev", f"{source}:agent_trace:{trace_id}:{content}"),
                        kind="run_state_trace",
                        source=source,
                        content=content,
                        notes=f"agent trace {trace_id}",
                        metadata={
                            "path": source,
                            "extension": ".json",
                            "parser": "run_state_json",
                            "trace_id": trace_id,
                            "citation": f"{source}:agent_traces[{index - 1}]",
                        },
                    )
                )
    reviews = data.get("reviews", [])
    if isinstance(reviews, list):
        for index, review in enumerate(reviews, start=1):
            if not isinstance(review, dict):
                continue
            review_id = str(review.get("id", f"review-{index}"))
            findings = review.get("findings", [])
            content = " ".join(
                str(part)
                for part in [
                    review.get("hypothesis_id", ""),
                    review.get("decision", ""),
                    " ".join(str(item) for item in findings if item) if isinstance(findings, list) else findings,
                ]
                if part
            )
            if content:
                evidence.append(
                    Evidence(
                        id=stable_id("ev", f"{source}:review:{review_id}:{content}"),
                        kind="run_state_review",
                        source=source,
                        content=content,
                        notes=f"review {review_id}",
                        metadata={
                            "path": source,
                            "extension": ".json",
                            "parser": "run_state_json",
                            "review_id": review_id,
                            "citation": f"{source}:reviews[{index - 1}]",
                        },
                    )
                )
    if evidence:
        return evidence
    return [_json_summary_evidence(path, data)]


def _json_summary_evidence(path: Path, data: object) -> Evidence:
    source = _source_for(path)
    content = json.dumps(data, sort_keys=True)[:2000]
    return Evidence(
        id=stable_id("ev", f"{source}:json:{content}"),
        kind="json_source",
        source=source,
        content=content,
        notes="structured json summary",
        metadata={
            "path": source,
            "extension": ".json",
            "parser": "json_summary",
            "citation": f"{source}:json",
        },
    )


def _unique_evidence(evidence: Iterable[Evidence]) -> list[Evidence]:
    by_id: dict[str, Evidence] = {}
    for item in evidence:
        by_id.setdefault(item.id, item)
    return list(by_id.values())


def merge_evidence(*groups: Iterable[Evidence]) -> list[Evidence]:
    merged: list[Evidence] = []
    for group in groups:
        merged.extend(group)
    return _unique_evidence(merged)
