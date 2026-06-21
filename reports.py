"""Report generation: five report types, each as PDF (with embedded photos) or CSV.

Public API:
    individual_skill_pdf / _csv (resident, skill, records)
    transcript_pdf / _csv        (resident, records)
    cohort_by_skill_pdf / _csv   (skill, records)
    cohort_matrix_pdf / _csv     (records)
    friday_gate_pdf / _csv       (week_label, week_records, records)

All *_pdf functions return bytes; all *_csv functions return a str.
Records are the plain dicts produced by storage.new_record().
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import config
from storage import b64_to_bytes

NAVY = colors.HexColor(config.NAVY)
WARM = colors.HexColor(config.WARM_GRAY)


# ---------------------------------------------------------------------------
# Analytics helpers
# ---------------------------------------------------------------------------
def _sorted_desc(records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda r: r.get("timestamp", ""), reverse=True)


def latest_rating(records: list[dict], resident: str, skill: str) -> str | None:
    """Most recent final rating for a resident on a skill, or None."""
    for rec in _sorted_desc(records):
        if rec.get("resident") == resident and rec.get("skill") == skill:
            return rec.get("final_rating") or None
    return None


def resident_records(records: list[dict], resident: str) -> list[dict]:
    return [r for r in records if r.get("resident") == resident]


def gate_status(records: list[dict], resident: str) -> tuple[str, str]:
    """Return (status, detail) for a Friday-gate decision on a resident.

    PASS when there are no current 'N' ratings AND the fraction of skills rated
    'C' meets config.GATE_MIN_COMPETENT. Otherwise FAIL with the reason.
    """
    latest = {
        skill: latest_rating(records, resident, skill) for skill in config.SKILLS
    }
    evaluated = {s: r for s, r in latest.items() if r}
    if not evaluated:
        return "INCOMPLETE", "No skills evaluated yet."

    n_count = sum(1 for r in evaluated.values() if r == "N")
    c_count = sum(1 for r in evaluated.values() if r == "C")
    c_frac = c_count / len(evaluated)

    if n_count > 0:
        bad = [s for s, r in evaluated.items() if r == "N"]
        return "FAIL", f"{n_count} skill(s) need improvement: {', '.join(bad)}."
    if c_frac < config.GATE_MIN_COMPETENT:
        return (
            "FAIL",
            f"Only {c_count}/{len(evaluated)} skills competent "
            f"({c_frac:.0%}; need {config.GATE_MIN_COMPETENT:.0%}).",
        )
    return "PASS", f"{c_count}/{len(evaluated)} skills competent, no N ratings."


# ---------------------------------------------------------------------------
# Shared PDF building blocks
# ---------------------------------------------------------------------------
def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("AidmTitle", parent=ss["Title"], textColor=NAVY,
                          fontName="Helvetica-Bold", fontSize=20, spaceAfter=4))
    ss.add(ParagraphStyle("AidmSub", parent=ss["Normal"], textColor=colors.grey,
                          fontSize=10, spaceAfter=12))
    ss.add(ParagraphStyle("AidmH2", parent=ss["Heading2"], textColor=NAVY,
                          fontName="Helvetica-Bold", fontSize=13, spaceBefore=10,
                          spaceAfter=4))
    ss.add(ParagraphStyle("AidmBody", parent=ss["Normal"], fontSize=9.5,
                          alignment=TA_LEFT, leading=13))
    ss.add(ParagraphStyle("AidmSmall", parent=ss["Normal"], fontSize=8,
                          textColor=colors.grey))
    return ss


def _header(title: str, subtitle: str, styles) -> list:
    return [
        Paragraph(config.APP_TITLE, styles["AidmSmall"]),
        Paragraph(title, styles["AidmTitle"]),
        Paragraph(subtitle, styles["AidmSub"]),
    ]


def _rating_cell(rating: str | None):
    """A small color-coded paragraph for a rating, for use in tables."""
    if not rating:
        return Paragraph('<font color="#999999">—</font>',
                         ParagraphStyle("c", fontSize=9))
    color = config.RATING_COLORS.get(rating, "#000000")
    return Paragraph(
        f'<b><font color="{color}">{rating}</font></b>',
        ParagraphStyle("c", fontSize=10, alignment=1),
    )


def _legend(styles) -> Paragraph:
    parts = [
        f'<font color="{config.RATING_COLORS[r]}"><b>{r}</b></font> = '
        f"{config.RATING_LABELS[r]}"
        for r in config.RATINGS
    ]
    return Paragraph("Legend: " + " &nbsp;|&nbsp; ".join(parts), styles["AidmSmall"])


def _fmt_ts(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


def _photo_flowable(b64: str, max_w=2.2 * inch, max_h=1.8 * inch):
    """Return a reportlab Image for an embedded photo, scaled to fit, or None."""
    raw = b64_to_bytes(b64)
    if not raw:
        return None
    try:
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(raw)) as im:
            w, h = im.size
        ratio = min(max_w / w, max_h / h)
        return Image(io.BytesIO(raw), width=w * ratio, height=h * ratio)
    except Exception:
        return None


def _build(elements: list, landscape_mode=False) -> bytes:
    buf = io.BytesIO()
    pagesize = landscape(LETTER) if landscape_mode else LETTER
    doc = SimpleDocTemplate(
        buf, pagesize=pagesize, title=config.APP_TITLE,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
    )
    doc.build(elements)
    return buf.getvalue()


def _generated_line(styles) -> Paragraph:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return Paragraph(f"Generated {stamp}", styles["AidmSmall"])


# ---------------------------------------------------------------------------
# 1. Individual skill report
# ---------------------------------------------------------------------------
def individual_skill_pdf(resident: str, skill: str, records: list[dict]) -> bytes:
    styles = _styles()
    rows = [r for r in _sorted_desc(records)
            if r.get("resident") == resident and r.get("skill") == skill]

    els = _header(
        "Individual Skill Report",
        f"{resident} &nbsp;·&nbsp; {skill} ({config.skill_domain(skill)})",
        styles,
    )
    current = latest_rating(records, resident, skill)
    els.append(Paragraph(
        f"Current level: <b><font color=\"{config.RATING_COLORS.get(current, '#999')}\">"
        f"{config.RATING_LABELS.get(current, 'Not yet evaluated')}</font></b>",
        styles["AidmBody"],
    ))
    els.append(_legend(styles))
    els.append(Spacer(1, 8))

    if not rows:
        els.append(Paragraph("No evaluations recorded for this skill.", styles["AidmBody"]))
    for rec in rows:
        els.append(Paragraph(
            f"{_fmt_ts(rec.get('timestamp',''))} &nbsp;·&nbsp; "
            f"Mentor: {rec.get('mentor','—')} &nbsp;·&nbsp; "
            f"Rating: <b><font color=\"{config.RATING_COLORS.get(rec.get('final_rating'),'#000')}\">"
            f"{rec.get('final_rating','—')}</font></b>",
            styles["AidmH2"],
        ))
        if rec.get("note"):
            els.append(Paragraph(f"<b>Note:</b> {rec['note']}", styles["AidmBody"]))
        if rec.get("ai_rationale"):
            els.append(Paragraph(f"<b>AI draft:</b> {rec['ai_rationale']}", styles["AidmBody"]))
        if rec.get("mentor_comment"):
            els.append(Paragraph(f"<b>Mentor comment:</b> {rec['mentor_comment']}", styles["AidmBody"]))
        photo = _photo_flowable(rec.get("photo", ""))
        if photo:
            els.append(Spacer(1, 4))
            els.append(photo)
        els.append(Spacer(1, 10))

    els.append(_generated_line(styles))
    return _build(els)


def individual_skill_csv(resident: str, skill: str, records: list[dict]) -> str:
    rows = [r for r in _sorted_desc(records)
            if r.get("resident") == resident and r.get("skill") == skill]
    return _csv(
        ["timestamp", "mentor", "final_rating", "ai_rating", "note", "mentor_comment"],
        rows,
    )


# ---------------------------------------------------------------------------
# 2. Transcript (one resident, all skills)
# ---------------------------------------------------------------------------
def transcript_pdf(resident: str, records: list[dict]) -> bytes:
    styles = _styles()
    els = _header("Resident Transcript", resident, styles)

    status, detail = gate_status(records, resident)
    els.append(Paragraph(
        f"Gate status: <b>{status}</b> — {detail}", styles["AidmBody"]))
    els.append(_legend(styles))
    els.append(Spacer(1, 8))

    # Summary table grouped by domain.
    data = [["Domain", "Skill", "Current"]]
    for domain, skills in config.SKILL_GROUPS.items():
        for i, skill in enumerate(skills):
            data.append([
                domain if i == 0 else "",
                skill,
                _rating_cell(latest_rating(records, resident, skill)),
            ])
    table = Table(data, colWidths=[1.4 * inch, 3.6 * inch, 0.9 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, WARM]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
    ]))
    els.append(table)
    els.append(Spacer(1, 12))

    # Chronological log.
    els.append(Paragraph("Evaluation log", styles["AidmH2"]))
    rows = _sorted_desc(resident_records(records, resident))
    if not rows:
        els.append(Paragraph("No evaluations recorded.", styles["AidmBody"]))
    for rec in rows:
        line = (
            f"{_fmt_ts(rec.get('timestamp',''))} · {rec.get('skill','—')} · "
            f"<b><font color=\"{config.RATING_COLORS.get(rec.get('final_rating'),'#000')}\">"
            f"{rec.get('final_rating','—')}</font></b> · {rec.get('mentor','—')}"
        )
        els.append(Paragraph(line, styles["AidmBody"]))
        if rec.get("note"):
            els.append(Paragraph(f"&nbsp;&nbsp;<i>{rec['note']}</i>", styles["AidmSmall"]))
    els.append(Spacer(1, 10))
    els.append(_generated_line(styles))
    return _build(els)


def transcript_csv(resident: str, records: list[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["skill", "domain", "current_rating"])
    for skill in config.SKILLS:
        w.writerow([skill, config.skill_domain(skill),
                    latest_rating(records, resident, skill) or ""])
    return out.getvalue()


# ---------------------------------------------------------------------------
# 3. Cohort by skill (all residents, one skill)
# ---------------------------------------------------------------------------
def cohort_by_skill_pdf(skill: str, records: list[dict]) -> bytes:
    styles = _styles()
    els = _header("Cohort Report — by Skill",
                  f"{skill} ({config.skill_domain(skill)})", styles)
    els.append(_legend(styles))
    els.append(Spacer(1, 8))

    data = [["Resident", "Current", "# Evaluations"]]
    for resident in config.RESIDENTS:
        n = sum(1 for r in records
                if r.get("resident") == resident and r.get("skill") == skill)
        data.append([resident, _rating_cell(latest_rating(records, resident, skill)), str(n)])
    table = Table(data, colWidths=[3.2 * inch, 1.4 * inch, 1.6 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, WARM]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    els.append(table)
    els.append(Spacer(1, 10))
    els.append(_generated_line(styles))
    return _build(els)


def cohort_by_skill_csv(skill: str, records: list[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["resident", "current_rating", "num_evaluations"])
    for resident in config.RESIDENTS:
        n = sum(1 for r in records
                if r.get("resident") == resident and r.get("skill") == skill)
        w.writerow([resident, latest_rating(records, resident, skill) or "", n])
    return out.getvalue()


# ---------------------------------------------------------------------------
# 4. Full cohort matrix (residents x skills)
# ---------------------------------------------------------------------------
def cohort_matrix_pdf(records: list[dict]) -> bytes:
    styles = _styles()
    els = _header("Full Cohort Matrix", "All residents × all skills", styles)
    els.append(_legend(styles))
    els.append(Spacer(1, 6))

    header = ["Resident"] + [s.split(" ")[0] + "…" if len(s) > 14 else s
                             for s in config.SKILLS]
    # Use short skill labels rotated would be ideal, but keep simple: index columns.
    skill_index = [str(i + 1) for i in range(len(config.SKILLS))]
    header = ["Resident"] + skill_index
    data = [header]
    for resident in config.RESIDENTS:
        row = [Paragraph(resident, styles["AidmBody"])]
        for skill in config.SKILLS:
            row.append(_rating_cell(latest_rating(records, resident, skill)))
        data.append(row)

    col_widths = [1.8 * inch] + [(8.0 * inch) / len(config.SKILLS)] * len(config.SKILLS)
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, WARM]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    els.append(table)
    els.append(Spacer(1, 10))

    # Skill index key.
    els.append(Paragraph("Skill key", styles["AidmH2"]))
    for i, skill in enumerate(config.SKILLS, start=1):
        els.append(Paragraph(f"<b>{i}.</b> {skill} ({config.skill_domain(skill)})",
                             styles["AidmSmall"]))
    els.append(Spacer(1, 8))
    els.append(_generated_line(styles))
    return _build(els, landscape_mode=True)


def cohort_matrix_csv(records: list[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["resident"] + config.SKILLS)
    for resident in config.RESIDENTS:
        w.writerow([resident] + [
            latest_rating(records, resident, skill) or "" for skill in config.SKILLS
        ])
    return out.getvalue()


# ---------------------------------------------------------------------------
# 5. Friday gate review
# ---------------------------------------------------------------------------
def friday_gate_pdf(week_label: str, records: list[dict]) -> bytes:
    styles = _styles()
    els = _header("Friday Gate Review", week_label, styles)
    els.append(Paragraph(
        f"A resident passes the gate with no 'Needs Improvement' ratings and at "
        f"least {config.GATE_MIN_COMPETENT:.0%} of evaluated skills at "
        f"'Competent'.", styles["AidmSmall"]))
    els.append(Spacer(1, 8))

    data = [["Resident", "Status", "Detail"]]
    style_rows = []
    for i, resident in enumerate(config.RESIDENTS, start=1):
        status, detail = gate_status(records, resident)
        data.append([
            Paragraph(resident, styles["AidmBody"]),
            Paragraph(f"<b>{status}</b>", styles["AidmBody"]),
            Paragraph(detail, styles["AidmBody"]),
        ])
        color = {"PASS": colors.HexColor("#E8F5E9"),
                 "FAIL": colors.HexColor("#FFEBEE"),
                 "INCOMPLETE": colors.HexColor("#FFF8E1")}.get(status, colors.white)
        style_rows.append(("BACKGROUND", (0, i), (-1, i), color))

    table = Table(data, colWidths=[2.0 * inch, 1.1 * inch, 3.8 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        *style_rows,
    ]))
    els.append(table)
    els.append(Spacer(1, 10))
    els.append(_generated_line(styles))
    return _build(els)


def friday_gate_csv(week_label: str, records: list[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["resident", "status", "detail"])
    for resident in config.RESIDENTS:
        status, detail = gate_status(records, resident)
        w.writerow([resident, status, detail])
    return out.getvalue()


# ---------------------------------------------------------------------------
# CSV helper
# ---------------------------------------------------------------------------
def _csv(columns: list[str], rows: list[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(columns)
    for r in rows:
        w.writerow([r.get(c, "") for c in columns])
    return out.getvalue()
