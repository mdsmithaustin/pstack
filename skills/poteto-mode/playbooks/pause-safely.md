### Pause safely

**You own a clean stop. Leave a checkpoint a cold-start agent can resume from.** This is explicit only. On "keep going", "going to bed, keep going", or "don't stop", do not pause.

1. Stop at a safe boundary. Finish the current atomic step or back out of it. Start nothing new, and cancel any nested subagents.
2. Take no irreversible action to pause. No PR and no push unless you already had one out.
3. Make the work durable. Commit uncommitted edits as one clear `wip:` commit on the current branch so nothing is lost. If the tree is broken, say so in the commit body in one line. If `git commit` fails, as it does where `.git` is read-only, save the work outside the checkout in two files. Run both commands from the repository root (`cd "$(git rev-parse --show-toplevel)"`), because `git ls-files` lists only the current directory. Write tracked changes, staged and unstaged, including deletions, with `git diff --binary HEAD > <patch>`. Archive untracked files with `git ls-files -z -o --exclude-standard | tar --null -T - -czf <tarball>`. Put both paths in the resume note.
4. Write the resume note off-context. Capture intent, what you were doing, progress and what's verified, current state, next steps, key files, and gotchas. For the compaction trigger write it to a file like `/tmp/<slug>-resume.md`. If a show-me-your-work trail exists, point at it instead of duplicating it.

**Reply:** where you are in the loop, what's on disk versus still in your head (paths, no diff dumps), the commits you made and whether the tree is clean, and the first action on resume. This is a pause, not a final report.
