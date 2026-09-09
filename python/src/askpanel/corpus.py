"""Corpus loading, linting, and the cached system block.

The corpus is the feature: a set of markdown files the host writes in its users'
vocabulary. ``load_corpus`` joins them in filename order; ``lint_corpus`` catches the
mistakes that make a help assistant confidently wrong; ``system_blocks`` turns the text
into the cached system prompt prefix, byte-for-byte identical on every call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import prompts

CORPUS_SEPARATOR = "\n\n---\n\n"
CORPUS_GLOB = "*.md"

DEFAULT_BANNED_WORDS: tuple[str, ...] = (
    "endpoint",
    "database",
    "postgres",
    "jsonb",
    "migration",
    "alembic",
    "api",
    "backend",
    "frontend",
    "deploy",
    "env var",
)

#: Below this many characters the assembled prompt is unlikely to reach the provider's
#: minimum cacheable prefix; the linter warns (does not fail).
RECOMMENDED_MIN_CHARS = 8000

#: Rough tokens-per-character ratio for English prose. An estimate, not a count.
CHARS_PER_TOKEN = 4


def corpus_files(corpus_dir: str | Path) -> list[Path]:
    """The markdown files of a corpus directory, sorted by filename."""
    d = Path(corpus_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"corpus directory not found: {d}")
    return sorted(p for p in d.glob(CORPUS_GLOB) if p.is_file())


def load_corpus(corpus_dir: str | Path) -> str:
    """Read every ``*.md`` in ``corpus_dir`` in filename order, joined by a separator.

    Files are stripped of surrounding whitespace so the result is stable across editors.
    Returns ``""`` for an empty directory (the module then reports itself disabled).
    """
    texts = [p.read_text(encoding="utf-8").strip() for p in corpus_files(corpus_dir)]
    return CORPUS_SEPARATOR.join(t for t in texts if t)


@dataclass(frozen=True)
class LintIssue:
    """One finding from ``lint_corpus``. ``severity`` is ``"error"`` or ``"warning"``."""

    file: str
    line: int  # 1-based; 0 when the finding is about the whole file or corpus
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        return f"{where}: {self.severity}: {self.message}"


def _banned_pattern(words: tuple[str, ...] | list[str]) -> re.Pattern[str] | None:
    words = [w.strip() for w in words if w and w.strip()]
    if not words:
        return None
    alts = [re.escape(w).replace(r"\ ", r"\s+") for w in words]
    return re.compile(r"(?<![\w-])(" + "|".join(alts) + r")(?![\w-])", re.IGNORECASE)


def lint_text(
    text: str,
    *,
    filename: str = "<text>",
    banned: tuple[str, ...] | list[str] = DEFAULT_BANNED_WORDS,
) -> list[LintIssue]:
    """Lint one file's text. Rules:

    - the first non-empty line must be a markdown title (``# ...``)
    - the file must not be empty
    - no banned implementation words (whole-word, case-insensitive)
    """
    issues: list[LintIssue] = []
    lines = text.splitlines()
    first = next(((i, ln) for i, ln in enumerate(lines, start=1) if ln.strip()), None)
    if first is None:
        issues.append(LintIssue(filename, 0, "file is empty"))
        return issues
    line_no, line = first
    if not re.match(r"^#\s+\S", line):
        issues.append(
            LintIssue(
                filename,
                line_no,
                "first line must be a title (`# What this file is about`)",
            )
        )
    pattern = _banned_pattern(banned)
    if pattern is not None:
        for i, ln in enumerate(lines, start=1):
            for m in pattern.finditer(ln):
                issues.append(
                    LintIssue(
                        filename,
                        i,
                        f"banned word {m.group(1)!r}: users don't say this; "
                        "describe what they see instead",
                    )
                )
    return issues


def lint_corpus(
    corpus_dir: str | Path,
    *,
    banned: tuple[str, ...] | list[str] = DEFAULT_BANNED_WORDS,
    min_chars: int = RECOMMENDED_MIN_CHARS,
) -> list[LintIssue]:
    """Lint every file in a corpus directory. Errors mean the corpus should not ship.

    Warnings (``severity == "warning"``): no files at all; total size below
    ``min_chars`` (prompt caching probably will not engage).
    """
    files = corpus_files(corpus_dir)
    issues: list[LintIssue] = []
    if not files:
        return [LintIssue(str(corpus_dir), 0, "no *.md files found", "warning")]
    total = 0
    for p in files:
        text = p.read_text(encoding="utf-8")
        total += len(text.strip())
        issues.extend(lint_text(text, filename=p.name, banned=banned))
    if total < min_chars:
        issues.append(
            LintIssue(
                str(corpus_dir),
                0,
                f"corpus is {total} characters; aim above {min_chars} so prompt caching engages",
                "warning",
            )
        )
    return issues


def has_errors(issues: list[LintIssue]) -> bool:
    return any(i.severity == "error" for i in issues)


def estimate_tokens(text: str) -> int:
    """A rough token estimate (characters / 4). Good enough to see whether caching engages."""
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


@lru_cache(maxsize=64)
def corpus_block_text(corpus_text: str, product_name: str) -> str:
    """The text of the cached block: preamble + corpus + postamble."""
    return (
        prompts.CORPUS_PREAMBLE.format(product_name=product_name)
        + corpus_text.strip()
        + prompts.CORPUS_POSTAMBLE
    )


@lru_cache(maxsize=64)
def _corpus_block(corpus_text: str, product_name: str) -> dict:
    return {
        "type": "text",
        "text": corpus_block_text(corpus_text, product_name),
        "cache_control": {"type": "ephemeral"},
    }


@lru_cache(maxsize=64)
def _instructions_block(instructions: str) -> dict:
    return {"type": "text", "text": instructions}


def system_blocks(corpus_text: str, product_name: str, instructions: str) -> list[dict]:
    """The system prompt as provider blocks.

    Block 0 is the corpus with ``cache_control: ephemeral``; it depends only on the
    corpus text and product name, so it is byte-identical across help, interview, and
    summarize requests and across turns. Block 1 is the (uncached) mode instructions.
    Results are memoised; callers get fresh list copies of the same dict objects and
    must not mutate them.
    """
    return [_corpus_block(corpus_text, product_name), _instructions_block(instructions)]


def assembled_prompt(blocks: list[dict]) -> str:
    """Flatten system blocks to one string (for ``askpanel prompt`` and tests)."""
    return "\n\n".join(b["text"] for b in blocks)


__all__ = [
    "CORPUS_SEPARATOR",
    "DEFAULT_BANNED_WORDS",
    "RECOMMENDED_MIN_CHARS",
    "LintIssue",
    "corpus_files",
    "load_corpus",
    "lint_text",
    "lint_corpus",
    "has_errors",
    "estimate_tokens",
    "corpus_block_text",
    "system_blocks",
    "assembled_prompt",
]
