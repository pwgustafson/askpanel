"""``askpanel`` command line: lint a corpus, print the assembled prompt, run the demo."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import corpus as corpus_mod
from . import prompts


def _cmd_lint(args: argparse.Namespace) -> int:
    banned = tuple(args.ban) if args.ban else corpus_mod.DEFAULT_BANNED_WORDS
    if args.allow:
        banned = tuple(w for w in banned if w.lower() not in {a.lower() for a in args.allow})
    try:
        issues = corpus_mod.lint_corpus(args.dir, banned=banned, min_chars=args.min_chars)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    for issue in issues:
        print(issue)
    errors = sum(1 for i in issues if i.severity == "error")
    warnings = len(issues) - errors
    files = len(corpus_mod.corpus_files(args.dir))
    print(f"{files} file(s), {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def _cmd_prompt(args: argparse.Namespace) -> int:
    try:
        text = corpus_mod.load_corpus(args.dir)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    if args.mode == "help":
        instructions = prompts.help_instructions(args.product)
    elif args.mode == "interview":
        instructions = prompts.interview_instructions(args.product)
    else:
        instructions = prompts.summarize_instructions(args.product)
    blocks = corpus_mod.system_blocks(text, args.product, instructions)
    assembled = corpus_mod.assembled_prompt(blocks)
    print(assembled)
    corpus_chars = len(blocks[0]["text"])
    print(
        f"\n--- {len(assembled)} characters, ~{corpus_mod.estimate_tokens(assembled)} tokens "
        f"(cached corpus block: {corpus_chars} characters, "
        f"~{corpus_mod.estimate_tokens(blocks[0]['text'])} tokens; estimate = chars/4)",
        file=sys.stderr,
    )
    if len(text) < corpus_mod.RECOMMENDED_MIN_CHARS:
        print(
            f"warning: corpus is {len(text)} characters; aim above "
            f"{corpus_mod.RECOMMENDED_MIN_CHARS} so prompt caching engages",
            file=sys.stderr,
        )
    return 0


def _find_demo_dir(explicit: str | None) -> Path | None:
    if explicit:  # an explicit --dir is authoritative; don't fall back to guessing
        d = Path(explicit)
        return d if (d / "server.py").is_file() else None
    candidates: list[Path] = []
    if os.environ.get("ASKPANEL_DEMO_DIR"):
        candidates.append(Path(os.environ["ASKPANEL_DEMO_DIR"]))
    here = Path.cwd()
    for base in [here, *here.parents]:
        candidates.append(base / "examples" / "demo")
    pkg = Path(__file__).resolve()
    for base in pkg.parents:
        candidates.append(base / "examples" / "demo")
    for c in candidates:
        if (c / "server.py").is_file():
            return c
    return None


def _cmd_serve_demo(args: argparse.Namespace) -> int:
    demo = _find_demo_dir(args.dir)
    if demo is None:
        print(
            "Could not find examples/demo/server.py. Run this from a checkout of the "
            "askpanel repository, pass --dir <path-to-examples/demo>, or set "
            "ASKPANEL_DEMO_DIR.",
            file=sys.stderr,
        )
        return 2
    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is not installed. Install with: pip install 'askpanel[demo]'", file=sys.stderr
        )
        return 2
    sys.path.insert(0, str(demo))
    os.environ.setdefault("ASKPANEL_DEMO_DIR", str(demo))
    print(f"Serving demo from {demo} on http://{args.host}:{args.port}")
    if not (demo / "web" / "dist" / "index.html").is_file():
        print(
            "note: examples/demo/web/dist is missing; the API works but the page is "
            "not built. Run `npm install && npm run build` in examples/demo/web.",
            file=sys.stderr,
        )
    uvicorn.run("server:app", host=args.host, port=args.port, reload=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="askpanel", description="AskPanel corpus tools")
    sub = p.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="check a corpus directory; exit 1 on errors")
    lint.add_argument("dir")
    lint.add_argument("--ban", action="append", help="replace the banned word list (repeatable)")
    lint.add_argument("--allow", action="append", help="remove a word from the banned list")
    lint.add_argument("--min-chars", type=int, default=corpus_mod.RECOMMENDED_MIN_CHARS)
    lint.set_defaults(func=_cmd_lint)

    prompt = sub.add_parser("prompt", help="print the assembled system prompt and a token estimate")
    prompt.add_argument("dir")
    prompt.add_argument("--product", default="the product", help="product name used in the prompt")
    prompt.add_argument("--mode", choices=["help", "interview", "summarize"], default="help")
    prompt.set_defaults(func=_cmd_prompt)

    demo = sub.add_parser("serve-demo", help="run the example app (needs uvicorn)")
    demo.add_argument("--dir", help="path to examples/demo (auto-detected in a checkout)")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8765)
    demo.set_defaults(func=_cmd_serve_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
