from dataclasses import dataclass, field


class ParseError(ValueError):
    pass


@dataclass
class Record:
    id: str
    fields: dict = field(default_factory=dict)


def parse(text):
    records = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = {}
        for pair in line.split(";"):
            pair = pair.strip()
            if not pair:
                continue
            key, sep, value = pair.partition("=")
            if not sep or not key.strip():
                raise ParseError(f"line {number}: bad pair {pair!r}")
            fields[key.strip().lower()] = value.strip()
        if "id" not in fields:
            raise ParseError(f"line {number}: missing id")
        record_id = fields.pop("id").lower()
        records.append(Record(record_id, fields))
    return records
