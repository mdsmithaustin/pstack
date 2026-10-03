from dataclasses import dataclass, field


@dataclass
class Group:
    tag: str
    entries: list = field(default_factory=list)


def group_by_tag(entries):
    groups = {}
    for entry in entries:
        group = groups.setdefault(entry.tag, Group(entry.tag))
        group.entries.append(entry)
    return sorted_groups(groups.values())


def sorted_groups(groups):
    ordered = sorted(groups, key=lambda group: group.tag)
    for group in ordered:
        group.entries.sort(key=lambda entry: entry.timestamp)
    return ordered


def busiest(groups):
    return max(groups, key=lambda group: len(group.entries), default=None)


def between(group, start, end):
    return [e for e in group.entries if start <= e.timestamp <= end]


def tag_sizes(groups):
    return {group.tag: len(group.entries) for group in groups}


def drop_empty(groups):
    return [group for group in groups if group.entries]


def entry_count(groups):
    return sum(len(group.entries) for group in groups)
