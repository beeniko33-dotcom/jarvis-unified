"""Bounded HTML page metadata extraction; page bodies are not returned or stored."""
from __future__ import annotations

from dataclasses import dataclass
from email.message import Message
from html.parser import HTMLParser

from .safe_fetch import FetchResult, SafeFetchError, safe_fetch_url

_MAX_FIELD_CHARS = 500
_MAX_HEADINGS = 10
_MAX_HEADING_CHARS = 200
_SKIP_TAGS = {"script", "style", "noscript", "template"}


@dataclass(frozen=True)
class PageMetadata:
    source_url: str
    final_url: str
    status: int
    title: str | None
    description: str | None
    headings: tuple[str, ...]


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.description: str | None = None
        self.headings: list[str] = []
        self._active_tag: str | None = None
        self._active_value = ""
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth:
            if tag in _SKIP_TAGS:
                self._skip_depth += 1
            return
        if tag in _SKIP_TAGS:
            self._skip_depth = 1
            return

        attributes = {key.lower(): value for key, value in attrs if value is not None}
        if tag == "meta" and self.description is None:
            name = (attributes.get("name") or "").lower()
            prop = (attributes.get("property") or "").lower()
            if name == "description" or prop == "og:description":
                self.description = self._normalize(attributes.get("content", ""))[:_MAX_FIELD_CHARS] or None
        elif tag == "title" and self.title is None:
            self._start_capture(tag)
        elif tag in {"h1", "h2", "h3"} and len(self.headings) < _MAX_HEADINGS:
            self._start_capture(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            if tag in _SKIP_TAGS:
                self._skip_depth -= 1
            return
        if tag != self._active_tag:
            return

        value = self._normalize(self._active_value)
        if tag == "title" and self.title is None:
            self.title = value[:_MAX_FIELD_CHARS] or None
        elif tag in {"h1", "h2", "h3"} and value:
            self.headings.append(value[:_MAX_HEADING_CHARS])
        self._active_tag = None
        self._active_value = ""

    def handle_data(self, data: str) -> None:
        if self._active_tag is None or self._skip_depth:
            return
        remaining = _MAX_FIELD_CHARS - len(self._active_value)
        if remaining > 0:
            self._active_value += data[:remaining]

    def _start_capture(self, tag: str) -> None:
        self._active_tag = tag
        self._active_value = ""

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split())


def extract_page_metadata(url: str) -> PageMetadata:
    """Fetch one public HTML page and return only bounded title/description/headings."""
    result: FetchResult = safe_fetch_url(url)
    content_type = Message()
    content_type["content-type"] = result.content_type
    media_type = content_type.get_content_type().lower()
    if media_type not in {"text/html", "application/xhtml+xml"}:
        raise SafeFetchError("URL did not return an HTML document")

    charset = content_type.get_content_charset() or "utf-8"
    try:
        html = result.body.decode(charset, errors="replace")
    except LookupError as exc:
        raise SafeFetchError("HTML document uses an unsupported character encoding") from exc

    parser = _MetadataParser()
    parser.feed(html)
    parser.close()
    return PageMetadata(
        source_url=result.url,
        final_url=result.final_url,
        status=result.status,
        title=parser.title,
        description=parser.description,
        headings=tuple(parser.headings[:_MAX_HEADINGS]),
    )
