from __future__ import annotations

import codecs
import json
import ipaddress
import socket
import threading
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from code_scientist.evidence import SKIP_DIRS, TEXT_EXTENSIONS, _read_text, _tokens
from code_scientist.models import AgentToolCall, Evidence, ToolBudgetState, stable_id
from code_scientist.safety import SafetyPolicy, review_evidence_safety


class ToolSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolSearchResult:
    query: str
    evidence: list[Evidence]
    blocked_count: int = 0
    blocked_reasons: list[str] | None = None

    @property
    def evidence_refs(self) -> list[str]:
        return [item.id for item in self.evidence]


@dataclass(frozen=True)
class AgentRetrievalRequest:
    tool: str
    query: str
    rationale: str
    source_ref: str = ""


class AgentRetrievalSession:
    """Thread-safe governed executor for agent-originated retrieval requests."""

    def __init__(
        self,
        evidence_store,
        budget_limit: int,
        executors: dict[str, Callable[[str], ToolSearchResult]],
        *,
        budget_used: int = 0,
        safety_policies: list[SafetyPolicy] | None = None,
        seen_requests: list[tuple[str, str]] | None = None,
    ) -> None:
        self.evidence_store = evidence_store
        self.executors = dict(executors)
        self.safety_policies = list(safety_policies or [])
        self._limit = max(int(budget_limit), 0)
        self._used = min(max(int(budget_used), 0), self._limit)
        self._lock = threading.Lock()
        self._seen_requests: set[tuple[str, str]] = {
            (tool, _normalize_agent_query(query).lower())
            for tool, query in (seen_requests or [])
            if tool and _normalize_agent_query(query)
        }

    @property
    def available_tools(self) -> list[str]:
        return sorted(self.executors)

    def budget_state(self) -> ToolBudgetState:
        with self._lock:
            return ToolBudgetState(limit=self._limit, used=self._used)

    def execute(
        self,
        requests: list[AgentRetrievalRequest],
        *,
        cycle: int,
        agent: str,
        task_id: str,
        executor_overrides: dict[str, Callable[[str], ToolSearchResult]] | None = None,
    ) -> tuple[list[Evidence], list[AgentToolCall]]:
        gathered: list[Evidence] = []
        calls: list[AgentToolCall] = []
        for index, request in enumerate(requests):
            cleaned_query = _normalize_agent_query(request.query)
            cleaned_source_ref = _normalize_source_ref(request.source_ref)
            executor = (executor_overrides or {}).get(request.tool) or self.executors.get(request.tool)
            is_reference_fetch = request.tool in {
                "web_document_fetch",
                "literature_full_text_fetch",
            }
            executor_input = cleaned_source_ref if is_reference_fetch else cleaned_query
            request_key = (request.tool, executor_input.lower())
            with self._lock:
                remaining = max(self._limit - self._used, 0)
                if executor is None:
                    calls.append(
                        self._call_record(
                            request,
                            cleaned_query,
                            cycle,
                            agent,
                            task_id,
                            index,
                            status="tool_unavailable",
                            budget_before=remaining,
                            budget_after=remaining,
                            error=f"Tool is not enabled for this run: {request.tool}",
                        )
                    )
                    continue
                if is_reference_fetch and not cleaned_source_ref:
                    calls.append(
                        self._call_record(
                            request,
                            cleaned_query,
                            cycle,
                            agent,
                            task_id,
                            index,
                            status="invalid_source_ref",
                            budget_before=remaining,
                            budget_after=remaining,
                            error="Reference-bound fetch requires an observed evidence source_ref.",
                        )
                    )
                    continue
                if not is_reference_fetch and not cleaned_query:
                    calls.append(
                        self._call_record(
                            request,
                            cleaned_query,
                            cycle,
                            agent,
                            task_id,
                            index,
                            status="invalid_query",
                            budget_before=remaining,
                            budget_after=remaining,
                            error="Agent retrieval query was blank after normalization.",
                        )
                    )
                    continue
                if request_key in self._seen_requests:
                    calls.append(
                        self._call_record(
                            request,
                            cleaned_query,
                            cycle,
                            agent,
                            task_id,
                            index,
                            status="duplicate_query",
                            budget_before=remaining,
                            budget_after=remaining,
                        )
                    )
                    continue
                if remaining <= 0:
                    calls.append(
                        self._call_record(
                            request,
                            cleaned_query,
                            cycle,
                            agent,
                            task_id,
                            index,
                            status="budget_exhausted",
                            budget_before=0,
                            budget_after=0,
                        )
                    )
                    continue
                self._seen_requests.add(request_key)
                self._used += 1
                budget_before = remaining
                budget_after = max(self._limit - self._used, 0)

            try:
                result = executor(executor_input)
            except Exception as exc:
                calls.append(
                    self._call_record(
                        request,
                        cleaned_query,
                        cycle,
                        agent,
                        task_id,
                        index,
                        status="failed",
                        budget_before=budget_before,
                        budget_after=budget_after,
                        error=str(exc),
                    )
                )
                continue

            safe_evidence: list[Evidence] = []
            blocked_reasons = list(result.blocked_reasons or [])
            for item in result.evidence:
                decision = review_evidence_safety(item, safety_policies=self.safety_policies)
                if decision.allowed:
                    safe_evidence.append(item)
                else:
                    blocked_reasons.extend(decision.flags)
            safe_evidence = _unique_evidence_by_id(safe_evidence)
            with self._lock:
                new_evidence = self.evidence_store.add_many(safe_evidence)
            gathered.extend(new_evidence)
            status = "completed" if new_evidence else ("blocked" if blocked_reasons else "no_results")
            calls.append(
                self._call_record(
                    request,
                    cleaned_query,
                    cycle,
                    agent,
                    task_id,
                    index,
                    status=status,
                    budget_before=budget_before,
                    budget_after=budget_after,
                    evidence_refs=[item.id for item in new_evidence],
                    blocked_reasons=_unique(blocked_reasons),
                )
            )
        return _unique_evidence_by_id(gathered), calls

    @staticmethod
    def _call_record(
        request: AgentRetrievalRequest,
        cleaned_query: str,
        cycle: int,
        agent: str,
        task_id: str,
        index: int,
        *,
        status: str,
        budget_before: int,
        budget_after: int,
        evidence_refs: list[str] | None = None,
        blocked_reasons: list[str] | None = None,
        error: str = "",
    ) -> AgentToolCall:
        source_ref = _normalize_source_ref(request.source_ref)
        identity = (
            f"{cycle}:{task_id}:{agent}:{request.tool}:{cleaned_query}:"
            f"{source_ref}:{index}:{status}"
        )
        return AgentToolCall(
            id=stable_id("tool-call", identity),
            cycle=cycle,
            task_id=task_id,
            agent=agent,
            tool=request.tool,
            query=cleaned_query,
            rationale=request.rationale,
            status=status,
            source_ref=source_ref,
            evidence_refs=list(evidence_refs or []),
            blocked_reasons=list(blocked_reasons or []),
            budget_before=budget_before,
            budget_after=budget_after,
            error=error,
        )


def _normalize_agent_query(value: str, max_chars: int = 400) -> str:
    cleaned = " ".join(
        "".join(character if character.isprintable() else " " for character in str(value)).split()
    )
    return cleaned[:max_chars].strip()


def _normalize_source_ref(value: str, max_chars: int = 160) -> str:
    cleaned = "".join(character for character in str(value).strip() if character.isalnum() or character in "-_")
    return cleaned[:max_chars]


def _open_url(request: Request, timeout_seconds: float, _allowed_domains: list[str] | None):
    return urlopen(request, timeout=timeout_seconds)


class _PublicOnlyRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_domains: list[str] | None) -> None:
        super().__init__()
        self.allowed_domains = allowed_domains

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_public_http_url(newurl, self.allowed_domains)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_public_url(
    request: Request,
    timeout_seconds: float,
    allowed_domains: list[str] | None,
):
    _assert_public_http_url(request.full_url, allowed_domains)
    response = build_opener(_PublicOnlyRedirectHandler(allowed_domains)).open(
        request,
        timeout=timeout_seconds,
    )
    _assert_public_http_url(response.geturl(), allowed_domains)
    return response


def _assert_public_http_url(url: str, allowed_domains: list[str] | None = None) -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ToolSafetyError("Agent fetch URL must use public HTTP or HTTPS.")
    if parsed.username or parsed.password:
        raise ToolSafetyError("Agent fetch URLs cannot contain credentials.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ToolSafetyError("Agent fetch URL has an invalid port.") from exc
    if port not in {None, 80, 443}:
        raise ToolSafetyError("Agent fetch URL port is not allowed.")

    hostname = parsed.hostname.rstrip(".").lower()
    normalized_domains = [
        domain.strip().rstrip(".").lower()
        for domain in (allowed_domains or [])
        if domain.strip()
    ]
    if normalized_domains and not any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in normalized_domains
    ):
        raise ToolSafetyError(f"Agent fetch domain is not researcher-approved: {hostname}")

    try:
        addresses = {
            record[4][0]
            for record in socket.getaddrinfo(
                hostname,
                port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as exc:
        raise ToolSafetyError(f"Agent fetch domain could not be resolved: {hostname}") from exc
    if not addresses:
        raise ToolSafetyError(f"Agent fetch domain did not resolve: {hostname}")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ToolSafetyError(
                f"Agent fetch resolved to a non-public address: {hostname} -> {address}"
            )


def _unique_evidence_by_id(evidence: list[Evidence]) -> list[Evidence]:
    unique: list[Evidence] = []
    seen: set[str] = set()
    for item in evidence:
        if item.id in seen:
            continue
        seen.add(item.id)
        unique.append(item)
    return unique


@dataclass(frozen=True)
class _FetchedWebDocument:
    evidence: Evidence
    links: list[str]


@dataclass(frozen=True)
class _ExtractedText:
    text: str
    sections: list["_TextSection"]


@dataclass(frozen=True)
class _RobotsPolicy:
    rules: tuple[tuple[str, bool], ...] = ()

    def allows(self, url: str) -> bool:
        path = urlparse(url).path or "/"
        matched_rule: tuple[str, bool] | None = None
        for rule_path, allow in self.rules:
            if not rule_path or not path.startswith(rule_path):
                continue
            if matched_rule is None or len(rule_path) > len(matched_rule[0]):
                matched_rule = (rule_path, allow)
        return matched_rule[1] if matched_rule else True


@dataclass(frozen=True)
class _TextSection:
    path: tuple[str, ...]
    start_char: int
    end_char: int


@dataclass(frozen=True)
class _TextSpanChunk:
    index: int
    start_char: int
    end_char: int
    content: str
    section: _TextSection | None = None


class LocalRepositorySearchTool:
    name = "local_repository_search"

    def __init__(self, allowed_roots: list[str | Path]) -> None:
        if not allowed_roots:
            raise ToolSafetyError("At least one allowed root is required for local repository search.")
        self.allowed_roots = [Path(root).resolve() for root in allowed_roots]

    def search(self, root: str | Path, query: str, limit: int = 10) -> ToolSearchResult:
        resolved_root = Path(root).resolve()
        if not _is_within_allowed_roots(resolved_root, self.allowed_roots):
            raise ToolSafetyError(f"Search root is not allowed: {resolved_root}")
        if limit <= 0:
            return ToolSearchResult(query=query, evidence=[])

        query_tokens = set(_tokens(query))
        if not query_tokens:
            return ToolSearchResult(query=query, evidence=[])

        candidates: list[tuple[int, str, int, Evidence]] = []
        blocked_reasons: list[str] = []
        for file_path in sorted(resolved_root.rglob("*")):
            if not _should_search_file(file_path):
                continue
            file_candidates: list[tuple[int, str, int, Evidence]] = []
            for line_number, line in _matching_lines(file_path, query_tokens):
                evidence = _evidence_for_line(file_path, resolved_root, query, line_number, line)
                decision = review_evidence_safety(evidence)
                if not decision.allowed:
                    blocked_reasons.extend(decision.flags)
                    continue
                score = len(query_tokens & set(_tokens(line)))
                file_candidates.append((score, str(file_path), line_number, evidence))
            if file_candidates:
                file_candidates.sort(key=lambda item: (-item[0], item[2], item[3].id))
                candidates.append(file_candidates[0])

        candidates.sort(key=lambda item: (-item[0], item[1], item[2], item[3].id))
        evidence = [item[3] for item in candidates[:limit]]
        unique_blocked_reasons = _unique(blocked_reasons)
        return ToolSearchResult(
            query=query,
            evidence=evidence,
            blocked_count=len(blocked_reasons),
            blocked_reasons=unique_blocked_reasons,
        )


class WebEvidenceTool:
    name = "web_evidence_fetch"

    def __init__(self, timeout_seconds: float = 10, max_bytes: int = 200_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def fetch(self, url: str) -> Evidence:
        return self.fetch_with_links(url).evidence

    def fetch_with_links(self, url: str) -> _FetchedWebDocument:
        cleaned_url = url.strip()
        parsed = urlparse(cleaned_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ToolSafetyError(f"Web evidence URL must be HTTP(S): {url}")

        request = Request(
            cleaned_url,
            headers={"User-Agent": "code-scientist/0.1 evidence-fetch"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read(self.max_bytes)
            content_type = response.headers.get("content-type", "")

        text = raw.decode(_charset_from_content_type(content_type), errors="replace")
        is_html = _looks_like_html(content_type, text)
        extracted = _html_to_text_with_sections(text) if is_html else _ExtractedText(_normalize_space(text), [])
        content = extracted.text
        if not content:
            raise ToolSafetyError(f"Fetched web evidence was empty: {cleaned_url}")

        stored_content = content[:6000]
        sections = _clip_text_sections(extracted.sections, len(stored_content))
        metadata = {
            "tool": self.name,
            "url": cleaned_url,
            "citation": cleaned_url,
            "content_type": content_type,
            "span_count": str(len(_span_chunks_for_content(stored_content, sections))),
        }
        _add_section_metadata(metadata, sections)
        evidence = Evidence(
            id=stable_id("ev", f"{self.name}:{cleaned_url}:{content[:500]}"),
            kind="web_document",
            source=cleaned_url,
            content=stored_content,
            notes=f"web evidence fetched from `{cleaned_url}`",
            metadata=metadata,
        )
        return _FetchedWebDocument(
            evidence=evidence,
            links=_links_from_html(text, cleaned_url) if is_html else [],
        )


class WebSearchTool:
    name = "web_search"

    def __init__(
        self,
        base_url: str = "https://html.duckduckgo.com/html/",
        timeout_seconds: float = 10,
        max_bytes: int = 500_000,
        extra_query_params: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.extra_query_params = dict(extra_query_params or {})

    def search(
        self,
        query: str,
        limit: int = 5,
        fetch_documents: bool = False,
        fetch_crawl_depth: int = 0,
        max_crawl_pages_per_result: int = 5,
    ) -> ToolSearchResult:
        cleaned_query = query.strip()
        if not cleaned_query or limit <= 0:
            return ToolSearchResult(query=cleaned_query, evidence=[])
        bounded_crawl_depth = max(0, fetch_crawl_depth)
        page_limit = max(1, max_crawl_pages_per_result)

        query_params = {"q": cleaned_query, **self.extra_query_params}
        search_url = f"{self.base_url}?{urlencode(query_params)}"
        request = Request(
            search_url,
            headers={"User-Agent": "code-scientist/0.1 web-search"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read(self.max_bytes)
            content_type = response.headers.get("content-type", "")

        text = raw.decode(_charset_from_content_type(content_type), errors="replace")
        raw_results = _web_search_results_from_response(text, content_type)
        evidence: list[Evidence] = []
        blocked_reasons: list[str] = []
        for rank, result in enumerate(raw_results[:limit], start=1):
            item = _evidence_for_web_search_result(
                query=cleaned_query,
                result=result,
                rank=rank,
                search_url=search_url,
            )
            decision = review_evidence_safety(item)
            if not decision.allowed:
                blocked_reasons.extend(decision.flags)
                continue
            evidence.append(item)
            if fetch_documents:
                try:
                    fetched_document = _fetch_web_search_document_with_links(
                        search_result=item,
                        timeout_seconds=self.timeout_seconds,
                        max_bytes=self.max_bytes,
                        crawl_root_url=item.source if bounded_crawl_depth else "",
                        crawl_depth=0,
                    )
                except Exception:
                    continue
                if fetched_document is None:
                    continue
                document = fetched_document.evidence
                document_decision = review_evidence_safety(document)
                if not document_decision.allowed:
                    blocked_reasons.extend(document_decision.flags)
                    continue
                evidence.append(document)
                for span in _web_document_spans(
                    document,
                    kind="web_search_document_span",
                    tool="web_search_document_span",
                ):
                    span_decision = review_evidence_safety(span)
                    if not span_decision.allowed:
                        blocked_reasons.extend(span_decision.flags)
                        continue
                    evidence.append(span)
                if bounded_crawl_depth:
                    crawled = _crawl_web_search_result_documents(
                        search_result=item,
                        root_document=document,
                        links=fetched_document.links,
                        crawl_depth=bounded_crawl_depth,
                        page_limit=page_limit,
                        timeout_seconds=self.timeout_seconds,
                        max_bytes=self.max_bytes,
                    )
                    for crawled_document in crawled:
                        crawled_decision = review_evidence_safety(crawled_document)
                        if not crawled_decision.allowed:
                            blocked_reasons.extend(crawled_decision.flags)
                            continue
                        evidence.append(crawled_document)
                        for span in _web_document_spans(
                            crawled_document,
                            kind="web_search_document_span",
                            tool="web_search_document_span",
                        ):
                            span_decision = review_evidence_safety(span)
                            if not span_decision.allowed:
                                blocked_reasons.extend(span_decision.flags)
                                continue
                            evidence.append(span)
        return ToolSearchResult(
            query=cleaned_query,
            evidence=evidence,
            blocked_count=len(blocked_reasons),
            blocked_reasons=_unique(blocked_reasons),
        )


class OpenAlexLiteratureSearchTool:
    name = "openalex_literature_search"

    def __init__(
        self,
        base_url: str = "https://api.openalex.org/works",
        timeout_seconds: float = 10,
        max_bytes: int = 10_000_000,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def search(
        self,
        query: str,
        limit: int = 5,
        include_full_text: bool = False,
        safety_policies: list[SafetyPolicy] | None = None,
    ) -> ToolSearchResult:
        cleaned_query = query.strip()
        if not cleaned_query or limit <= 0:
            return ToolSearchResult(query=cleaned_query, evidence=[])

        search_url = f"{self.base_url}?{urlencode({'search': cleaned_query, 'per-page': str(limit)})}"
        request = Request(
            search_url,
            headers={"User-Agent": "code-scientist/0.1 literature-search"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = response.read(self.max_bytes)

        data = json.loads(payload.decode("utf-8", errors="replace"))
        raw_results = data.get("results", []) if isinstance(data, dict) else []
        evidence: list[Evidence] = []
        blocked_reasons: list[str] = []
        for raw_result in raw_results[:limit]:
            if not isinstance(raw_result, dict):
                continue
            item = _evidence_for_openalex_work(cleaned_query, raw_result)
            decision = review_evidence_safety(item, safety_policies=safety_policies)
            if not decision.allowed:
                blocked_reasons.extend(decision.flags)
                continue
            evidence.append(item)
            if include_full_text:
                full_text_url = _openalex_full_text_url(raw_result)
                if not full_text_url:
                    continue
                try:
                    full_text = _fetch_openalex_full_text(
                        query=cleaned_query,
                        work=raw_result,
                        url=full_text_url,
                        timeout_seconds=self.timeout_seconds,
                        max_bytes=self.max_bytes,
                    )
                except Exception:
                    continue
                if full_text is None:
                    continue
                full_text_decision = review_evidence_safety(full_text, safety_policies=safety_policies)
                if not full_text_decision.allowed:
                    blocked_reasons.extend(full_text_decision.flags)
                    continue
                evidence.append(full_text)
                for span in _openalex_full_text_spans(full_text):
                    span_decision = review_evidence_safety(span, safety_policies=safety_policies)
                    if not span_decision.allowed:
                        blocked_reasons.extend(span_decision.flags)
                        continue
                    evidence.append(span)

        return ToolSearchResult(
            query=cleaned_query,
            evidence=evidence,
            blocked_count=len(blocked_reasons),
            blocked_reasons=_unique(blocked_reasons),
        )


def collect_local_repo_search_evidence(
    query: str,
    roots: list[str | Path],
    limit_per_root: int = 10,
) -> list[Evidence]:
    if not roots:
        return []
    tool = LocalRepositorySearchTool(allowed_roots=roots)
    evidence: list[Evidence] = []
    seen: set[str] = set()
    for root in roots:
        result = tool.search(root, query, limit=limit_per_root)
        for item in result.evidence:
            if item.id not in seen:
                seen.add(item.id)
                evidence.append(item)
    return evidence


def collect_literature_search_evidence(
    queries: list[str],
    limit_per_query: int = 5,
    include_full_text: bool = False,
    safety_policies: list[SafetyPolicy] | None = None,
) -> list[Evidence]:
    if not queries:
        return []
    tool = OpenAlexLiteratureSearchTool()
    evidence: list[Evidence] = []
    seen: set[str] = set()
    for query in queries:
        cleaned_query = query.strip()
        if not cleaned_query:
            continue
        result = tool.search(
            cleaned_query,
            limit=limit_per_query,
            include_full_text=include_full_text,
            safety_policies=safety_policies,
        )
        for item in result.evidence:
            if item.id not in seen:
                seen.add(item.id)
                evidence.append(item)
    return evidence


def collect_web_search_evidence(
    queries: list[str],
    limit_per_query: int = 5,
    fetch_documents: bool = False,
    fetch_crawl_depth: int = 0,
) -> list[Evidence]:
    if not queries:
        return []
    tool = WebSearchTool()
    evidence: list[Evidence] = []
    seen: set[str] = set()
    for query in queries:
        cleaned_query = query.strip()
        if not cleaned_query:
            continue
        result = tool.search(
            cleaned_query,
            limit=limit_per_query,
            fetch_documents=fetch_documents,
            fetch_crawl_depth=fetch_crawl_depth,
        )
        for item in result.evidence:
            if item.id not in seen:
                seen.add(item.id)
                evidence.append(item)
    return evidence


def collect_web_evidence(
    urls: list[str],
    timeout_seconds: float = 10,
    crawl_depth: int = 0,
    max_crawl_pages_per_root: int = 5,
) -> list[Evidence]:
    if not urls:
        return []
    tool = WebEvidenceTool(timeout_seconds=timeout_seconds)
    bounded_depth = max(0, crawl_depth)
    page_limit = max(1, max_crawl_pages_per_root)
    evidence: list[Evidence] = []
    seen: set[str] = set()
    for url in urls:
        root_url = url.strip()
        if not root_url:
            continue
        frontier: list[tuple[str, str, int]] = [(root_url, "", 0)]
        seen_urls: set[str] = set()
        robots_cache: dict[str, _RobotsPolicy] = {}
        fetched_count = 0
        while frontier and fetched_count < page_limit:
            current_url, parent_url, depth = frontier.pop(0)
            if current_url in seen_urls:
                continue
            seen_urls.add(current_url)

            fetched = tool.fetch_with_links(current_url)
            fetched_count += 1
            item = (
                _with_crawl_metadata(fetched.evidence, root_url=root_url, parent_url=parent_url, depth=depth)
                if bounded_depth
                else fetched.evidence
            )
            if item.id not in seen:
                seen.add(item.id)
                evidence.append(item)
            for span in _web_document_spans(item, kind="web_document_span", tool="web_document_span"):
                if span.id not in seen:
                    seen.add(span.id)
                    evidence.append(span)

            if depth >= bounded_depth:
                continue
            for link in fetched.links:
                if (
                    link not in seen_urls
                    and _same_origin(link, root_url)
                    and _robots_allows_crawl(link, root_url, timeout_seconds, tool.max_bytes, robots_cache)
                ):
                    frontier.append((link, item.source, depth + 1))
    return evidence


def build_agent_retrieval_executors(
    *,
    evidence_store=None,
    repo_roots: list[str | Path] | None = None,
    enable_web_search: bool = False,
    enable_literature_search: bool = False,
    fetch_allowed_domains: list[str] | None = None,
    safety_policies: list[SafetyPolicy] | None = None,
) -> dict[str, Callable[[str], ToolSearchResult]]:
    """Build the closed, researcher-enabled tool set available to agent planners.

    Planner-selected arbitrary URLs, roots, crawling, full text, and shell commands
    are intentionally excluded. Those high-cost parameters remain researcher-owned.
    """
    executors: dict[str, Callable[[str], ToolSearchResult]] = {}
    roots = [Path(root) for root in (repo_roots or [])]
    if roots:
        repo_tool = LocalRepositorySearchTool(allowed_roots=roots)

        def search_repositories(query: str) -> ToolSearchResult:
            evidence: list[Evidence] = []
            blocked_reasons: list[str] = []
            for root in roots:
                result = repo_tool.search(root, query, limit=5)
                evidence.extend(result.evidence)
                blocked_reasons.extend(result.blocked_reasons or [])
            return ToolSearchResult(
                query=query,
                evidence=_unique_evidence_by_id(evidence),
                blocked_count=len(blocked_reasons),
                blocked_reasons=_unique(blocked_reasons),
            )

        executors["repo_search"] = search_repositories
    if enable_web_search:
        web_tool = WebSearchTool()
        executors["web_search"] = lambda query: web_tool.search(
            query,
            limit=5,
            fetch_documents=False,
            fetch_crawl_depth=0,
        )
        if evidence_store is not None:

            def fetch_web_document(source_ref: str) -> ToolSearchResult:
                search_result = evidence_store.get(source_ref)
                if search_result is None or search_result.kind != "web_search_result":
                    raise ToolSafetyError(
                        "web_document_fetch source_ref must identify an observed web search result."
                    )
                fetched = _fetch_web_search_document_with_links(
                    search_result=search_result,
                    timeout_seconds=web_tool.timeout_seconds,
                    max_bytes=web_tool.max_bytes,
                    public_only=True,
                    allowed_domains=fetch_allowed_domains,
                )
                if fetched is None:
                    return ToolSearchResult(query=source_ref, evidence=[])
                decision = review_evidence_safety(
                    fetched.evidence,
                    safety_policies=safety_policies,
                )
                if not decision.allowed:
                    return ToolSearchResult(
                        query=source_ref,
                        evidence=[],
                        blocked_count=1,
                        blocked_reasons=decision.flags,
                    )
                return ToolSearchResult(
                    query=source_ref,
                    evidence=[
                        fetched.evidence,
                        *_web_document_spans(
                            fetched.evidence,
                            kind="web_search_document_span",
                            tool="web_search_document_span",
                        ),
                    ],
                )

            executors["web_document_fetch"] = fetch_web_document
    if enable_literature_search:
        literature_tool = OpenAlexLiteratureSearchTool()
        executors["literature_search"] = lambda query: literature_tool.search(
            query,
            limit=5,
            include_full_text=False,
            safety_policies=safety_policies,
        )
        if evidence_store is not None:

            def fetch_literature_full_text(source_ref: str) -> ToolSearchResult:
                search_result = evidence_store.get(source_ref)
                if search_result is None or search_result.kind != "literature_search_result":
                    raise ToolSafetyError(
                        "literature_full_text_fetch source_ref must identify an observed "
                        "literature search result."
                    )
                full_text_url = search_result.metadata.get("full_text_url", "").strip()
                if not full_text_url:
                    return ToolSearchResult(query=source_ref, evidence=[])
                work = {
                    "id": search_result.metadata.get("openalex_id", ""),
                    "display_name": search_result.metadata.get("title", ""),
                    "doi": search_result.metadata.get("doi", ""),
                }
                full_text = _fetch_openalex_full_text(
                    query=search_result.metadata.get("query", ""),
                    work=work,
                    url=full_text_url,
                    timeout_seconds=literature_tool.timeout_seconds,
                    max_bytes=literature_tool.max_bytes,
                    public_only=True,
                    allowed_domains=fetch_allowed_domains,
                )
                if full_text is None:
                    return ToolSearchResult(query=source_ref, evidence=[])
                decision = review_evidence_safety(full_text, safety_policies=safety_policies)
                if not decision.allowed:
                    return ToolSearchResult(
                        query=source_ref,
                        evidence=[],
                        blocked_count=1,
                        blocked_reasons=decision.flags,
                    )
                return ToolSearchResult(
                    query=source_ref,
                    evidence=[full_text, *_openalex_full_text_spans(full_text)],
                )

            executors["literature_full_text_fetch"] = fetch_literature_full_text
    return executors


def _is_within_allowed_roots(path: Path, allowed_roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in allowed_roots)


def _should_search_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS


def _matching_lines(path: Path, query_tokens: set[str]) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(_read_text(path).splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        line_tokens = set(_tokens(line))
        if query_tokens & line_tokens:
            matches.append((line_number, line))
    return matches


def _evidence_for_line(
    path: Path,
    root: Path,
    query: str,
    line_number: int,
    line: str,
) -> Evidence:
    source = str(path)
    relative_path = str(path.relative_to(root))
    citation = f"{source}:line {line_number}"
    return Evidence(
        id=stable_id("ev", f"{LocalRepositorySearchTool.name}:{source}:{line_number}:{query}:{line}"),
        kind="tool_result_repo_search",
        source=source,
        content=line,
        notes=f"local repository search hit for `{query}` at {relative_path}:{line_number}",
        metadata={
            "tool": LocalRepositorySearchTool.name,
            "query": query,
            "path": source,
            "relative_path": relative_path,
            "start_line": str(line_number),
            "end_line": str(line_number),
            "citation": citation,
            "safety_allowed": "true",
        },
    )


def _evidence_for_openalex_work(query: str, work: dict) -> Evidence:
    openalex_id = _metadata_text(work.get("id"))
    title = _metadata_text(work.get("display_name") or work.get("title"), "Untitled literature result")
    publication_year = _metadata_text(work.get("publication_year"))
    doi = _metadata_text(work.get("doi"))
    landing_page_url = _openalex_landing_page_url(work)
    abstract = _openalex_abstract_text(work.get("abstract_inverted_index"))
    source = landing_page_url or doi or openalex_id or "openalex:unknown-work"
    citation = doi or landing_page_url or openalex_id or source
    full_text_url = _openalex_full_text_url(work)
    content_parts = [title]
    if publication_year:
        content_parts.append(f"Publication year: {publication_year}")
    if abstract:
        content_parts.append(abstract)
    content = ". ".join(content_parts)
    return Evidence(
        id=stable_id("ev", f"{OpenAlexLiteratureSearchTool.name}:{query}:{openalex_id}:{title}:{citation}"),
        kind="literature_search_result",
        source=source,
        content=content[:6000],
        notes=f"OpenAlex literature search result for `{query}`.",
        metadata={
            "tool": OpenAlexLiteratureSearchTool.name,
            "query": query,
            "title": title,
            "publication_year": publication_year,
            "doi": doi,
            "openalex_id": openalex_id,
            "full_text_url": full_text_url,
            "citation": citation,
        },
    )


@dataclass(frozen=True)
class _ParsedWebSearchResult:
    title: str
    url: str
    snippet: str


def _evidence_for_web_search_result(
    query: str,
    result: _ParsedWebSearchResult,
    rank: int,
    search_url: str,
) -> Evidence:
    content = _normalize_space(". ".join(part for part in [result.title, result.snippet] if part))
    return Evidence(
        id=stable_id("ev", f"{WebSearchTool.name}:{query}:{rank}:{result.url}:{content[:500]}"),
        kind="web_search_result",
        source=result.url,
        content=content[:4000],
        notes=f"web search result {rank} for `{query}`.",
        metadata={
            "tool": WebSearchTool.name,
            "query": query,
            "title": result.title,
            "snippet": result.snippet,
            "result_rank": str(rank),
            "search_url": search_url,
            "citation": result.url,
        },
    )


def _fetch_web_search_document(
    search_result: Evidence,
    timeout_seconds: float,
    max_bytes: int,
) -> Evidence | None:
    fetched = _fetch_web_search_document_with_links(
        search_result=search_result,
        timeout_seconds=timeout_seconds,
        max_bytes=max_bytes,
    )
    return fetched.evidence if fetched else None


def _fetch_web_search_document_with_links(
    search_result: Evidence,
    timeout_seconds: float,
    max_bytes: int,
    *,
    url: str | None = None,
    parent_document: Evidence | None = None,
    crawl_root_url: str = "",
    crawl_depth: int = 0,
    public_only: bool = False,
    allowed_domains: list[str] | None = None,
) -> _FetchedWebDocument | None:
    cleaned_url = (url or search_result.source).strip()
    parsed = urlparse(cleaned_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    request = Request(
        cleaned_url,
        headers={"User-Agent": "code-scientist/0.1 web-search-document-fetch"},
    )
    opener = _open_public_url if public_only else _open_url
    with opener(request, timeout_seconds, allowed_domains) as response:
        raw = response.read(max_bytes)
        content_type = response.headers.get("content-type", "")

    text = raw.decode(_charset_from_content_type(content_type), errors="replace")
    extracted = _document_bytes_to_text_with_sections(raw, content_type, cleaned_url)
    content = extracted.text
    if not content:
        return None

    stored_content = content[:8000]
    sections = _clip_text_sections(extracted.sections, len(stored_content))
    query = search_result.metadata.get("query", "")
    result_rank = search_result.metadata.get("result_rank", "")
    title = search_result.metadata.get("title", "")
    citation = cleaned_url if parent_document else search_result.metadata.get("citation") or cleaned_url
    tool_name = "web_search_document_crawl_fetch" if parent_document else "web_search_document_fetch"
    metadata = {
        "tool": tool_name,
        "parent_evidence_id": parent_document.id if parent_document else search_result.id,
        "parent_search_result_id": search_result.id,
        "query": query,
        "result_rank": result_rank,
        "title": title,
        "citation": citation,
        "content_type": content_type,
        "span_count": str(len(_span_chunks_for_content(stored_content, sections))),
    }
    if crawl_root_url:
        metadata["crawl_root_url"] = crawl_root_url
        metadata["crawl_depth"] = str(crawl_depth)
    if parent_document:
        metadata["crawl_parent_url"] = parent_document.source
    _add_section_metadata(metadata, sections)
    evidence = Evidence(
        id=stable_id("ev", f"web_search_document_fetch:{search_result.id}:{cleaned_url}:{content[:500]}"),
        kind="web_search_document",
        source=cleaned_url,
        content=stored_content,
        notes=f"web search result page fetched from `{cleaned_url}`.",
        metadata=metadata,
    )
    return _FetchedWebDocument(
        evidence=evidence,
        links=_links_from_html(text, cleaned_url) if _looks_like_html(content_type, text) else [],
    )


def _crawl_web_search_result_documents(
    search_result: Evidence,
    root_document: Evidence,
    links: list[str],
    crawl_depth: int,
    page_limit: int,
    timeout_seconds: float,
    max_bytes: int,
) -> list[Evidence]:
    documents: list[Evidence] = []
    root_url = root_document.source
    seen_urls = {root_url}
    robots_cache: dict[str, _RobotsPolicy] = {}
    frontier: list[tuple[str, Evidence, int]] = [
        (link, root_document, 1)
        for link in links
        if _same_origin(link, root_url)
        and _robots_allows_crawl(link, root_url, timeout_seconds, max_bytes, robots_cache)
    ]
    fetched_count = 1
    while frontier and fetched_count < page_limit:
        current_url, parent_document, depth = frontier.pop(0)
        if current_url in seen_urls:
            continue
        seen_urls.add(current_url)
        try:
            fetched = _fetch_web_search_document_with_links(
                search_result=search_result,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
                url=current_url,
                parent_document=parent_document,
                crawl_root_url=root_url,
                crawl_depth=depth,
            )
        except Exception:
            continue
        if fetched is None:
            continue
        fetched_count += 1
        documents.append(fetched.evidence)
        if depth >= crawl_depth:
            continue
        for link in fetched.links:
            if (
                link not in seen_urls
                and _same_origin(link, root_url)
                and _robots_allows_crawl(link, root_url, timeout_seconds, max_bytes, robots_cache)
            ):
                frontier.append((link, fetched.evidence, depth + 1))
    return documents


def _web_document_spans(document: Evidence, kind: str, tool: str) -> list[Evidence]:
    spans: list[Evidence] = []
    citation = document.metadata.get("citation") or document.source
    parent_search_result_id = (
        document.metadata.get("parent_search_result_id")
        or document.metadata.get("parent_evidence_id", "")
    )
    sections = _text_sections_from_metadata(document.metadata)
    for chunk in _span_chunks_for_content(document.content, sections):
        metadata = {
            "tool": tool,
            "parent_evidence_id": document.id,
            "span_index": str(chunk.index),
            "span_start_char": str(chunk.start_char),
            "span_end_char": str(chunk.end_char),
            "citation": f"{citation}#span-{chunk.index}",
        }
        metadata.update(_section_metadata_for_span(chunk.section))
        for key in (
            "query",
            "result_rank",
            "title",
            "url",
            "content_type",
            "crawl_root_url",
            "crawl_parent_url",
            "crawl_depth",
        ):
            value = document.metadata.get(key)
            if value:
                metadata[key] = value
        if parent_search_result_id and kind == "web_search_document_span":
            metadata["parent_search_result_id"] = parent_search_result_id
        spans.append(
            Evidence(
                id=stable_id(
                    "ev",
                    f"{tool}:{document.id}:{chunk.index}:{chunk.start_char}:{chunk.end_char}:{chunk.content[:500]}",
                ),
                kind=kind,
                source=f"{document.source}#span-{chunk.index}",
                content=chunk.content,
                notes=_span_notes("span", chunk.index, "fetched web document", chunk.section),
                metadata=metadata,
            )
        )
    return spans


def _with_crawl_metadata(document: Evidence, root_url: str, parent_url: str, depth: int) -> Evidence:
    metadata = {
        **document.metadata,
        "crawl_root_url": root_url,
        "crawl_depth": str(depth),
    }
    if parent_url:
        metadata["crawl_parent_url"] = parent_url
    return replace(document, metadata=metadata)


def _same_origin(url: str, root_url: str) -> bool:
    parsed = urlparse(url)
    root = urlparse(root_url)
    return parsed.scheme == root.scheme and parsed.netloc == root.netloc


def _robots_allows_crawl(
    url: str,
    root_url: str,
    timeout_seconds: float,
    max_bytes: int,
    cache: dict[str, _RobotsPolicy],
) -> bool:
    origin = _origin_for_url(root_url)
    if not origin:
        return True
    if origin not in cache:
        cache[origin] = _fetch_robots_policy(origin, timeout_seconds, max_bytes)
    return cache[origin].allows(url)


def _origin_for_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _fetch_robots_policy(origin: str, timeout_seconds: float, max_bytes: int) -> _RobotsPolicy:
    robots_url = f"{origin}/robots.txt"
    request = Request(
        robots_url,
        headers={"User-Agent": "code-scientist/0.1 robots-policy"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(max_bytes)
            content_type = response.headers.get("content-type", "")
    except Exception:
        return _RobotsPolicy()
    text = raw.decode(_charset_from_content_type(content_type), errors="replace")
    return _parse_robots_policy(text)


def _parse_robots_policy(text: str) -> _RobotsPolicy:
    active_agents: list[str] = []
    rules: list[tuple[str, bool]] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = line.split(":", 1)
        field_name = field.strip().lower()
        field_value = value.strip()
        if field_name == "user-agent":
            active_agents = [field_value.lower()]
            continue
        if field_name not in {"allow", "disallow"} or not _robots_group_applies(active_agents):
            continue
        if field_value:
            rules.append((field_value, field_name == "allow"))
    return _RobotsPolicy(rules=tuple(_unique_robot_rules(rules)))


def _robots_group_applies(agents: list[str]) -> bool:
    if not agents:
        return False
    return any(agent in {"*", "code-scientist", "code-scientist/0.1"} for agent in agents)


def _unique_robot_rules(rules: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    seen: set[tuple[str, bool]] = set()
    unique: list[tuple[str, bool]] = []
    for rule in rules:
        if rule not in seen:
            seen.add(rule)
            unique.append(rule)
    return unique


def _links_from_html(html: str, base_url: str) -> list[str]:
    parser = _HTMLLinkExtractor(base_url)
    parser.feed(html)
    return parser.links()


def _web_search_results_from_html(html: str) -> list[_ParsedWebSearchResult]:
    parser = _WebSearchHTMLParser()
    parser.feed(html)
    return parser.results()


def _web_search_results_from_response(text: str, content_type: str) -> list[_ParsedWebSearchResult]:
    stripped = text.lstrip()
    if "xml" in content_type.lower() or stripped.startswith("<?xml") or stripped.startswith("<rss"):
        return _web_search_results_from_rss(text)
    return _web_search_results_from_html(text)


def _web_search_results_from_rss(xml_text: str) -> list[_ParsedWebSearchResult]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    results: list[_ParsedWebSearchResult] = []
    for item in root.findall(".//item"):
        title = _normalize_space(item.findtext("title", default=""))
        url = _normalize_space(item.findtext("link", default=""))
        snippet = _normalize_space(item.findtext("description", default=""))
        parsed = urlparse(url)
        if title and parsed.scheme in {"http", "https"} and parsed.netloc:
            results.append(_ParsedWebSearchResult(title=title, url=url, snippet=snippet))
    return results


class _WebSearchHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_title_parts: list[str] = []
        self._current_snippet_parts: list[str] = []
        self._current_url = ""
        self._capture: str | None = None
        self._parsed: list[_ParsedWebSearchResult] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = {name.lower(): value or "" for name, value in attrs}
        classes = set(attributes.get("class", "").split())
        if tag.lower() == "a" and "result__a" in classes:
            self._finish_current()
            self._current_url = _clean_web_search_url(attributes.get("href", ""))
            self._capture = "title"
            return
        if "result__snippet" in classes:
            self._capture = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._capture == "title":
            self._capture = None
        elif self._capture == "snippet" and tag.lower() in {"a", "div", "span"}:
            self._capture = None

    def handle_data(self, data: str) -> None:
        if self._capture == "title":
            self._current_title_parts.append(data.strip())
        elif self._capture == "snippet":
            self._current_snippet_parts.append(data.strip())

    def results(self) -> list[_ParsedWebSearchResult]:
        self._finish_current()
        return self._parsed

    def _finish_current(self) -> None:
        title = _normalize_space(" ".join(self._current_title_parts))
        snippet = _normalize_space(" ".join(self._current_snippet_parts))
        if title and self._current_url:
            self._parsed.append(
                _ParsedWebSearchResult(
                    title=title,
                    url=self._current_url,
                    snippet=snippet,
                )
            )
        self._current_title_parts = []
        self._current_snippet_parts = []
        self._current_url = ""
        self._capture = None


def _clean_web_search_url(raw_url: str) -> str:
    cleaned = raw_url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return cleaned
    if parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        target = unquote(target).strip()
        target_parsed = urlparse(target)
        if target_parsed.scheme in {"http", "https"} and target_parsed.netloc:
            return target
    return cleaned


def _openalex_landing_page_url(work: dict) -> str:
    primary_location = work.get("primary_location")
    if isinstance(primary_location, dict):
        landing_page_url = _metadata_text(primary_location.get("landing_page_url"))
        if landing_page_url:
            return landing_page_url
    return ""


def _openalex_full_text_url(work: dict) -> str:
    primary_location = work.get("primary_location")
    if isinstance(primary_location, dict):
        candidate = _metadata_text(primary_location.get("pdf_url"))
        if candidate:
            return candidate
    best_oa_location = work.get("best_oa_location")
    if isinstance(best_oa_location, dict):
        candidate = _metadata_text(best_oa_location.get("pdf_url"))
        if candidate:
            return candidate
    open_access = work.get("open_access")
    if isinstance(open_access, dict):
        candidate = _metadata_text(open_access.get("oa_url"))
        if candidate:
            return candidate
    if isinstance(best_oa_location, dict):
        candidate = _metadata_text(best_oa_location.get("landing_page_url"))
        if candidate:
            return candidate
    if isinstance(primary_location, dict):
        candidate = _metadata_text(primary_location.get("landing_page_url"))
        if candidate:
            return candidate
    return ""


def _fetch_openalex_full_text(
    query: str,
    work: dict,
    url: str,
    timeout_seconds: float,
    max_bytes: int,
    public_only: bool = False,
    allowed_domains: list[str] | None = None,
) -> Evidence | None:
    cleaned_url = url.strip()
    parsed = urlparse(cleaned_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    request = Request(
        cleaned_url,
        headers={"User-Agent": "code-scientist/0.1 literature-full-text-fetch"},
    )
    opener = _open_public_url if public_only else _open_url
    with opener(request, timeout_seconds, allowed_domains) as response:
        raw = response.read(max_bytes)
        content_type = response.headers.get("content-type", "")

    extracted = _document_bytes_to_text_with_sections(raw, content_type, cleaned_url)
    content = extracted.text
    if not content:
        return None

    stored_content = content[:8000]
    sections = _clip_text_sections(extracted.sections, len(stored_content))
    span_count = len(_span_chunks_for_content(stored_content, sections))
    openalex_id = _metadata_text(work.get("id"))
    title = _metadata_text(work.get("display_name") or work.get("title"), "Untitled literature result")
    doi = _metadata_text(work.get("doi"))
    citation = doi or openalex_id or cleaned_url
    metadata = {
        "tool": "openalex_full_text_fetch",
        "query": query,
        "title": title,
        "doi": doi,
        "openalex_id": openalex_id,
        "parent_openalex_id": openalex_id,
        "full_text_url": cleaned_url,
        "citation": citation,
        "content_type": content_type,
        "span_count": str(span_count),
    }
    _add_section_metadata(metadata, sections)
    return Evidence(
        id=stable_id("ev", f"openalex_full_text_fetch:{query}:{openalex_id}:{cleaned_url}:{content[:500]}"),
        kind="literature_full_text",
        source=cleaned_url,
        content=stored_content,
        notes=f"OpenAlex open-access full text fetched for `{query}`.",
        metadata=metadata,
    )


def _openalex_full_text_spans(full_text: Evidence) -> list[Evidence]:
    spans: list[Evidence] = []
    citation = full_text.metadata.get("citation") or full_text.source
    sections = _text_sections_from_metadata(full_text.metadata)
    for chunk in _span_chunks_for_content(full_text.content, sections):
        span_source = f"{full_text.source}#span-{chunk.index}"
        span_citation = f"{citation}#span-{chunk.index}"
        metadata = {
            "tool": "openalex_full_text_span",
            "parent_evidence_id": full_text.id,
            "span_index": str(chunk.index),
            "span_start_char": str(chunk.start_char),
            "span_end_char": str(chunk.end_char),
            "citation": span_citation,
        }
        metadata.update(_section_metadata_for_span(chunk.section))
        for key in ("query", "title", "doi", "openalex_id", "parent_openalex_id", "full_text_url", "content_type"):
            value = full_text.metadata.get(key)
            if value:
                metadata[key] = value
        spans.append(
            Evidence(
                id=stable_id(
                    "ev",
                    f"openalex_full_text_span:{full_text.id}:{chunk.index}:{chunk.start_char}:{chunk.end_char}:{chunk.content[:500]}",
                ),
                kind="literature_full_text_span",
                source=span_source,
                content=chunk.content,
                notes=_span_notes("span", chunk.index, "OpenAlex full text", chunk.section),
                metadata=metadata,
            )
        )
    return spans


def _span_chunks_for_content(
    content: str,
    sections: list[_TextSection] | None = None,
    max_span_chars: int = 1200,
    max_spans: int = 5,
) -> list[_TextSpanChunk]:
    if not sections:
        return [
            _TextSpanChunk(index=index, start_char=start, end_char=end, content=text)
            for index, start, end, text in _full_text_span_chunks(
                content,
                max_span_chars=max_span_chars,
                max_spans=max_spans,
            )
        ]

    chunks: list[_TextSpanChunk] = []
    text_length = len(content)
    for section in sections:
        if len(chunks) >= max_spans:
            break
        start = max(0, min(section.start_char, text_length))
        end = max(start, min(section.end_char, text_length))
        section_text = content[start:end].strip()
        if not section_text:
            continue
        remaining = max_spans - len(chunks)
        local_offset = start + (len(content[start:end]) - len(content[start:end].lstrip()))
        for _local_index, local_start, local_end, span_text in _full_text_span_chunks(
            section_text,
            max_span_chars=max_span_chars,
            max_spans=remaining,
        ):
            chunks.append(
                _TextSpanChunk(
                    index=len(chunks) + 1,
                    start_char=local_offset + local_start,
                    end_char=local_offset + local_end,
                    content=span_text,
                    section=section,
                )
            )
    if chunks:
        return chunks
    return [
        _TextSpanChunk(index=index, start_char=start, end_char=end, content=text)
        for index, start, end, text in _full_text_span_chunks(
            content,
            max_span_chars=max_span_chars,
            max_spans=max_spans,
        )
    ]


def _full_text_span_chunks(
    content: str,
    max_span_chars: int = 1200,
    max_spans: int = 5,
) -> list[tuple[int, int, int, str]]:
    text = _normalize_space(content)
    if not text:
        return []

    chunks: list[tuple[int, int, int, str]] = []
    cursor = 0
    while cursor < len(text) and len(chunks) < max_spans:
        end = min(len(text), cursor + max_span_chars)
        if end < len(text):
            split = text.rfind(" ", cursor, end)
            if split > cursor:
                end = split
        span_text = text[cursor:end].strip()
        if span_text:
            chunks.append((len(chunks) + 1, cursor, end, span_text))
        cursor = end
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
    return chunks


def _openalex_abstract_text(inverted_index: object) -> str:
    if not isinstance(inverted_index, dict):
        return ""
    positioned_words: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and position >= 0:
                positioned_words.append((position, word))
    if not positioned_words:
        return ""
    return " ".join(word for _position, word in sorted(positioned_words))


def _metadata_text(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _clip_text_sections(sections: list[_TextSection], max_chars: int) -> list[_TextSection]:
    clipped: list[_TextSection] = []
    for section in sections:
        if section.start_char >= max_chars:
            continue
        end_char = min(section.end_char, max_chars)
        if end_char <= section.start_char:
            continue
        clipped.append(
            _TextSection(
                path=section.path,
                start_char=section.start_char,
                end_char=end_char,
            )
        )
    return clipped


def _add_section_metadata(metadata: dict[str, str], sections: list[_TextSection]) -> None:
    if not sections:
        return
    metadata["section_count"] = str(len(sections))
    metadata["html_section_ranges"] = json.dumps(
        [
            {
                "path": list(section.path),
                "start_char": section.start_char,
                "end_char": section.end_char,
            }
            for section in sections
        ],
        separators=(",", ":"),
    )


def _text_sections_from_metadata(metadata: dict[str, str]) -> list[_TextSection]:
    raw_sections = metadata.get("html_section_ranges", "")
    if not raw_sections:
        return []
    try:
        parsed = json.loads(raw_sections)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    sections: list[_TextSection] = []
    for raw_section in parsed:
        if not isinstance(raw_section, dict):
            continue
        raw_path = raw_section.get("path")
        start_char = raw_section.get("start_char")
        end_char = raw_section.get("end_char")
        if not isinstance(raw_path, list) or not isinstance(start_char, int) or not isinstance(end_char, int):
            continue
        path = tuple(_metadata_text(part) for part in raw_path if _metadata_text(part))
        if path and 0 <= start_char < end_char:
            sections.append(_TextSection(path=path, start_char=start_char, end_char=end_char))
    return sections


def _section_metadata_for_span(section: _TextSection | None) -> dict[str, str]:
    if section is None or not section.path:
        return {}
    return {
        "section_path": _format_section_path(section.path),
        "section_heading": section.path[-1],
        "section_anchor": _section_anchor(section.path),
        "section_start_char": str(section.start_char),
        "section_end_char": str(section.end_char),
    }


def _span_notes(prefix: str, index: int, source_description: str, section: _TextSection | None) -> str:
    notes = f"{prefix} {index} from {source_description}"
    if section is not None and section.path:
        notes = f"{notes} section `{_format_section_path(section.path)}`"
    return notes


def _format_section_path(path: tuple[str, ...]) -> str:
    return " > ".join(path)


def _section_anchor(path: tuple[str, ...]) -> str:
    slug_parts = [_slugify(part) for part in path]
    return "-".join(part for part in slug_parts if part)


def _slugify(text: str) -> str:
    slug: list[str] = []
    previous_dash = False
    for char in text.lower():
        if char.isalnum():
            slug.append(char)
            previous_dash = False
        elif not previous_dash:
            slug.append("-")
            previous_dash = True
    return "".join(slug).strip("-")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[tuple[str, tuple[str, ...]]] = []
        self.skip_depth = 0
        self._heading_level = 0
        self._heading_parts: list[str] = []
        self._heading_stack: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, _attrs) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if _is_heading_tag(normalized_tag):
            self._heading_level = int(normalized_tag[1])
            self._heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if self._heading_level and normalized_tag == f"h{self._heading_level}":
            heading = _normalize_space(" ".join(self._heading_parts))
            if heading:
                self._heading_stack = [
                    (level, text) for level, text in self._heading_stack if level < self._heading_level
                ]
                self._heading_stack.append((self._heading_level, heading))
                self._append_part(heading)
            self._heading_level = 0
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = _normalize_space(data)
        if not text:
            return
        if self._heading_level:
            self._heading_parts.append(text)
            return
        self._append_part(text)

    def text(self) -> str:
        return self.extracted_text().text

    def extracted_text(self) -> _ExtractedText:
        text_parts: list[str] = []
        part_ranges: list[tuple[tuple[str, ...], int, int]] = []
        for part, path in self.parts:
            if text_parts:
                text_parts.append(" ")
            start_char = sum(len(text_part) for text_part in text_parts)
            text_parts.append(part)
            end_char = start_char + len(part)
            part_ranges.append((path, start_char, end_char))
        text = "".join(text_parts)
        return _ExtractedText(text=text, sections=_sections_from_part_ranges(part_ranges))

    def _append_part(self, text: str) -> None:
        self.parts.append((text, self._current_path()))

    def _current_path(self) -> tuple[str, ...]:
        return tuple(text for _level, text in self._heading_stack)


def _is_heading_tag(tag: str) -> bool:
    return len(tag) == 2 and tag[0] == "h" and tag[1].isdigit() and 1 <= int(tag[1]) <= 6


def _sections_from_part_ranges(part_ranges: list[tuple[tuple[str, ...], int, int]]) -> list[_TextSection]:
    sections: list[_TextSection] = []
    active_path: tuple[str, ...] = ()
    active_start = 0
    active_end = 0
    for path, start_char, end_char in part_ranges:
        if not path:
            continue
        if path == active_path:
            active_end = end_char
            continue
        if active_path:
            sections.append(_TextSection(path=active_path, start_char=active_start, end_char=active_end))
        active_path = path
        active_start = start_char
        active_end = end_char
    if active_path:
        sections.append(_TextSection(path=active_path, start_char=active_start, end_char=active_end))
    if sections and sections[0].start_char > 0:
        first = sections[0]
        sections[0] = _TextSection(path=first.path, start_char=0, end_char=first.end_char)
    return sections


class _HTMLLinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._links: list[str] = []
        self._page_nofollow = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag_name = tag.lower()
        attributes = {name.lower(): value or "" for name, value in attrs}
        if tag_name == "meta" and attributes.get("name", "").strip().lower() == "robots":
            directives = _robots_directives(attributes.get("content", ""))
            if "nofollow" in directives or "none" in directives:
                self._page_nofollow = True
                self._links = []
            return
        if tag_name != "a" or self._page_nofollow:
            return
        rel_values = _robots_directives(attributes.get("rel", ""))
        if "nofollow" in rel_values:
            return
        href = attributes.get("href", "").strip()
        if not href:
            return
        absolute = urljoin(self.base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return
        cleaned = parsed._replace(fragment="").geturl()
        if cleaned and cleaned not in self._links:
            self._links.append(cleaned)

    def links(self) -> list[str]:
        return [] if self._page_nofollow else self._links


def _robots_directives(value: str) -> set[str]:
    return {part.strip().lower() for part in value.replace(",", " ").split() if part.strip()}


def _charset_from_content_type(content_type: str) -> str:
    for part in content_type.split(";"):
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            candidate = value.strip().strip("\"'")
            # A server-supplied charset is untrusted: an unknown codec name would
            # raise LookupError from raw.decode() (before errors="replace" can
            # help) and abort the collector. Validate it, fall back to utf-8.
            try:
                codecs.lookup(candidate)
            except (LookupError, ValueError):
                return "utf-8"
            return candidate
    return "utf-8"


def _looks_like_html(content_type: str, text: str) -> bool:
    lowered_type = content_type.lower()
    if "html" in lowered_type:
        return True
    stripped = text.lstrip().lower()
    return stripped.startswith("<!doctype html") or stripped.startswith("<html")


def _html_to_text(html: str) -> str:
    return _html_to_text_with_sections(html).text


def _html_to_text_with_sections(html: str) -> _ExtractedText:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.extracted_text()


def _document_bytes_to_text(raw: bytes, content_type: str, url: str) -> str:
    return _document_bytes_to_text_with_sections(raw, content_type, url).text


def _document_bytes_to_text_with_sections(raw: bytes, content_type: str, url: str) -> _ExtractedText:
    lowered_type = content_type.lower()
    if "pdf" in lowered_type or urlparse(url).path.lower().endswith(".pdf"):
        return _ExtractedText(_normalize_space(_pdf_bytes_to_text(raw)), [])
    text = raw.decode(_charset_from_content_type(content_type), errors="replace")
    if _looks_like_html(content_type, text):
        return _html_to_text_with_sections(text)
    return _ExtractedText(_normalize_space(text), [])


def _pdf_bytes_to_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(BytesIO(raw))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        if extracted.strip():
            return extracted
    except Exception:
        pass
    try:
        import pymupdf  # type: ignore[import-not-found]

        from code_scientist.evidence import (
            PDF_MAX_PAGES,
            PDF_MAX_RENDER_PIXELS,
            PDF_OCR_DPI,
            _rapidocr_engine,
        )

        document = pymupdf.open(stream=raw, filetype="pdf")
        texts: list[str] = []
        try:
            for page in list(document)[:PDF_MAX_PAGES]:
                estimated_pixels = (
                    float(page.rect.width) / 72 * PDF_OCR_DPI
                    * float(page.rect.height) / 72 * PDF_OCR_DPI
                )
                if estimated_pixels > PDF_MAX_RENDER_PIXELS:
                    continue
                pixmap = page.get_pixmap(
                    dpi=PDF_OCR_DPI,
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )
                output = _rapidocr_engine()(pixmap.tobytes("png"))
                texts.extend(str(text).strip() for text in (output.txts or ()) if str(text).strip())
        finally:
            document.close()
        return "\n".join(texts)
    except Exception:
        return ""


def _normalize_space(text: str) -> str:
    cleaned = "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in text)
    return " ".join(cleaned.split())


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique
