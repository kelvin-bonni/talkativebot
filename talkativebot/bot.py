"""Conversation orchestration: route, start/resume, ask, and conclude."""

from typing import Any, Iterable, Optional

from .models import (DEFAULT_SCOPE, ConversationScope, IncomingMessage, OutgoingMessage,
                     PendingInteraction)
from .questions import DefaultOptionSelector, QuestionType, SelectedAnswer
from .routing import (ConversationMessageRouter, ConversationRouteMode,
                      ConversationStartRegistry, ConversationStartRequest,
                      DefaultConversationMessageRouter)
from .storage import InMemoryPendingInteractionStore


class OutputChannel:
    def send(self, message: OutgoingMessage) -> Any:
        raise NotImplementedError


class InputMessageHandler:
    def handle(self, message: IncomingMessage) -> Any:
        raise NotImplementedError


class OutputChannelRegistry:
    def __init__(self, channels: Optional[Iterable[OutputChannel]] = None) -> None:
        self._channels = {getattr(channel, "name", "default"): channel for channel in (channels or ())}

    def register(self, name: str, channel: OutputChannel) -> None:
        self._channels[name] = channel

    def get(self, name: str) -> OutputChannel:
        if name not in self._channels:
            raise KeyError("No output channel registered for {!r}".format(name))
        return self._channels[name]


class TalkativeBot(InputMessageHandler):
    START_TRIGGER_FACT = "__talkative.start.trigger"
    START_RAW_INPUT_FACT = "__talkative.start.raw_input"
    UNKNOWN_START_PREFIX = "I don't know how to start a conversation from: "

    def __init__(self, pending_store: Any = None, output_channels: Any = None,
                 start_registry: Any = None, router: Any = None,
                 option_selector: Any = None, topic_scanner: Any = None,
                 conversation_factory: Any = None) -> None:
        self.pending_store = pending_store or InMemoryPendingInteractionStore()
        self.output_channels = output_channels or OutputChannelRegistry()
        self.start_registry = start_registry or ConversationStartRegistry()
        self.router = router or DefaultConversationMessageRouter()
        self.option_selector = option_selector or DefaultOptionSelector()
        self.topic_scanner = topic_scanner
        self.conversation_factory = conversation_factory
        self._scope = DEFAULT_SCOPE

    def create_conversation(self, conversation_type: type, address: Any) -> Any:
        if self.conversation_factory is not None:
            return self.conversation_factory.create(conversation_type, address)
        return conversation_type(self, address, topic_scanner=self.topic_scanner)

    def play(self, conversation: Any) -> Any:
        return conversation.play()

    def handle(self, message: IncomingMessage) -> Any:
        route = self.router.route(message, self)
        if route is None:
            from .routing import ConversationRoute
            route = ConversationRoute(message.address)
        scope = route.scope or DEFAULT_SCOPE
        if route.mode in (ConversationRouteMode.RESUME_OR_START, ConversationRouteMode.RESUME_ONLY):
            pending = self.pending_store.find_by_address(route.address, scope)
            if pending is not None:
                return self._resume(message, pending, route.address, scope)
        if route.mode in (ConversationRouteMode.RESUME_OR_START, ConversationRouteMode.START_ONLY):
            return self._start(message, route.address, scope)
        return self._send_unknown(route.address, message.text)

    def _resume(self, message: IncomingMessage, pending: PendingInteraction,
                address: Any, scope: ConversationScope) -> Any:
        question = pending.question
        option = None
        if question.type == QuestionType.CHOICE:
            option = self.option_selector.select(question, message)
            if option is None:
                raise ValueError("Invalid choice: {}".format(message.text))
        conversation_type = pending.conversation_type
        if isinstance(conversation_type, str):
            conversation_type = self._load_type(conversation_type)
        conversation = self.create_conversation(conversation_type, address)
        conversation.facts.replace(pending.facts)
        topic = conversation.get_topic(pending.topic_key)
        if topic is None:
            raise ValueError("Pending topic {!r} does not exist".format(pending.topic_key))
        topic.on_input(SelectedAnswer(option, message.text, message))
        self.pending_store.delete_by_address(address, scope)
        previous_scope, self._scope = self._scope, scope
        try:
            return conversation.play()
        finally:
            self._scope = previous_scope

    def _start(self, message: IncomingMessage, address: Any, scope: ConversationScope) -> Any:
        request = ConversationStartRequest(message, scope)
        resolved = self.start_registry.resolve(request)
        if resolved is None or resolved.conversation_type is None:
            return self._send_unknown(address, message.text)
        conversation_type = resolved.conversation_type
        if isinstance(conversation_type, str):
            conversation_type = self._load_type(conversation_type)
        conversation = self.create_conversation(conversation_type, address)
        conversation.facts.replace(resolved.initial_facts)
        conversation.facts.put(self.START_TRIGGER_FACT, message.text)
        conversation.facts.put(self.START_RAW_INPUT_FACT, message.text)
        previous_scope, self._scope = self._scope, scope
        try:
            return conversation.play()
        finally:
            self._scope = previous_scope

    @staticmethod
    def _load_type(path: str) -> type:
        import importlib
        module_name, _, class_name = path.rpartition(".")
        if not module_name:
            raise ValueError("Conversation type must be a fully qualified name")
        return getattr(importlib.import_module(module_name), class_name)

    def ask(self, conversation: Any, topic: Any, question_or_message: Any) -> Any:
        if isinstance(question_or_message, OutgoingMessage):
            outgoing = question_or_message
            question = None
        else:
            question = question_or_message
            rendered = question.text
            if question.options:
                rendered += "\n" + "\n".join("{}. {}".format(option.value, option.text)
                                               for option in question.options)
            outgoing = OutgoingMessage(conversation.address, rendered)
        if question is not None:
            pending = PendingInteraction(
                address=conversation.address,
                conversation_type="{}.{}".format(type(conversation).__module__, type(conversation).__name__),
                topic_key=topic.get_key(), question=question, facts=conversation.facts.snapshot())
            self.pending_store.save(pending, self._scope)
        return self.output_channels.get(conversation.address.channel).send(outgoing)

    def conclude(self, conversation: Any, text_or_message: Any) -> Any:
        outgoing = text_or_message if isinstance(text_or_message, OutgoingMessage) else OutgoingMessage(
            conversation.address, str(text_or_message))
        result = self.output_channels.get(conversation.address.channel).send(outgoing)
        conversation.abandon()
        return result

    def _send_unknown(self, address: Any, raw_input: str) -> Any:
        output = OutgoingMessage(address, self.UNKNOWN_START_PREFIX + str(raw_input))
        return self.output_channels.get(address.channel).send(output)

    def find_pending_interaction(self, address: Any, scope: ConversationScope = DEFAULT_SCOPE) -> Any:
        return self.pending_store.find_by_address(address, scope)