"""Writing sample practice with AI-powered feedback."""

import random
from datetime import datetime
from typing import List, Optional, Tuple

from database import Database
from models import Student, WritingSample
from question_generator import QuestionGenerator
from timer import Timer
import config
import display


# Hardcoded prompts — no API call needed for prompt selection

ELEMENTARY_PROMPTS: List[Tuple[str, str]] = [
    (
        "picture",
        "Imagine this picture: A child stands at a fork in a path in a magical forest. "
        "One path leads up a steep hill covered in wildflowers. The other path goes through "
        "a dark, mysterious tunnel made of twisted tree branches. A friendly squirrel sits "
        "between the two paths, holding a small golden key.\n\n"
        "Write a story about what happens next."
    ),
    (
        "picture",
        "Imagine this picture: A boy and a girl discover a small wooden boat washed up on "
        "the shore of a lake. Inside the boat, there is a treasure map drawn on old, "
        "wrinkled paper. In the distance, you can see a small island with a tall tree.\n\n"
        "Write a story about what happens next."
    ),
    (
        "picture",
        "Imagine this picture: A girl opens her front door on a snowy morning and finds "
        "a baby penguin standing on the doorstep. The penguin is wearing a tiny red scarf "
        "and is holding an envelope in its beak.\n\n"
        "Write a story about what happens next."
    ),
    (
        "picture",
        "Imagine this picture: A group of friends are playing in a park when they notice "
        "a rainbow that seems to touch down right behind the big oak tree. As they run toward "
        "it, they see something glowing at the base of the tree.\n\n"
        "Write a story about what happens next."
    ),
    (
        "picture",
        "Imagine this picture: A child is sitting in class when they look out the window "
        "and see a hot air balloon landing in the school playground. A person in a colorful "
        "coat steps out and waves at the school.\n\n"
        "Write a story about what happens next."
    ),
    (
        "picture",
        "Imagine this picture: A dog and a cat are sitting together watching a sunset. "
        "Between them is a picnic basket, and behind them is a cozy tent set up for camping. "
        "Fireflies are starting to appear in the evening air.\n\n"
        "Write a story about this scene."
    ),
    (
        "picture",
        "Imagine this picture: A child wakes up to find that their bedroom has transformed "
        "overnight. The floor has become soft green grass, the ceiling looks like a blue sky "
        "with clouds, and there is a small stream running through the middle of the room.\n\n"
        "Write a story about what happens next."
    ),
    (
        "picture",
        "Imagine this picture: A girl is walking home from school when she notices a tiny "
        "door at the base of a large tree. The door is only about six inches tall and has "
        "a tiny doorknob and a welcome mat.\n\n"
        "Write a story about what happens next."
    ),
    (
        "picture",
        "Write about a day when everything went wrong at first but ended up turning "
        "into the best day ever."
    ),
    (
        "picture",
        "Write a story about a kid who discovers they can talk to animals, but only "
        "for one day."
    ),
]


MIDDLE_PROMPTS: List[Tuple[str, str]] = [
    (
        "creative",
        "If you could have dinner with any person from history, who would it be? "
        "Describe the evening: where you would eat, what you would talk about, "
        "and what you would hope to learn from them."
    ),
    (
        "creative",
        "Write a story that begins with this sentence: 'The door had always been "
        "there, but nobody had ever noticed it until Tuesday.'"
    ),
    (
        "personal",
        "Describe a challenge you have faced and how you overcame it. "
        "What did you learn about yourself in the process?"
    ),
    (
        "personal",
        "What is a quality you admire in someone you know? Describe a time when "
        "that person demonstrated this quality and how it affected you."
    ),
    (
        "creative",
        "Imagine you wake up one morning to discover that you are the last person "
        "on Earth. Write about your first day."
    ),
    (
        "personal",
        "Describe a place that is special to you. What makes it special? "
        "Use details to help the reader see, hear, and feel what it is like to be there."
    ),
    (
        "creative",
        "Write a story about a character who receives an unexpected gift that "
        "changes their life in a surprising way."
    ),
    (
        "personal",
        "If you could change one thing about your school, what would it be and why? "
        "How would this change make school better for everyone?"
    ),
    (
        "creative",
        "Write a story that takes place entirely during a thunderstorm. "
        "The storm should play an important role in the story."
    ),
    (
        "personal",
        "Think about a time when you had to make a difficult decision. "
        "What were your choices? What did you decide, and how did it turn out?"
    ),
    (
        "creative",
        "Write a story about two characters who start as rivals but end up "
        "becoming friends."
    ),
    (
        "personal",
        "What is something you are passionate about? Why does it matter to you, "
        "and how has it shaped who you are?"
    ),
]


class WritingPractice:
    def __init__(self, db: Database, generator: QuestionGenerator, student: Student):
        self.db = db
        self.generator = generator
        self.student = student

    def run_writing_practice(self) -> None:
        """Main entry point for standalone writing practice."""
        while True:
            options = [
                "New writing prompt",
                "Choose prompt type",
                "View past submissions",
                "Back to main menu",
            ]
            choice = display.show_menu("Writing Practice", options)

            if choice == 1:
                self._write_new(prompt_type=None)
            elif choice == 2:
                self._choose_and_write()
            elif choice == 3:
                self._view_past()
            elif choice == 4:
                break

    def run_timed_writing(self, session_id: Optional[int] = None) -> None:
        """Run a timed writing section (for full test mode)."""
        level_config = config.LEVEL_CONFIGS.get(self.student.level)
        time_minutes = level_config.writing_time_minutes if level_config else 15

        prompt_type, prompt_text = self._get_random_prompt()

        display.show_writing_prompt(prompt_text, time_minutes)

        if config.TIMER_ENABLED:
            timer = Timer(time_minutes * 60)
            timer.start()
        else:
            timer = None

        response = self._collect_writing_input(timer)

        if timer:
            timer.stop()

        if not response.strip():
            display.show_info("No writing submitted.")
            return

        # Get AI feedback
        display.show_info("Getting feedback on your writing...")
        feedback = self.generator.generate_writing_feedback(
            prompt_text, response, self.student.level, self.student.grade
        )

        display.show_writing_feedback(feedback)

        # Save
        sample = WritingSample(
            student_id=self.student.id,
            session_id=session_id,
            prompt=prompt_text,
            response=response,
            feedback=feedback,
        )
        self.db.save_writing_sample(sample)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_new(self, prompt_type: Optional[str] = None) -> None:
        """Generate a prompt and collect writing."""
        level_config = config.LEVEL_CONFIGS.get(self.student.level)
        time_minutes = level_config.writing_time_minutes if level_config else 15

        if prompt_type:
            ptype, prompt_text = self._get_prompt_by_type(prompt_type)
        else:
            ptype, prompt_text = self._get_random_prompt()

        display.show_writing_prompt(prompt_text, time_minutes)

        use_timer = False
        if config.TIMER_ENABLED:
            use_timer = display.confirm("Start timer?")

        timer = None
        if use_timer:
            timer = Timer(time_minutes * 60)
            timer.start()

        response = self._collect_writing_input(timer)

        if timer:
            timer.stop()

        if not response.strip():
            display.show_info("No writing submitted.")
            return

        # Get feedback
        display.show_info("Getting feedback on your writing...")
        feedback = self.generator.generate_writing_feedback(
            prompt_text, response, self.student.level, self.student.grade
        )

        display.show_writing_feedback(feedback)

        # Save
        sample = WritingSample(
            student_id=self.student.id,
            prompt=prompt_text,
            response=response,
            feedback=feedback,
        )
        self.db.save_writing_sample(sample)
        display.show_success("Writing sample saved!")
        display.press_enter_to_continue()

    def _choose_and_write(self) -> None:
        """Let the student choose a prompt type."""
        if self.student.level == "elementary":
            # All elementary prompts are picture-based
            self._write_new(prompt_type="picture")
        else:
            options = ["Creative prompt", "Personal essay prompt"]
            choice = display.show_menu("Prompt Type", options)
            ptype = "creative" if choice == 1 else "personal"
            self._write_new(prompt_type=ptype)

    def _view_past(self) -> None:
        """View past writing submissions."""
        samples = self.db.get_writing_samples(self.student.id, limit=10)

        if not samples:
            display.show_info("No writing samples yet.")
            display.press_enter_to_continue()
            return

        from rich.table import Table
        table = Table(title="Past Writing Samples", border_style="dim")
        table.add_column("#", justify="right")
        table.add_column("Date", style="dim")
        table.add_column("Prompt (first 60 chars)")

        for i, s in enumerate(samples, 1):
            date = s.created_at[:10] if s.created_at else "?"
            prompt_preview = s.prompt[:60] + "..." if len(s.prompt) > 60 else s.prompt
            table.add_row(str(i), date, prompt_preview)

        display.console.print(table)
        display.console.print()

        idx = display.prompt_int("View which sample? (0 to go back)", 0, len(samples))
        if idx == 0:
            return

        sample = samples[idx - 1]
        display.console.print()
        display.console.print(f"[bold]Prompt:[/bold] {sample.prompt}")
        display.console.print()
        display.console.print("[bold]Your Response:[/bold]")
        display.console.print(sample.response)

        if sample.feedback:
            display.show_writing_feedback(sample.feedback)

        display.press_enter_to_continue()

    def _get_random_prompt(self) -> Tuple[str, str]:
        """Return a random (prompt_type, prompt_text) for the student's level."""
        if self.student.level == "elementary":
            return random.choice(ELEMENTARY_PROMPTS)
        else:
            return random.choice(MIDDLE_PROMPTS)

    def _get_prompt_by_type(self, prompt_type: str) -> Tuple[str, str]:
        """Return a prompt of the specified type."""
        if self.student.level == "elementary":
            prompts = ELEMENTARY_PROMPTS
        else:
            prompts = [p for p in MIDDLE_PROMPTS if p[0] == prompt_type]
            if not prompts:
                prompts = MIDDLE_PROMPTS

        return random.choice(prompts)

    def _collect_writing_input(self, timer: Optional[Timer] = None) -> str:
        """Collect multi-line text input. Double blank line or Ctrl+D to finish."""
        lines = []
        blank_count = 0

        while True:
            # Check timer
            if timer and timer.is_time_up():
                display.show_warning("Time's up!")
                break

            try:
                if timer:
                    remaining = timer.get_formatted_remaining()
                    line = display.console.input(f"  [{remaining}] ")
                else:
                    line = display.console.input("  ")
            except EOFError:
                break

            if line.strip() == "":
                blank_count += 1
                if blank_count >= 2:
                    break
                lines.append("")
            else:
                blank_count = 0
                lines.append(line)

        return "\n".join(lines).strip()
