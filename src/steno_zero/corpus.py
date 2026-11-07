"""Corpus: Russian Wikisource texts, pinned by revision and checked by SHA-256."""

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from steno_zero.alphabet import ALPHABET, normalize

API_URL: str = (
    "https://ru.wikisource.org/w/api.php?action=parse&oldid={oldid}&prop=text&format=json&formatversion=2"
)
USER_AGENT: str = "steno-zero/0.1.0 (https://github.com/Breakdown08/steno-zero)"
MIN_PAUSE_S: float = 1.0
MAX_RETRIES: int = 5

_VOID: frozenset[str] = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
)
_SKIP_CLASSES: frozenset[str] = frozenset({"ws-noexport", "references"})


@dataclass
class _Frame:
    tag: str
    skip: bool
    text_root: bool
    paragraph: bool


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[_Frame] = []
        self.found: bool = False
        self.done: bool = False
        self.paragraphs: list[str] = []
        self.current: list[str] = []

    def _inside(self) -> bool:
        return any(f.text_root for f in self.stack)

    def _skipping(self) -> bool:
        return any(f.skip for f in self.stack)

    def _in_paragraph(self) -> bool:
        return any(f.paragraph for f in self.stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.done:
            return
        classes: set[str] = set((dict(attrs).get("class") or "").split())
        if tag == "br":
            if self._inside() and not self._skipping() and self._in_paragraph():
                self.current.append(" ")
            return
        if tag in _VOID:
            return
        root: bool = tag == "div" and "text" in classes and not self.found
        if root:
            self.found = True
        skip: bool = (
            tag in ("style", "script")
            or (tag == "sup" and "reference" in classes)
            or bool(classes & _SKIP_CLASSES)
        )
        paragraph: bool = tag == "p" and self._inside() and not self._in_paragraph()
        if paragraph and not self._skipping() and not skip:
            self.current = []
        self.stack.append(_Frame(tag, skip, root, paragraph))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self.done or tag in _VOID:
            return
        i: int
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                break
        else:
            return
        popped: list[_Frame] = self.stack[i:]
        del self.stack[i:]
        frame: _Frame
        for frame in popped:
            if frame.paragraph and not self._skipping() and not frame.skip:
                self.paragraphs.append("".join(self.current))
                self.current = []
            if frame.text_root:
                self.done = True

    def handle_data(self, data: str) -> None:
        if self._inside() and not self._skipping() and self._in_paragraph():
            self.current.append(data)


def extract_text(html: str) -> str:
    parser: _Extractor = _Extractor()
    parser.feed(html)
    parser.close()
    if not parser.found:
        raise ValueError('no <div class="text"> in the page')
    return "\n".join(parser.paragraphs)


_last_request: list[float] = [0.0]


def _pause(seconds: float) -> None:
    time.sleep(seconds)


def _read(request: urllib.request.Request) -> bytes:
    response: Any = urllib.request.urlopen(request, timeout=60)
    with response:
        data: bytes = response.read()
    return data


def wikisource_html(oldid: int) -> str:
    request: urllib.request.Request = urllib.request.Request(
        API_URL.format(oldid=oldid), headers={"User-Agent": USER_AGENT}
    )
    wait: float = 2.0
    attempt: int
    for attempt in range(MAX_RETRIES + 1):
        since: float = time.monotonic() - _last_request[0]
        if since < MIN_PAUSE_S:
            _pause(MIN_PAUSE_S - since)
        _last_request[0] = time.monotonic()
        try:
            payload: dict[str, Any] = json.loads(_read(request))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == MAX_RETRIES:
                raise
            retry: str | None = exc.headers.get("Retry-After")
            _pause(float(retry) if retry is not None and retry.isdigit() else wait)
            wait *= 2
            continue
        html: str = payload["parse"]["text"]
        return html
    raise RuntimeError("unreachable")  # pragma: no cover


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_corpus(sources: Path, out: Path, get: Callable[[int], str] = wikisource_html) -> str:
    spec: dict[str, Any] = json.loads(sources.read_text(encoding="utf-8"))
    texts: list[str] = [normalize(extract_text(get(w["oldid"]))) for w in spec["works"]]
    data: bytes = (" ".join(texts) + "\n").encode("utf-8")
    sha: str = _sha256(data)
    expected: str | None = spec.get("corpus_sha256")
    if expected is not None and expected != sha:
        raise ValueError(f"corpus sha256 mismatch: sources.json has {expected}, fetched text has {sha}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return sha


def load_corpus(path: Path, sha256: str | None = None) -> str:
    data: bytes = path.read_bytes()
    if sha256 is not None and _sha256(data) != sha256:
        raise ValueError(f"{path}: sha256 mismatch")
    text: str = data.decode("utf-8").removesuffix("\n")
    bad: set[str] = set(text) - set(ALPHABET)
    if bad:
        raise ValueError(f"{path}: symbols outside the alphabet: {sorted(bad)!r}")
    return text


def split_corpus(text: str, test_fraction: float = 0.1) -> tuple[str, str]:
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be in (0, 1)")
    cut: int = int(len(text) * (1 - test_fraction))
    return text[:cut], text[cut:]
