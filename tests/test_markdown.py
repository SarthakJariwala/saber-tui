from __future__ import annotations

import re
import threading

import saber_tui.components.markdown as markdown_module
from saber_tui.components.markdown import DefaultTextStyle, Markdown, MarkdownOptions, MarkdownTheme
from saber_tui.utils import strip_ansi, visible_width


def ansi(code: str):
    return lambda text: f"\x1b[{code}m{text}\x1b[0m"


THEME = MarkdownTheme(
    heading=ansi("36"),
    link=ansi("34"),
    link_url=ansi("2"),
    code=ansi("33"),
    code_block=ansi("32"),
    code_block_border=ansi("2"),
    quote=ansi("3"),
    quote_border=ansi("2"),
    hr=ansi("2"),
    list_bullet=ansi("36"),
    bold=ansi("1"),
    italic=ansi("3"),
    strikethrough=ansi("9"),
    underline=ansi("4"),
)


def plain(markdown: Markdown, width: int = 80) -> list[str]:
    return [strip_ansi(line).rstrip() for line in markdown.render(width)]


def test_empty_padding_cache_and_updates() -> None:
    markdown = Markdown("", 1, 1, THEME)
    assert markdown.render(20) == []

    markdown.set_text("hello")
    first = markdown.render(20)
    assert first is markdown.render(20)
    assert [line.rstrip() for line in first] == ["", " hello", ""]

    markdown.append_text(" world")
    assert plain(markdown, 20)[1] == " hello world"


def test_headings_inline_styles_and_strict_strikethrough() -> None:
    output = Markdown("### Why `code` is **bold** and ~~gone~~, not ~this~", theme=THEME).render(100)[0]
    assert strip_ansi(output).rstrip() == "### Why code is bold and gone, not ~this~"
    for code in ("\x1b[36m", "\x1b[33m", "\x1b[1m", "\x1b[9m"):
        assert code in output


def test_nested_ordered_unordered_and_task_lists() -> None:
    markdown = Markdown("1. first\n   - [x] nested\n   - [ ] todo\n2. second", theme=THEME)
    assert plain(markdown) == ["1. first", "    - [x] nested", "    - [ ] todo", "2. second"]


def test_ordered_markers_normalize_or_preserve() -> None:
    source = "4. fourth\n3. third\n\n10) ten\n7) seven\n\n+ plus\n* star\n- minus"
    assert plain(Markdown(source, theme=THEME)) == [
        "4. fourth",
        "5. third",
        "",
        "10. ten",
        "11. seven",
        "",
        "- plus",
        "- star",
        "- minus",
    ]
    options = MarkdownOptions(preserve_ordered_list_markers=True)
    assert plain(Markdown(source, theme=THEME, options=options)) == [
        "4. fourth",
        "3. third",
        "",
        "10) ten",
        "7) seven",
        "",
        "+ plus",
        "* star",
        "- minus",
    ]


def test_list_continuation_lines_align_after_marker() -> None:
    assert plain(Markdown("10. alpha beta gamma delta epsilon", theme=THEME), 21) == [
        "10. alpha beta gamma",
        "    delta epsilon",
    ]


def test_lists_preserve_source_spacing_before_distinct_blocks() -> None:
    cases = [
        ("- item\n\nparagraph", ["- item", "", "paragraph"]),
        ("- item\n\n```py\nx = 1\n```", ["- item", "", "```py", "  x = 1", "```"]),
        ("- item\n\n> quote", ["- item", "", "│ quote"]),
    ]
    for source, expected in cases:
        assert plain(Markdown(source, theme=THEME)) == expected


def test_loose_list_paragraph_spacing() -> None:
    source = "1. first paragraph\n\n   second paragraph\n\n2. next"
    assert plain(Markdown(source, theme=THEME)) == [
        "1. first paragraph",
        "",
        "   second paragraph",
        "",
        "2. next",
    ]


def test_list_spacing_preprocessor_ignores_fenced_code_content() -> None:
    source = "```text\n- item\n\nparagraph\n```"
    lines = plain(Markdown(source, theme=THEME))

    assert lines == ["```text", "  - item", "", "  paragraph", "```"]
    assert "saber-tui-list-break" not in "".join(lines)


def test_code_blocks_highlighting_indent_and_spacing() -> None:
    seen: list[tuple[str, str | None]] = []

    def highlight(code: str, language: str | None) -> list[str]:
        seen.append((code, language))
        return [f"HL:{line}" for line in code.splitlines()]

    theme = MarkdownTheme(highlight_code=highlight, code_block_indent="| ")
    markdown = Markdown("before\n```python extra\nx = 1\n```\nafter", theme=theme)
    assert plain(markdown) == ["before", "", "```python extra", "| HL:x = 1", "```", "", "after"]
    assert seen == [("x = 1", "python")]


def test_streaming_partial_code_fences_keep_height_stable() -> None:
    cases = [
        ("```ts\nconst x = 1;\n``", ["```ts", "  const x = 1;", "```"]),
        ("```ts\n``", ["```ts", "", "```"]),
        ("````\n```", ["```", "", "```"]),
        ("~~~~~\n~~~~", ["```", "", "```"]),
    ]
    for source, expected in cases:
        assert plain(Markdown(source, theme=THEME)) == expected

    partial = Markdown("```ts\nconst x = 1;\n``", theme=THEME)
    complete = Markdown("```ts\nconst x = 1;\n```", theme=THEME)
    assert len(partial.render(80)) == len(complete.render(80))


def test_streaming_partial_fences_are_stable_inside_lists_and_quotes() -> None:
    cases = [
        ("- ```python\n  value = 1\n  ``", "- ```python\n  value = 1\n  ```"),
        ("> ```python\n> value = 1\n> ``", "> ```python\n> value = 1\n> ```"),
    ]
    for partial_source, complete_source in cases:
        partial = plain(Markdown(partial_source, theme=THEME))
        complete = plain(Markdown(complete_source, theme=THEME))
        assert partial == complete


def test_blockquotes_wrap_every_line_and_render_nested_blocks() -> None:
    markdown = Markdown("> quote with **bold** and `code` that wraps\n>\n> - item", theme=THEME)
    lines = markdown.render(24)
    content = [strip_ansi(line).rstrip() for line in lines if strip_ansi(line).rstrip()]
    assert all(line.startswith("│") for line in content)
    assert any("- item" in line for line in content)
    assert "\x1b[1m" in "".join(lines)
    assert "\x1b[33m" in "".join(lines)


def test_horizontal_rule_html_and_hard_breaks() -> None:
    markdown = Markdown("<thinking>visible</thinking>\n\n---\n\na  \nb", theme=THEME)
    lines = plain(markdown, 20)
    assert "<thinking>visible</thinking>" in "".join(lines)
    assert "─" * 20 in lines
    assert lines[-2:] == ["a", "b"]


def test_links_have_plain_fallback_without_duplicates() -> None:
    options = MarkdownOptions(hyperlinks=False)
    markdown = Markdown(
        "[click](https://example.com) https://bare.example user@example.com [mail](mailto:x@y.com)",
        theme=THEME,
        options=options,
    )
    output = " ".join(plain(markdown, 200))
    assert "click (https://example.com)" in output
    assert output.count("https://bare.example") == 1
    assert output.count("user@example.com") == 1
    assert "mailto:user@example.com" not in output
    assert "mail (mailto:x@y.com)" in output


def test_explicit_email_link_label_does_not_create_nested_osc8_link() -> None:
    markdown = Markdown(
        "[user@example.com](https://example.com)",
        theme=THEME,
        options=MarkdownOptions(hyperlinks=True),
    )
    output = "".join(markdown.render(80))
    assert output.count("\x1b]8;;https://example.com\x1b\\") == 1
    assert "\x1b]8;;mailto:user@example.com\x1b\\" not in output


def test_links_emit_osc8_when_enabled() -> None:
    markdown = Markdown(
        "[click](https://example.com)",
        theme=THEME,
        options=MarkdownOptions(hyperlinks=True),
    )
    output = "".join(markdown.render(80))
    assert "\x1b]8;;https://example.com\x1b\\" in output
    assert "\x1b]8;;\x1b\\" in output
    without_osc = re.sub(r"\x1b\]8;;[^\x1b]*\x1b\\", "", output)
    assert "(https://example.com)" not in without_osc


def test_default_style_is_restored_after_inline_code_and_fills_background() -> None:
    style = DefaultTextStyle(color=ansi("90"), bg_color=ansi("44"), italic=True)
    markdown = Markdown("thinking `code` after", 1, 1, THEME, style)
    lines = markdown.render(30)
    assert len(lines) == 3
    assert all(visible_width(line) == 30 for line in lines)
    output = "".join(lines)
    assert "\x1b[90m" in output
    assert "\x1b[3m" in output
    assert "\x1b[33m" in output
    assert "\x1b[44m" in output


def test_tables_render_wrap_and_fit_width() -> None:
    source = (
        "| Command | Description |\n"
        "| --- | --- |\n"
        "| npm install | Install all dependencies |\n"
        "| build | Build project |"
    )
    markdown = Markdown(source, theme=THEME)
    lines = markdown.render(30)
    plain_lines = [strip_ansi(line).rstrip() for line in lines]
    assert plain_lines[0].startswith("┌─")
    assert any("Command" in line for line in plain_lines)
    assert sum("┼" in line for line in plain_lines) == 2
    assert plain_lines[-1].startswith("└─")
    assert all(visible_width(line) <= 30 for line in lines)
    assert "Install all" in " ".join(plain_lines)


def test_extremely_narrow_table_falls_back_without_overflow() -> None:
    markdown = Markdown("| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |", theme=THEME)
    lines = markdown.render(5)
    assert lines
    assert all(visible_width(line) <= 5 for line in lines)


def test_marker_preservation_does_not_leak_annotations_into_paragraphs() -> None:
    source = "paragraph\n2. continuation\n8) still prose"
    markdown = Markdown(
        source,
        theme=THEME,
        options=MarkdownOptions(preserve_ordered_list_markers=True),
    )
    output = "\n".join(plain(markdown))

    assert output == source
    assert "\ue100" not in output
    assert "\ue101" not in output


def test_preserved_markers_stay_attached_to_quoted_and_outside_lists() -> None:
    markdown = Markdown(
        "> - quoted\n\n3) outside",
        theme=THEME,
        options=MarkdownOptions(preserve_ordered_list_markers=True),
    )
    assert plain(markdown) == ["│ - quoted", "", "3) outside"]


def test_preserve_backslash_escapes_option() -> None:
    source = r"Use \*literal\* and \~tilde"
    assert plain(Markdown(source, theme=THEME)) == ["Use *literal* and ~tilde"]
    options = MarkdownOptions(preserve_backslash_escapes=True)
    assert plain(Markdown(source, theme=THEME, options=options)) == [source]


def test_preserved_backslashes_are_restored_in_code_and_html() -> None:
    source = "`a\\*b`\n\n```text\nc\\*d\n```\n\n<span>e\\*f</span>"
    options = MarkdownOptions(preserve_backslash_escapes=True)
    output = "\n".join(plain(Markdown(source, theme=THEME, options=options)))

    assert "a\\*b" in output
    assert "c\\*d" in output
    assert "<span>e\\*f</span>" in output
    assert "\ue000" not in output
    assert "\ue001" not in output


def test_concurrent_text_update_does_not_commit_stale_render_cache(monkeypatch) -> None:
    markdown = Markdown("old text", theme=THEME)
    parser_started = threading.Event()
    parser_continue = threading.Event()
    original_parser = markdown_module._MARKDOWN

    def slow_parser(source: str):
        parser_started.set()
        assert parser_continue.wait(timeout=2)
        return original_parser(source)

    monkeypatch.setattr(markdown_module, "_MARKDOWN", slow_parser)
    rendered: list[list[str]] = []
    thread = threading.Thread(target=lambda: rendered.append(markdown.render(40)))
    thread.start()
    assert parser_started.wait(timeout=2)

    markdown.set_text("new text")
    parser_continue.set()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert markdown._cached_text is None
    assert plain(markdown, 40) == ["new text"]
    assert "old text" in strip_ansi(rendered[0][0])


def test_render_replaces_tabs_and_respects_padding_width() -> None:
    lines = Markdown("a\tb", 2, 1, THEME).render(12)
    assert len(lines) == 3
    assert strip_ansi(lines[1]).rstrip() == "  a   b"
    assert all(visible_width(line) == 12 for line in lines)


def test_padding_never_exceeds_narrow_render_width() -> None:
    markdown = Markdown("wide", padding_x=4, theme=THEME)
    for width in (0, 1, 2):
        lines = markdown.render(width)
        assert lines
        assert all(visible_width(line) <= width for line in lines)
