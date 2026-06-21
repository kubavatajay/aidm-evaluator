"""Static configuration for the AIDM Bootcamp Evaluator.

Edit RESIDENTS and SKILLS to match your cohort. Everything else in the app
reads from here, so this is the single place to curate the program.
"""

# ---------------------------------------------------------------------------
# Branding / theme (kept in sync with .streamlit/config.toml)
# ---------------------------------------------------------------------------
NAVY = "#1F3864"
WARM_GRAY = "#f5f5f3"
APP_TITLE = "AIDM Bootcamp Evaluator"

# ---------------------------------------------------------------------------
# Rubric: the three competency levels every skill is rated on.
# C / D / N is the program's shorthand.
# ---------------------------------------------------------------------------
RATINGS = ["C", "D", "N"]

RATING_LABELS = {
    "C": "Competent",
    "D": "Developing",
    "N": "Needs Improvement",
}

RATING_DESCRIPTIONS = {
    "C": "Performs the skill independently and reliably, to standard.",
    "D": "Performs the skill with prompting or partial success; progressing.",
    "N": "Cannot yet perform the skill to standard; needs focused practice.",
}

# Colors used in PDF/CSV/legend rendering.
RATING_COLORS = {
    "C": "#2E7D32",  # green
    "D": "#ED6C02",  # amber
    "N": "#C62828",  # red
}

# A "Friday gate" passes when the resident has no N's and meets the C threshold.
GATE_MIN_COMPETENT = 0.6  # fraction of evaluated skills that must be "C"

# ---------------------------------------------------------------------------
# People and competencies. Replace these with your real cohort/curriculum.
# ---------------------------------------------------------------------------
MENTORS = [
    "Dr. Patel",
    "Dr. Nguyen",
    "Dr. Okafor",
    "Dr. Romano",
]

RESIDENTS = [
    "Alex Kim",
    "Bianca Torres",
    "Caleb Johnson",
    "Dana Whitfield",
    "Ekene Eze",
    "Farah Haddad",
]

# Skills grouped by domain. The flat list (SKILLS) is derived below.
SKILL_GROUPS = {
    "Airway": [
        "Bag-mask ventilation",
        "Endotracheal intubation",
        "Supraglottic airway placement",
    ],
    "Vascular Access": [
        "Peripheral IV placement",
        "Ultrasound-guided IV",
        "Central line insertion",
    ],
    "Procedures": [
        "Suturing & wound closure",
        "Lumbar puncture",
        "Chest tube placement",
    ],
    "Clinical Reasoning": [
        "Differential diagnosis",
        "Point-of-care ultrasound (POCUS)",
        "Disposition decision-making",
    ],
}

SKILLS = [skill for group in SKILL_GROUPS.values() for skill in group]


def skill_domain(skill: str) -> str:
    """Return the domain heading a skill belongs to (or 'Other')."""
    for domain, skills in SKILL_GROUPS.items():
        if skill in skills:
            return domain
    return "Other"
