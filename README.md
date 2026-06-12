# ⚽ World Cup Briefing Tool

An AI-assisted workflow for generating structured football briefings using news aggregation, tactical references, and LLM-powered synthesis.

This project was created to support fast-turnaround football analysis workflows during the Data World Cup 2026 project.

The tool:
- collects recent match-related news
- filters and organizes references
- generates structured pre-match briefings
- generates structured post-match briefings
- suggests tactical hypotheses, metrics, and article ideas

---

# 🚀 Features

- Google News RSS aggregation
- Reference source prioritization
- Date filtering (only recent articles)
- AI-generated tactical and analytical briefings
- CSV export of collected articles
- Markdown export of generated reports
- Config-based workflow (no need to edit the script)

---

# 📂 Project Structure

```bash
worldcup-briefing-tool/
│
├── briefing.py
├── post_match_briefing.py
├── match_config.json
├── post_match_config.json
├── reference_sources.csv
├── requirements.txt
├── .env
├── .gitignore
│
└── outputs/
```

---

# ⚙️ Installation

## 1. Clone the repository

```bash
git clone <your-repo-url>
cd worldcup-briefing-tool
```

---

## 2. Create a virtual environment (recommended)

### Mac/Linux

```bash
python -m venv .venv
source .venv/bin/activate
```

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

# 🔑 NVIDIA API Key Setup

This project uses NVIDIA's AI inference platform.

## 1. Create an NVIDIA account

Go to:

https://build.nvidia.com/explore/discover

Create a free account if needed.

---

## 2. Find the model

Search for:

```text
openai/gpt-oss-120b
```

---

## 3. Generate an API Key

Inside the model page:
- click **Get API Key**
- create a new key
- copy the generated key

---

## 4. Create a `.env` file

Create a file named:

```bash
.env
```

Add:

```env
NVIDIA_API_KEY=your_api_key_here
```

---

# ⚠️ Important

Never upload your `.env` file to GitHub.

The repository already ignores it through `.gitignore`.

---

# 📝 Match Configuration

Edit the `match_config.json` file:

```json
{
  "team_a": "Mexico",
  "team_b": "South Africa",
  "match_date": "2026-06-11",
  "generate_pdf": true
}
```

## Parameters

| Parameter | Description |
|---|---|
| `team_a` | Home team |
| `team_b` | Away team |
| `match_date` | Match date (`YYYY-MM-DD`) |

Optional parameters:

| Parameter | Default | Description |
|---|---|---|
| `output_dir` | `outputs` | Output folder |
| `reference_sources_path` | `reference_sources.csv` | CSV with trusted source categories and URLs |
| `max_articles_per_query` | `8` | Max news results per query |
| `days_before_match` | `30` | Article recency filter |
| `generate_pdf` | `false` | Generate a PDF automatically after the Markdown briefing |
| `pdf_output_dir` | Same as `output_dir` | Optional folder for generated PDFs |

---

# 📚 Reference Sources

Trusted sources are stored in:

```bash
reference_sources.csv
```

Schema:

```csv
category,name,url
Analytics & Data,Opta Analyst,https://theanalyst.com
```

Both workflows use this file:
- pre-match uses it to prioritize trusted sources in the collected articles
- post-match uses it to run targeted source searches before broader searches

---

# ▶️ Running the Project

## Pre-match briefing

```bash
python briefing.py
```

## Post-match briefing

Edit `post_match_config.json`:

```json
{
  "team_a": "Mexico",
  "team_b": "South Africa",
  "match_date": "2026-06-11",
  "match_datetime_utc": "2026-06-11T22:00:00Z",
  "score": "2-1",
  "generate_pdf": true
}
```

`match_datetime_utc` is optional. When provided, post-match filtering starts from that exact UTC time instead of midnight on the match date.

`reference_sources_path` is optional. It points to the shared CSV used by both pre-match and post-match workflows to prioritize trusted analytics, tactical, and media sources.

`reference_urls` can still be added to `post_match_config.json` when you want to force one or more specific articles into the post-match briefing. It is not needed for normal runs.

Other optional post-match parameters:

| Parameter | Default | Description |
|---|---|---|
| `output_dir` | `outputs` | Output folder |
| `max_articles_per_query` | `8` | Max general news results per query |
| `max_reference_articles_per_query` | `3` | Max trusted-source results per targeted query |
| `days_after_match` | `3` | Post-match article window |
| `generate_pdf` | `false` | Generate a PDF automatically after the Markdown briefing |
| `pdf_output_dir` | Same as `output_dir` | Optional folder for generated PDFs |

Then run:

```bash
python post_match_briefing.py
```

You can also pass a custom config file:

```bash
python post_match_briefing.py path/to/config.json
```

---

# 📤 Outputs

The script generates:

## 1. Articles CSV

```bash
outputs/mexico_vs_south_africa_articles.csv
```

Contains:
- titles
- URLs
- publication dates
- summaries
- source prioritization

---

## 2. AI Briefing

```bash
outputs/mexico_vs_south_africa_briefing.md
```

Contains:
- main storylines
- tactical hypotheses
- key players
- metrics to track
- visual ideas
- article angle suggestions

## 3. Post-Match Articles CSV

```bash
outputs/mexico_vs_south_africa_post_match_articles.csv
```

Contains post-match references collected from the match date through the configured post-match window.

## 4. Post-Match Briefing

```bash
outputs/mexico_vs_south_africa_post_match_briefing.md
```

Contains:
- confirmed match facts from collected sources
- post-match storylines
- tactical reading
- turning points to review
- data checks
- visualization ideas
- article angles

---

# 📄 Markdown to PDF

Edit `pdf_config.json`:

```json
{
  "markdown_path": "outputs/mexico_vs_south_africa_post_match_briefing.md",
  "output_dir": "outputs"
}
```

Then run:

```bash
python md_to_pdf.py
```

You can also pass a custom config:

```bash
python md_to_pdf.py path/to/pdf_config.json
```

Optional config fields:

| Parameter | Description |
|---|---|
| `markdown_path` | Source Markdown file |
| `output_dir` | Folder where the PDF will be saved |
| `output_filename` | Optional custom PDF filename |
| `output_path` | Optional full PDF path; overrides `output_dir` and `output_filename` |

The PDF converter uses `reportlab`, which is included in `requirements.txt`.

---

# 🧠 Reference Sources

## Analytics & Data
- The Analyst
- StatsBomb
- Total Football Analysis
- Hudl
- FIFA Project

## Tactical Analysis
- Coaches' Voice
- Breaking The Lines
- Tifo Football
- Spielverlagerung

## Media & Tournament Coverage
- BBC Sport
- The Guardian
- ESPN FC
- Reuters
- FourFourTwo
- GOAL
- The Athletic

---

# 🎯 Project Goal

This tool was designed as a lightweight MVP to support:
- football storytelling
- tactical preparation
- pre-match ideation
- fast post-match workflows
- collaborative football analytics projects

The objective is not to replace analysis, but to accelerate context gathering and idea generation before and after matches.
