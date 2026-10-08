"""CSV export of candidates (name, email, education, academic, skill match,
experience, overall match, recommendation, human decision).

Only the columns above are exported — contact/identifying extras such as phone
numbers and dates of birth are deliberately not included.
"""

from __future__ import annotations

import csv
import io

from ..audit import record
from ..scoring import RECOMMENDATION_LABELS
from .candidates import DECISION_LABELS, STATUS_LABELS, list_candidates

UNSAFE_CELL_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Neutralise spreadsheet formula injection.

    Excel and Google Sheets interpret a cell starting with =, +, - or @ as a
    formula, so resume-derived text could execute on the reviewer's machine.
    Prefixing an apostrophe forces the cell to be read as literal text.
    """
    if isinstance(value, str) and value.startswith(UNSAFE_CELL_PREFIXES):
        return "'" + value
    return value


COLUMNS = [
    ("Name", "name"),
    ("Email", "email"),
    ("Education", "education"),
    ("Academic score", "academic_display"),
    ("Skill match %", "skills_match"),
    ("Experience", "experience_label"),
    ("Overall match %", "overall_score"),
    ("Recommendation", "recommendation_label"),
    ("Human decision", "human_decision_label"),
    ("Status", "status_label"),
    ("Screening profile", "profile_title"),
    ("Candidate ID", "id"),
]


def build_export_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        academic = ""
        if item.get("academic_value") is not None:
            if item.get("academic_type") == "percentage":
                academic = f"{item['academic_value']:g}%"
            else:
                academic = f"{item['academic_value']:g} CGPA"
        rows.append(
            {
                **item,
                "email": item.get("email") or "Not found",
                "education": item.get("education") or "Not found",
                "academic_display": academic or "Not found",
                "recommendation_label": RECOMMENDATION_LABELS.get(item.get("recommendation"), item.get("recommendation") or ""),
                "human_decision_label": DECISION_LABELS.get(item.get("human_decision"), "") if item.get("human_decision") else "Not decided",
                "status_label": STATUS_LABELS.get(item.get("status"), item.get("status") or ""),
            }
        )
    return rows


def export_csv(conn, params: dict) -> tuple[str, bytes, int]:
    """Run the same filtering as the candidate table and render a CSV file."""
    query = dict(params)
    query["page"] = 1
    query["page_size"] = 200
    items: list[dict] = []
    page = 1
    while True:
        query["page"] = page
        result = list_candidates(conn, query)
        items.extend(result["items"])
        if len(items) >= result["total"] or not result["items"]:
            break
        page += 1

    rows = build_export_rows(items)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[label for label, _ in COLUMNS], lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({label: csv_safe(row.get(key, "")) for label, key in COLUMNS})

    profile_part = f"profile-{params['profile_id']}" if params.get("profile_id") else "all-profiles"
    filename = f"meritos-candidates-{profile_part}.csv"
    record(
        conn,
        "export_generated",
        entity_type="export",
        profile_id=int(params["profile_id"]) if params.get("profile_id") else None,
        message=f"CSV export generated: {len(rows)} candidate(s)",
        data={"count": len(rows), "filters": {k: v for k, v in params.items() if v not in (None, "", "overall")}},
    )
    return filename, ("\ufeff" + buffer.getvalue()).encode("utf-8"), len(rows)
