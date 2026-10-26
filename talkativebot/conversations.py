"""Conversation execution and per-conversation runtime support."""

from typing import Any, Dict, Iterable, List, Optional

from .models import Facts
from .topics import ConversationAwareTopic, TopicFactory, TopicScanner


class Conversation:
    def play(self) -> Any:
        raise NotImplementedError


class AbstractConversation(Conversation):
    def __init__(self, bot: Any, address: Any,
                 topic_scanner: Optional[TopicScanner] = None,
                 topic_factory: Optional[TopicFactory] = None) -> None:
        self.bot = bot
        self.address = address
        self.facts = Facts()
        self._closed = False
        self._abandoned = False
        self._topics: Dict[str, Any] = {}
        self._current_topic = None
        self._runtime = None
        self._topic_scanner = topic_scanner or TopicScanner(())
        self._topic_factory = topic_factory or TopicFactory()
        for topic_class in self._topic_scanner.scan(type(self)):
            instance = self._topic_factory.create(topic_class, self)
            self.register_topic(instance)

    def register_topic(self, topic: Any) -> None:
        key = topic.get_key()
        if not key or key.strip() != key:
            raise ValueError("Topic key must be nonblank and trimmed")
        if key in self._topics:
            raise ValueError("Duplicate topic key: {}".format(key))
        if isinstance(topic, ConversationAwareTopic):
            topic.set_conversation(self)
        self._topics[key] = topic

    def get_topic(self, key: str) -> Any:
        return self._topics.get(key)

    def get_topics(self) -> List[Any]:
        return list(self._topics.values())

    def get_current_topic(self) -> Any:
        return self._current_topic

    def is_terminated(self) -> bool:
        return self._closed or self._abandoned

    def is_closed(self) -> bool:
        return self.is_terminated() or bool(self._topics and
                                             not any(t.is_playable(self.facts) for t in self._topics.values()))

    def next_topic(self) -> Any:
        if self._current_topic is not None:
            next_key = self._current_topic.get_next_topic_key()
            if next_key:
                candidate = self._topics.get(next_key)
                if candidate is not None and candidate.is_playable(self.facts):
                    return candidate
        playable = [t for t in self._topics.values() if t.is_playable(self.facts)]
        if not playable:
            return None
        return min(playable, key=lambda t: (t.get_order(), t.get_key()))

    def play(self) -> Any:
        if self.is_terminated():
            return self.on_already_closed()
        selected = self.next_topic()
        if selected is None:
            self._closed = True
            return self.on_conversation_closed()
        self._current_topic = selected
        result = selected.play()
        remaining = any(t.is_playable(self.facts) for t in self._topics.values())
        if not remaining:
            self._closed = True
            return self.on_conversation_closed()
        return self.on_topic_played(selected)

    def on_topic_closed(self, topic: Any) -> None:
        return None

    def on_topic_played(self, topic: Any) -> Any:
        return None

    def on_conversation_closed(self) -> Any:
        return None

    def on_already_closed(self) -> Any:
        return None

    def abandon(self) -> None:
        self._abandoned = True
        self._closed = True

    def set_runtime(self, runtime: Any) -> None:
        self._runtime = runtime

    def get_runtime(self) -> Any:
        if self._runtime is None:
            raise RuntimeError("Conversation runtime has not been initialized")
        return self._runtime


class ConversationFactory:
    def create(self, conversation_type: Any, address: Any) -> Conversation:
        return conversation_type(self.bot, address)

    def __init__(self, bot: Any = None) -> None:
        self.bot = bot


class ConversationRuntimeRegistry:
    def __init__(self) -> None:
        self._runtimes: Dict[str, Any] = {}

    def get_or_initialize(self, conversation_type: type, initializer: Any) -> Any:
        key = "{}.{}".format(conversation_type.__module__, conversation_type.__name__)
        if key not in self._runtimes:
            runtime = initializer.initialize(conversation_type)
            self._runtimes[key] = runtime
        return self._runtimes[key]

    def close(self) -> None:
        for runtime in self._runtimes.values():
            close = getattr(runtime, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    def clear(self) -> None:
        self._runtimes.clear()