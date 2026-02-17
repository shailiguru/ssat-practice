# Product Requirements Document: SSAT Practice

**Product Name:** SSAT Practice
**Version:** 1.0
**Last Updated:** February 2026
**Status:** Deployed (Streamlit Cloud)

---

## 1. Overview

SSAT Practice is an AI-powered study tool for students preparing for the SSAT (Secondary School Admission Test). It generates unlimited practice questions using Claude, tracks progress across sessions with persistent cloud storage, and uses AI agents to provide personalized insights.

**Target Users:**
- Students in grades 3-7 preparing for SSAT Elementary or Middle Level exams
- Parents monitoring their child's preparation progress

**Core Value Proposition:**
- Unlimited AI-generated practice questions (no static question banks)
- Realistic test simulation with timed sections and scoring
- Persistent progress tracking across devices via cloud database
- AI-powered mistake analysis, vocabulary building, and parent reports
- Gamification (streaks, badges) to build consistent study habits

---

## 2. Architecture

### System Diagram

```
┌─────────────────────────────────────┐
│         Streamlit Cloud             │
│  ┌───────────────────────────────┐  │
│  │         web_app.py            │  │
│  │  (UI, routing, session state) │  │
│  └──────┬──────────┬─────────────┘  │
│         │          │                │
│  ┌──────▼──┐  ┌────▼──────────┐    │
│  │database │  │  agents.py    │    │
│  │  .py    │  │  (AI agents)  │    │
│  └────┬────┘  └──────┬────────┘    │
└───────┼──────────────┼──────────────┘
        │              │
   ┌────▼────┐   ┌─────▼──────┐
   │Supabase │   │ Claude API │
   │PostgreSQL│   │ (Sonnet)   │
   └─────────┘   └────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit (Python) |
| Backend | Python 3.11+ |
| Database | Supabase PostgreSQL (session pooler) |
| AI Model | Claude Sonnet 4.5 (via Anthropic SDK) |
| Hosting | Streamlit Community Cloud |
| DB Driver | psycopg2-binary |

### File Structure

```
ssat-practice/
├── web_app.py          # Main Streamlit app (1865 lines) — UI, routing, all pages
├── database.py         # PostgreSQL database layer (891 lines) — all queries
├── agents.py           # AI agent functions (163 lines) — Claude API calls
├── badges.py           # Badge definitions and check logic (91 lines)
├── config.py           # Configuration, SSAT constants, level definitions
├── models.py           # Dataclasses: Student, Question, Answer, TestSession, etc.
├── question_generator.py  # Claude-powered question generation with JSON parsing
├── question_cache.py   # Question pool management and auto-replenishment
├── scoring.py          # Raw → scaled score conversion, percentile lookup
├── leveling.py         # Adaptive difficulty and level-up/down logic
├── progress.py         # Progress tracker with rule-based recommendations
├── display.py          # Rich console display helpers (legacy CLI)
├── review.py           # Review session logic (legacy CLI)
├── writing.py          # Writing sample prompts and AI grading
├── timer.py            # Timer utilities (legacy CLI)
├── app.py              # Legacy CLI entry point
├── requirements.txt    # Python dependencies
├── data/
│   ├── percentile_tables.json  # SSAT score-to-percentile mapping
│   └── vocabulary_lists.json   # Grade-level vocabulary reference
└── .streamlit/
    └── secrets.toml    # API keys (not in repo)
```

---

## 3. Database Schema

**Engine:** Supabase PostgreSQL (connection via session pooler, port 5432)

### Tables

| Table | Purpose |
|-------|---------|
| `students` | Student profiles (name, grade, level) |
| `questions` | AI-generated question bank |
| `test_sessions` | Practice session metadata and scores |
| `answers` | Individual question responses |
| `topic_mastery` | Per-topic accuracy and difficulty tracking |
| `writing_samples` | Essay prompts, responses, and AI feedback |
| `badges` | Earned gamification badges per student |
| `vocabulary` | Personal vocabulary study cards per student |

### Key Relationships

```
students (1) ──< (N) test_sessions
students (1) ──< (N) answers
students (1) ──< (N) topic_mastery
students (1) ──< (N) badges
students (1) ──< (N) vocabulary
test_sessions (1) ──< (N) answers
questions (1) ──< (N) answers
```

---

## 4. Features

### Phase 1: Core Test Engine

#### F1. Student Profile Management
- Create/select student profiles with name, grade (3-7), and SSAT level
- Automatic level assignment: grades 3-4 → Elementary, grades 5-7 → Middle
- Persistent across sessions via cloud database

#### F2. AI Question Generation
- Claude generates questions on-demand in structured JSON format
- Supports 7 question types: Synonym, Analogy, Arithmetic, Algebra, Geometry, Word Problem, Reading Comprehension
- Questions tagged with type, topic, and difficulty (1-5 scale)
- Duplicate prevention — students never see the same question twice per session
- Reading comprehension includes full passages with multiple follow-up questions
- Auto-replenishment when unseen pool drops below threshold

#### F3. Full Practice Test
- Simulates a complete SSAT with all sections in order
- Elementary: Math (30Q/30min), Verbal (30Q/20min), Reading (28Q/30min)
- Middle: Quant 1 (25Q/30min), Reading (40Q/40min), Verbal (60Q/30min), Quant 2 (25Q/30min)
- Real countdown timer per section
- No instant feedback during test (mirrors real SSAT)
- Writing sample section with AI-graded essay feedback
- Complete score report at end: raw scores, scaled scores, percentiles per section

#### F4. Scoring System
- Raw score calculation with wrong-answer penalty (Middle level: -0.25 per wrong)
- Raw-to-scaled score conversion using official SSAT score ranges
- Percentile lookup from reference tables
- Elementary: 300-600 per section / Middle: 440-710 per section

### Phase 2: Practice Modes

#### F5. Quick Drill
- 10-20 questions on a single topic (user chooses topic and count)
- Instant feedback after each question (correct/wrong + explanation)
- Session summary with accuracy breakdown at completion
- Best for targeted skill building

#### F6. Section Practice
- Practice a full section (e.g., Verbal only) with timer
- Mimics real test conditions for that section
- Scored and tracked separately

#### F7. 5-Minute Mini Test
- 10 mixed questions across all topic types
- Fixed 5-minute countdown timer (always on)
- No instant feedback (test conditions)
- Results page with per-topic accuracy breakdown
- Quick, low-pressure way to practice daily

### Phase 3: Progress Tracking

#### F8. Progress Dashboard
- Total questions answered, full tests completed, practice sessions
- Per-topic accuracy bars (Synonyms, Analogies, Arithmetic, etc.)
- Scaled score trend across full tests
- Recent session history with dates and scores

#### F9. Topic Mastery Tracking
- Tracks accuracy per question type over all attempts
- Rolling window (last 50 attempts) for trend detection
- Visual mastery indicators on dashboard

#### F10. Adaptive Difficulty
- Difficulty level (1.0-5.0) adjusts per topic based on performance
- Increases by 0.5 when session accuracy > 85% (on 5+ questions)
- Decreases by 0.5 when session accuracy < 50%
- Questions generated at the student's current difficulty level

#### F11. Level Progression
- Automatic level-up recommendation when mastery criteria met
- Requires 85%+ accuracy on 20+ questions across all topics
- Requires 85th+ percentile on last 3 full tests
- Level-down protection: only suggests if below 40th percentile on 2 consecutive tests

#### F12. Review Page
- Three tabs: Wrong Answers, Topic Breakdown, Session History
- Wrong answers show question, student's choice, correct answer, and explanation
- Topic breakdown shows accuracy and trend per question type
- Session history lists all past sessions with scores

#### F13. Rule-Based Recommendations
- Identifies weak topics (< 60% accuracy) and near-mastery topics (60-85%)
- Score trend detection across full tests
- Highlights strong areas for encouragement
- Suggests next actions (take full test, focus on weak area, etc.)

### Phase 4: Infrastructure

#### F14. Streamlit Web App
- Converted from CLI (Rich terminal) to Streamlit web interface
- Sidebar navigation with student selector
- Session state-driven page routing
- Responsive layout with columns, expanders, and metrics

#### F15. Supabase PostgreSQL Migration
- Migrated from SQLite (single-file, Streamlit Cloud read-only issue) to Supabase
- Uses session pooler (port 5432) for connection stability
- DSN string passed directly to psycopg2
- Handles dotted usernames in connection strings
- Auto-creates all tables on first connection

#### F16. Streamlit Cloud Deployment
- Deployed at Streamlit Community Cloud
- Secrets managed via `.streamlit/secrets.toml` (not in repo)
- Required secrets: `ANTHROPIC_API_KEY`, `SUPABASE_DB_URL`

### Phase 5: AI Agents & Gamification

#### F17. Answer Check Nudge
- **Problem:** Students rush through questions without double-checking
- **Solution:** Intercepts every Submit action with a confirmation step
- Shows the selected answer with a rotating nudge message ("Did you double-check?", "Are you sure?", etc.)
- Two buttons: "Yes, Submit" (records answer) and "Go Back" (returns to question)
- Tracks how many answers the student changed after being nudged
- Displays changed-answer count on completion screen
- Applied to all 4 test modes: Quick Drill, Mini Test, Full Test, Section Practice
- Lighter nudge (buttons only, no extra text) for timed tests

#### F18. Study Streaks & Badges
- **Problem:** No motivation system to build consistent practice habits
- **Streaks:** Counts consecutive days with at least one practice session
- **Badges (11 total):**

| Badge | Criteria | Icon |
|-------|----------|------|
| First Steps | Complete first session | Target |
| 3-Day Streak | 3 consecutive practice days | Fire |
| Week Warrior | 7 consecutive practice days | Lightning |
| Two-Week Titan | 14 consecutive practice days | Muscle |
| Century Club | 100 questions answered | 100 |
| 500 Club | 500 questions answered | Trophy |
| Math Whiz | 85%+ on 20+ math questions | Numbers |
| Word Master | 85%+ on 20+ verbal questions | Books |
| Speed Demon | Mini test with 2+ min to spare | Stopwatch |
| Perfect 10 | 10/10 on a mini test | Star |
| Double Checker | Change 5+ answers after nudge | Magnifier |

- Badge checks run after every session completion
- New badges trigger `st.balloons()` celebration
- Home page displays streak metrics and earned badges
- Sidebar shows current streak next to student name

#### F19. Mistake Pattern Detector (AI Agent)
- **Problem:** Review page shows accuracy numbers but not *why* the student is getting questions wrong
- **Trigger:** "Analyze My Mistakes" button on Review page (4th tab: AI Insights)
- **How it works:**
  1. Collects up to 30 most recent wrong answers with full question context
  2. Sends to Claude with system prompt: "Analyze this student's mistake patterns"
  3. Claude returns markdown with 3-5 specific patterns and 2-3 actionable tips
- **Architecture:** Single-turn Claude API call (one request → one response)
- **Example patterns:** "Picks words that sound similar rather than mean the same thing", "Struggles with fractions in word problems but handles standalone fractions well"
- Result cached in session_state (no re-call on page refresh within session)

#### F20. Parent Report Agent (AI Agent)
- **Problem:** Parents want progress updates without hovering over their child
- **Trigger:** "Generate Parent Report" button on Progress page
- **How it works:**
  1. Gathers student stats, topic mastery, streak data, session count
  2. Sends to Claude with system prompt: "Write a 200-300 word parent-friendly report"
  3. Claude returns a warm, actionable summary with strengths, areas for growth, and specific next-week suggestions
- **Architecture:** Single-turn Claude API call
- **Tone:** Warm, encouraging, jargon-free, age-appropriate
- Result displayed as formatted markdown with copy capability

#### F21. Vocabulary Builder (AI Agent + New Page)
- **Problem:** Students miss verbal questions but never study the missed words
- **Trigger:** "Build from Missed Questions" button on Vocabulary page
- **How it works:**
  1. Extracts words from missed synonym and analogy questions
  2. Sends word list to Claude with system prompt: "Generate kid-friendly definitions"
  3. Claude returns JSON array with definition, example sentence, and memory tip per word
  4. Words saved to `vocabulary` table for persistent study
- **Architecture:** Single-turn Claude API call returning structured JSON
- **Study Modes:**
  - **Word Cards:** Expandable cards showing word, definition, example, and memory tip
  - **Quiz Me:** Pick-the-definition multiple choice quiz with randomized wrong choices
- Tracks times_reviewed and times_correct per word

---

## 5. AI Agent Architecture

All AI features use **single-turn** Claude API calls. There is no multi-turn conversation, no agent memory, and no tool use. Each agent follows the same pattern:

```
User clicks button
  → App collects relevant data from database
  → Builds system prompt (role + format instructions)
  → Builds user prompt (student data + context)
  → Single _call_claude() API call
  → Parses response (markdown or JSON)
  → Displays result in UI
```

### Agent Summary

| Agent | Input | Output | Model | Max Tokens |
|-------|-------|--------|-------|------------|
| Question Generator | Topic, difficulty, level | JSON array of questions | Sonnet 4.5 | 8192 |
| Writing Grader | Student essay + prompt | Markdown feedback | Sonnet 4.5 | 2048 |
| Mistake Analyzer | 30 wrong Q&A pairs | Markdown (patterns + tips) | Sonnet 4.5 | 2048 |
| Parent Report | Stats + mastery data | Markdown (200-300 words) | Sonnet 4.5 | 2048 |
| Vocabulary Builder | List of missed words | JSON array of word cards | Sonnet 4.5 | 4096 |

### Why Single-Turn?
- **Cost efficient:** One API call per feature invocation
- **Predictable latency:** No waiting for multi-step chains
- **Simple error handling:** Success or failure, no partial states
- **Sufficient for use case:** These tasks don't require iterative reasoning or tool use

---

## 6. State Management

The app uses Streamlit's `session_state` as the primary state machine. Key state variables:

| Key | Purpose |
|-----|---------|
| `current_page` | Active page route (home, drill, mini_test, full_test, etc.) |
| `student` | Current Student object |
| `test_phase` | Phase within a test flow (setup, question, confirm, feedback, complete) |
| `test_questions` | List of questions for current session |
| `test_index` | Current question index |
| `test_answers` | Accumulated answers |
| `test_changed_answers` | Count of answers changed after nudge |
| `test_start_time` | Timer start for timed modes |
| `cached_mistake_analysis` | Cached AI mistake analysis result |
| `cached_parent_report` | Cached AI parent report result |

### Test Flow State Machine

```
setup → question → confirm → feedback (drill only) → question → ... → complete
                      ↓
                  (Go Back)
                      ↓
                   question
```

---

## 7. Configuration

All configuration lives in `config.py` and can be overridden via environment variables or Streamlit secrets:

| Setting | Default | Description |
|---------|---------|-------------|
| `ANTHROPIC_API_KEY` | (required) | Claude API key |
| `SUPABASE_DB_URL` | (required) | PostgreSQL connection string |
| `SSAT_MODEL` | claude-sonnet-4-5-20250929 | Claude model for all AI calls |
| `SSAT_TIMER_ENABLED` | true | Enable/disable countdown timers |
| `SSAT_QUESTIONS_PER_BATCH` | 25 | Questions generated per API call |

---

## 8. Development History

| Commit | Feature |
|--------|---------|
| `aa28071` - `0b4b6da` | Initial Streamlit app + Cloud deployment fixes |
| `f15456b` | Fix SQLite cross-thread error |
| `890aaab` | Fix API key loading from Streamlit secrets |
| `c925413` | Fix math questions having wrong correct_answer letter |
| `bc018cb` | Fix repeated questions across sessions |
| `1cf66b5` | Revamp progress page with daily tracking |
| `8a79e70` | Migrate from SQLite to Supabase PostgreSQL |
| `ca7635d` - `86dd4ef` | Fix Supabase connection issues (auth, pooler, debug output) |
| `b87c64e` | Add 5-minute mini test feature |
| `7adb342` | Add AI agents, gamification, and answer-check nudge |

---

## 9. Known Limitations

1. **No user authentication** — student profiles are open, no password protection
2. **Single-turn AI agents** — no conversational follow-up (e.g., "tell me more about pattern #3")
3. **No offline support** — requires internet for both database and AI calls
4. **Question quality depends on Claude** — occasional formatting issues in generated questions
5. **No collaborative features** — single-student use, no classrooms or teacher dashboards
6. **Vocabulary quiz uses random wrong choices** — not intelligently selected distractors

---

## 10. Future Considerations

- Multi-turn AI tutoring agent for interactive mistake review
- Spaced repetition algorithm for vocabulary review scheduling
- Teacher/tutor dashboard with multi-student views
- Mobile-optimized layout
- Timed writing practice with real-time AI coaching
- Peer comparison (anonymized percentile among app users)
- Export progress reports as PDF
