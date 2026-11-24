"""Compose YAML nodes with the bundled parser from PyYAML 6.0.3."""

from .composer import Composer
from .error import YAMLError
from .nodes import MappingNode, ScalarNode
from .parser import Parser
from .reader import Reader
from .resolver import BaseResolver
from .scanner import Scanner


class _Loader(Reader, Scanner, Parser, Composer, BaseResolver):
    def __init__(self, stream):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BaseResolver.__init__(self)


def mapping_keys(stream):
    try:
        root = _Loader(stream).get_single_node()
    except (YAMLError, ValueError, RecursionError):
        return []
    if isinstance(root, MappingNode):
        return [key.value for key, _ in root.value if isinstance(key, ScalarNode)]
    return []
