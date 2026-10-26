---
name: pr-recap
description: Write or refresh a visual recap of a GitHub pull request for its reviewers, posted as one PR comment between pstack-recap markers. The recap opens with two sentences on why the change exists and what it changes, then one hand-drawn sketch of the changed mechanism, attached as an image, then one line on what the PR does not prove. Risk, SHAs, reading order, and file areas sit in a collapsed block below. Use after you open a PR or push to one, or when asked to "recap this PR", "visual recap", "PR recap", "diagram this PR", or "summarize this PR for reviewers". Skip trivial PRs.
---

# PR recap

Write one recap of a pull request for the people who review it. A reviewer should understand from the first screen why the change exists, what it changes, and how. The recap points into the diff. It does not replace reading the diff.

Run this workflow locally. The recap is one PR comment: GitHub Markdown plus one PNG that `gh` attaches. It needs `gh` and the bundled sketch tool; see [sketch setup](references/sketch.md#setup) for runtime requirements. It posts nothing to any other host.

## Decide whether the PR gets a recap

Skip the recap when the diff has no behavior that a reviewer must trace. Examples are a version pin and its hashes, a typo or wording fix, a formatting-only change, a lockfile-only change, and the revert of one commit. A version pin skips even across a major version, because a pin has no mechanism to sketch.

For a skipped PR, post nothing on GitHub. Put one line in your reply:

`Recap skipped for PR <n>: <what the diff is>, <why it needs no recap>.`

Otherwise, write the recap. Write it again after each push that changes the diff, once the new head is published and any gate run on it has reached its outcome.

## Gather the facts

1. Resolve `<host>/<owner>/<repo>` from origin's fetch URL. Pass `-R <host>/<owner>/<repo>` to every `gh pr` call. Pass `--hostname <host>` to every `gh api` call.
2. Read the PR record with `gh pr view <n> -R <host>/<owner>/<repo> --json number,title,body,baseRefName,baseRefOid,headRefOid,files,commits,reviews,comments,closingIssuesReferences`. Record `baseRefOid` and `headRefOid`. Every fact in the recap describes the diff between those two SHAs.
3. Read the whole diff with `gh pr diff <n> -R <host>/<owner>/<repo>`. Read the code around each hunk you will describe, its callers, and each linked issue. Make no claim about a file you did not read.
4. Read the posted reviews, the posted verdict comments, and the CI runs on the head. A verdict that is not posted on the PR is not evidence.
5. Build every claim from these records. Session memory can help you find a record. It cannot prove a claim.

## Find the story before you write

Answer three questions in your notes, each from a record:

- **Why.** What went wrong, or what was needed, before this PR? Name the concrete symptom a person saw, such as a lost route, a wrong verdict, or a merge with no watcher. "Improves X" is not a why.
- **What.** The one mechanism the PR changes. If it changes several, pick the one the why depends on.
- **How.** The move that fixes it, such as a reorder, a new role, a new check, or a rewired call.

Do not invent a rationale. State a reason only when the diff, the PR body, a linked issue, a commit message, or a posted review gives it. Write any other reason as `(a guess)`.

## Write the comment

Copy the template in [the block](references/block.md). The first screen has exactly three parts:

1. **The story.** At most two sentences and 60 words. The first says why, with the concrete symptom. The second says what changed and how, in the words a reviewer will find in the diff. No semicolons, no file lists, no counts that the sketch already shows.
2. **The sketch.** One image of the changed mechanism. See [the sketch](references/sketch.md).
3. **Not covered.** One line naming what the PR does not prove, such as an unmeasured runtime, an untested path, or a caveat from the posted verdict.

Everything else goes in one collapsed `<details>` block after them: the risk line, the SHAs, the reading order, the changed areas as a short list, and links to the proof. Do not use tables.

Never copy a secret, token, or credential-looking value from the diff. Write `<redacted>` in its place.

Use the **technical-writing** skill on the recap's sentences. Then use the **unslop** skill.

## Draw the sketch

Use one writable work folder outside the skill for `scene.json`, `sketch.png`, `story.txt`, and `recap.md`. Run the render, reader, and posting commands from that folder. Replace `<skill>` with the absolute path to this skill's directory.

Follow [the sketch](references/sketch.md). In short: pick one drawing from its catalog, write `scene.json` in the work folder, render it with `bun "<skill>/scripts/sketch/sketch.mjs" scene.json sketch.png`, fix every problem it reports, then look at the PNG yourself before you use it.

When your runtime has no Bun or only an older one, render through the `npx` route in [sketch setup](references/sketch.md#setup). Skip the sketch when that route fails too, or when your runtime cannot show you an image. Post the story, the "Not covered" line, and the details block, and say in your reply that the sketch was skipped and why. Do not substitute a Mermaid diagram or a table.

## Check every claim before you post

1. List each factual sentence in the recap and each label in the sketch.
2. Check each one against a hunk of the diff or a SHA-pinned line. Mark it verified, corrected, unsupported, or unverifiable.
3. Fix each corrected claim. Delete each unsupported or unverifiable claim, or rewrite it as a guess. Re-render the sketch if a label changed.
4. Check each link. Pin source links to the recorded head SHA. Review and CI links must point at records on the PR, with CI runs on that head. Never include a bot review's URL anywhere in the comment, code spans included. A recap does not triage a review's findings, and watch-pr and merge-gate never count a recap as acknowledging one.
5. Read `headRefOid` again. If it moved, rebuild the recap from the new diff.

Keep the marks in your notes, not in the comment. Report the counts in your reply.

## Post or update the comment

Write the recap to `recap.md` in the same work folder, including when the sketch is skipped. Run the posting commands from that folder. The image line must name the file you attach, as `![<alt text>](./sketch.png)` for `--attach sketch.png`. `gh` uploads the attachment and rewrites that link.

```sh
gh pr comment <n> -R <host>/<owner>/<repo> --body-file recap.md --attach sketch.png
```

The command prints the new comment URL. Then delete your older recap comment, so the PR keeps one recap:

```sh
me=$(gh api --hostname <host> user --jq .login)
gh api --hostname <host> --paginate "repos/<owner>/<repo>/issues/<n>/comments" \
	--jq ".[] | select(.user.login == \"$me\" and (.body | startswith(\"<!-- pstack-recap:start -->\"))) | .id" |
	sed '$d' | while read -r id; do gh api --hostname <host> -X DELETE "repos/<owner>/<repo>/issues/comments/$id"; done
```

Read the new comment back with `gh api --hostname <host> "repos/<owner>/<repo>/issues/comments/<id>" --jq .body`. Confirm it holds both markers and the head SHA you recorded. When you attach a sketch, also confirm a `user-attachments` image link. Without a sketch, post with `--body-file recap.md` alone.

Post it as a PR comment, never in the PR body. In a repository gated by no-mistakes, the gate owns the PR body.

## Reply

- The comment URL and the head SHA that the recap describes, or the skip line.
- Which catalog drawing you used, or why you skipped the sketch.
- The claim check counts: verified, corrected, and deleted or rewritten as guesses.

[CREDITS.md](CREDITS.md) names the sources this skill adapts.
