from __future__ import annotations

from askpanel import corpus as c
from askpanel import prompts


def write(tmp_path, name, text):
    (tmp_path / name).write_text(text, encoding="utf-8")


def test_load_corpus_filename_order_and_separator(tmp_path):
    write(tmp_path, "10-later.md", "# Later\n\nlater text\n")
    write(tmp_path, "02-early.md", "\n# Early\n\nearly text\n\n")
    write(tmp_path, "notes.txt", "ignored")
    assert c.load_corpus(tmp_path) == "# Early\n\nearly text\n\n---\n\n# Later\n\nlater text"


def test_load_corpus_empty_dir(tmp_path):
    assert c.load_corpus(tmp_path) == ""


def test_lint_title_required(tmp_path):
    write(tmp_path, "a.md", "Sharing\n\nsome text " * 100)
    issues = c.lint_corpus(tmp_path)
    assert any("title" in i.message for i in issues)
    write(tmp_path, "a.md", "\n\n# Sharing\n\n" + "some text " * 1000)
    assert not c.has_errors(c.lint_corpus(tmp_path))


def test_lint_empty_file(tmp_path):
    write(tmp_path, "a.md", "  \n")
    assert any("empty" in i.message for i in c.lint_corpus(tmp_path))


def test_lint_banned_words_whole_word_case_insensitive():
    text = "# T\n\nThe API returns rows. Contact the Backend. An apiary is fine. Set an env  var."
    issues = c.lint_text(text)
    words = sorted(i.message.split("'")[1] for i in issues)
    assert words == ["API", "Backend", "env  var"]
    assert all(i.line == 3 for i in issues)
    assert c.lint_text("# T\n\nendpoints and endpoint-ish") == []  # not whole words
    assert c.lint_text("# T\n\nthe endpoint here")[0].message.startswith("banned word 'endpoint'")


def test_lint_custom_banned_list():
    text = "# T\n\nOur database is fine but the widget is not."
    assert c.lint_text(text, banned=["widget"])[0].message.startswith("banned word 'widget'")
    assert c.lint_text(text, banned=[]) == []


def test_lint_size_warning_and_no_files(tmp_path):
    assert c.lint_corpus(tmp_path)[0].severity == "warning"
    write(tmp_path, "a.md", "# Short\n\ntiny")
    issues = c.lint_corpus(tmp_path)
    assert [i.severity for i in issues] == ["warning"]
    assert "8000" in issues[0].message
    assert not c.has_errors(issues)
    assert c.lint_corpus(tmp_path, min_chars=1) == []


def test_lint_issue_str():
    assert str(c.LintIssue("a.md", 3, "m")) == "a.md:3: error: m"
    assert str(c.LintIssue("dir", 0, "m", "warning")) == "dir: warning: m"


def test_system_blocks_byte_stable_and_shared_prefix():
    ins_help = prompts.help_instructions("Orchard")
    ins_int = prompts.interview_instructions("Orchard")
    b1 = c.system_blocks("# Doc\n\ntext", "Orchard", ins_help)
    b2 = c.system_blocks("# Doc\n\ntext", "Orchard", ins_help)
    b3 = c.system_blocks("# Doc\n\ntext", "Orchard", ins_int)
    assert b1 == b2
    assert b1 is not b2  # fresh list
    assert b1[0] is b2[0] is b3[0]  # same cached corpus block object across modes
    assert b1[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in b1[1]
    assert b1[0]["text"].encode() == b2[0]["text"].encode()
    assert b1[1]["text"] != b3[1]["text"]
    assert b1[0]["text"].startswith("You are the in-app help assistant for Orchard")
    assert "<documentation>\n# Doc\n\ntext\n</documentation>" in b1[0]["text"]


def test_system_blocks_change_with_inputs():
    ins = prompts.help_instructions("Orchard")
    a = c.system_blocks("# A", "Orchard", ins)
    b = c.system_blocks("# B", "Orchard", ins)
    d = c.system_blocks("# A", "Pear", prompts.help_instructions("Pear"))
    assert a[0]["text"] != b[0]["text"]
    assert a[0]["text"] != d[0]["text"]


def test_estimate_tokens():
    assert c.estimate_tokens("") == 0
    assert c.estimate_tokens("abcd") == 1
    assert c.estimate_tokens("abcde") == 2


def test_prompt_boundaries_present():
    h = prompts.help_instructions("Orchard", extra_instructions="Never discuss pricing.")
    for phrase in (
        "no access to the product's data",
        "hold that line",
        "Never promise",
        "Never reveal",
    ):
        assert phrase in h
    assert "Additional guidance from the Orchard team:\nNever discuss pricing." in h
    i = prompts.interview_instructions("Orchard", ["Q1?", "Q2?"], max_turns=4)
    assert "1. Q1?\n2. Q2?" in i
    assert "one question per turn" in i
    assert "turn 4" in i
    assert "documentation already covers" in i
    s = prompts.summarize_instructions("Orchard")
    for f in ('"title"', '"problem"', '"workaround"', '"outcome"', '"already_supported"'):
        assert f in s
    assert "feature request" in s
    h = prompts.summarize_instructions("Orchard", "help")
    assert "summarize a question" in h and "what the assistant was able to answer" in h.lower()
    assert "Never ask the same question twice" in i
    assert "what done would look like" in i
    assert "{" not in h.replace("{", "", 0) or "{product_name}" not in h
