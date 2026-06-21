# AIDM Bootcamp Evaluator

A Streamlit app for mentors to assess residents on procedural skills during a
bootcamp: capture a photo + note, get an **AI-drafted C/D/N rating**, validate
or override it, save, and export reports as **PDF or CSV**.

- **Storage:** Google Sheets (free, with a personal Gmail) or a local JSON file.
- **AI drafts:** real Claude API, with a transparent simulated fallback.
- **Photos** are compressed and embedded directly in the data and the PDFs — no
  second cloud service needed.

---

## Quick start (zero config)

```bash
pip install -r requirements.txt
streamlit run app.py
```

It runs immediately on **local storage** with **simulated** AI drafts. Open the
browser tab Streamlit prints, pick your name under *Signed in as*, and start
evaluating. This is enough to try the whole flow.

---

## Turning on the real features

Copy the example secrets file and fill in only the parts you want:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

### 1. Real Claude AI drafts

Add your key (from <https://console.anthropic.com>):

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

The app uses `claude-opus-4-8`. With a photo attached, Claude looks at the image
too. Without a key, a deterministic keyword heuristic produces a clearly-labeled
*simulated* draft so the app still works.

### 2. Google Sheets storage (free, personal Gmail — no Workspace needed)

Google **Sheets** is free for any Google account; you do **not** need a paid
Google Workspace subscription. One-time setup:

1. Create a free project at <https://console.cloud.google.com>.
2. Enable the **Google Sheets API** and **Google Drive API** for it.
3. Create a **Service Account** → add a **JSON key** → download it.
4. Create a normal Google Sheet in your Drive. Copy the long ID from its URL:
   `https://docs.google.com/spreadsheets/d/`**`THIS_ID`**`/edit`
5. **Share** that sheet (Editor) with the service account's `client_email`.
6. Paste the JSON fields and the sheet ID into `.streamlit/secrets.toml`
   (see `secrets.toml.example` for the exact layout).

On the next launch the *Setup* page will show **Storage: Google Sheets**.

---

## The app

- **Evaluate** — sign in, pick resident / skill / date, attach a photo (upload or
  camera) and a note, generate the AI draft, confirm or override the rating, add
  a comment, save.
- **Reports** — five exports, each as PDF (with embedded photos where relevant)
  or CSV:
  1. **Individual skill** — one resident, one skill, full history.
  2. **Resident transcript** — one resident, all skills, plus gate status.
  3. **Cohort by skill** — every resident's current level on one skill.
  4. **Full cohort matrix** — residents × skills grid.
  5. **Friday gate review** — weekly pass/fail per resident with reasons.
- **Setup** — status, the rubric, the program roster, and recent-evaluation
  management.

## Customizing

Everything program-specific lives in **`config.py`**: mentors, residents, the
skill curriculum (grouped by domain), the C/D/N rubric text and colors, and the
Friday-gate threshold. Edit that one file to fit your cohort.

## Project layout

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI (Evaluate / Reports / Setup) |
| `config.py` | Roster, skills, rubric, theme |
| `storage.py` | Local-JSON and Google-Sheets backends + photo compression |
| `ai_draft.py` | Claude API draft + simulated fallback |
| `reports.py` | PDF/CSV generation for all five report types |

## Notes

- The AI never has the final say — every saved rating is the mentor's validated
  choice.
- Photos are compressed to fit within a single spreadsheet cell, so a single
  Google Sheet is the only thing that must persist.
- Local storage (`data/evaluations.json`) is git-ignored. Commit nothing with
  resident data to a public repo.
