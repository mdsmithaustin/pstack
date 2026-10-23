# The recap block

Copy this shape. Replace each `<...>` with facts from the PR record and the diff. Keep the markers exactly as written, because the cleanup command finds earlier recaps by the start marker.

````markdown
<!-- pstack-recap:start -->
<Why, with the concrete symptom.> <What changed and how.>

![<alt text: the whole story of the sketch in one or two sentences>](./sketch.png)

**Not covered.** <What this PR does not prove.>

<details>
<summary>Details for reviewers</summary>

**Risk.** <Low | Medium | High>. <One reason, tied to a file or a behavior in the diff.>

Base `<base SHA, 8 characters>` on `<base branch>`, head `<head SHA, 8 characters>`. <N> files, +<added> -<deleted>.

**Start here.** <The one or two files or symbols with the new behavior, as SHA-pinned links.>

**Then.**

- <Area>: <paths>. <One sentence from the diff.>
- <Area>: <paths>. <One sentence from the diff.>

**Proof.** <Links to the posted verdict, the CI run on the head, or a test that fails before the fix.>

These pointers are a start, not the review. Read the whole diff, because a defect can sit in a file this recap ranks low.

</details>
<!-- pstack-recap:end -->
````

## The story

Good: `Uploads over 10 MB failed with a 413 because the proxy rejects larger request bodies, so users with phone videos could not attach them. This PR splits each upload into 4 MB chunks in <code>uploadFile</code> and reassembles them in <code>/upload/complete</code>.`

Bad: `Updates upload.ts and proxy.conf and adds chunk tests.` It leads with files and gives no why.

Bad: `Improves upload robustness.` It names no symptom a person saw.

## The alt text

Write the alt text as the story the sketch tells, in plain sentences, with every label it shows. A reader who cannot load the image should lose nothing.

## Layout

- Leave a blank line after `</summary>` and around every list inside `<details>`. Without it, GitHub shows the raw Markdown.
- Keep the area list to the areas a reviewer should open, at most six. Group mechanical edits, such as ledger updates or link fixes, into one item.

## The risk line

- **Low.** The change cannot alter what a user or caller observes, or a test pins every behavior it touches.
- **Medium.** It changes observable behavior on a path with partial coverage, or it moves rules a runtime reads.
- **High.** It changes a contract, a security boundary, stored data, or a merge or release path, and coverage is thin.

Name the file or behavior that sets the level.
