from __future__ import annotations

from askpanel.cli import main


def test_lint_cli(tmp_path, capsys):
    (tmp_path / "01-a.md").write_text("# Good\n\n" + "fine words " * 900)
    assert main(["lint", str(tmp_path)]) == 0
    (tmp_path / "02-b.md").write_text("no title\n\nuses the database\n")
    assert main(["lint", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "02-b.md:1: error: first line must be a title" in out
    assert "02-b.md:3: error: banned word 'database'" in out
    assert main(["lint", str(tmp_path), "--allow", "database"]) == 1  # title error remains
    assert main(["lint", str(tmp_path / "missing")]) == 2


def test_prompt_cli(tmp_path, capsys):
    (tmp_path / "01-a.md").write_text("# Good\n\nhello")
    assert main(["prompt", str(tmp_path), "--product", "Orchard", "--mode", "interview"]) == 0
    captured = capsys.readouterr()
    assert "help assistant for Orchard" in captured.out
    assert "Mode: feature request interview" in captured.out
    assert "tokens" in captured.err
    assert "warning: corpus is" in captured.err


def test_serve_demo_missing_dir(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASKPANEL_DEMO_DIR", raising=False)
    assert main(["serve-demo", "--dir", str(tmp_path / "nope")]) == 2
    assert "Could not find" in capsys.readouterr().err
