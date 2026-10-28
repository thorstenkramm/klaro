"""Linear delimiter matching must behave exactly like the original forward scan."""

from __future__ import annotations

import random

from klaro import markdown
from klaro.markdown import _closing_positions, plain_name, render_name, render_option

PRIVATE_USE = range(0xE000, 0xF900)


def forward_scan(source: str, start: int, opening: str, closing: str) -> int | None:
    """The original quadratic reference: scan from one opening delimiter."""
    depth = 0
    escaped = False
    for index in range(start, len(source)):
        character = source[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
        elif character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def test_closing_positions_match_forward_scan_for_random_sources() -> None:
    generator = random.Random(20261027)
    alphabet = "[]()\\!a "
    for _ in range(20_000):
        source = "".join(generator.choice(alphabet) for _ in range(generator.randint(0, 20)))
        for opening, closing in (("[", "]"), ("(", ")")):
            matches = _closing_positions(source, opening, closing)
            expected = {
                index: match
                for index, character in enumerate(source)
                if character == opening
                and (match := forward_scan(source, index, opening, closing)) is not None
            }
            assert matches == expected, source


def test_escaped_opening_still_matches_when_scanning_starts_there() -> None:
    assert _closing_positions("\\[a]", "[", "]") == {1: 3}
    assert _closing_positions("[\\[a]]", "[", "]") == {0: 4, 2: 4}


def test_nested_protected_source_is_restored_without_placeholders() -> None:
    source = "x <-```\n-<b></b>\n#.</b>"

    rendered = render_name.__wrapped__(source)
    option = render_option.__wrapped__(source)
    plain = plain_name.__wrapped__(source)

    assert "&lt;b&gt;&lt;/b&gt;" in rendered
    assert "&lt;b&gt;&lt;/b&gt;" in option.head
    assert "<b></b>" in plain
    for output in (str(rendered), str(option.head), plain):
        assert not any(ord(character) in PRIVATE_USE for character in output)


def test_rendering_is_cached_per_source() -> None:
    markdown.render_option.cache_clear()
    source = "Cached **option**"

    assert render_option(source) is render_option(source)
    assert markdown.render_option.cache_info().hits == 1
