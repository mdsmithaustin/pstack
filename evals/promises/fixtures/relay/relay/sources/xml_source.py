import xml.etree.ElementTree as ET


def load(path):
    root = ET.parse(path).getroot()
    lines = []
    for node in root.iter("item"):
        pairs = [f"{child.tag}={(child.text or '').strip()}" for child in node]
        lines.append(";".join(pairs))
    return "\n".join(lines) + "\n"
