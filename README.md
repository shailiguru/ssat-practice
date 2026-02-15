# SSAT Practice Test

An SSAT practice test application that generates grade-appropriate questions using Claude AI, tracks progress over time, and automatically adjusts difficulty. Available as a **web app** (Streamlit) or **terminal app** (CLI).

## Features

- **Full Practice Tests** — Simulate complete SSAT test conditions with timed sections
- **Section Practice** — Focus on a single section (Math, Verbal, or Reading)
- **Quick Drills** — 10-20 targeted questions with instant feedback
- **Dynamic Question Generation** — Claude AI generates infinite variety of SSAT-style questions
- **Progress Tracking** — Score trends, topic breakdowns, and personalized recommendations
- **Adaptive Difficulty** — Questions get harder as skills improve
- **Writing Practice** — Timed writing prompts with AI-powered feedback
- **Review Mode** — Review missed questions with explanations and retry drills

## Supported Levels

| Level | Grades | Sections | Scoring |
|-------|--------|----------|---------|
| Elementary | 3-4 | Math, Verbal, Reading, Writing | No penalty for wrong answers |
| Middle | 5-7 | Quant 1, Reading, Verbal, Quant 2, Writing | -0.25 for wrong answers |

## Quick Start — Web App (Recommended)

The easiest way to use SSAT Practice is through the web interface.

### Run Locally

```bash
cd ssat-practice
pip install -r requirements.txt

# Configure your API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Launch the web app
streamlit run web_app.py
```

A browser tab will open automatically. Create a student profile and start practicing!

### Deploy to Streamlit Community Cloud (Free)

For zero-setup access from any browser:

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
3. Click **New app** → select your repo → set main file to `web_app.py`
4. In **Settings → Secrets**, paste:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-your-key-here"
   ```
5. Click **Deploy** — your app will be live at a public URL

> **Note:** SQLite data on Streamlit Cloud persists during the app instance lifetime but resets on redeployment. This is fine for practice use.

### Pre-generate Questions (Recommended)

After creating a profile, go to **Settings** (sidebar) → **Pre-generate Question Pool** to build a question bank. This avoids wait times during tests.

---

## Alternative: Terminal App (CLI)

### Prerequisites

- Python 3.10+
- An Anthropic API key ([get one here](https://console.anthropic.com/))

### Installation

```bash
cd ssat-practice
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### First Run

```bash
python app.py
```

On first run, you'll be prompted to create a student profile. The app will automatically select the appropriate SSAT level based on the student's grade.

## Usage

### Main Menu

1. **Start Practice Test (Full)** — Complete SSAT simulation with all sections, timed
2. **Section Practice** — Pick one section to practice
3. **Quick Drill** — Fast targeted practice (10-20 questions) with instant feedback
4. **Review Missed Questions** — Review mistakes and retry them
5. **Writing Practice** — Practice with writing prompts and AI feedback
6. **View Progress & Scores** — Dashboard with score trends and topic analysis
7. **Switch Profile** — Switch between student profiles
8. **Settings** — Timer toggle, level override, question generation, progress reset

### Tips for Students

- Start with **Quick Drills** to warm up on specific topics
- Use **Section Practice** to build endurance for full sections
- Take **Full Practice Tests** periodically to track overall progress
- **Review missed questions** regularly — they'll come back in spaced repetition!
- The app adjusts difficulty automatically, so questions get harder as you improve

## Configuration

Edit `.env` to customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (required) | Your Anthropic API key |
| `SSAT_DB_PATH` | `ssat_practice.db` | Database file location |
| `SSAT_MODEL` | `claude-sonnet-4-5-20250929` | Claude model for question generation |
| `SSAT_TIMER_ENABLED` | `true` | Enable/disable section timers |
| `SSAT_QUESTIONS_PER_BATCH` | `25` | Questions per batch generation |

## Score Reports

Scores are **estimated approximations** for practice purposes. They use linear scaling and approximate percentile tables. Official SSAT scores use proprietary equating formulas that vary by test form.

- **Elementary:** 300-600 per section, 900-1800 total
- **Middle:** 440-710 per section, 1320-2130 total

## File Structure

```
ssat-practice/
├── web_app.py                # Streamlit web app (recommended)
├── app.py                    # CLI entry point (alternative)
├── config.py                 # Configuration & constants
├── database.py               # SQLite schema & queries
├── models.py                 # Data classes
├── scoring.py                # Scoring engine
├── question_generator.py     # Claude API integration
├── question_cache.py         # Question pool management
├── test_runner.py            # CLI test orchestration
├── timer.py                  # CLI countdown timer
├── display.py                # Rich terminal UI (CLI only)
├── progress.py               # Analytics & recommendations
├── leveling.py               # Adaptive difficulty
├── writing.py                # Writing prompts
├── review.py                 # CLI review mode
├── data/
│   ├── percentile_tables.json
│   └── vocabulary_lists.json
├── .streamlit/
│   └── secrets.toml.example  # Template for Streamlit Cloud
├── requirements.txt
├── .env.example
└── README.md
```
