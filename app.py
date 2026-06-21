"""AIDM Bootcamp Evaluator — Streamlit front end.

Run with:  streamlit run app.py

Flow: a mentor signs in, captures a daily evaluation (resident + skill + date +
photo + note), gets an AI-drafted C/D/N rating, validates or overrides it, and
saves. The Reports hub exports five report types as PDF or CSV. Data persists to
Google Sheets when configured, otherwise to a local JSON file.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

import ai_draft
import config
import reports
from storage import compress_image_to_b64, get_backend, new_record

st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon="🩺",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Resources & state
# ---------------------------------------------------------------------------
@st.cache_resource
def _backend():
    return get_backend()


backend, backend_msg = _backend()


def load_records() -> list[dict]:
    try:
        return backend.list_evaluations()
    except Exception as exc:
        st.error(f"Could not load evaluations: {exc}")
        return []


# A little CSS to match the navy / warm-gray identity.
st.markdown(
    f"""
    <style>
      .stApp {{ background-color: {config.WARM_GRAY}; }}
      .block-container {{ padding-top: 2rem; max-width: 1100px; }}
      h1, h2, h3 {{ color: {config.NAVY}; }}
      div[data-testid="stSidebar"] {{ background-color: #ffffff; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def rating_badge(rating: str) -> str:
    color = config.RATING_COLORS.get(rating, "#666")
    label = config.RATING_LABELS.get(rating, rating)
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:12px;font-weight:600;font-size:0.85rem">'
        f"{rating} · {label}</span>"
    )


# ---------------------------------------------------------------------------
# Sidebar: sign-in + navigation + status
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"### 🩺 {config.APP_TITLE}")

    mentor = st.selectbox(
        "Signed in as", ["—"] + config.MENTORS,
        index=0 if "mentor" not in st.session_state
        else (["—"] + config.MENTORS).index(st.session_state.get("mentor", "—")),
    )
    if mentor != "—":
        st.session_state["mentor"] = mentor

    page = st.radio("Go to", ["Evaluate", "Reports", "Setup"], index=0)

    st.divider()
    st.caption(f"**Storage:** {backend.name}")
    st.caption(
        "**AI drafts:** " + ("Live (Claude)" if ai_draft.is_live() else "Simulated")
    )


def require_signin() -> str | None:
    m = st.session_state.get("mentor")
    if not m or m == "—":
        st.info("👈 Select your name under **Signed in as** to begin.")
        return None
    return m


# ===========================================================================
# PAGE: Evaluate
# ===========================================================================
def page_evaluate():
    mentor = require_signin()
    if not mentor:
        return

    st.title("Daily Evaluation")
    st.caption(f"Mentor: **{mentor}**")

    col1, col2, col3 = st.columns(3)
    with col1:
        resident = st.selectbox("Resident", config.RESIDENTS)
    with col2:
        # Skill grouped by domain via labeled options.
        skill_options = []
        for domain, skills in config.SKILL_GROUPS.items():
            for sk in skills:
                skill_options.append(f"{domain} — {sk}")
        choice = st.selectbox("Skill", skill_options)
        skill = choice.split(" — ", 1)[1]
    with col3:
        eval_date = st.date_input("Date", value=date.today())

    st.subheader("Evidence")
    photo_bytes = None
    tab_upload, tab_camera = st.tabs(["Upload photo", "Use camera"])
    with tab_upload:
        up = st.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png"],
                              key="uploader")
        if up:
            photo_bytes = up.getvalue()
    with tab_camera:
        cam = st.camera_input("Take a photo (optional)", key="camera")
        if cam:
            photo_bytes = cam.getvalue()

    if photo_bytes:
        st.image(photo_bytes, width=240, caption="Attached photo")

    note = st.text_area(
        "Observation note",
        placeholder="What did you observe? e.g. 'Placed peripheral IV on first "
        "attempt, independently, with good sterile technique.'",
        height=110,
    )

    # --- AI draft ---
    if st.button("✨ Generate AI draft", type="primary"):
        if not note.strip() and not photo_bytes:
            st.warning("Add a note or a photo first so the draft has something to assess.")
        else:
            with st.spinner("Drafting assessment…"):
                draft = ai_draft.draft_assessment(skill, note, photo_bytes)
            st.session_state["draft"] = draft
            # Pre-seed the mentor's choice with the AI's suggestion.
            st.session_state["final_rating"] = draft["rating"]

    draft = st.session_state.get("draft")
    if draft:
        st.markdown("#### AI-drafted assessment")
        tag = "🟢 Claude" if draft.get("source") == "ai" else "🟡 Simulated"
        st.markdown(
            f"{tag} &nbsp; {rating_badge(draft['rating'])}", unsafe_allow_html=True
        )
        st.write(draft["rationale"])

        st.markdown("#### Mentor validation")
        st.caption("Confirm the AI's rating or override it. You have the final say.")
        final = st.radio(
            "Final rating",
            config.RATINGS,
            index=config.RATINGS.index(
                st.session_state.get("final_rating", draft["rating"])
            ),
            format_func=lambda r: f"{r} — {config.RATING_LABELS[r]}",
            horizontal=True,
            key="final_rating",
        )
        comment = st.text_area(
            "Mentor comment (optional)",
            placeholder="Add anything the rating should be read alongside.",
            height=80,
            key="mentor_comment",
        )

        if st.button("💾 Save evaluation", type="primary"):
            rec = new_record(
                mentor=mentor,
                resident=resident,
                skill=skill,
                date=eval_date.isoformat(),
                ai_rating=draft["rating"],
                ai_rationale=draft["rationale"],
                final_rating=final,
                mentor_comment=comment,
                note=note,
                photo=compress_image_to_b64(photo_bytes) if photo_bytes else "",
            )
            try:
                backend.add_evaluation(rec)
                st.success(
                    f"Saved: {resident} · {skill} · "
                    f"{config.RATING_LABELS[final]}."
                )
                # Clear the draft so the next card starts fresh.
                for k in ("draft", "final_rating", "mentor_comment"):
                    st.session_state.pop(k, None)
                st.rerun()
            except Exception as exc:
                st.error(f"Save failed: {exc}")


# ===========================================================================
# PAGE: Reports
# ===========================================================================
def page_reports():
    st.title("Reports")
    records = load_records()
    if not records:
        st.info("No evaluations recorded yet. Add some on the Evaluate page.")
        return

    report_type = st.selectbox(
        "Report type",
        [
            "Individual skill",
            "Resident transcript",
            "Cohort by skill",
            "Full cohort matrix",
            "Friday gate review",
        ],
    )

    pdf_bytes = None
    csv_text = None
    stem = "report"

    if report_type == "Individual skill":
        c1, c2 = st.columns(2)
        resident = c1.selectbox("Resident", config.RESIDENTS)
        skill = c2.selectbox("Skill", config.SKILLS)
        pdf_bytes = reports.individual_skill_pdf(resident, skill, records)
        csv_text = reports.individual_skill_csv(resident, skill, records)
        stem = f"{resident}_{skill}".replace(" ", "_")
        st.markdown(
            "**Current level:** "
            + rating_badge(reports.latest_rating(records, resident, skill) or "N/A"),
            unsafe_allow_html=True,
        )

    elif report_type == "Resident transcript":
        resident = st.selectbox("Resident", config.RESIDENTS)
        pdf_bytes = reports.transcript_pdf(resident, records)
        csv_text = reports.transcript_csv(resident, records)
        stem = f"{resident}_transcript".replace(" ", "_")
        status, detail = reports.gate_status(records, resident)
        st.markdown(f"**Gate status:** {status} — {detail}")

    elif report_type == "Cohort by skill":
        skill = st.selectbox("Skill", config.SKILLS)
        pdf_bytes = reports.cohort_by_skill_pdf(skill, records)
        csv_text = reports.cohort_by_skill_csv(skill, records)
        stem = f"cohort_{skill}".replace(" ", "_")

    elif report_type == "Full cohort matrix":
        pdf_bytes = reports.cohort_matrix_pdf(records)
        csv_text = reports.cohort_matrix_csv(records)
        stem = "cohort_matrix"
        _render_matrix_preview(records)

    elif report_type == "Friday gate review":
        week_label = st.text_input(
            "Week label", value=f"Week ending {date.today().isoformat()}"
        )
        pdf_bytes = reports.friday_gate_pdf(week_label, records)
        csv_text = reports.friday_gate_csv(week_label, records)
        stem = "friday_gate"
        _render_gate_preview(records)

    st.divider()
    d1, d2 = st.columns(2)
    if pdf_bytes:
        d1.download_button("⬇️ Download PDF", data=pdf_bytes,
                           file_name=f"{stem}.pdf", mime="application/pdf",
                           type="primary")
    if csv_text:
        d2.download_button("⬇️ Download CSV", data=csv_text,
                           file_name=f"{stem}.csv", mime="text/csv")


def _render_matrix_preview(records: list[dict]):
    st.markdown("#### Preview")
    header = "| Resident | " + " | ".join(
        str(i + 1) for i in range(len(config.SKILLS))
    ) + " |"
    sep = "|---" * (len(config.SKILLS) + 1) + "|"
    lines = [header, sep]
    for resident in config.RESIDENTS:
        cells = []
        for skill in config.SKILLS:
            r = reports.latest_rating(records, resident, skill)
            cells.append(r if r else "·")
        lines.append(f"| {resident} | " + " | ".join(cells) + " |")
    st.markdown("\n".join(lines))
    with st.expander("Skill key"):
        for i, skill in enumerate(config.SKILLS, start=1):
            st.write(f"**{i}.** {skill} ({config.skill_domain(skill)})")


def _render_gate_preview(records: list[dict]):
    st.markdown("#### Preview")
    for resident in config.RESIDENTS:
        status, detail = reports.gate_status(records, resident)
        icon = {"PASS": "✅", "FAIL": "❌", "INCOMPLETE": "⚠️"}.get(status, "•")
        st.write(f"{icon} **{resident}** — {status}: {detail}")


# ===========================================================================
# PAGE: Setup
# ===========================================================================
def page_setup():
    st.title("Setup")

    st.subheader("Status")
    st.write(f"- **Storage backend:** {backend.name}")
    st.caption(f"  {backend_msg}")
    st.write(
        f"- **AI drafts:** {'Live Claude API' if ai_draft.is_live() else 'Simulated heuristic'}"
    )
    if not ai_draft.is_live():
        st.caption(
            "  Add `ANTHROPIC_API_KEY` to `.streamlit/secrets.toml` for real "
            "Claude-drafted assessments. See `secrets.toml.example`."
        )

    st.subheader("Program configuration")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Mentors**")
        for m in config.MENTORS:
            st.write(f"- {m}")
        st.markdown("**Residents**")
        for r in config.RESIDENTS:
            st.write(f"- {r}")
    with c2:
        st.markdown("**Skills by domain**")
        for domain, skills in config.SKILL_GROUPS.items():
            st.write(f"*{domain}*")
            for sk in skills:
                st.write(f"&nbsp;&nbsp;• {sk}", unsafe_allow_html=True)
    st.caption("Edit `config.py` to change mentors, residents, or the skill curriculum.")

    st.subheader("Rubric")
    for r in config.RATINGS:
        st.markdown(
            f"{rating_badge(r)} &nbsp; {config.RATING_DESCRIPTIONS[r]}",
            unsafe_allow_html=True,
        )

    st.subheader("Recent evaluations")
    records = load_records()
    if not records:
        st.caption("None yet.")
        return
    st.caption(f"{len(records)} total. Showing the 15 most recent.")
    for rec in records[:15]:
        ts = rec.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
        cols = st.columns([5, 1])
        cols[0].markdown(
            f"{ts} · **{rec.get('resident')}** · {rec.get('skill')} · "
            + rating_badge(rec.get("final_rating", "")),
            unsafe_allow_html=True,
        )
        if cols[1].button("Delete", key=f"del_{rec['id']}"):
            backend.delete_evaluation(rec["id"])
            st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
if page == "Evaluate":
    page_evaluate()
elif page == "Reports":
    page_reports()
else:
    page_setup()
