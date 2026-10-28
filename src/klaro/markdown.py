"""Small, safe Markdown rendering policy for question names and offered answers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from html import escape

from markdown_it import MarkdownIt
from markdown_it.token import Token
from markupsafe import Markup

# Sources are immutable after creation, so rendered results are safe to reuse.
_CACHE_SIZE = 2_048

_INLINE = MarkdownIt("zero").enable(["text", "newline", "backticks", "emphasis"])
_OPTION = MarkdownIt("zero").enable(
    ["paragraph", "text", "newline", "backticks", "emphasis", "fence", "code"]
)
_BLOCK_MARKER = re.compile(r"^(?: {0,3}(?:#{1,6}\s|>\s?|[-+]\s|\*\s|\d+[.)]\s|\|))")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HTML_PAIR = re.compile(r"<([A-Za-z][A-Za-z0-9-]*)\b[^>]*>.*?</\1\s*>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RenderedOption:
    head: Markup
    body: Markup


class _Protection:
    def __init__(self, source: str) -> None:
        marker = "\ue000"
        while marker in source:
            marker = chr(ord(marker) + 1)
        self.marker = marker
        self.values: list[str] = []
        self._placeholder = re.compile(f"{re.escape(marker)}(\\d+){re.escape(marker)}")

    def protect(self, value: str) -> str:
        index = len(self.values)
        self.values.append(value)
        return f"{self.marker}{index}{self.marker}"

    def restore(self, value: str) -> str:
        """Restore placeholders in one pass, including ones nested in protected values."""
        if not self.values:
            return value
        return self._placeholder.sub(
            lambda match: self.restore(self.values[int(match.group(1))]), value
        )


def _closing_positions(source: str, opening: str, closing: str) -> dict[int, int]:
    """Map every opening delimiter to its matching closing delimiter in linear time.

    A backslash escapes the following character. As when scanning forward from an
    opening delimiter, the start itself always counts as opening, even when escaped.
    """
    level_after: list[int] = []
    is_closing: list[bool] = []
    level = 0
    escaped = False
    for character in source:
        closes = False
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == opening:
            level += 1
        elif character == closing:
            level -= 1
            closes = True
        level_after.append(level)
        is_closing.append(closes)

    # Depth changes by one per delimiter, so the match of an opening is the first
    # closing delimiter afterwards that returns to the level before that opening.
    matches: dict[int, int] = {}
    nearest_closing_at_level: dict[int, int] = {}
    for index in range(len(source) - 1, -1, -1):
        if is_closing[index]:
            nearest_closing_at_level[level_after[index]] = index
        elif source[index] == opening:
            match = nearest_closing_at_level.get(level_after[index] - 1)
            if match is not None:
                matches[index] = match
    return matches


def _next_positions(source: str, character: str) -> list[int]:
    """Return, for every index, the next position of ``character`` at or after it (or -1)."""
    positions = [-1] * (len(source) + 1)
    for index in range(len(source) - 1, -1, -1):
        positions[index] = index if source[index] == character else positions[index + 1]
    return positions


def _protect_html_pairs(source: str, protection: _Protection) -> str:
    output: list[str] = []
    index = 0
    for match in _HTML_PAIR.finditer(source):
        output.append(source[index : match.start()])
        output.append(protection.protect(match.group(0)))
        index = match.end()
    output.append(source[index:])
    return "".join(output)


def _protect_inline(source: str, protection: _Protection) -> str:
    brackets = _closing_positions(source, "[", "]")
    parentheses = _closing_positions(source, "(", ")")
    next_angle = _next_positions(source, ">")
    output: list[str] = []
    index = 0
    while index < len(source):
        bracket_start = index + 1 if source.startswith("![", index) else index
        if source[bracket_start : bracket_start + 1] == "[":
            bracket_end = brackets.get(bracket_start)
            if bracket_end is not None:
                end = bracket_end + 1
                if end < len(source) and source[end] == "(":
                    destination_end = parentheses.get(end)
                    if destination_end is not None:
                        end = destination_end + 1
                elif end < len(source) and source[end] == "[":
                    reference_end = brackets.get(end)
                    if reference_end is not None:
                        end = reference_end + 1
                output.append(protection.protect(source[index:end]))
                index = end
                continue
        if source[index] == "<":
            end = next_angle[index + 1]
            if end != -1:
                output.append(protection.protect(source[index : end + 1]))
                index = end + 1
                continue
        output.append(source[index])
        index += 1
    return "".join(output)


def _protect_block_markers(source: str, protection: _Protection) -> str:
    output = []
    for line in source.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        newline = line[len(content) :]
        if _BLOCK_MARKER.match(content):
            content = protection.protect(content)
        output.append(content + newline)
    return "".join(output)


def _protect_name_blocks(source: str, protection: _Protection) -> str:
    lines = source.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    while index < len(lines):
        match = _FENCE.match(lines[index])
        if match:
            marker = match.group(1)
            character = marker[0]
            minimum = len(marker)
            end = index + 1
            closing = re.compile(rf"^ {{0,3}}{re.escape(character)}{{{minimum},}}[ \t]*(?:\r?\n|$)")
            while end < len(lines) and not closing.match(lines[end]):
                end += 1
            if end < len(lines):
                end += 1
            output.append(protection.protect("".join(lines[index:end])))
            index = end
            continue
        if lines[index].startswith(("    ", "\t")):
            output.append(protection.protect(lines[index]))
        else:
            output.append(lines[index])
        index += 1
    return "".join(output)


def _inline_tokens(source: str, *, name: bool) -> tuple[list[Token], _Protection]:
    protection = _Protection(source)
    if name:
        source = _protect_name_blocks(source, protection)
    source = _protect_block_markers(source, protection)
    source = _protect_html_pairs(source, protection)
    source = _protect_inline(source, protection)
    parsed = _INLINE.parseInline(source)
    children = parsed[0].children if parsed and parsed[0].children else []
    return children, protection


def _render_inline(source: str, *, name: bool = False) -> Markup:
    children, protection = _inline_tokens(source, name=name)
    output: list[str] = []
    for token in children:
        content = escape(protection.restore(token.content))
        if token.type == "text":
            output.append(content)
        elif token.type == "code_inline":
            output.append(f"<code>{content}</code>")
        elif token.type == "strong_open":
            output.append("<strong>")
        elif token.type == "strong_close":
            output.append("</strong>")
        elif token.type == "em_open":
            output.append("<em>")
        elif token.type == "em_close":
            output.append("</em>")
        elif token.type in {"softbreak", "hardbreak"}:
            output.append("\n" if name else "<br>\n")
        else:
            raise ValueError(f"Unexpected inline Markdown token: {token.type}")
    return Markup("".join(output))  # noqa: S704 - every fragment above is escaped or fixed markup


@lru_cache(maxsize=_CACHE_SIZE)
def render_name(source: str) -> Markup:
    """Render only supported inline formatting; block-like name syntax stays literal."""
    return _render_inline(source, name=True)


@lru_cache(maxsize=_CACHE_SIZE)
def plain_name(source: str) -> str:
    """Convert supported name formatting to text while retaining unsupported syntax."""
    children, protection = _inline_tokens(source, name=True)
    output: list[str] = []
    for token in children:
        if token.type in {"text", "code_inline"}:
            output.append(protection.restore(token.content))
        elif token.type in {"softbreak", "hardbreak"}:
            output.append("\n")
        elif token.type not in {"strong_open", "strong_close", "em_open", "em_close"}:
            raise ValueError(f"Unexpected inline Markdown token: {token.type}")
    return "".join(output)


def _has_text_first(tokens: Sequence[Token]) -> bool:
    return bool(
        len(tokens) >= 2
        and tokens[0].type == "paragraph_open"
        and tokens[1].type == "inline"
        and tokens[1].content.strip()
    )


@lru_cache(maxsize=_CACHE_SIZE)
def is_text_first_option(source: str) -> bool:
    return _has_text_first(_OPTION.parse(source))


@lru_cache(maxsize=_CACHE_SIZE)
def render_option(source: str) -> RenderedOption:
    tokens = _OPTION.parse(source)
    if not _has_text_first(tokens):
        raise ValueError("An option must begin with a nonempty paragraph")
    head = _render_inline(tokens[1].content)
    body: list[str] = []
    index = 2
    while index < len(tokens):
        token = tokens[index]
        if token.type == "paragraph_close":
            index += 1
            continue
        if token.type == "paragraph_open":
            inline = tokens[index + 1]
            if inline.type != "inline" or tokens[index + 2].type != "paragraph_close":
                raise ValueError("Unexpected paragraph Markdown tokens")
            body.append(f"<p>{_render_inline(inline.content)}</p>")
            index += 3
            continue
        if token.type in {"fence", "code_block"}:
            body.append(
                '<pre tabindex="0" aria-label="Code block"><code>'
                f"{escape(token.content)}</code></pre>"
            )
            index += 1
            continue
        raise ValueError(f"Unexpected block Markdown token: {token.type}")
    # Each body fragment is rendered Markup or escaped code.
    return RenderedOption(head=head, body=Markup("".join(body)))  # noqa: S704
