# The sketch

One hand-drawn image of the mechanism the PR changes. It shows the overview a reviewer needs before reading the diff: what used to happen, where it went wrong, and what happens now. It does not list every file, call site, or test.

## Pick a drawing

Pick the one drawing below whose shape matches the story you wrote in your notes. Each has an example scene in `examples/`. Copy the closest example and change it. Do not combine two drawings in one image.

| Drawing | Use when the PR | Example |
|---|---|---|
| Rewire | sends the same things somewhere new: callers to a new role, events to a queue, requests to a new handler | [rewire.json](examples/rewire.json) |
| To scale | fixes a size, a limit, or a position: a file past a cut, a payload past a limit, a section placed too late in a file | [to-scale.json](examples/to-scale.json) |
| Flow | adds, removes, or reorders a step that runs every time: a new stage, a skipped stage, a gate that now stops bad input | [flow.json](examples/flow.json) |
| Check | adds a check, lint, test, or evaluator that judges something after the fact: a log, a recording, a file | [check.json](examples/check.json) |
| Bars | reports or changes a measured number: eval results, latency, pass counts, sizes across several runs or platforms | [bars.json](examples/bars.json) |

Ask these in order and take the first yes:

1. Is the story a number that went up or down? Draw **Bars**.
2. Did something break because it sat past a limit or in the wrong place inside one thing? Draw **To scale**, even when the fix also moves text into new files.
3. Does the PR add a tool that judges a record, rather than change what runs? Draw **Check**. Draw the record the tool reads, cross out the spot it now catches, and show its verdicts in a brace.
4. Do the same callers now go somewhere else? Draw **Rewire**.
5. Otherwise draw **Flow**. If even a flow would only restate the story sentences, skip the sketch and say so in your reply.

## Rules

1. **Name the things, and count only crowds.** Draw up to four like things as separate boxes with their real names, such as `auth`, `billing`, `search`. Draw five or more as one stacked box with a count, such as `6 webhook handlers`, with their kinds on its second line. Never draw one box per call site.
2. **Give the changed thing one name.** When the PR moves or resizes something, label it the same way in the old picture and the new one, so the eye can follow it.
3. **Cross out the old path.** Draw what used to happen in gray. Put a ✕ on the arrow or step that went wrong, and next to it a short gloss with the symptom, such as `upload fails`.
4. **Draw the new path in the accent tone.** Use `accent` only for what this PR adds or changes. Everything unchanged stays `ink` or `gray`.
5. **Put the why on an element, in plain words.** The gloss next to the old target says what it meant to a person, such as `= request waits 9 s` or `app ran on old schema`. Write it so a reader who has never opened this repository understands it. Status codes, enum values, and internal terms such as `ERR_PARTIAL_WRITE` or `shard window` stay out of the image. The comment can name them.
6. **Keep one number per side.** Show the number the why depends on, such as the limit that cut the file. Leave other sizes, budgets, and counts to the comment.
7. **Draw sizes to scale** when the story is about a size or a limit. Pick one scale, such as 0.01 px per byte, and write it in your notes.
8. **Use real names.** Labels use the names in the diff: role names, file names, model names, limits. Never invent an example value.
9. **Keep words few.** Labels name things. Gloss words explain them, and the tool allows at most 12. Captions, SHAs, and caveats belong in the comment, not the image.
10. **No headline, legend, or footer inside the image.** The story sentences above the image do that job.

## Write the scene

A scene is JSON: a `story`, a `height` (at most 420), and a list of `shapes`. Write it to `scene.json` in one writable work folder outside the skill. Keep `sketch.png`, `story.txt`, and `recap.md` in that same folder.

Write the `story` first, from your notes. The tool fails the scene when the drawing leaves any of it out.

| Field | Holds | The tool checks |
|---|---|---|
| `drawing` | The catalog drawing: `rewire`, `to scale`, `flow`, `check`, or `bars` | It is one of these five values; every drawing except `bars` has a ✕ |
| `seen` | A sentence quoted from the PR body, a linked issue, a commit, or a review that says what a person saw go wrong, such as `"Checkout pages showed prices from an hour ago."` | It is present |
| `symptom` | That sentence restated in six plain words or fewer, as the gloss beside the ✕, such as `stale for 1 h`. Name what the person saw, not the rule that was broken or the check that was skipped | Some text in the drawing holds it |
| `number` | The one number the why depends on, such as the limit that cut the file: `10 MB`. Optional, except in a `to scale` drawing | Some text holds it, and a `to scale` drawing has a line for it |
| `added` | Each part the PR adds or moves, named as rule 1 says: up to four names, or one `6 webhook handlers` count | Each one is drawn |

The canvas is 782 px wide, the width of a GitHub comment. `x` and `y` are in CSS pixels from the top left. A text `y` is its baseline.

| Kind | Fields | Draws |
|---|---|---|
| `box` | `x`, `y`, `w`, `h`, `label`, optional `sub`, `stack` (2 or 3 for a group), `size` (`label`, `big`, `sub`), `tone` | A box with a centered label |
| `page` | `x`, `y`, `w`, `h`, optional `title` above it, `label`, `bands` (`[{y0, y1, label, tone}]`, offsets from the page top), `lines` (false hides the text lines), `tone` | A document, with highlighted regions |
| `arrow` | `from`, `to`, optional `bend` (control point), `crossed` (true draws ✕ at its middle), `head` (false hides it), `tone` | A curved arrow |
| `line` | `from`, `to`, optional `dashed`, `tone` | A straight line, such as a cut or a limit |
| `brace` | `x`, `y0`, `y1`, `rows` (`[[key, value, valueTone]]`), optional `keyWidth`, `tone` | A brace with one row per value, such as per harness or per region |
| `cross` | `x`, `y` | A ✕ on its own |
| `text` | `x`, `y`, `text`, optional `size` (`note`, `sub`, `label`), `tone`, `anchor`, `words` (false for a label that is not a gloss) | Free text. It counts as gloss unless `words` is false |
| `underline` | `from`, `to`, optional `tone` | A hand-drawn underline |

Tones are `ink`, `gray`, `accent`, and `faint`.

## Render and check

Run the tool from the work folder. Replace `<skill>` with the absolute path to this skill's directory:

```sh
bun "<skill>/scripts/sketch/sketch.mjs" scene.json sketch.png
```

It prints a JSON report and exits 0 when the image is clean, 1 when it lists `problems`, and 2 when it could not render. It reports text under 16 px, text off the canvas, text that does not fit its box, overlapping text, a line through text, more than 12 gloss words, identifier-style words such as `snake_case`, `ALLCAPS`, or `camelCase`, characters the hand-drawn font cannot draw, such as `→` or `≤`, and any part of the `story` that the drawing leaves out. File names such as `order-check.py` pass. Move shapes and rewrite words until `problems` is empty.

Then open `sketch.png` and look at it yourself. The tool cannot see a crowded corner, an arrow that points the wrong way, or a ✕ that hides its arrow. Fix what you see and render again.

Last, have another model read it as a reviewer would. Put the two story sentences in `story.txt` next to the PNG, then give a fresh reader only [the reader prompt](reader.md), `story.txt`, and the PNG. Pick a reader from a different model family when you can:

Run both commands from the same work folder that holds `sketch.png` and `story.txt`, using the same absolute `<skill>` path:

- On Claude Code, run `codex exec -s read-only --skip-git-repo-check -i sketch.png -- - < "<skill>/references/reader.md"` when `codex` is on PATH.
- On Codex, run `claude -p --model sonnet --allowedTools Read < "<skill>/references/reader.md"` when `claude` is on PATH.
- Otherwise use a subagent of your own family, and say so in your reply.

Then fix the sketch from its answer. Change at most two labels per read, and make every word you add replace one, so the sketch gets clearer instead of busier:

- When its **Symptom** line is "no" or names something other than your `seen` sentence, rewrite the symptom gloss first.
- Rewrite a gloss on its **Words to guess** list in plain words. A name from the diff, such as a file or role, can stay when the story sentences name it too.
- Draw a **Still wanted** fact only when it is the why or a part the PR adds and the sketch does not show it at all.

Render again and repeat the read once. Report the reader's model and what you changed.

## Setup

The tool needs Bun 1.4.0 or later. Bun 1.3.14 and older cannot read its `bun.lock` and fail with `Unknown lockfile version`, so the tool exits 2. With an older Bun, run the same command through `npx bun@1.4.0` in place of `bun`, which needs Node and network access. When that is not possible, skip the sketch and say why in your reply. `npm ci` does not work here, because the folder has no `package-lock.json`.

Its pinned dependencies are in [its package.json](../scripts/sketch/package.json): Rough.js for the strokes, opentype.js to measure text, and resvg to write the PNG. On its first run, and after `package.json` or `bun.lock` changes, the tool runs `bun install --frozen-lockfile`, which needs network access. It first tries its own folder. If installation there fails, it creates a fresh private temporary folder and installs there for that invocation. None of the packages starts a browser. A sandbox needs a writable output folder and either a writable skill folder or a writable temporary folder for the dependencies.

Hermes v0.22.4 has run the tool and viewed the PNG with `vision_analyze`. Follow the skill's [sketch fallback](../SKILL.md#draw-the-sketch) when either capability is unavailable.

When the tool exits 2, read its message. If it cannot install a package or write the PNG, skip the sketch and say why in your reply.
