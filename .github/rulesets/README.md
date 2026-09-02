# Repository rulesets

`copilot-code-review.json` asks Copilot to review every pull request against the default branch and to review again on each push, so the Babysit watcher's `pending-review-bots` wait also covers fix pushes. Drafts are skipped.

Apply it in the GitHub UI under Settings, Rules, Rulesets, "Import a ruleset", or from a shell:

```sh
gh api --method POST repos/<owner>/<repo>/rulesets --input .github/rulesets/copilot-code-review.json
```

Re-running the command creates a duplicate; edit the existing ruleset instead. Applied to pstack and agent-loop-runner on 2026-09-02.
