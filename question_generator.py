"""Claude API integration for SSAT question generation and writing feedback."""

import json
import time
import uuid
from typing import Dict, List, Optional

import anthropic

import config
from models import Question


class QuestionGenerationError(Exception):
    """Raised when question generation fails after retries."""


class QuestionGenerator:
    def __init__(self):
        api_key = config.ANTHROPIC_API_KEY
        # On Streamlit Cloud, the key may not be available at config import time.
        # Read it directly from st.secrets as a fallback.
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
            except Exception:
                pass
        self.client = anthropic.Anthropic(api_key=api_key)
        self._last_request_time: float = 0

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < config.RATE_LIMIT_SECONDS:
            time.sleep(config.RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_questions(
        self,
        question_type: str,
        level: str,
        grade: int,
        difficulty: int = 3,
        count: int = 10,
        topics: Optional[List[str]] = None,
    ) -> List[Question]:
        """Generate a batch of SSAT questions via Claude API.

        Returns a list of Question objects (without DB IDs).
        Raises QuestionGenerationError if all retries fail.
        """
        batch_id = str(uuid.uuid4())[:8]
        system_prompt = self._build_system_prompt(question_type, level, grade, difficulty)
        user_prompt = self._build_user_prompt(question_type, count, difficulty, grade, topics)

        response_text = self._call_api(system_prompt, user_prompt)
        return self._parse_response(
            response_text, question_type, level, grade, difficulty, batch_id
        )

    def generate_reading_comprehension(
        self,
        level: str,
        grade: int,
        difficulty: int = 3,
        num_passages: int = 2,
        questions_per_passage: int = 4,
    ) -> List[Question]:
        """Generate reading comprehension passages with questions."""
        batch_id = str(uuid.uuid4())[:8]
        word_count = 150 if level == "elementary" else 300

        system_prompt = self._build_rc_system_prompt(level, grade, difficulty)
        user_prompt = (
            f"Generate {num_passages} reading comprehension passages.\n"
            f"Each passage should be approximately {word_count} words.\n"
            f"For each passage, generate {questions_per_passage} multiple-choice questions.\n"
            f"Mix passage topics: fiction, nonfiction, science, social studies.\n\n"
            f"Return as JSON with this exact structure:\n"
            f'{{"passages": [{{"passage_text": "...", "questions": [{{"stem": "...", '
            f'"choices": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}, '
            f'"correct_answer": "B", "explanation": "...", '
            f'"topic": "main_idea|inference|detail|vocabulary_in_context|tone"}}]}}]}}'
        )

        response_text = self._call_api(system_prompt, user_prompt)
        return self._parse_rc_response(
            response_text, level, grade, difficulty, batch_id
        )

    def generate_writing_feedback(
        self,
        prompt_text: str,
        student_response: str,
        level: str,
        grade: int,
    ) -> str:
        """Generate encouraging feedback on a writing sample."""
        system_prompt = (
            f"You are a warm, encouraging writing tutor for a student in grade {grade}. "
            f"Provide constructive feedback on their writing for a {level}-level SSAT writing sample.\n\n"
            f"Guidelines:\n"
            f"- Start with specific praise (what they did well)\n"
            f"- Note 2-3 areas for improvement\n"
            f"- Use age-appropriate language\n"
            f"- Be encouraging and supportive throughout\n"
            f"- Comment on: organization, use of details, creativity, grammar\n"
            f"- Keep feedback to 150-200 words\n"
            f"- Do NOT give a grade or score"
        )
        user_prompt = (
            f"Writing Prompt: {prompt_text}\n\n"
            f"Student's Response:\n{student_response}\n\n"
            f"Please provide encouraging, constructive feedback."
        )

        try:
            return self._call_api(system_prompt, user_prompt, max_tokens=1024)
        except QuestionGenerationError:
            return (
                "Great effort! Your writing has been saved. "
                "AI feedback is temporarily unavailable — check back later!"
            )

    # ------------------------------------------------------------------
    # System prompts
    # ------------------------------------------------------------------

    def _build_system_prompt(
        self, question_type: str, level: str, grade: int, difficulty: int
    ) -> str:
        level_display = "Elementary" if level == "elementary" else "Middle"

        base = (
            f"You are an expert SSAT test question writer. Generate {level_display} Level "
            f"SSAT questions appropriate for a student currently in grade {grade}.\n\n"
            f"Requirements:\n"
            f"- Each question must have exactly 5 answer choices (A through E)\n"
            f"- Only ONE correct answer per question\n"
            f"- Distractors should be plausible but clearly wrong to a well-prepared student\n"
            f"- Difficulty: {difficulty}/5 (where 3 = grade-level appropriate)\n"
            f"- Return ONLY valid JSON, no other text\n\n"
        )

        if question_type == "synonym":
            base += (
                f"Generate SYNONYM questions. Each question presents a word in CAPS and asks "
                f"which choice is closest in meaning.\n"
                f"Format: 'WORD most nearly means...'\n"
                f"Use vocabulary appropriate for grade {grade}.\n"
                f"{'Avoid obscure words.' if difficulty <= 2 else ''}\n"
                f"{'Include more challenging vocabulary.' if difficulty >= 4 else ''}\n"
            )
        elif question_type == "analogy":
            base += (
                f"Generate ANALOGY questions using the format: "
                f"'X is to Y as ___ is to ___'\n"
                f"Relationship types to use: synonyms, antonyms, part-to-whole, "
                f"cause-effect, degree/intensity, category, function/purpose.\n"
                f"{'Use simple, concrete relationships.' if level == 'elementary' else 'Use abstract relationships too.'}\n"
            )
        elif question_type in ("arithmetic", "algebra", "geometry", "word_problem"):
            math_focus = {
                "arithmetic": "arithmetic operations, fractions, decimals, percents",
                "algebra": "basic algebra, solving for x, evaluating expressions, order of operations",
                "geometry": "area, perimeter, volume, angles, shapes, coordinate plane basics",
                "word_problem": "multi-step word problems requiring mathematical reasoning",
            }
            base += (
                f"Generate QUANTITATIVE (math) questions focusing on: {math_focus[question_type]}.\n"
                f"No calculator allowed. Ensure arithmetic produces clean answers.\n"
                f"{'For elementary: stick to whole numbers, basic fractions, simple geometry.' if level == 'elementary' else ''}\n"
                f"{'For middle level: include negative numbers, ratios, proportions, more complex operations.' if level == 'middle' else ''}\n"
                f"Include the full solution steps in the explanation.\n"
                f"\nCRITICAL: You MUST double-check every math question before returning it.\n"
                f"1. Solve the problem yourself step by step.\n"
                f"2. Verify your computed answer matches one of the 5 choices.\n"
                f"3. Set correct_answer to the letter (A-E) of THAT matching choice.\n"
                f"4. The explanation MUST show the work AND its final answer MUST match the choice labeled by correct_answer.\n"
                f"If the answer does not appear among the choices, regenerate the question.\n"
            )

        base += (
            f"\nReturn JSON with this exact structure:\n"
            f'{{"questions": [{{"stem": "question text", '
            f'"choices": {{"A": "first choice", "B": "second choice", "C": "third choice", '
            f'"D": "fourth choice", "E": "fifth choice"}}, '
            f'"correct_answer": "B", '
            f'"explanation": "Why B is correct", '
            f'"topic": "{question_type}"}}]}}'
        )
        return base

    def _build_rc_system_prompt(self, level: str, grade: int, difficulty: int) -> str:
        level_display = "Elementary" if level == "elementary" else "Middle"
        return (
            f"You are an expert SSAT test question writer. Generate {level_display} Level "
            f"SSAT reading comprehension content for a student in grade {grade}.\n\n"
            f"Requirements:\n"
            f"- Each passage should be engaging and age-appropriate\n"
            f"- Mix genres: fiction, nonfiction, science, social studies, poetry\n"
            f"- Each question must have exactly 5 answer choices (A through E)\n"
            f"- Question types: main idea, supporting details, inference, "
            f"vocabulary in context, tone/purpose\n"
            f"- Difficulty: {difficulty}/5\n"
            f"- Return ONLY valid JSON, no other text\n"
        )

    def _build_user_prompt(
        self,
        question_type: str,
        count: int,
        difficulty: int,
        grade: int,
        topics: Optional[List[str]] = None,
    ) -> str:
        # Add a random seed phrase to encourage variety across batches
        import random
        variety_seeds = [
            "Use creative, original scenarios.",
            "Use diverse real-world contexts and themes.",
            "Vary the subject matter widely — nature, sports, cooking, travel, science, history.",
            "Make each question unique with different contexts and numbers.",
            "Use a wide range of topics and settings.",
            "Include varied scenarios — school, animals, weather, space, food, music.",
        ]
        seed = random.choice(variety_seeds)

        prompt = f"Generate exactly {count} {question_type} questions at difficulty {difficulty}/5 for grade {grade}."
        prompt += f"\n{seed}"
        prompt += "\nEach question must be substantially different from the others — vary the context, numbers, and wording."
        if topics:
            prompt += f"\nFocus on these specific topics: {', '.join(topics)}"
        prompt += "\nReturn ONLY the JSON object, no markdown formatting or code blocks."
        return prompt

    # ------------------------------------------------------------------
    # API call with retries
    # ------------------------------------------------------------------

    def _call_api(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 0
    ) -> str:
        """Make API call with retry logic for transient errors."""
        if not max_tokens:
            max_tokens = config.MAX_TOKENS

        last_error = None
        for attempt in range(config.MAX_RETRIES):
            self._rate_limit()
            try:
                response = self.client.messages.create(
                    model=config.MODEL,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return response.content[0].text

            except anthropic.RateLimitError as e:
                last_error = e
                wait = (2 ** attempt) * 2
                time.sleep(wait)
            except anthropic.APIConnectionError as e:
                last_error = e
                wait = (2 ** attempt) * 2
                time.sleep(wait)
            except anthropic.InternalServerError as e:
                last_error = e
                wait = (2 ** attempt) * 2
                time.sleep(wait)
            except anthropic.AuthenticationError as e:
                raise QuestionGenerationError(
                    "Invalid API key. Check your ANTHROPIC_API_KEY in .env"
                ) from e
            except anthropic.BadRequestError as e:
                raise QuestionGenerationError(f"Bad request: {e}") from e

        raise QuestionGenerationError(
            f"Failed after {config.MAX_RETRIES} retries: {last_error}"
        )

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        response_text: str,
        question_type: str,
        level: str,
        grade: int,
        difficulty: int,
        batch_id: str,
    ) -> List[Question]:
        """Parse Claude's JSON response into Question objects."""
        # Strip markdown code blocks if present
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise QuestionGenerationError(f"Invalid JSON response: {e}\nResponse: {text[:500]}")

        questions_data = data.get("questions", [])
        if not questions_data:
            raise QuestionGenerationError("No questions in response")

        questions = []
        for qd in questions_data:
            q = self._validate_and_create_question(
                qd, question_type, level, grade, difficulty, batch_id
            )
            if q:
                questions.append(q)

        if not questions:
            raise QuestionGenerationError("No valid questions after parsing")

        return questions

    def _parse_rc_response(
        self,
        response_text: str,
        level: str,
        grade: int,
        difficulty: int,
        batch_id: str,
    ) -> List[Question]:
        """Parse reading comprehension response with passages + questions."""
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise QuestionGenerationError(f"Invalid JSON: {e}")

        passages = data.get("passages", [])
        questions = []

        for passage_data in passages:
            passage_text = passage_data.get("passage_text", "")
            if not passage_text:
                continue

            for qd in passage_data.get("questions", []):
                qd["passage"] = passage_text
                q = self._validate_and_create_question(
                    qd, "reading_comprehension", level, grade, difficulty, batch_id
                )
                if q:
                    questions.append(q)

        return questions

    @staticmethod
    def _extract_numbers(text: str) -> List[str]:
        """Extract numeric values (int/float/fraction) from text."""
        import re
        # Match integers, decimals, and simple fractions
        return re.findall(r'-?\d+(?:\.\d+)?(?:/\d+)?', text)

    def _try_fix_correct_answer(
        self,
        choices: Dict[str, str],
        correct: str,
        explanation: str,
        question_type: str,
    ) -> str:
        """For math questions, check if the explanation's final answer matches the
        tagged correct choice. If not, try to find the right letter."""
        if question_type not in ("arithmetic", "algebra", "geometry", "word_problem"):
            return correct

        if not explanation:
            return correct

        # Get numbers from explanation (last number is usually the answer)
        expl_numbers = self._extract_numbers(explanation)
        if not expl_numbers:
            return correct

        final_answer = expl_numbers[-1]

        # Check if the tagged correct choice contains the final answer
        correct_text = choices.get(correct, "")
        if final_answer in correct_text:
            return correct  # Already consistent

        # The tagged answer doesn't match — search for the right choice
        for letter in ("A", "B", "C", "D", "E"):
            if letter in choices and final_answer in choices[letter]:
                return letter  # Found the matching choice

        # Could not resolve — keep original (better than discarding)
        return correct

    def _validate_and_create_question(
        self,
        qd: Dict,
        question_type: str,
        level: str,
        grade: int,
        difficulty: int,
        batch_id: str,
    ) -> Optional[Question]:
        """Validate a single question dict and return a Question object."""
        stem = qd.get("stem", "").strip()
        choices = qd.get("choices", {})
        correct = qd.get("correct_answer", "").strip().upper()
        explanation = qd.get("explanation", "")
        topic = qd.get("topic", question_type)
        passage = qd.get("passage")

        # Validate
        if not stem:
            return None
        if not isinstance(choices, dict) or len(choices) < 4:
            return None
        if correct not in ("A", "B", "C", "D", "E"):
            return None
        if correct not in choices:
            return None

        # Ensure all 5 choices exist
        for letter in "ABCDE":
            if letter not in choices:
                choices[letter] = ""

        # For math questions, verify the correct_answer matches the explanation
        correct = self._try_fix_correct_answer(choices, correct, explanation, question_type)

        return Question(
            level=level,
            question_type=question_type,
            topic=topic,
            difficulty=difficulty,
            stem=stem,
            passage=passage,
            choices=choices,
            correct_answer=correct,
            explanation=explanation,
            batch_id=batch_id,
        )
