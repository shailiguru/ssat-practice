#!/usr/bin/env python3
"""SSAT Practice Test — Main entry point and menu system."""

import sys
from datetime import datetime
from typing import Optional

import config
from database import Database
from models import Student
import display


def check_api_key() -> bool:
    """Verify the Anthropic API key is configured."""
    if not config.ANTHROPIC_API_KEY:
        display.show_error(
            "ANTHROPIC_API_KEY is not set.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Add your Anthropic API key\n"
            "  3. Run the app again\n"
        )
        return False
    return True


def select_or_create_profile(db: Database) -> Optional[Student]:
    """List existing profiles or create a new one."""
    students = db.list_students()

    if not students:
        display.show_info("No profiles found. Let's create one!")
        return create_new_profile(db)

    options = [f"{s.name} (Grade {s.grade}, {s.level.title()} Level)" for s in students]
    options.append("Create new profile")

    choice = display.show_menu("Select Profile", options)

    if choice == len(options):
        return create_new_profile(db)
    return students[choice - 1]


def create_new_profile(db: Database) -> Student:
    """Prompt for name, grade, level and save to DB."""
    display.console.print()
    name = display.prompt_text("Student's name")
    if not name:
        display.show_error("Name cannot be empty.")
        return create_new_profile(db)

    grade = display.prompt_int("Current grade", 3, 8)

    if grade <= 4:
        level = "elementary"
        display.show_info(f"Grade {grade} → Elementary Level SSAT")
    elif grade <= 7:
        level = "middle"
        display.show_info(f"Grade {grade} → Middle Level SSAT")
    else:
        level = "middle"
        display.show_info(f"Grade {grade} → Upper Level SSAT (using Middle Level format)")

    student = db.create_student(name, grade, level)
    display.show_success(f"Profile created for {name}!")
    return student


def settings_menu(db: Database, student: Student) -> Student:
    """Settings submenu."""
    while True:
        options = [
            f"Timer: {'ON' if config.TIMER_ENABLED else 'OFF'}",
            f"Adjust grade level (currently {student.grade})",
            f"Adjust test level (currently {student.level.title()})",
            "Pre-generate question pool",
            "View question pool stats",
            "Reset progress (caution!)",
            "Back to main menu",
        ]

        choice = display.show_menu("Settings", options)

        if choice == 1:
            config.TIMER_ENABLED = not config.TIMER_ENABLED
            state = "ON" if config.TIMER_ENABLED else "OFF"
            display.show_success(f"Timer is now {state}")

        elif choice == 2:
            new_grade = display.prompt_int("New grade level", 3, 8)
            student.grade = new_grade
            if new_grade <= 4:
                student.level = "elementary"
            elif new_grade <= 7:
                student.level = "middle"
            db.update_student(student)
            display.show_success(f"Grade updated to {new_grade} ({student.level.title()} Level)")

        elif choice == 3:
            level_choice = display.show_menu("Select Level", [
                "Elementary Level (Grades 3-4)",
                "Middle Level (Grades 5-7)",
            ])
            student.level = "elementary" if level_choice == 1 else "middle"
            db.update_student(student)
            display.show_success(f"Level updated to {student.level.title()}")

        elif choice == 4:
            try:
                from question_generator import QuestionGenerator
                from question_cache import QuestionCache
                generator = QuestionGenerator()
                cache = QuestionCache(db, generator)
                cache.generate_batch_interactive(student)
            except Exception as e:
                display.show_error(f"Failed to generate questions: {e}")

        elif choice == 5:
            try:
                from question_cache import QuestionCache
                from question_generator import QuestionGenerator
                generator = QuestionGenerator()
                cache = QuestionCache(db, generator)
                stats = cache.get_pool_stats(student.id, student.level)
                display.show_pool_stats(stats)
            except Exception as e:
                display.show_error(f"Failed to get pool stats: {e}")
            display.press_enter_to_continue()

        elif choice == 6:
            if display.confirm("This will delete ALL progress for this student. Are you sure?"):
                if display.confirm("This CANNOT be undone. Really delete?"):
                    _reset_student_progress(db, student)
                    display.show_success("Progress has been reset.")

        elif choice == 7:
            break

    return student


def _reset_student_progress(db: Database, student: Student) -> None:
    """Delete all answers, sessions, mastery, and writing samples for a student."""
    db.conn.execute("DELETE FROM answers WHERE student_id = ?", (student.id,))
    db.conn.execute("DELETE FROM test_sessions WHERE student_id = ?", (student.id,))
    db.conn.execute("DELETE FROM topic_mastery WHERE student_id = ?", (student.id,))
    db.conn.execute("DELETE FROM writing_samples WHERE student_id = ?", (student.id,))
    db.conn.commit()


def main_menu_loop(db: Database, student: Student) -> None:
    """Main menu loop."""
    while True:
        display.clear_screen()
        display.show_banner()
        display.show_info(f"Student: {student.name} | Grade {student.grade} | {student.level.title()} Level")
        display.console.print()

        options = [
            "Start Practice Test (Full)",
            "Section Practice",
            "Quick Drill (10-20 questions)",
            "Review Missed Questions",
            "Writing Practice",
            "View Progress & Scores",
            "Switch Profile",
            "Settings",
            "Exit",
        ]

        choice = display.show_menu("Main Menu", options)

        try:
            if choice == 1:
                from test_runner import TestRunner
                from question_cache import QuestionCache
                from question_generator import QuestionGenerator
                generator = QuestionGenerator()
                cache = QuestionCache(db, generator)
                runner = TestRunner(db, cache, student)
                runner.run_full_test()

            elif choice == 2:
                from test_runner import TestRunner
                from question_cache import QuestionCache
                from question_generator import QuestionGenerator
                generator = QuestionGenerator()
                cache = QuestionCache(db, generator)
                runner = TestRunner(db, cache, student)
                runner.run_section_practice()

            elif choice == 3:
                from test_runner import TestRunner
                from question_cache import QuestionCache
                from question_generator import QuestionGenerator
                generator = QuestionGenerator()
                cache = QuestionCache(db, generator)
                runner = TestRunner(db, cache, student)
                runner.run_quick_drill()

            elif choice == 4:
                from review import ReviewManager
                from question_cache import QuestionCache
                from question_generator import QuestionGenerator
                generator = QuestionGenerator()
                cache = QuestionCache(db, generator)
                reviewer = ReviewManager(db, cache, student)
                reviewer.run_review()

            elif choice == 5:
                from writing import WritingPractice
                from question_generator import QuestionGenerator
                generator = QuestionGenerator()
                wp = WritingPractice(db, generator, student)
                wp.run_writing_practice()

            elif choice == 6:
                from progress import ProgressTracker
                tracker = ProgressTracker(db, student)
                tracker.show_dashboard()
                display.press_enter_to_continue()

            elif choice == 7:
                new_student = select_or_create_profile(db)
                if new_student:
                    student = new_student

            elif choice == 8:
                student = settings_menu(db, student)

            elif choice == 9:
                display.show_info("Goodbye! Keep up the great work!")
                break

        except KeyboardInterrupt:
            display.console.print("\n")
            display.show_info("Returning to main menu...")
            continue
        except Exception as e:
            display.show_error(f"An error occurred: {e}")
            display.press_enter_to_continue()


def main() -> None:
    """Entry point."""
    display.clear_screen()
    display.show_banner()

    # Check API key
    has_key = check_api_key()
    if not has_key:
        display.show_warning("Running without API key. You can only use cached questions.")
        display.press_enter_to_continue()

    # Initialize database
    db_url = config.SUPABASE_DB_URL
    if not db_url:
        display.show_error("SUPABASE_DB_URL not configured. Set it in .env or environment.")
        sys.exit(1)
    db = Database(db_url)
    db.initialize()

    try:
        # Select or create profile
        student = select_or_create_profile(db)
        if not student:
            display.show_error("No profile selected. Exiting.")
            sys.exit(1)

        # Run main menu
        main_menu_loop(db, student)

    except KeyboardInterrupt:
        display.console.print("\n")
        display.show_info("Goodbye!")
    finally:
        db.close()


if __name__ == "__main__":
    main()
