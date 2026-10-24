# Credits

`pr-recap` is pstack's own skill. Six MIT-licensed projects shaped its rules, it vendors one OFL-licensed font, and its sketch tool installs three npm packages. This file carries the notices those sources require. It names each rule the skill adapted, and it quotes a source only where `SKILL.md` or a reference file copies its words.

## Kent C. Dodds, `kcd-skills` `visual-recap`

Source: https://github.com/kentcdodds/kcd-skills/tree/113d0df108995736a840d2fde56fe1c457709038/skills/visual-recap (commit `113d0df1`, read 2026-10-20), files `SKILL.md` and [block-format.md](https://github.com/kentcdodds/kcd-skills/blob/113d0df108995736a840d2fde56fe1c457709038/skills/visual-recap/references/block-format.md).

Adapted: one marker-delimited block whose collapsed `<details>` element carries the risk, the base and head SHAs, and the parts the change touches. The recap is rebuilt after a push that changes the diff, and its claims come from the diff instead of session memory. The block layout rule about blank lines comes from `block-format.md` line 5, "Leave a blank line after `<summary>` and around every fence", which `references/block.md` extends to lists.

Copied: "It does not replace reading the diff." (`SKILL.md` line 17), in the opening paragraph of `SKILL.md`.

Copyright (c) 2026 Kent C. Dodds. MIT License.

## r13v, `pi-feature-dev` `visual-recap`

Source: https://github.com/r13v/pi-feature-dev/blob/c4b26e3c8cb55a3cd85825348d668aa53f742240/skills/visual-recap/SKILL.md (commit `c4b26e3c`, read 2026-10-20).

Adapted: the risk levels in `references/block.md` paraphrase the Risk table and the sentences after it (lines 64 to 70).

Copyright (c) 2026 pi-feature-dev contributors. MIT License.

## Builder.io, `skills` `visual-recap`

Source: https://github.com/BuilderIO/skills/blob/20ff8a101fe8300e44cb3b2d570cb93c7580e1b9/skills/visual-recap/SKILL.md (commit `20ff8a10`, dated 2026-10-14, read 2026-10-20).

Adapted: skip a small or obvious diff (lines 56 to 58), build every factual block from the real diff and never infer or invent it (lines 501 to 502), and never copy a secret into the recap (lines 517 to 520).

Copied: "credential-looking" and the `<redacted>` placeholder (lines 518 and 520), in the secret rule of `SKILL.md`.

Copyright (c) 2026 Builder.io. MIT License.

## Nico Bailon, `visual-explainer`

Source: https://github.com/nicobailon/visual-explainer/tree/5f378868e0ea745a6284b51e710c390f0c76f72c/plugins/visual-explainer (commit `5f378868`, v0.14.0, dated 2026-10-19, read 2026-10-20), files `SKILL.md`, `commands/diff-review.md`, and `commands/fact-check.md`.

Adapted: state that reads without color (line 33), which the sketch applies as gray, ✕, and accent. The claim check before posting follows `commands/fact-check.md` lines 8 to 10.

Copied: "Do not invent a rationale." (`commands/diff-review.md` line 10), in the block rules of `SKILL.md`. The four statuses "verified, corrected, unsupported, or unverifiable" (`commands/fact-check.md` line 9), in the claim check of `SKILL.md`.

Copyright (c) 2025 Nico Bailon. MIT License.

## Jo Van Eyck, `skills` `c4-diff`

Source: https://github.com/jovaneyck/skills/blob/f2de8f7042a5125116ed27627fc7320b73048469/skills/engineering/c4-diff/SKILL.md (commit `f2de8f70`, read 2026-10-20).

Adapted: evidence for every changed element (line 180) and "If you can't point to the code, don't draw it." (line 48), which the sketch applies as real names from the diff on every label.

Copyright (c) 2026 Jo Van Eyck. MIT License.

## Cursor, `pr-review-canvas`

Source: https://github.com/cursor/plugins/blob/08631ab2ef4168447c8e5daaff31b14ddd6e70ae/pr-review-canvas/skills/pr-review-canvas/SKILL.md (commit `08631ab2`, read 2026-10-20), and the earlier copy at https://github.com/cursor/plugins/blob/469d9f7d7885e0f6dcaa46ad66228b8a150380c0/cursor-team-kit/skills/pr-review-canvas/SKILL.md (commit `469d9f7d`).

Adapted: the reading order, which lists files by reviewer value instead of file-tree order (lines 27 to 33 of the `08631ab2` copy), here as "Start here" and "Then".

Copyright (c) 2026 Cursor. MIT License.

## Excalidraw, Excalifont

Source: https://github.com/excalidraw/excalidraw/blob/21ffaf4d76bf8554c3ba5561ab8ff41ce89b55fa/packages/excalidraw/fonts/Excalifont/Excalifont-Regular-a88b72a24fb54c9f94e3b5fdaa7481c9.woff2 (commit `21ffaf4d`, the basic Latin subset, read 2026-10-22). Excalidraw publishes the font only as WOFF2 subsets.

`scripts/sketch/vendor/Excalifont-Regular.ttf` is that subset converted to TrueType with no glyph changes, which makes it a Modified Version under the licence. The licence declares no Reserved Font Name. The full licence text is in `scripts/sketch/vendor/OFL-Excalifont.txt`.

Copyright (c) 2024 by Excalidraw. Excalifont derives from Virgil, with modifications by Ján Filípek. SIL Open Font License 1.1.

## Packages the sketch tool installs

[`scripts/sketch/package.json`](scripts/sketch/package.json) pins the npm packages below. pstack does not vendor or modify them. See [sketch setup](references/sketch.md#setup) for installation behavior.

- Rough.js 4.6.6, MIT License, https://github.com/rough-stuff/rough
- opentype.js 2.0.0, MIT License, https://github.com/opentypejs/opentype.js
- resvg-js 2.6.2, Mozilla Public License 2.0, https://github.com/thx/resvg-js

## MIT permission notice

The six adapted skill projects above use the MIT License, whose notice reads:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

The story-first layout, the sketch catalog and its rules, the scene format, the layout checks in `scripts/sketch`, and the comment cleanup are pstack's own.
