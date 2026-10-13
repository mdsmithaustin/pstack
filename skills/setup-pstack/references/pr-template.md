# Set up the repository PR template

Run this during full repository setup or when asked to configure a PR template. Resolve the consumer repository with `git rev-parse --show-toplevel`. Apply changes within the session's authorized repository scope. Keep unrelated changes and all existing configuration fields.

## Select the author format

Read the repository's PR instructions and discover its existing templates. Check the repository root, `docs/`, and `.github/` for `pull_request_template.md` or `.txt`, including case variants and `PULL_REQUEST_TEMPLATE/` directories. Also check paths named by repository instructions and `.no-mistakes.yaml` `pr.template`.

- Keep an explicit `pr.template` choice. If its target is missing or invalid, report that configuration error instead of replacing it with the poteto default.
- Keep an existing repository template or documented custom format. When exactly one template is selected unambiguously and no-mistakes has no `pr.template`, configure that path. With multiple candidates and no selection, ask which one to use before changing configuration.
- When a documented custom format exists without a template, create a template for that format within the authorized setup scope. Resolve an ambiguous format with the user before writing it.
- When no repository template or custom format exists, copy [the bundled poteto template](../assets/pull_request_template.md) to `.github/pull_request_template.md`. Create the directory if needed. Create the file only if absent. On reruns, preserve the repository's copy and any local edits.

The [Opening a PR playbook](../../poteto-mode/playbooks/opening-a-pr.md) owns body format precedence and finalization. A separately installed PR-writing skill is optional and does not select the repository format.

## Connect no-mistakes when configured

When the repository already has `.no-mistakes.yaml` or a `no-mistakes` Git remote, set only the missing `pr.template` field to the selected repository-relative Markdown path. Merge into the existing YAML mapping. If the file is absent, create it with this field. Report malformed YAML or a conflicting `pr` value rather than overwriting it. Keep existing `publish_intent`, `appendix`, and every unrelated setting. Do not initialize no-mistakes or change its upstream code.

For the bundled template, the configuration is:

```yaml
pr:
  template: .github/pull_request_template.md
```

No-mistakes does not discover templates automatically. It reads the configured path and template bytes from the pinned trusted default-branch commit. Deliver the template and config together through the repository's normal review path. Until both land, report activation as pending. A feature-branch copy does not activate template mode for its own publication. See the [no-mistakes template contract](https://kunchenguid.github.io/no-mistakes/reference/repo-config/#prtemplate).

An existing generic PR with an unowned pipeline attestation may require author reconciliation before template mode can adopt it. Preserve its author text and issue-closing references. Use the installed no-mistakes instructions and its reported error to reconcile obsolete generated evidence; never manufacture ownership markers. Keep this separate from template installation.

## Verify the setup

Read the final template and configuration. Confirm that the selected path is repository-relative, names a regular nonempty UTF-8 Markdown file, and preserves the repository's selected format. Verify the final YAML with a YAML parser and check that unrelated values match their pre-edit values. On a rerun with an existing template and selection, leave both files unchanged.

For the bundled default, confirm Why, What changed, Scope, Blast Radius, and Verification in that order. Keep Tradeoffs optional. Report which files changed, the selected format, and whether no-mistakes activation is pending or verified on the trusted default branch. Template instructions and `##` headings do not guarantee model compliance; the opening playbook still checks the live PR after publication.
