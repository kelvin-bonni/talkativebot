"""Topic metadata, lifecycle, and module-based topic discovery."""

from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Type


class TopicState(Enum):
    NEW = "new"
    PLAYING = "playing"
    CLOSED = "closed"
    FAILED = "failed"


def topic(key: str = "", name: str = "", description: str = "",
          conversation: Optional[type] = None, can_replay: bool = False,
          order: int = 0, next: Optional[str] = None) -> Callable[[type], type]:
    def decorate(topic_class: type) -> type:
        topic_class.__topic_metadata__ = {
            "key": key, "name": name, "description": description,
            "conversation": conversation, "can_replay": can_replay,
            "order": order, "next": next,
        }
        return topic_class
    return decorate


class ConversationTopic:
    def get_key(self) -> str:
        raise NotImplementedError

    def is_playable(self, facts: Any) -> bool:
        raise NotImplementedError

    def play(self) -> Any:
        raise NotImplementedError

    def on_input(self, selected_answer: Any) -> None:
        self.close()

    def close(self) -> None:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError


class ConversationAwareTopic:
    def set_conversation(self, conversation: Any) -> None:
        self.conversation = conversation


class AbstractTopic(ConversationTopic, ConversationAwareTopic):
    def __init__(self, conversation: Any = None) -> None:
        self.conversation = conversation
        self.state = TopicState.NEW

    @property
    def metadata(self) -> Dict[str, Any]:
        return getattr(type(self), "__topic_metadata__", {})

    def get_key(self) -> str:
        return self.metadata.get("key") or self._decapitalize(type(self).__name__)

    def get_name(self) -> str:
        return self.metadata.get("name") or type(self).__name__

    def get_description(self) -> str:
        return self.metadata.get("description", "")

    def get_order(self) -> int:
        return self.metadata.get("order", 0)

    def get_next_topic_key(self) -> Optional[str]:
        return self.metadata.get("next")

    def can_replay(self) -> bool:
        return bool(self.metadata.get("can_replay", False))

    @staticmethod
    def _decapitalize(value: str) -> str:
        return value[:1].lower() + value[1:] if value else value

    def is_playable(self, facts: Any) -> bool:
        if self.conversation is None or self.conversation.is_terminated():
            return False
        persisted_closed = facts.get("__talkative.topic.{}.closed".format(self.get_key()), False)
        if (self.state == TopicState.CLOSED or persisted_closed) and not self.can_replay():
            return False
        return self.can_play_with_facts(facts)

    def can_play_with_facts(self, facts: Any) -> bool:
        return True

    def play(self) -> Any:
        if not self.is_playable(self.conversation.facts):
            return None
        self.state = TopicState.PLAYING
        try:
            return self.do_play(self.conversation.facts)
        except Exception:
            self.state = TopicState.FAILED
            raise

    def do_play(self, facts: Any) -> Any:
        raise NotImplementedError

    def on_input(self, selected_answer: Any) -> None:
        self.close()

    def close(self) -> None:
        if self.state == TopicState.CLOSED:
            return
        self.state = TopicState.CLOSED
        self.conversation.facts.put("__talkative.topic.{}.closed".format(self.get_key()), True)
        self.conversation.on_topic_closed(self)

    def reset(self) -> None:
        self.state = TopicState.NEW
        self.conversation.facts.remove("__talkative.topic.{}.closed".format(self.get_key()))

    def ask(self, question: Any) -> Any:
        return self.conversation.bot.ask(self.conversation, self, question)

    def conclude(self, text_or_message: Any) -> Any:
        return self.conversation.bot.conclude(self.conversation, text_or_message)


class TopicFactory:
    def create(self, topic_class: type, conversation: Any) -> ConversationTopic:
        try:
            instance = topic_class(conversation)
        except TypeError:
            instance = topic_class()
        if isinstance(instance, ConversationAwareTopic):
            instance.set_conversation(conversation)
        return instance


class TopicScanner:
    def __init__(self, topic_classes: Iterable[type]) -> None:
        self.topic_classes = tuple(topic_classes)

    def scan(self, conversation_type: type) -> List[type]:
        found = []
        for cls in self.topic_classes:
            metadata = getattr(cls, "__topic_metadata__", None)
            if metadata is None or not issubclass(cls, ConversationTopic):
                continue
            owner = metadata.get("conversation")
            if owner is None or owner is object or issubclass(conversation_type, owner):
                found.append(cls)
        return sorted(found, key=lambda cls: (getattr(cls, "__topic_metadata__", {}).get("order", 0),
                                               getattr(cls, "__topic_metadata__", {}).get("key") or
                                               AbstractTopic._decapitalize(cls.__name__)))