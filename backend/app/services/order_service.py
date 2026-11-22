"""Challenge ordering rules. Pure functions: no database, no CTFd."""
from typing import NamedTuple

from app.services.errors import BadRequest


class Row(NamedTuple):
    slug: str
    category: str
    ctfd_id: int | None


class CtfdPos(NamedTuple):
    position: int
    value: int


def _group(rows: list[Row]) -> list[str]:
    """Stable grouping by category, in order of each category's first appearance."""
    cats = list(dict.fromkeys(r.category for r in rows))
    return [r.slug for c in cats for r in rows if r.category == c]


def reconcile(rows: list[Row], ctfd: dict[int, CtfdPos]) -> list[str]:
    """Spec 6.2 GET steps 2-4: published rows follow CTFd, drafts keep their slots, then regroup."""
    idx = [i for i, r in enumerate(rows) if r.ctfd_id in ctfd]
    pub = sorted((rows[i] for i in idx), key=lambda r: (
        ctfd[r.ctfd_id].position == 0, ctfd[r.ctfd_id].position, ctfd[r.ctfd_id].value, r.ctfd_id))
    out = list(rows)
    for i, r in zip(idx, pub):
        out[i] = r
    return _group(out)


def validate_order(order: list[str], rows: list[Row]) -> None:
    if len(order) != len(set(order)) or set(order) != {r.slug for r in rows}:
        raise BadRequest("order must list every challenge exactly once", code="order_mismatch")
    cat = {r.slug: r.category for r in rows}
    seen: set[str] = set()
    prev = None
    for s in order:
        c = cat[s]
        if c != prev and c in seen:
            raise BadRequest(f"category {c!r} is not contiguous", code="order_category_split")
        seen.add(c)
        prev = c


def move_to_category_end(rows: list[Row], slug: str, new_category: str) -> list[str]:
    """Spec 6.2 'change category': after the last challenge of the new category, else the very end."""
    rest = [r for r in rows if r.slug != slug]
    ends = [i for i, r in enumerate(rest) if r.category == new_category]
    at = ends[-1] + 1 if ends else len(rest)
    out = [r.slug for r in rest]
    out.insert(at, slug)
    return out
