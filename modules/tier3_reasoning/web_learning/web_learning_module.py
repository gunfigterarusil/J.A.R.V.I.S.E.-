"""V9.3 Web Learning / Search module.

This module gives JAV a bounded, auditable way to learn from the web:
- search web pages using a simple HTML search backend
- fetch sources with timeouts and size limits
- extract readable text without heavy dependencies
- ask the LLM to summarize/compare sources when available
- store sourced notes into long-term memory

It is not autonomous browsing by default. It runs only when requested through
chat/voice/desktop and always emits source metadata.
"""
from __future__ import annotations

import asyncio
import html
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

from core import CognitiveModule, CognitiveEvent as Event, Priority


class WebResult:
    def __init__(self, title: str, url: str, snippet: str = "") -> None:
        self.title = title
        self.url = url
        self.snippet = snippet

    def to_dict(self) -> Dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self.skip_stack: List[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self.skip_stack.append(tag)
        if tag == "title":
            self._in_title = True
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if self.skip_stack and self.skip_stack[-1] == tag:
            self.skip_stack.pop()
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        if self.skip_stack:
            return
        text = html.unescape(data or "").strip()
        if not text:
            return
        if self._in_title:
            self.title += text + " "
        else:
            self.parts.append(text + " ")

    def get_text(self, max_chars: int) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        return text.strip()[:max_chars]


class WebLearningModule(CognitiveModule):
    MODULE_DESCRIPTION = "V9.3 bounded web search, web reading, and sourced long-term learning"
    MODULE_VERSION = "0.1.0"

    def __init__(self) -> None:
        super().__init__(module_id="web_learning", cost={"cpu": 0.12, "gpu": 0.0, "ram": 0.08})
        self.enabled = True
        self.search_enabled = True
        self.learn_enabled = True
        self.max_results = 5
        self.max_sources = 4
        self.timeout = 12.0
        self.max_chars_per_page = 9000
        self.user_agent = "JAV-WebLearning/0.1 (+local user agent)"
        self.last_report: Dict[str, Any] = {}

    def initialize(self, kernel) -> None:
        super().initialize(kernel)
        cfg = getattr(kernel.config, "web_learning", None)
        if cfg is not None:
            self.enabled = bool(getattr(cfg, "enabled", True))
            self.search_enabled = bool(getattr(cfg, "search_enabled", True))
            self.learn_enabled = bool(getattr(cfg, "learn_enabled", True))
            self.max_results = int(getattr(cfg, "max_results", 5) or 5)
            self.max_sources = int(getattr(cfg, "max_sources", 4) or 4)
            self.timeout = float(getattr(cfg, "timeout_seconds", 12.0) or 12.0)
            self.max_chars_per_page = int(getattr(cfg, "max_chars_per_page", 9000) or 9000)
            self.user_agent = str(getattr(cfg, "user_agent", self.user_agent) or self.user_agent)
        kernel.event_bus.register_consumer(self.module_id, [
            "web_search_requested",
            "web_learn_requested",
            "web_fetch_requested",
        ])

    async def on_event(self, event: Event) -> None:
        if not self.enabled:
            return
        if event.type == "web_search_requested":
            await self._handle_search(event)
        elif event.type == "web_fetch_requested":
            await self._handle_fetch(event)
        elif event.type == "web_learn_requested":
            await self._handle_learn(event)

    async def _handle_search(self, event: Event) -> None:
        query = str(event.data.get("query") or event.data.get("query_text") or "").strip()
        if not query:
            self._respond("Web search needs a query.")
            return
        results = await self._search(query, int(event.data.get("max_results", self.max_results) or self.max_results))
        self.last_report = {"mode": "search", "query": query, "results": [r.to_dict() for r in results], "timestamp": time.time()}
        lines = [f"Web search: {query}"]
        if not results:
            lines.append("No results found or search backend unavailable.")
        for i, r in enumerate(results, 1):
            snip = f" — {r.snippet}" if r.snippet else ""
            lines.append(f"{i}. {r.title}\n   {r.url}{snip}")
        self._emit("web_search_completed", self.last_report)
        if event.data.get("respond", True):
            self._respond("\n".join(lines))

    async def _handle_fetch(self, event: Event) -> None:
        url = str(event.data.get("url") or "").strip()
        if not url:
            self._respond("Web fetch needs a URL.")
            return
        page = await self._fetch_page(url)
        self.last_report = {"mode": "fetch", "url": url, "page": page, "timestamp": time.time()}
        self._emit("web_fetch_completed", self.last_report)
        if event.data.get("respond", True):
            if page.get("error"):
                self._respond(f"Could not fetch {url}: {page.get('error')}")
            else:
                text = str(page.get("text", ""))[:1600]
                self._respond(f"Fetched: {page.get('title') or url}\nSource: {url}\n\n{text}")

    async def _handle_learn(self, event: Event) -> None:
        topic = str(event.data.get("topic") or event.data.get("query") or event.data.get("query_text") or "").strip()
        if not topic:
            self._respond("Web learning needs a topic.")
            return
        max_sources = int(event.data.get("max_sources", self.max_sources) or self.max_sources)
        search_results = await self._search(topic, max(self.max_results, max_sources)) if self.search_enabled else []
        chosen = search_results[:max_sources]
        pages: List[Dict[str, Any]] = []
        for result in chosen:
            page = await self._fetch_page(result.url)
            page["search_title"] = result.title
            page["search_snippet"] = result.snippet
            pages.append(page)

        report = await self._build_learning_report(topic, chosen, pages)
        self.last_report = report
        self._emit("web_learning_completed", report)
        if self.learn_enabled:
            self._store_learning(report)
        if event.data.get("respond", True):
            self._respond(self._format_report(report))

    async def _search(self, query: str, max_results: int) -> List[WebResult]:
        # DuckDuckGo Lite works without API keys. If it changes, the module fails
        # gracefully and still allows direct URL fetches.
        url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
        try:
            html_text = await self._http_get(url, max_chars=180000)
        except Exception:
            return []
        return self._parse_duckduckgo_lite(html_text, max_results=max_results)

    def _parse_duckduckgo_lite(self, html_text: str, max_results: int) -> List[WebResult]:
        results: List[WebResult] = []
        # DDG Lite result links usually contain class=result-link and href=/l/?uddg=<url>.
        pattern = re.compile(r'<a[^>]+href="([^"]+)"[^>]*class="result-link"[^>]*>(.*?)</a>', re.I | re.S)
        matches = pattern.findall(html_text)
        if not matches:
            pattern = re.compile(r'<a[^>]+class="result-link"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
            matches = pattern.findall(html_text)
        for href, title_html in matches:
            title = re.sub(r"<.*?>", "", title_html)
            title = html.unescape(re.sub(r"\s+", " ", title)).strip()
            url = html.unescape(href)
            if "uddg=" in url:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                url = unquote((params.get("uddg") or [url])[0])
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith(("http://", "https://")):
                continue
            if any(r.url == url for r in results):
                continue
            results.append(WebResult(title=title or url, url=url, snippet=""))
            if len(results) >= max_results:
                break
        return results

    async def _fetch_page(self, url: str) -> Dict[str, Any]:
        if not url.startswith(("http://", "https://")):
            return {"url": url, "error": "Only http/https URLs are supported"}
        try:
            raw = await self._http_get(url, max_chars=self.max_chars_per_page * 8)
            parser = _TextExtractor()
            parser.feed(raw)
            text = parser.get_text(self.max_chars_per_page)
            title = parser.title.strip() or urlparse(url).netloc
            return {
                "url": url,
                "title": title[:240],
                "text": text,
                "chars": len(text),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "domain": urlparse(url).netloc,
            }
        except Exception as exc:
            return {"url": url, "error": str(exc), "fetched_at": datetime.now(timezone.utc).isoformat()}

    async def _http_get(self, url: str, max_chars: int = 100000) -> str:
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5"}
        try:
            import httpx  # type: ignore
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text[:max_chars]
        except ImportError:
            import urllib.request
            def _blocking() -> str:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:  # nosec - user requested web read
                    data = r.read(max_chars)
                    charset = r.headers.get_content_charset() or "utf-8"
                    return data.decode(charset, errors="replace")
            return await asyncio.to_thread(_blocking)

    async def _build_learning_report(self, topic: str, results: List[WebResult], pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        usable = [p for p in pages if p.get("text") and not p.get("error")]
        source_blocks = []
        for i, p in enumerate(usable, 1):
            source_blocks.append(
                f"SOURCE {i}: {p.get('title')}\nURL: {p.get('url')}\nTEXT:\n{str(p.get('text'))[:2500]}"
            )
        fallback_summary = self._fallback_summary(topic, usable)
        llm_summary = ""
        llm = getattr(self.kernel, "llm_router", None) if self.kernel else None
        if llm is not None and usable:
            prompt = (
                "You are JAV's web learning cortex. Summarize the sources into durable memory.\n"
                "Rules: be concise, mark uncertainty, never invent facts not supported by the sources.\n"
                "Return Ukrainian if the topic is Ukrainian/Russian; otherwise use the user's language.\n\n"
                f"TOPIC: {topic}\n\n" + "\n\n".join(source_blocks[:4]) +
                "\n\nProduce:\n1) short answer\n2) key facts\n3) useful follow-up actions\n4) source reliability notes"
            )
            try:
                res = await llm.generate(prompt, task="summarization")
                llm_summary = str(getattr(res, "text", "") or "").strip()
                if "NullProvider" in llm_summary or len(llm_summary) < 20:
                    llm_summary = ""
            except Exception:
                llm_summary = ""
        summary = llm_summary or fallback_summary
        confidence = self._confidence(usable)
        return {
            "topic": topic,
            "summary": summary,
            "sources": [
                {
                    "title": p.get("title") or p.get("search_title") or r.title,
                    "url": p.get("url") or r.url,
                    "domain": p.get("domain") or urlparse(r.url).netloc,
                    "chars": p.get("chars", 0),
                    "error": p.get("error", ""),
                    "fetched_at": p.get("fetched_at", ""),
                }
                for r, p in zip(results, pages)
            ],
            "source_count": len(usable),
            "confidence": confidence,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "mode": "web_learning_v9.3",
        }

    def _fallback_summary(self, topic: str, pages: List[Dict[str, Any]]) -> str:
        if not pages:
            return f"I could not collect readable web sources for: {topic}"
        lines = [f"Web learning note for: {topic}", "Key extracted source snippets:"]
        for i, p in enumerate(pages[:4], 1):
            text = str(p.get("text", "")).replace("\n", " ")
            text = re.sub(r"\s+", " ", text).strip()[:500]
            lines.append(f"{i}. {p.get('title') or p.get('url')}: {text}")
        return "\n".join(lines)

    def _confidence(self, pages: List[Dict[str, Any]]) -> float:
        if not pages:
            return 0.0
        domains = {p.get("domain") for p in pages if p.get("domain")}
        base = min(0.85, 0.25 + len(pages) * 0.15 + len(domains) * 0.08)
        avg_chars = sum(int(p.get("chars", 0) or 0) for p in pages) / max(1, len(pages))
        if avg_chars > 2000:
            base += 0.08
        return round(min(0.95, base), 2)

    def _store_learning(self, report: Dict[str, Any]) -> None:
        if not self.kernel:
            return
        topic = report.get("topic", "")
        sources = report.get("sources", [])
        source_text = "; ".join(f"{s.get('title')} <{s.get('url')}>" for s in sources[:6])
        note = {
            "subject": f"web:{topic}",
            "predicate": "learned",
            "object": str(report.get("summary", ""))[:3000],
            "confidence": float(report.get("confidence", 0.5) or 0.5),
            "source": "web_learning",
            "sources": sources,
            "checked_at": report.get("checked_at"),
            "text": f"WEB LEARNING: {topic}\n{report.get('summary')}\nSources: {source_text}",
        }
        self.kernel.event_bus.emit(
            Event(type="semantic_memory_store_requested", data=note, source_module=self.module_id),
            Priority.COGNITIVE,
        )
        self.kernel.event_bus.emit(
            Event(type="user_utterance", data={"text": note["text"], "importance": 0.82, "source": "web_learning", "_skip_action_intent": True, "_skip_llm": True}, source_module=self.module_id),
            Priority.BACKGROUND,
        )

    def _format_report(self, report: Dict[str, Any]) -> str:
        lines = [f"Web learning completed: {report.get('topic')}", f"confidence≈{report.get('confidence')} sources={report.get('source_count')}", "", str(report.get("summary", "")).strip(), "", "Sources:"]
        for i, s in enumerate(report.get("sources", [])[:8], 1):
            status = "ok" if not s.get("error") else f"error: {s.get('error')}"
            lines.append(f"{i}. {s.get('title') or s.get('domain')} — {s.get('url')} [{status}]")
        return "\n".join(lines).strip()

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(Event(type=event_type, data=data, source_module=self.module_id), Priority.COGNITIVE)

    def _respond(self, text: str) -> None:
        if self.kernel:
            self.kernel.event_bus.emit(Event(type="response_generated", data={"text": text, "source": "web_learning/v9.3"}, source_module=self.module_id), Priority.COGNITIVE)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "enabled": self.enabled,
            "search_enabled": self.search_enabled,
            "learn_enabled": self.learn_enabled,
            "max_results": self.max_results,
            "max_sources": self.max_sources,
            "last_report": self.last_report,
        })
        return base


def create_module() -> WebLearningModule:
    return WebLearningModule()
