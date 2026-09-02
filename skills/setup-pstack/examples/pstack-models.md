---
description: pstack per-role model choices (overrides skill defaults)
---
# pstack model configuration. One line per role. Delete a line to fall back to the skill default.
# `inherit-parent` or `auto` as a value: the role runs on the parent chat model (omit the model). Alias entries in a panel list still count toward its fan-out.
# `model@effort` pins the reasoning effort (none, low, medium, high, xhigh, max; ultra only on gpt-5.6-sol). No suffix: the harness skill's policy applies (floor high).
# `## codex`, `## claude-code`, `## hermes` sections override the lines above for that harness only.
feature, refactoring: sonnet
bug-fix: fable
perf-issue: fable
hillclimb: fable
judgment and prose: fable
hardest tasks: fable
how explorer: sonnet
how explainer: fable
how critics: fable, opus, sonnet, haiku
why investigators: sonnet
why synthesizer: fable
reflect tooling: opus
reflect judgment, divergent, synthesizer: fable
arena runners: fable, opus, sonnet, haiku
arena cross-judge pool: fable, opus, sonnet, haiku
swarm workers: sonnet
architect runners: fable, opus, sonnet, haiku
interrogate reviewers: fable, opus, sonnet, haiku

## codex
feature, refactoring: gpt-5.6-terra@high
bug-fix: gpt-5.6-sol@xhigh
perf-issue: gpt-5.6-sol@xhigh
hillclimb: gpt-5.6-sol@xhigh
judgment and prose: gpt-5.6-sol@max
hardest tasks: gpt-5.6-sol@max
how explorer: gpt-5.6-terra@high
how explainer: gpt-5.6-sol@max
how critics: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high, gpt-5.6-luna@high
why investigators: gpt-5.6-terra@high
why synthesizer: gpt-5.6-sol@max
reflect tooling: gpt-5.6-sol@xhigh
reflect judgment, divergent, synthesizer: gpt-5.6-sol@max
arena runners: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high, gpt-5.6-luna@high
arena cross-judge pool: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high, gpt-5.6-luna@high
swarm workers: gpt-5.6-terra@high
architect runners: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high, gpt-5.6-luna@high
interrogate reviewers: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high, gpt-5.6-luna@high
