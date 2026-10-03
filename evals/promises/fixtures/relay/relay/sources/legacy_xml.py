import xml.dom.minidom


def load(path):
    document = xml.dom.minidom.parse(path)
    lines = []
    for node in document.getElementsByTagName("entry"):
        pairs = []
        for key, value in node.attributes.items():
            pairs.append(f"{key}={value}")
        lines.append(";".join(pairs))
    return "\n".join(lines) + "\n"
