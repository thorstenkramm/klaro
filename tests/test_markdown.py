from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from klaro.markdown import is_text_first_option, plain_name, render_name, render_option


def fragment(markup) -> BeautifulSoup:
    return BeautifulSoup(f"<div>{markup}</div>", "html.parser")


def test_supported_name_inline_formatting_and_plain_text() -> None:
    source = "Use **strong**, *emphasis*, and `code <tag>`."
    rendered = render_name(source)
    soup = fragment(rendered)
    assert soup.strong.text == "strong"
    assert soup.em.text == "emphasis"
    assert soup.code.text == "code <tag>"
    assert soup.find(["pre", "p", "a", "img", "script"]) is None
    assert plain_name(source) == "Use strong, emphasis, and code <tag>."


@pytest.mark.parametrize(
    "source",
    [
        "[Link *em*](https://example.com)",
        "[Link](javascript:alert(1))",
        "![Image **x**](javascript:alert(1))",
        "<script>**alert**</script>",
        "<img src=x onerror=alert(1)>",
        "# Heading **literal**",
        "- item *literal*",
        "> quote **literal**",
        "| A *literal* | B |",
    ],
)
def test_unsupported_inline_and_block_syntax_is_literal_and_inert(source: str) -> None:
    rendered = render_name(source)
    soup = fragment(rendered)
    assert soup.div.text == source
    assert soup.find(["a", "img", "script", "h1", "ul", "blockquote", "table"]) is None
    assert all(not tag.has_attr("href") and not tag.has_attr("src") for tag in soup.find_all(True))
    if source.startswith(("&", "#", "-", ">", "|")):
        assert soup.find(["em", "strong"]) is None


def test_entities_stay_literal_without_disabling_nearby_supported_formatting() -> None:
    soup = fragment(render_name("&copy; **bold**"))
    assert soup.div.text == "&copy; bold"
    assert soup.strong.text == "bold"
    assert "&amp;copy;" in str(render_name("&copy;"))


def test_raw_html_pair_preserves_nested_markdown_literally() -> None:
    source = "<script>**not bold** `not code`</script>"
    assert fragment(render_name(source)).div.text == source
    assert plain_name(source) == source


def test_name_fences_and_indented_blocks_remain_inline_literal_text() -> None:
    fenced = "Before\n```python\n**literal**\n```\nAfter"
    soup = fragment(render_name(fenced))
    assert soup.div.text == fenced
    assert soup.find(["pre", "code", "strong"]) is None
    assert plain_name(fenced) == fenced
    indented = "    **literal**"
    assert fragment(render_name(indented)).div.text == indented
    assert fragment(render_name(indented)).find(["pre", "code", "strong"]) is None


def test_option_splits_head_paragraphs_breaks_and_code_without_user_attributes() -> None:
    source = (
        "Choose **this** `option`  \nwith a break\n\n"
        "Second *paragraph*\n\n"
        "```python onload=alert(1) class=evil\n"
        "<script>alert(1)</script>\n"
        "```\n\n"
        "    indented <b>code</b>\n"
    )
    rendered = render_option(source)
    head = fragment(rendered.head)
    assert head.strong.text == "this"
    assert head.code.text == "option"
    assert head.br is not None
    assert head.find(["p", "pre"]) is None
    body = fragment(rendered.body)
    assert [p.text for p in body.find_all("p", recursive=False)] == []
    paragraphs = body.div.find_all("p", recursive=False)
    assert len(paragraphs) == 1
    assert paragraphs[0].em.text == "paragraph"
    code_blocks = body.find_all("pre")
    assert len(code_blocks) == 2
    assert code_blocks[0].code.text == "<script>alert(1)</script>\n"
    assert code_blocks[1].code.text == "indented <b>code</b>\n"
    for pre in code_blocks:
        assert pre.attrs == {"tabindex": "0", "aria-label": "Code block"}
    assert "onload" not in str(body)
    assert "class=evil" not in str(body)
    assert body.find(["script", "a", "img"]) is None
    assert all(
        set(tag.attrs) <= ({"tabindex", "aria-label"} if tag.name == "pre" else set())
        for tag in body.find_all(True)
    )


def test_option_plain_text_first_and_code_first_validation() -> None:
    assert is_text_first_option("\n\n  \n`inline code` head\n```\nbody\n```")
    for source in ["```\ncode\n```", "\n\n```python\ncode\n```", "    indented", "~~~\ncode\n~~~"]:
        assert not is_text_first_option(source)
        with pytest.raises(ValueError, match="nonempty paragraph"):
            render_option(source)


def test_option_head_and_plain_name_do_not_interpret_recommendation_prefixes() -> None:
    assert fragment(render_option("*literal* and **bold**").head).em.text == "literal"
    assert fragment(render_option("\\*literal").head).div.text == "\\*literal"
    assert plain_name("*literal*") == "literal"
