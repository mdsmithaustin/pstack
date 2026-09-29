"""Name the deletion a reframing buys.

Both cases are review cases, so each check is the precheck: it passes when the
review names the code the grading guide is about. The judge decides the verdict."""
from shared import review_names


def check_discord_actions_deny(answer, workspace):
    """The allow/deny loading and the two places that branch on an unset list."""
    return review_names(answer, (r"_load_action_config", r"_parse_action_names", r"_available_actions",
                                 r"_run_discord_action", r"\bdenylist\b"))


def check_discord_purge_messages(answer, workspace):
    """The purge action whose size branches must stay."""
    return review_names(answer, (r"purge_messages", r"bulk[- ]delete", r"len\(ids\)"))


CHECKS = {
    "discord-actions-deny": check_discord_actions_deny,
    "discord-purge-messages": check_discord_purge_messages,
}
