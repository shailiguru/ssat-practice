import os
from typing import Dict, List, Optional

from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from models import Answer, Question, SectionResult, Student, TestSession, TopicMastery

custom_theme = Theme({
    "correct": "bold green",
    "wrong": "bold red",
    "skip": "dim",
    "strong": "bold green",
    "needs_work": "bold yellow",
    "weak": "bold red",
    "info": "bold cyan",
    "header": "bold magenta",
    "timer_ok": "bold green",
    "timer_warn": "bold yellow",
    "timer_critical": "bold red",
})

console = Console(theme=custom_theme)


# ---------------------------------------------------------------------------
# General UI
# ---------------------------------------------------------------------------

def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def show_banner() -> None:
    banner = Text()
    banner.append("  SSAT Practice Test  ", style="bold white on blue")
    console.print()
    console.print(Align.center(banner))
    console.print(Align.center(Text("Personalized SSAT Prep for Success", style="dim")))
    console.print()


def show_menu(title: str, options: List[str]) -> int:
    """Show a numbered menu and return 1-indexed selection."""
    console.print(Rule(title, style="header"))
    console.print()
    for i, option in enumerate(options, 1):
        console.print(f"  [bold cyan]{i}.[/bold cyan] {option}")
    console.print()

    while True:
        try:
            raw = console.input("[bold]Choose an option: [/bold]").strip()
            choice = int(raw)
            if 1 <= choice <= len(options):
                return choice
            console.print(f"  Please enter a number between 1 and {len(options)}.", style="wrong")
        except (ValueError, EOFError):
            console.print(f"  Please enter a number between 1 and {len(options)}.", style="wrong")


def show_error(message: str) -> None:
    console.print(f"  [wrong]Error:[/wrong] {message}")


def show_success(message: str) -> None:
    console.print(f"  [correct]{message}[/correct]")


def show_info(message: str) -> None:
    console.print(f"  [info]{message}[/info]")


def show_warning(message: str) -> None:
    console.print(f"  [needs_work]Warning:[/needs_work] {message}")


def confirm(prompt: str) -> bool:
    while True:
        raw = console.input(f"  {prompt} [bold](y/n)[/bold]: ").strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        console.print("  Please enter y or n.", style="dim")


def prompt_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    raw = console.input(f"  {prompt}{suffix}: ").strip()
    return raw if raw else default


def prompt_int(prompt: str, min_val: int = 0, max_val: int = 100) -> int:
    while True:
        try:
            raw = console.input(f"  {prompt} ({min_val}-{max_val}): ").strip()
            val = int(raw)
            if min_val <= val <= max_val:
                return val
            console.print(f"  Please enter a number between {min_val} and {max_val}.", style="wrong")
        except (ValueError, EOFError):
            console.print(f"  Please enter a valid number.", style="wrong")


# ---------------------------------------------------------------------------
# Question display
# ---------------------------------------------------------------------------

def show_question(
    question_number: int,
    total: int,
    question: Question,
    time_remaining: Optional[int] = None,
) -> None:
    """Render a question with choices."""
    console.print()

    # Header line
    header_parts = [f"Question {question_number}/{total}"]
    if time_remaining is not None:
        time_str = format_time_remaining(time_remaining)
        header_parts.append(f"Time: {time_str}")
    header = "  |  ".join(header_parts)

    # Show passage for reading comprehension
    if question.passage:
        console.print(Panel(
            question.passage,
            title="[header]Reading Passage[/header]",
            border_style="cyan",
            padding=(1, 2),
        ))
        console.print()

    # Question stem
    console.print(Panel(
        f"[bold]{question.stem}[/bold]",
        title=f"[header]{header}[/header]",
        border_style="blue",
        padding=(0, 2),
    ))

    # Answer choices
    for letter in ["A", "B", "C", "D", "E"]:
        if letter in question.choices:
            console.print(f"    [bold]{letter})[/bold] {question.choices[letter]}")

    console.print()


def show_answer_feedback(
    is_correct: bool,
    selected: Optional[str],
    correct_answer: str,
    explanation: str,
    choices: Dict[str, str],
) -> None:
    """Show feedback after answering a question (used in drill mode)."""
    if selected is None:
        console.print("  [skip]Skipped[/skip]")
    elif is_correct:
        console.print(f"  [correct]Correct! ({correct_answer})[/correct]")
    else:
        console.print(
            f"  [wrong]Incorrect.[/wrong] You chose {selected}. "
            f"Correct answer: [correct]{correct_answer}) {choices.get(correct_answer, '')}[/correct]"
        )

    if explanation:
        console.print(f"  [dim]{explanation}[/dim]")
    console.print()


def get_answer_input() -> Optional[str]:
    """Prompt for A-E or S (skip). Returns uppercase letter or None."""
    while True:
        try:
            raw = console.input("  [bold]Your answer (A-E, or S to skip): [/bold]").strip().upper()
        except EOFError:
            return None
        if raw in ("A", "B", "C", "D", "E"):
            return raw
        if raw in ("S", ""):
            return None
        console.print("  Please enter A, B, C, D, E, or S to skip.", style="dim")


# ---------------------------------------------------------------------------
# Score display
# ---------------------------------------------------------------------------

def show_section_complete(section_name: str) -> None:
    console.print()
    console.print(Panel(
        f"[bold]Section Complete: {section_name}[/bold]",
        border_style="green",
        padding=(0, 2),
    ))
    console.print()


def show_section_result(result: SectionResult, level: str) -> None:
    """Show results for a single section."""
    table = Table(title=f"{result.section_name} Results", border_style="blue")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Raw Score", f"{result.raw_score:.1f}/{result.total_questions}")
    table.add_row("Scaled Score", str(result.scaled_score))
    table.add_row("Est. Percentile", f"{result.percentile}%")
    table.add_row("Correct", str(result.correct_count))
    table.add_row("Incorrect", str(result.wrong_count))
    table.add_row("Skipped", str(result.skipped_count))

    if result.time_used_seconds > 0:
        mins = int(result.time_used_seconds) // 60
        secs = int(result.time_used_seconds) % 60
        table.add_row("Time Used", f"{mins}m {secs}s")

    console.print(table)
    console.print()


def show_full_score_report(
    student: Student,
    session: TestSession,
    section_results: List[SectionResult],
    topic_breakdown: Dict[str, Dict],
) -> None:
    """Display the comprehensive end-of-test score report."""
    from config import LEVEL_CONFIGS
    level_config = LEVEL_CONFIGS.get(session.level)

    console.print()
    console.print(Rule("[bold]SSAT PRACTICE TEST - SCORE REPORT[/bold]", style="header"))
    console.print(Align.center(Text(
        f"{student.name} - Grade {student.grade} - {level_config.display_name if level_config else session.level}",
        style="bold",
    )))
    if session.started_at:
        console.print(Align.center(Text(f"Date: {session.started_at[:10]}", style="dim")))
    console.print()

    # Section scores table
    scores_table = Table(border_style="blue", padding=(0, 1))
    scores_table.add_column("Section", style="bold")
    scores_table.add_column("Raw", justify="right")
    scores_table.add_column("Scaled", justify="right")
    scores_table.add_column("Est. %ile", justify="right")
    if level_config:
        scores_table.add_column("Range", justify="right", style="dim")

    for sr in section_results:
        row = [
            sr.section_name,
            f"{sr.raw_score:.1f}/{sr.total_questions}",
            str(sr.scaled_score),
            f"{sr.percentile}%",
        ]
        if level_config:
            row.append(f"{level_config.score_min}-{level_config.score_max}")
        scores_table.add_row(*row)

    # Total row
    total_scaled = session.total_scaled or sum(sr.scaled_score for sr in section_results)
    total_correct = sum(sr.correct_count for sr in section_results)
    total_wrong = sum(sr.wrong_count for sr in section_results)
    total_skipped = sum(sr.skipped_count for sr in section_results)
    total_questions = sum(sr.total_questions for sr in section_results)

    scores_table.add_section()
    total_row = ["TOTAL", "", str(total_scaled), ""]
    if level_config:
        score_range_min = level_config.score_min * len(section_results)
        score_range_max = level_config.score_max * len(section_results)
        total_row.append(f"{score_range_min}-{score_range_max}")
    scores_table.add_row(*total_row, style="bold")

    console.print(scores_table)
    console.print()

    # Summary
    console.print(f"  Questions Answered: {total_correct + total_wrong}/{total_questions}")
    console.print(
        f"  Correct: [correct]{total_correct}[/correct]  |  "
        f"Incorrect: [wrong]{total_wrong}[/wrong]  |  "
        f"Skipped: [skip]{total_skipped}[/skip]"
    )
    console.print()

    # Topic breakdown
    if topic_breakdown:
        console.print(Rule("Topic Breakdown", style="dim"))
        strong = []
        needs_work = []
        weak = []

        for topic, data in sorted(topic_breakdown.items()):
            accuracy = data.get("accuracy", 0)
            entry = f"{topic} ({accuracy:.0%})"
            if accuracy >= 0.85:
                strong.append(entry)
            elif accuracy >= 0.60:
                needs_work.append(entry)
            else:
                weak.append(entry)

        if strong:
            console.print(f"  [strong]Strong:[/strong] {', '.join(strong)}")
        if needs_work:
            console.print(f"  [needs_work]Needs Work:[/needs_work] {', '.join(needs_work)}")
        if weak:
            console.print(f"  [weak]Weak:[/weak] {', '.join(weak)}")
        console.print()

    console.print(Rule(style="dim"))


def show_drill_summary(
    correct: int, total: int, topic: str, time_seconds: float
) -> None:
    """Summary shown at end of a quick drill."""
    accuracy = correct / total if total > 0 else 0
    mins = int(time_seconds) // 60
    secs = int(time_seconds) % 60

    if accuracy >= 0.85:
        style = "correct"
        msg = "Excellent work!"
    elif accuracy >= 0.60:
        style = "needs_work"
        msg = "Good effort! Keep practicing."
    else:
        style = "wrong"
        msg = "Keep working at it - you'll improve!"

    console.print()
    console.print(Panel(
        f"[bold]Quick Drill Complete: {topic}[/bold]\n\n"
        f"Score: [{style}]{correct}/{total} ({accuracy:.0%})[/{style}]\n"
        f"Time: {mins}m {secs}s\n\n"
        f"[{style}]{msg}[/{style}]",
        border_style="blue",
        padding=(1, 2),
    ))
    console.print()


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------

def show_progress_dashboard(
    student: Student,
    stats: Dict,
    sessions: List[TestSession],
    mastery: List[TopicMastery],
) -> None:
    """Render the full progress dashboard."""
    console.print()
    console.print(Rule(
        f"Progress Report - {student.name} (Grade {student.grade}, "
        f"{student.level.title()} Level)",
        style="header",
    ))
    console.print()

    # Overall stats
    console.print(
        f"  Tests Taken: {stats['full_tests']} full tests, "
        f"{stats['section_practices']} section practices, "
        f"{stats['drills']} drills"
    )
    console.print(f"  Total Questions Answered: {stats['total_answers']:,}")
    console.print()

    # Score trend for full tests
    full_tests = [s for s in sessions if s.mode == "full_test" and s.total_scaled]
    if full_tests:
        console.print(Rule("Score Trend (Full Tests)", style="dim"))
        show_score_trend(full_tests[:10])
        console.print()

    # Topic mastery
    if mastery:
        console.print(Rule("Topic Mastery", style="dim"))
        show_topic_breakdown(mastery)
        console.print()

    console.print(Rule(style="dim"))


def show_score_trend(sessions: List[TestSession]) -> None:
    """ASCII bar chart of recent test scores."""
    if not sessions:
        console.print("  No test data yet.")
        return

    # Determine scale
    scores = [s.total_scaled for s in sessions if s.total_scaled]
    if not scores:
        console.print("  No scored tests yet.")
        return

    max_score = max(scores)
    bar_width = 40

    table = Table(show_header=True, border_style="dim", padding=(0, 1))
    table.add_column("Date", style="dim", width=12)
    table.add_column("Score", justify="right", width=6)
    table.add_column("", width=bar_width + 2)

    for s in reversed(sessions):
        if not s.total_scaled:
            continue
        date_str = s.started_at[:10] if s.started_at else "?"
        score = s.total_scaled
        bar_len = int((score / max_score) * bar_width) if max_score > 0 else 0

        # Color based on relative performance
        from config import LEVEL_CONFIGS
        lc = LEVEL_CONFIGS.get(s.level)
        if lc:
            total_max = lc.score_max * len(lc.sections)
            total_min = lc.score_min * len(lc.sections)
            pct = (score - total_min) / (total_max - total_min) if total_max > total_min else 0
        else:
            pct = 0.5

        if pct >= 0.7:
            color = "green"
        elif pct >= 0.4:
            color = "yellow"
        else:
            color = "red"

        bar = Text("█" * bar_len, style=color)
        table.add_row(date_str, str(score), bar)

    console.print(table)


def show_topic_breakdown(mastery: List[TopicMastery]) -> None:
    """Table of topic mastery with color-coded accuracy."""
    from config import QUESTION_TYPE_DISPLAY

    table = Table(show_header=True, border_style="dim", padding=(0, 1))
    table.add_column("Topic", style="bold")
    table.add_column("Accuracy", justify="right")
    table.add_column("Attempted", justify="right")
    table.add_column("Difficulty", justify="right")
    table.add_column("Status")

    for m in mastery:
        if m.total_attempted == 0:
            continue
        accuracy = m.total_correct / m.total_attempted
        display_name = QUESTION_TYPE_DISPLAY.get(m.topic_tag, m.topic_tag.title())

        if accuracy >= 0.85:
            style = "strong"
            status = "Strong"
        elif accuracy >= 0.60:
            style = "needs_work"
            status = "Needs Work"
        else:
            style = "weak"
            status = "Weak"

        table.add_row(
            display_name,
            f"[{style}]{accuracy:.0%}[/{style}]",
            str(m.total_attempted),
            f"{m.difficulty_level:.1f}",
            f"[{style}]{status}[/{style}]",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Timer display
# ---------------------------------------------------------------------------

def format_time_remaining(seconds: int) -> str:
    """Return formatted time string with color based on remaining time."""
    mins = seconds // 60
    secs = seconds % 60
    time_str = f"{mins:02d}:{secs:02d}"

    if seconds <= 60:
        return f"[timer_critical]{time_str}[/timer_critical]"
    elif seconds <= 300:
        return f"[timer_warn]{time_str}[/timer_warn]"
    else:
        return f"[timer_ok]{time_str}[/timer_ok]"


# ---------------------------------------------------------------------------
# Writing display
# ---------------------------------------------------------------------------

def show_writing_prompt(prompt_text: str, time_minutes: int) -> None:
    console.print()
    console.print(Panel(
        prompt_text,
        title="[header]Writing Prompt[/header]",
        subtitle=f"Time: {time_minutes} minutes",
        border_style="magenta",
        padding=(1, 2),
    ))
    console.print()
    console.print("  [dim]Type your response below. Press Enter twice on a blank line when done.[/dim]")
    console.print()


def show_writing_feedback(feedback: str) -> None:
    console.print()
    console.print(Panel(
        feedback,
        title="[header]Writing Feedback[/header]",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


# ---------------------------------------------------------------------------
# Review display
# ---------------------------------------------------------------------------

def show_review_question(
    question_number: int,
    total: int,
    question: Question,
    student_answer: Optional[str],
) -> None:
    """Show a missed question during review with what the student answered."""
    show_question(question_number, total, question)

    if student_answer:
        console.print(
            f"  [wrong]Your answer: {student_answer}) "
            f"{question.choices.get(student_answer, '')}[/wrong]"
        )
    else:
        console.print("  [skip]You skipped this question.[/skip]")

    console.print(
        f"  [correct]Correct answer: {question.correct_answer}) "
        f"{question.choices.get(question.correct_answer, '')}[/correct]"
    )

    if question.explanation:
        console.print(f"\n  [dim]Explanation: {question.explanation}[/dim]")

    console.print()


# ---------------------------------------------------------------------------
# Level-up display
# ---------------------------------------------------------------------------

def show_level_up(student_name: str, old_level: str, new_level: str) -> None:
    console.print()
    console.print(Panel(
        f"[bold]LEVEL UP![/bold]\n\n"
        f"{student_name} has demonstrated mastery at the {old_level}!\n"
        f"Moving to {new_level}.\n"
        f"Questions will now be more challenging.\n\n"
        f"Keep up the great work!",
        border_style="green",
        padding=(1, 2),
        title="Congratulations!",
    ))
    console.print()


def show_level_down_offer(student_name: str, current_level: str, previous_level: str) -> bool:
    console.print()
    console.print(Panel(
        f"It looks like the {current_level} might be a stretch right now.\n"
        f"Would you like to go back to {previous_level} for more practice?",
        border_style="yellow",
        padding=(1, 2),
    ))
    return confirm("Go back to the previous level?")


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def show_section_intro(section_name: str, question_count: int, time_minutes: int) -> None:
    console.print()
    console.print(Panel(
        f"[bold]{section_name}[/bold]\n\n"
        f"Questions: {question_count}\n"
        f"Time: {time_minutes} minutes\n\n"
        f"[dim]Answer A-E for each question, or S to skip.[/dim]",
        border_style="blue",
        padding=(1, 2),
    ))
    console.print()


def press_enter_to_continue() -> None:
    try:
        console.input("  [dim]Press Enter to continue...[/dim]")
    except EOFError:
        pass


def show_pool_stats(stats: Dict[str, int]) -> None:
    """Show question pool statistics."""
    table = Table(title="Question Pool", border_style="dim")
    table.add_column("Type", style="bold")
    table.add_column("Available", justify="right")

    for qtype, count in sorted(stats.items()):
        from config import QUESTION_TYPE_DISPLAY
        display_name = QUESTION_TYPE_DISPLAY.get(qtype, qtype.title())
        style = "correct" if count >= 10 else ("needs_work" if count >= 5 else "wrong")
        table.add_row(display_name, f"[{style}]{count}[/{style}]")

    console.print(table)
