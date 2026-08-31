from __future__ import annotations


def paginate_query(query, *, page: int, per_page: int):
    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    return rows, total
