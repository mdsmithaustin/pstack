import io
import json
import stat
import struct
import sys
import zipfile
from xml.parsers import expat


MAX_ARCHIVE = 8 * 1024 * 1024
MAX_ENTRIES = 128
MAX_MEMBER = 1024 * 1024
MAX_EXPANDED = 8 * 1024 * 1024
MAX_OUTPUT = 64 * 1024
MAX_RECORDS = 32
MAX_EVIDENCE = 24 * 1024


def extra_fields(data):
    cursor = 0
    while cursor < len(data):
        if cursor + 4 > len(data):
            raise ValueError("invalid ZIP extra-field framing")
        kind, size = struct.unpack_from("<2H", data, cursor)
        if kind == 1:
            raise ValueError("unsupported ZIP64 member")
        cursor += 4 + size
        if cursor > len(data):
            raise ValueError("invalid ZIP extra-field range")


def directory(data):
    end = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if end < 0 or end + 22 > len(data):
        raise ValueError("missing ZIP end record")
    _, disk, start_disk, disk_count, count, size, offset, comment = struct.unpack_from("<4s4H2IH", data, end)
    if disk or start_disk or disk_count != count or count == 65535 or offset == 0xFFFFFFFF:
        raise ValueError("unsupported multidisk or ZIP64 archive")
    if count > MAX_ENTRIES or size > 256 * 1024:
        raise ValueError("ZIP directory limit exceeded")
    if end + 22 + comment != len(data) or offset + size != end:
        raise ValueError("invalid ZIP directory range")
    cursor = offset
    ranges = []
    names = set()
    while cursor < end:
        if cursor + 46 > end or data[cursor:cursor + 4] != b"PK\x01\x02":
            raise ValueError("invalid ZIP directory framing")
        fields = struct.unpack_from("<4s6H3I5H2I", data, cursor)
        flags, method, crc, compressed, expanded = fields[3], fields[4], fields[7], fields[8], fields[9]
        name_len, extra_len, comment_len, member_disk, local = fields[10], fields[11], fields[12], fields[13], fields[16]
        next_cursor = cursor + 46 + name_len + extra_len + comment_len
        if next_cursor > end or name_len > 1024 or local + 30 > offset or member_disk:
            raise ValueError("invalid ZIP member framing")
        name = data[cursor + 46:cursor + 46 + name_len]
        extra_fields(data[cursor + 46 + name_len:cursor + 46 + name_len + extra_len])
        if name in names:
            raise ValueError("duplicate ZIP member")
        names.add(name)
        if data[local:local + 4] != b"PK\x03\x04":
            raise ValueError("invalid ZIP local header")
        header = struct.unpack_from("<4s5H3I2H", data, local)
        if header[2] != flags or header[3] != method:
            raise ValueError("inconsistent ZIP member headers")
        local_name, local_extra = header[9], header[10]
        begin = local + 30 + local_name + local_extra
        if begin + compressed > offset or data[local + 30:local + 30 + local_name] != name:
            raise ValueError("invalid ZIP member range")
        extra_fields(data[local + 30 + local_name:begin])
        if not flags & 8 and (header[6], header[7], header[8]) != (crc, compressed, expanded):
            raise ValueError("inconsistent ZIP sizes or checksum")
        ranges.append((local, begin + compressed))
        cursor = next_cursor
        if len(ranges) > MAX_ENTRIES:
            raise ValueError("ZIP entry limit exceeded")
    if cursor != end or len(ranges) != count:
        raise ValueError("inconsistent ZIP entry count")
    previous = 0
    for begin, finish in sorted(ranges):
        if begin < previous:
            raise ValueError("overlapping ZIP members")
        previous = finish


def junit(data, member):
    parser = expat.ParserCreate(namespace_separator="}")
    stack = []
    records = []
    testcase = None
    failure = None
    elements = 0
    omitted = 0
    truncated = 0
    evidence = 0
    is_junit = False

    def reject(*args):
        raise ValueError("XML DTD or entity declaration is forbidden")

    def clipped(value, limit=256):
        nonlocal truncated
        if len(value) > limit:
            truncated += 1
        return value[:limit]

    def start(name, attributes):
        nonlocal testcase, failure, elements, is_junit
        name = name.rsplit("}", 1)[-1]
        elements += 1
        if elements > 50000 or len(stack) >= 64 or sum(len(k) + len(v) for k, v in attributes.items()) > 16384:
            raise ValueError("XML element, depth or attribute limit exceeded")
        if not stack:
            is_junit = name in ("testsuite", "testsuites")
        if is_junit and name == "testcase":
            if testcase is not None:
                raise ValueError("nested JUnit testcase")
            testcase = {"testName": clipped(attributes.get("name", "")), "classname": clipped(attributes.get("classname", ""))}
        if is_junit and name in ("failure", "error"):
            if testcase is None or not stack or stack[-1] != "testcase" or failure is not None:
                raise ValueError("JUnit failure or error lacks a direct testcase")
            failure = dict(testcase, member=clipped(member), kind=name, message=clipped(attributes.get("message", "")), type=clipped(attributes.get("type", "")), body="")
        stack.append(name)

    def text(value):
        nonlocal truncated
        if failure is not None:
            remaining = 2048 - len(failure["body"])
            if len(value) > remaining:
                truncated += 1
            failure["body"] += value[:remaining]

    def end(name):
        nonlocal testcase, failure, omitted, evidence
        name = name.rsplit("}", 1)[-1]
        if failure is not None and name == failure["kind"] and len(stack) >= 2 and stack[-2] == "testcase":
            cost = sum(len(value) for value in failure.values())
            if len(records) < MAX_RECORDS and evidence + cost <= MAX_EVIDENCE:
                records.append(failure)
                evidence += cost
            else:
                omitted += 1
            failure = None
        if name == "testcase":
            testcase = None
        stack.pop()

    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    parser.Parse(data, True)
    return records, omitted, truncated


def read_archive(data, mode, allowance):
    directory(data)
    result = {"records": [], "logs": [], "gaps": [], "expandedBytes": 0}
    names = set()
    omitted = 0
    truncated = 0
    evidence = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES:
            raise ValueError("ZIP entry limit exceeded")
        for entry in entries:
            name = entry.orig_filename
            parts = name.rstrip("/").split("/")
            permissions = entry.external_attr >> 16
            kind = stat.S_IFMT(permissions)
            if not name or "\x00" in name or "\\" in name or name.startswith("/") or ":" in parts[0] or any(part in ("", ".", "..") for part in parts) or name in names:
                raise ValueError("unsafe ZIP member path")
            names.add(name)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (not entry.is_dir() and permissions & 0o111):
                raise ValueError("symlink, special or executable ZIP member")
            if entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError("encrypted or unsupported ZIP member")
            if entry.file_size > MAX_MEMBER or entry.file_size > max(1, entry.compress_size) * 100:
                raise ValueError("ZIP member size or compression ratio limit exceeded")
            if entry.is_dir():
                if entry.file_size:
                    raise ValueError("nonempty ZIP directory")
            chunks = []
            size = 0
            with archive.open(entry) as stream:
                while True:
                    chunk = stream.read(16384)
                    if not chunk:
                        break
                    size += len(chunk)
                    result["expandedBytes"] += len(chunk)
                    if size > MAX_MEMBER or result["expandedBytes"] > min(MAX_EXPANDED, allowance) or size > max(1, entry.compress_size) * 100:
                        raise ValueError("ZIP expanded-byte limit exceeded")
                    chunks.append(chunk)
            if size != entry.file_size:
                raise ValueError("inconsistent ZIP expanded size")
            if entry.is_dir():
                continue
            content = b"".join(chunks)
            if mode == "logs":
                value = content.decode("utf-8", errors="strict")
                if len(result["logs"]) < 4:
                    truncated += int(len(value) > 8192 or len(name) > 256)
                    result["logs"].append({"member": name[:256], "text": value[:8192]})
                else:
                    omitted += 1
            elif name.lower().endswith(".xml") or content.lstrip().startswith((b"<", b"\xff\xfe", b"\xfe\xff")):
                records, dropped, fields = junit(content, name)
                omitted += dropped
                truncated += fields
                for record in records:
                    cost = sum(len(value) for value in record.values())
                    if len(result["records"]) >= MAX_RECORDS or evidence + cost > MAX_EVIDENCE:
                        omitted += 1
                    else:
                        result["records"].append(record)
                        evidence += cost
    if omitted:
        result["gaps"].append({"kind": "limit", "detail": "archive evidence omitted", "omitted": omitted})
    if truncated:
        result["gaps"].append({"kind": "limit", "detail": "archive evidence fields truncated", "omitted": truncated})
    while len(json.dumps(result, ensure_ascii=True).encode()) > MAX_OUTPUT:
        if result["records"]:
            result["records"].pop()
        elif result["logs"]:
            result["logs"].pop()
        else:
            raise ValueError("archive output limit exceeded")
        if not any(gap["detail"] == "archive output omitted" for gap in result["gaps"]):
            result["gaps"].append({"kind": "limit", "detail": "archive output omitted", "omitted": 0})
        result["gaps"][-1]["omitted"] += 1
    return result


def main():
    try:
        if sys.version_info < (3, 9):
            print(json.dumps({"error": "Python 3.9 or newer is required", "errorKind": "unavailable"}))
            return
        mode, allowance = sys.argv[1], int(sys.argv[2])
        if mode not in ("junit", "logs") or not 0 < allowance <= 32 * 1024 * 1024:
            raise ValueError("invalid archive worker request")
        data = sys.stdin.buffer.read(MAX_ARCHIVE + 1)
        if len(data) > MAX_ARCHIVE:
            raise ValueError("ZIP download limit exceeded")
        result = read_archive(data, mode, allowance)
    except (ValueError, IndexError, zipfile.BadZipFile, RuntimeError, NotImplementedError, UnicodeError, expat.ExpatError, struct.error) as error:
        result = {"error": str(error)[:256], "errorKind": "unsafe"}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
