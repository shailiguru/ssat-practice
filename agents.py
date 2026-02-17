"""AI agent functions: mistake analysis, parent reports, vocabulary builder."""

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
