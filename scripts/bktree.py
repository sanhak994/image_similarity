from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple


def default_distance(a: int, b: int) -> int:
    """Hamming distance for integers treated as bit strings."""
    return (a ^ b).bit_count()


@dataclass
class _BKNode:
    value: int
    payloads: List[Any] = field(default_factory=list)
    children: Dict[int, "_BKNode"] = field(default_factory=dict)


class BKTree:
    """Simple BK-tree for fuzzy matching integer hashes."""

    def __init__(self, distance: Callable[[int, int], int] | None = None) -> None:
        self._distance = distance or default_distance
        self._root: _BKNode | None = None

    def add(self, value: int, payload: Any) -> None:
        """Insert a value/payload into the tree."""
        if self._root is None:
            self._root = _BKNode(value=value, payloads=[payload])
            return

        node = self._root
        while True:
            dist = self._distance(value, node.value)
            if dist == 0:
                node.payloads.append(payload)
                return

            child = node.children.get(dist)
            if child is None:
                node.children[dist] = _BKNode(value=value, payloads=[payload])
                return

            node = child

    def query(self, value: int, max_distance: int) -> List[Tuple[Any, int]]:
        """Return payloads within max_distance of value."""
        if self._root is None:
            return []

        matches: List[Tuple[Any, int]] = []
        stack: List[_BKNode] = [self._root]

        while stack:
            node = stack.pop()
            dist = self._distance(value, node.value)
            if dist <= max_distance:
                matches.extend((payload, dist) for payload in node.payloads)

            low = dist - max_distance
            high = dist + max_distance
            for edge, child in node.children.items():
                if low <= edge <= high:
                    stack.append(child)

        return matches
