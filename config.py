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
    "N": "Not yet",
}

RATING_DESCRIPTIONS = {
    "C": "Performs the skill safely and to tolerance, unaided. Cleared for this skill.",
    "D": "Minor prompting or minor errors within tolerance. Brief focused repetition, then re-check.",
    "N": "Unsafe technique or out of tolerance. Named remediation before clinic entry for this skill.",
}

# Colors used in PDF/CSV/legend rendering.
RATING_COLORS = {
    "C": "#2E7D32",  # green
    "D": "#ED6C02",  # amber
    "N": "#C62828",  # red
}

# The Friday competency gate: "Competent across all domains = PASS." A resident
# clears the gate with no "Not yet" (N) ratings and at least this fraction at "C".
GATE_MIN_COMPETENT = 0.6  # fraction of evaluated skills that must be "C"

# ---------------------------------------------------------------------------
# People and competencies — AIDM Orthodontic Preclinical Boot Camp 2026.
# Faculty per the curriculum; residents are MASKED IDs (privacy by default —
# typodont/peer-practice only, no patient data, names masked).
# ---------------------------------------------------------------------------
MENTORS = [
    "Dr. Ravikumar Anthony",   # Program Director
    "Dr. Ajay Kubavat",        # Adjunct Director of Academic Affairs
    "Dr. Anthony Patel",       # Faculty (Friday)
]

# Founding cohort: 8 Residency Year 1 residents, masked.
RESIDENTS = [
    "Resident 1",
    "Resident 2",
    "Resident 3",
    "Resident 4",
    "Resident 5",
    "Resident 6",
    "Resident 7",
    "Resident 8",
]

# The seven interlinked skill domains, each with its assessable skills.
# The flat list (SKILLS) is derived below.
SKILL_GROUPS = {
    "Foundations & Bonding Science": [
        "Ergonomics & operator positioning",
        "Bracket types & prescriptions",
        "Bonding material science & isolation",
    ],
    "Direct Bonding": [
        "Direct bonding (full arch)",
        "Debonding & rebonding",
    ],
    "Wire Science & Bending": [
        "Wire identification (SS / NiTi / Gummetal)",
        "First-order bends & arch form",
        "Second / third-order & control bends",
        "Clinical arches & auxiliaries",
    ],
    "Archwire Placement & Ligation": [
        "Archwire seating & engagement",
        "Elastomeric & steel ligation",
        "Cinchback",
        "Archwire sequencing logic",
    ],
    "Records & Cephalometrics": [
        "Standardized photographic series",
        "Cephalometric landmark identification",
        "Dolphin workflow & tracing",
    ],
    "Advanced Bonding & Digital Orthodontics": [
        "Indirect bonding (IDB)",
        "Aligner attachment placement",
        "Interproximal reduction (IPR)",
        "Removable appliance fabrication",
        "Banding & separators",
        "Intraoral scanning",
        "Digital workflow / ClinCheck / aligners",
    ],
    "Patient Care & Emergencies": [
        "Patient instructions",
        "Orthodontic emergency management",
    ],
}

SKILLS = [skill for group in SKILL_GROUPS.values() for skill in group]


def skill_domain(skill: str) -> str:
    """Return the domain heading a skill belongs to (or 'Other')."""
    for domain, skills in SKILL_GROUPS.items():
        if skill in skills:
            return domain
    return "Other"
