"""Back-channel response phrases for JAV voice companion.

Back-channel phrases are short acknowledgments spoken immediately after
the user's utterance is transcribed, while the LLM is still thinking.
They eliminate dead silence and make the interaction feel alive.

Usage:
    phrase = pick_phrase(user_text, language="uk")
    # emit tts_say event with phrase
"""
from __future__ import annotations

import random
import re

# ---------------------------------------------------------------------------
# Phrase dictionaries
# ---------------------------------------------------------------------------

_PHRASES_UK = {
    "default": [
        "Розумію...",
        "Хвилинку...",
        "Слухаю...",
        "Зрозумів...",
        "Добре...",
        "Секунду...",
        "Обробляю...",
    ],
    "question": [
        "Цікаво, дай подумаю...",
        "Гарне питання, хвилинку...",
        "Зараз перевірю...",
        "Думаю над цим...",
        "Розбираюсь...",
        "Цікаве питання...",
    ],
    "long": [
        "Це займе секунду, аналізую...",
        "Обробляю, хвилинку...",
        "Зараз розберусь...",
        "Думаю...",
    ],
    "command": [
        "Виконую...",
        "Зараз зроблю...",
        "Добре, займусь цим...",
        "Беруся...",
    ],
    "greeting": [
        "Привіт!",
        "Слухаю вас.",
        "Добрий день!",
        "Тут, слухаю.",
    ],
}

_PHRASES_EN = {
    "default": [
        "One moment...",
        "I see...",
        "Got it...",
        "Sure...",
        "Let me think...",
        "Right...",
    ],
    "question": [
        "Good question, let me think...",
        "Interesting, give me a second...",
        "Let me look into that...",
        "Thinking about that...",
        "Let me consider...",
    ],
    "long": [
        "That'll take a moment, analyzing...",
        "Working on it...",
        "Let me work through this...",
        "Processing...",
    ],
    "command": [
        "On it...",
        "Sure, let me do that...",
        "Right away...",
        "I'll take care of that...",
    ],
    "greeting": [
        "Hello!",
        "I'm here.",
        "Good to hear from you.",
        "Listening.",
    ],
}

_PHRASES_RU = {
    "default": [
        "Понял...",
        "Одну секунду...",
        "Слушаю...",
        "Хорошо...",
        "Обрабатываю...",
    ],
    "question": [
        "Интересно, дай подумаю...",
        "Хороший вопрос, секунду...",
        "Разбираюсь...",
        "Думаю...",
    ],
    "long": [
        "Это займёт секунду...",
        "Анализирую...",
        "Работаю над этим...",
    ],
    "command": [
        "Выполняю...",
        "Сейчас сделаю...",
        "Берусь...",
    ],
    "greeting": [
        "Привет!",
        "Слушаю.",
        "Здесь.",
    ],
}

_LANG_MAP: dict[str, dict] = {
    "uk": _PHRASES_UK,
    "en": _PHRASES_EN,
    "ru": _PHRASES_RU,
}

# ---------------------------------------------------------------------------
# Phrase detection helpers
# ---------------------------------------------------------------------------

_QUESTION_WORDS_UK = re.compile(
    r"\b(що|як|чому|навіщо|коли|де|хто|скільки|чи|розкажи|поясни|поясніть|опиши)\b",
    re.IGNORECASE,
)
_QUESTION_WORDS_EN = re.compile(
    r"\b(what|how|why|when|where|who|which|explain|describe|tell me|show me)\b",
    re.IGNORECASE,
)
_GREETING_WORDS = re.compile(
    r"\b(привіт|hello|hi|hey|добрий|вітаю|добридень|слухай)\b",
    re.IGNORECASE,
)
_COMMAND_WORDS = re.compile(
    r"\b(запусти|відкрий|зроби|напиши|виконай|увімкни|вимкни|відправ|run|open|create|write|execute|turn on|turn off|send)\b",
    re.IGNORECASE,
)


def _classify(text: str) -> str:
    """Classify utterance type: default | question | long | command | greeting."""
    if _GREETING_WORDS.search(text):
        return "greeting"
    if _COMMAND_WORDS.search(text):
        return "command"
    if "?" in text or _QUESTION_WORDS_UK.search(text) or _QUESTION_WORDS_EN.search(text):
        return "question"
    if len(text.split()) > 20:
        return "long"
    return "default"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pick_phrase(user_text: str, language: str = "uk") -> str:
    """Pick a natural back-channel phrase for the given user utterance.

    Args:
        user_text: The transcribed user speech.
        language:  Language code — 'uk', 'en', 'ru'. Falls back to 'en'.

    Returns:
        A short acknowledgment string ready to be passed to TTS.
    """
    phrases = _LANG_MAP.get(language, _PHRASES_EN)
    category = _classify(user_text)
    pool = phrases.get(category, phrases["default"])
    return random.choice(pool)
