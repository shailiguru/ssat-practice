"""AI agent functions: mistake analysis, parent reports, vocabulary builder,
and the Study Coach multi-turn agent."""

import dataclasses
import json
from typing import Dict, List, Optional, Tuple

import anthropic

import config
from models import Answer, Question, Student, TopicMastery


def _call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> str:
    """Make a single Claude API call."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def analyze_mistake_patterns(
    wrong_answers: List[Tuple[Answer, Question]],
    student: Student,
) -> str:
    """Analyze patterns in wrong answers and return insights as markdown."""
    if not wrong_answers:
        return "No mistakes to analyze yet! Keep practicing."

    # Build context from wrong answers
    mistakes_text = []
    for i, (answer, question) in enumerate(wrong_answers[:30], 1):  # cap at 30
        chosen = answer.selected_answer or "skipped"
        correct = question.correct_answer
        chosen_text = question.choices.get(chosen, "N/A") if chosen != "skipped" else "skipped"
        correct_text = question.choices.get(correct, "")

        mistakes_text.append(
            f"{i}. [{question.question_type}] {question.stem}\n"
            f"   Student chose: {chosen}) {chosen_text}\n"
            f"   Correct: {correct}) {correct_text}"
        )

    system_prompt = (
        f"You are an expert SSAT tutor analyzing a grade {student.grade} student's mistakes. "
        f"Look at their wrong answers and identify 3-5 SPECIFIC patterns or misconceptions. "
        f"Don't just say 'needs more practice on synonyms' — explain the actual pattern. "
        f"For example: 'Picks words that sound similar rather than mean the same thing' or "
        f"'Struggles with fractions when they appear in word problems but handles standalone fractions well.'\n\n"
        f"Format your response as markdown with:\n"
        f"- A brief summary line\n"
        f"- Numbered list of 3-5 specific patterns with examples from their mistakes\n"
        f"- 2-3 actionable tips based on the patterns\n"
        f"Keep it encouraging and age-appropriate for a {student.grade}th grader."
    )

    user_prompt = (
        f"Here are {len(mistakes_text)} recent wrong answers from {student.name} "
        f"(grade {student.grade}, {student.level} level):\n\n"
        + "\n".join(mistakes_text)
    )

    return _call_claude(system_prompt, user_prompt)


def generate_parent_report(
    student: Student,
    stats: Dict,
    mastery: List[TopicMastery],
    streak_data: Dict,
    recent_session_count: int,
) -> str:
    """Generate a parent-friendly progress report."""
    # Build mastery summary
    mastery_lines = []
    for m in mastery:
        if m.total_attempted < 3:
            continue
        acc = m.total_correct / m.total_attempted if m.total_attempted > 0 else 0
        display = config.QUESTION_TYPE_DISPLAY.get(m.topic_tag, m.topic_tag.title())
        mastery_lines.append(f"- {display}: {acc:.0%} accuracy ({m.total_attempted} questions)")

    system_prompt = (
        f"You are writing a brief, warm progress report for the parent of a grade {student.grade} student "
        f"preparing for the SSAT ({student.level} level). Write 200-300 words that a parent would "
        f"find helpful and encouraging.\n\n"
        f"Include:\n"
        f"- How much they've been practicing (be specific with numbers)\n"
        f"- Their strongest areas\n"
        f"- Areas that need attention (frame positively)\n"
        f"- A specific suggestion for next week\n"
        f"- Encouraging sign-off\n\n"
        f"Don't use jargon. Don't give SSAT scores unless provided. Keep it warm and actionable."
    )

    user_prompt = (
        f"Student: {student.name}, Grade {student.grade}, {student.level.title()} Level\n\n"
        f"Practice Stats:\n"
        f"- Total questions answered: {stats.get('total_answers', 0)}\n"
        f"- Full tests completed: {stats.get('full_tests', 0)}\n"
        f"- Practice sessions: {recent_session_count}\n"
        f"- Current streak: {streak_data.get('current_streak', 0)} days\n"
        f"- Longest streak: {streak_data.get('longest_streak', 0)} days\n\n"
        f"Topic Performance:\n"
        + ("\n".join(mastery_lines) if mastery_lines else "- No data yet\n")
    )

    return _call_claude(system_prompt, user_prompt)


def build_vocabulary_list(
    wrong_verbal: List[Tuple[Answer, Question]],
    grade: int,
) -> List[Dict]:
    """Extract vocabulary from missed verbal questions and generate study cards."""
    if not wrong_verbal:
        return []

    # Extract words from stems
    words = set()
    for answer, question in wrong_verbal[:20]:
        stem = question.stem.upper()
        # Synonym stems are like "WORD most nearly means"
        if question.question_type == "synonym":
            parts = stem.split()
            if parts:
                words.add(parts[0].strip(".,!?"))
        # Analogy stems contain word pairs
        elif question.question_type == "analogy":
            for part in stem.replace("IS TO", "|").replace("AS", "|").split("|"):
                word = part.strip().split()[0] if part.strip() else ""
                if word and len(word) > 2:
                    words.add(word)

    if not words:
        return []

    system_prompt = (
        f"You are a vocabulary tutor for a grade {grade} student. "
        f"For each word, provide:\n"
        f"1. A simple, kid-friendly definition (1 sentence)\n"
        f"2. An example sentence a {grade}th grader would relate to\n"
        f"3. A memory tip (mnemonic, word root, or association)\n\n"
        f"Return ONLY valid JSON array. Each item: "
        f'{{"word": "...", "definition": "...", "example": "...", "tip": "..."}}\n'
        f"No other text, just the JSON array."
    )

    user_prompt = f"Words to define: {', '.join(sorted(words)[:15])}"

    try:
        response = _call_claude(system_prompt, user_prompt, max_tokens=4096)
        # Parse JSON from response
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(response[start:end])
    except Exception:
        pass

    return []


# ---------------------------------------------------------------------------
# Study Coach Agent — multi-turn agentic loop with tool use
# ---------------------------------------------------------------------------

STUDY_COACH_TOOLS = [
    {
        "name": "get_student_stats",
        "description": (
            "Get high-level practice statistics: number of full tests completed, "
            "section practices, drills, and total questions answered. "
            "Use this first to understand how much the student has practiced overall."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "integer",
                    "description": "The student's database ID",
                }
            },
            "required": ["student_id"],
        },
    },
    {
        "name": "get_topic_mastery",
        "description": (
            "Get per-topic accuracy breakdown: topic name, difficulty level, "
            "total attempted, total correct, and last-50-question accuracy. "
            "Topics include: synonym, analogy, arithmetic, algebra, geometry, "
            "word_problem, reading_comprehension. "
            "Use this to identify strong and weak areas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "integer",
                    "description": "The student's database ID",
                }
            },
            "required": ["student_id"],
        },
    },
    {
        "name": "get_streak_data",
        "description": (
            "Get study consistency data: current streak (consecutive days), "
            "longest streak, and total days practiced. "
            "Use this to assess study habits and consistency."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "integer",
                    "description": "The student's database ID",
                }
            },
            "required": ["student_id"],
        },
    },
    {
        "name": "get_daily_activity",
        "description": (
            "Get day-by-day practice activity for the last N days: questions "
            "answered, correct, wrong, skipped, and time spent per day. "
            "Use this to spot recent trends in practice volume and accuracy."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "integer",
                    "description": "The student's database ID",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back (default 30)",
                },
            },
            "required": ["student_id"],
        },
    },
    {
        "name": "get_daily_activity_by_topic",
        "description": (
            "Get day-by-day activity broken down by topic. Shows which topics "
            "the student has been practicing each day. Use this to detect if "
            "the student has been avoiding certain topics or over-focusing on others."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "integer",
                    "description": "The student's database ID",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back (default 30)",
                },
            },
            "required": ["student_id"],
        },
    },
    {
        "name": "get_recent_sessions",
        "description": (
            "Get the student's most recent practice sessions with mode "
            "(full_test, section_practice, quick_drill), dates, and scores. "
            "Use this to understand what types of practice they've been doing "
            "recently and their score trajectory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "integer",
                    "description": "The student's database ID",
                },
                "mode": {
                    "type": "string",
                    "description": (
                        "Filter by session mode: 'full_test', "
                        "'section_practice', 'quick_drill', or omit for all"
                    ),
                    "enum": ["full_test", "section_practice", "quick_drill"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum sessions to return (default 20)",
                },
            },
            "required": ["student_id"],
        },
    },
    {
        "name": "get_wrong_answers",
        "description": (
            "Get the student's most recent wrong answers with the full "
            "question text, their selected answer, the correct answer, and "
            "the question type/topic. Use this to identify specific "
            "misconceptions and error patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "integer",
                    "description": "The student's database ID",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum wrong answers to return (default 20)",
                },
            },
            "required": ["student_id"],
        },
    },
    {
        "name": "get_frequently_missed",
        "description": (
            "Get questions the student has gotten wrong multiple times. "
            "These represent persistent knowledge gaps. Returns the question "
            "details and how many times it was missed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "integer",
                    "description": "The student's database ID",
                },
                "min_wrong_count": {
                    "type": "integer",
                    "description": (
                        "Minimum times a question must be wrong to include "
                        "(default 2)"
                    ),
                },
            },
            "required": ["student_id"],
        },
    },
]


def _study_coach_system_prompt(student: Student) -> str:
    """Build the system prompt for the Study Coach agent."""
    level_config = config.LEVEL_CONFIGS.get(student.level)
    sections_desc = (
        ", ".join(s.name for s in level_config.sections)
        if level_config
        else "all sections"
    )

    return (
        f"You are Coach, a friendly and encouraging SSAT study coach for "
        f"{student.name}, a grade {student.grade} student preparing for the "
        f"SSAT {student.level.title()} Level exam.\n\n"
        f"SSAT {student.level.title()} Level has these sections: {sections_desc}.\n"
        f"Topics tested: Synonyms, Analogies, Arithmetic, "
        f"{'Algebra, ' if student.level == 'middle' else ''}"
        f"Geometry, Word Problems, Reading Comprehension.\n\n"
        f"YOUR TASK:\n"
        f"Use the available tools to examine {student.name}'s practice data, "
        f"then produce a personalized study recommendation for today. "
        f"You must call tools to gather real data — do not make assumptions.\n\n"
        f"INVESTIGATION STRATEGY:\n"
        f"1. Start with get_student_stats to understand overall practice volume\n"
        f"2. Use get_topic_mastery to find strengths and weaknesses\n"
        f"3. Check get_streak_data and get_recent_sessions for study patterns\n"
        f"4. If you find weak topics, use get_wrong_answers to understand "
        f"specific mistakes\n"
        f"5. Use get_daily_activity_by_topic to check if they're avoiding "
        f"weak areas\n\n"
        f"RECOMMENDATION FORMAT (use markdown):\n"
        f"- Start with a brief, encouraging greeting (1-2 sentences "
        f"acknowledging their effort)\n"
        f'- **Today\'s Focus**: ONE specific topic or activity to '
        f"focus on, with why\n"
        f'- **Your Plan**: 2-3 concrete action items (e.g., "Do a '
        f'10-question geometry drill", not "practice more math")\n'
        f'- **Quick Win**: One easy confidence-boosting suggestion\n'
        f'- **Streak Status**: Current streak with a motivational note\n\n'
        f"CONSTRAINTS:\n"
        f'- Be specific: say "Geometry (52% accuracy)" not "math needs work"\n'
        f"- Be encouraging: always lead with something positive\n"
        f"- Be concrete: recommend specific practice modes (quick drill, "
        f"mini test, section practice, full test)\n"
        f"- Be age-appropriate: this is a grade {student.grade} student\n"
        f"- Keep the entire recommendation under 300 words\n"
        f"- If the student has very little data (< 10 questions), recommend "
        f"starting with a 5-minute mini test to get a baseline\n"
        f"- If the student has been inactive (0-day streak), gently encourage "
        f"them to get back on track\n"
        f"- NEVER mention tool names, API calls, or technical details in "
        f"your recommendation\n"
        f"- Do NOT call more tools than necessary — 3-5 tool calls should "
        f"be sufficient"
    )


def _execute_tool(db, tool_name: str, tool_input: dict) -> str:
    """Execute a Study Coach tool call and return JSON string result."""
    student_id = tool_input["student_id"]

    try:
        if tool_name == "get_student_stats":
            result = db.get_student_stats(student_id)

        elif tool_name == "get_topic_mastery":
            mastery_list = db.get_topic_mastery(student_id)
            result = []
            for m in mastery_list:
                d = dataclasses.asdict(m)
                d["accuracy"] = (
                    round(m.total_correct / m.total_attempted, 3)
                    if m.total_attempted > 0
                    else 0
                )
                d["last_50_accuracy"] = (
                    round(m.last_50_correct / m.last_50_attempted, 3)
                    if m.last_50_attempted > 0
                    else 0
                )
                result.append(d)

        elif tool_name == "get_streak_data":
            result = db.get_streak_data(student_id)

        elif tool_name == "get_daily_activity":
            days = tool_input.get("days", 30)
            result = db.get_daily_activity(student_id, days=days)

        elif tool_name == "get_daily_activity_by_topic":
            days = tool_input.get("days", 30)
            result = db.get_daily_activity_by_topic(student_id, days=days)

        elif tool_name == "get_recent_sessions":
            mode = tool_input.get("mode")
            limit = tool_input.get("limit", 20)
            sessions = db.get_sessions_for_student(
                student_id, mode=mode, limit=limit
            )
            result = [dataclasses.asdict(s) for s in sessions]

        elif tool_name == "get_wrong_answers":
            limit = tool_input.get("limit", 20)
            wrong = db.get_wrong_answers_for_student(student_id, limit=limit)
            result = []
            for answer, question in wrong:
                result.append(
                    {
                        "question_type": question.question_type,
                        "topic": question.topic,
                        "difficulty": question.difficulty,
                        "stem": question.stem[:200],
                        "student_answer": answer.selected_answer or "skipped",
                        "correct_answer": question.correct_answer,
                        "student_answer_text": (
                            question.choices.get(answer.selected_answer, "N/A")
                            if answer.selected_answer
                            else "skipped"
                        ),
                        "correct_answer_text": question.choices.get(
                            question.correct_answer, ""
                        ),
                    }
                )

        elif tool_name == "get_frequently_missed":
            min_wrong = tool_input.get("min_wrong_count", 2)
            missed = db.get_frequently_missed_questions(
                student_id, min_wrong_count=min_wrong
            )
            result = []
            for question, count in missed:
                result.append(
                    {
                        "question_type": question.question_type,
                        "topic": question.topic,
                        "difficulty": question.difficulty,
                        "stem": question.stem[:200],
                        "correct_answer": question.correct_answer,
                        "times_wrong": count,
                    }
                )

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {str(e)}"})


def run_study_coach(db, student: Student) -> str:
    """Run the Study Coach agent. Returns markdown study recommendation.

    This is a multi-turn agentic loop:
    1. Send initial goal message with student context
    2. Claude decides which tools to call
    3. Execute tool calls, feed results back
    4. Repeat until Claude produces a final text response
    """
    MAX_TURNS = 10

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    system_prompt = _study_coach_system_prompt(student)

    messages = [
        {
            "role": "user",
            "content": (
                f"Please analyze {student.name}'s SSAT practice data and create "
                f"a personalized study recommendation for today. "
                f"Their student_id is {student.id}. "
                f"Start by checking their overall stats, then dig deeper "
                f"into areas that need attention."
            ),
        }
    ]

    for turn in range(MAX_TURNS):
        response = client.messages.create(
            model=config.MODEL,
            max_tokens=1500,
            system=system_prompt,
            tools=STUDY_COACH_TOOLS,
            messages=messages,
        )

        # Final text response — no more tool calls
        if response.stop_reason == "end_turn":
            text_parts = [
                block.text
                for block in response.content
                if block.type == "text"
            ]
            if text_parts:
                return "\n".join(text_parts)
            return "I couldn't generate a recommendation. Please try again."

        # Claude wants to call tools
        if response.stop_reason == "tool_use":
            # Add Claude's response (with tool_use blocks) to messages
            messages.append(
                {"role": "assistant", "content": response.content}
            )

            # Execute each tool call and build tool_result blocks
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_str = _execute_tool(db, block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_str,
                        }
                    )

            # Feed tool results back as user message
            messages.append({"role": "user", "content": tool_results})

        else:
            # Unexpected stop_reason — extract whatever text we have
            text_parts = [
                b.text for b in response.content if b.type == "text"
            ]
            if text_parts:
                return "\n".join(text_parts)
            return "Study coach encountered an unexpected state."

    # Hit max turns — should never happen in practice
    return (
        "I gathered a lot of data but ran out of processing steps. "
        "Please try again."
    )
