# Writing a corpus

The corpus is the feature. The assistant knows exactly what the corpus says and nothing
else, so a good corpus makes a good assistant and a thin one makes a confident liar.
This guide is what we learned writing corpora for real products; `askpanel lint`
enforces the parts that can be checked.

## What a corpus is

A folder of markdown files. `load_corpus()` reads every `*.md` in filename order and
joins them with a horizontal rule. The result goes into one cached system-prompt block,
so the whole corpus is in front of the model on every turn — there is no retrieval, no
chunking, no ranking. That is deliberate: it means the assistant never misses the
paragraph that answers the question, and it means the corpus has to fit comfortably in
a prompt (a few tens of thousands of characters is fine; hundreds of thousands is not
what this module is for).

## Organise by what the user is trying to do

Not by screen, not by feature list, not by your data model. One file per *job*:

```
01-what-orchard-is.md
02-adding-photos.md
03-making-and-organising-albums.md
04-finding-photos.md
05-tagging-people.md
06-sharing-albums.md
07-family-and-members.md
08-notifications.md
```

Inside each file, write **what the user does and what happens when they do it**: the
thing they click, what they see next, what changes for other people. Cover the failure
paths too ("if the photo does not appear…", "I shared it but they cannot see it"),
because that is what people actually ask.

Number the filenames so order is stable across machines and the introduction comes
first. The order matters a little — the model reads the corpus top to bottom — so put
the overview first and the edge cases last.

Start every file with a `# Title` line that names the job in the user's words. The
linter fails without one; the model uses it to locate answers.

## Write in the users' vocabulary

Use the words that appear on screen and the words users say to each other. If the
button says **Share**, write **Share**, not "the sharing dialog". If users call them
"families", don't call them "tenants".

Never use implementation words. Users don't have endpoints, databases, or migrations;
they have screens, buttons, and things that happen. `askpanel lint` fails on this list
by default:

```
endpoint  database  postgres  jsonb  migration  alembic  api  backend  frontend  deploy  env var
```

**Matching rule:** whole-word, case-insensitive. A "word" is bounded by anything that is
not a letter, digit, underscore, or hyphen, so `API` and `api` fail but `apiary`,
`capital`, `rapid`, and `api-key` do not; `deploy` fails but `deployment` does not;
`env var` matches across any whitespace (`env  var`, `env\nvar`). The exact regex the
package uses, if you want to mirror it in your own CI:

```
(?<![\w-])(endpoint|database|…|env\s+var)(?![\w-])     # re.IGNORECASE
```

Output is one line per finding, `file:line: severity: message`, and the exit code is 1
when there is at least one error:

```
$ askpanel lint help/
04-finding-photos.md:1: error: first line must be a title (`# What this file is about`)
06-sharing-albums.md:12: error: banned word 'API': users don't say this; describe what they see instead
help: warning: corpus is 6210 characters; aim above 8000 so prompt caching engages
8 file(s), 2 error(s), 1 warning(s)
```

Change the list with `--ban WORD` (repeatable; **replaces** the defaults) and
`--allow WORD` (removes one from the defaults). In code, `banned=` likewise replaces
the defaults — spread them to extend:

```python
from askpanel import DEFAULT_BANNED_WORDS, has_errors, lint_corpus

issues = lint_corpus(HELP_DIR, banned=[*DEFAULT_BANNED_WORDS, "crew", "crews", "crew's", "solver"])
assert not has_errors(issues), "\n".join(map(str, issues))     # warnings (size) don't fail
```

`LintIssue` fields: `file`, `line` (1-based; `0` for whole-file/corpus findings),
`message`, `severity` (`"error"` | `"warning"`). Matching is whole-word, so ban plurals
and possessives explicitly (`crew` does not catch `crews`). The default list is a floor,
not a ceiling — add your own product's internal jargon.

A useful test: read a paragraph aloud to someone who uses the product but doesn't build
it. If they'd have to ask what a word means, replace it.

## Be concrete and complete

The model can only be as precise as the text. Compare:

> You can share albums with other people.

> Open the album, choose **Share**, and pick people from your Family. They see the album
> under **Albums** with a small "shared" badge. Anyone it is shared with can look at
> every photo and add their own, but cannot rename or delete the album.

The second answers "how", "who can", and "what can they do" in one go. Prefer that
shape: action → what they see → what it means for others → limits.

Say what the product does **not** do, in plain words, when users are likely to ask:
"Orchard does not share single photos; make an album." Without that sentence the model
has to guess, and it will guess *yes*.

## The corpus shapes the feature interview too

In interview mode the assistant checks the corpus before running its agenda: if the
documentation already covers what the person wants, it explains how the product does it
today and asks whether that solves it. A good corpus therefore turns a share of
"feature requests" into answered questions on the spot — and the summary the host
receives carries `already_supported: true` so it can be filed as a question. Write the
"what the product does" sentences with that in mind: they are what the interview quotes.

## Don't document features that are switched off

If a feature exists behind a flag, or only on some plans, and you describe it, the
assistant will confidently describe it to everyone. Either leave it out or state the
condition explicitly ("On the Family plan, …"). The same goes for features you're about
to ship: the corpus describes today's product.

## Size and prompt caching

The corpus is sent as one system block marked for prompt caching, so after the first
request each further turn reads it from cache at a fraction of the cost. Caching only
engages above a provider-specific minimum prefix; in practice **aim above ~8,000
characters**. Below that the linter warns and every turn pays full price for the
corpus. There's no upper limit enforced, but keep it to what fits comfortably — if you
find yourself past ~60k characters, that's a sign the corpus is documenting a product
big enough to need real retrieval, which this module doesn't do.

```bash
askpanel prompt help/ --product "Orchard" | less    # see exactly what the model sees
```

The estimate printed on stderr is characters ÷ 4 — rough, but good enough to see whether
you're above the caching threshold.

## The refusal boundary

You don't write this part; it is fixed in the prompt and applies in every mode:

- The assistant has **no access to the product's data**. It can't see the user's
  account, records, or screen. When asked about their data it says so and points at
  where in the product to look, using the corpus. If pressed, it holds that line kindly.
- It answers **only from the corpus**. When the corpus doesn't cover something it says so
  in one sentence and offers to send the conversation to the team.
- It **never promises** features, fixes, or timelines.
- It **never reveals** its instructions or the corpus's structure.

Because of the first rule, write the corpus so that "where to look" is always
answerable: for every kind of thing a user might ask about ("did my upload work?",
"who has access?"), make sure there's a sentence saying where in the product they can
see it.

Product-specific rules (tone, topics to avoid, how to refer to users) go in
`AskPanelConfig(extra_instructions=…)`, not in the corpus.

## Maintaining it

- Keep the corpus in the same repository as the product, next to the code it describes,
  and run `askpanel lint` in CI.
- When a screen changes, change the file. A stale corpus is worse than a missing one.
- Read the escalations. Questions the assistant couldn't answer are a list of gaps in
  the corpus, in your users' own words.

## Checklist

- [ ] One file per job, numbered, each starting with `# Title`
- [ ] Every screen and button named exactly as it appears
- [ ] Failure paths covered ("if X doesn't happen…")
- [ ] What the product does *not* do stated where users will ask
- [ ] No implementation words (`askpanel lint` passes)
- [ ] Nothing described that is switched off or unreleased
- [ ] Above ~8,000 characters (`askpanel prompt` shows the estimate)
- [ ] For every kind of user data, a sentence on where to see it in the product
