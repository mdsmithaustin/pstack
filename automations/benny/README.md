# benny

benny gives you two automations for slack issue reports, built to run on a scheduled cloud agent runner (e.g. claude code scheduled agents, or any cron-driven ci job that invokes your cli). one triages each report. the other reproduces confirmed bugs and may prepare a small draft fix.

the files in this directory are dormant setup and automation sources. they do not appear as slash skills.

## set it up

1. point your cli at [`FOR_AGENTS.md`](./FOR_AGENTS.md) and name the target repository.
2. let setup merge this whole directory into the target at `.agents/automations/benny/`. it must preserve destination-only files and review conflicts instead of overwriting local edits.
3. let setup install pstack at project scope in the target repository for shared dependencies:

```sh
npx skills add mdsmithaustin/pstack
```

4. keep user-owned configuration outside the copied pack, for example in `.agents/benny/`. adapt [`configuration.example.yaml`](./templates/configuration.example.yaml) and [`feature-map.example.md`](./skills/reproduce-and-fix-issues/references/feature-map.example.md).
5. commit the installed `.agents/skills/`, `.agents/automations/benny/`, and any secret-free configuration before enabling either automation.
6. review each new automation draft or update existing automations in your automation platform's config. then send a harmless test report and verify every source-channel post stays in the original thread.
