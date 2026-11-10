"""A small DOM built with html.parser (standard library) for the static checks of docs/index.html."""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from tests.helpers import ROOT

DOCS: Path = ROOT / "docs"
VOID: frozenset[str] = frozenset(
    {"meta", "link", "br", "hr", "img", "input", "source", "area", "base", "col"}
)


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    parent: Node | None = None
    children: list[Node] = field(default_factory=list)
    text: str = ""

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def walk(self) -> list[Node]:
        out: list[Node] = [self]
        child: Node
        for child in self.children:
            out += child.walk()
        return out

    def inside(self, ancestor_id: str) -> bool:
        node: Node | None = self.parent
        while node is not None:
            if node.attrs.get("id") == ancestor_id:
                return True
            node = node.parent
        return False


class Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: Node = Node("#root", {})
        self.stack: list[Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node: Node = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node: Node = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        i: int
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].text += data


def read(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def parse(html: str) -> Node:
    builder: Builder = Builder()
    builder.feed(html)
    builder.close()
    return builder.root


def index_dom() -> Node:
    return parse(read("index.html"))


def style_text(root: Node) -> str:
    return "\n".join(n.text for n in root.walk() if n.tag == "style")


def css_rules(css: str) -> list[tuple[str, str]]:
    """(selector list, body) of every simple rule; comments removed."""
    clean: str = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", clean)]


def section(readme: str, title: str) -> str:
    match: re.Match[str] | None = re.search(
        rf"^## {re.escape(title)}\s*$(.*?)(?=^## |\Z)", readme, re.S | re.M
    )
    assert match is not None, title
    return match.group(1)
