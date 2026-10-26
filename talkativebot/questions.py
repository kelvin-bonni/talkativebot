"""Question and choice-selection primitives."""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Tuple


@dataclass(frozen=True)
class Option:
    value: int
    text: str


class QuestionType(Enum):
    CHOICE = "choice"
    TEXT = "text"


@dataclass(frozen=True)
class Question:
    text: str
    options: Tuple[Option, ...] = ()
    type: Optional[QuestionType] = None

    def __post_init__(self) -> None:
        options = tuple(self.options or ())
        object.__setattr__(self, "options", options)
        if self.type is None:
            object.__setattr__(self, "type", QuestionType.CHOICE if options else QuestionType.TEXT)

    @classmethod
    def choice(cls, text: str, options: Iterable[Option]) -> "Question":
        options = tuple(options)
        if not options:
            raise ValueError("Choice questions require at least one option")
        return cls(text, options, QuestionType.CHOICE)

    @classmethod
    def text_input(cls, text: str) -> "Question":
        return cls(text, (), QuestionType.TEXT)


@dataclass(frozen=True)
class SelectedAnswer:
    option: Optional[Option]
    raw_input: str
    message: object

    def get_text(self) -> str:
        return self.option.text if self.option is not None else self.raw_input

    def get_value(self) -> int:
        if self.option is None:
            raise ValueError("Text answers do not have an option value")
        return self.option.value


class DefaultOptionSelector:
    def select(self, question: Question, message: object) -> Optional[Option]:
        raw = (getattr(message, "text", "") or "").strip()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = None
        if value is not None:
            for option in question.options:
                if option.value == value:
                    return option
        for option in question.options:
            if option.text.lower() == raw.lower():
                return option
        return None