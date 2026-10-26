"""Conversation routing and start-resolution extension points."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, List, Optional

from .models import DEFAULT_SCOPE, ConversationAddress, ConversationScope, IncomingMessage


class ConversationRouteMode(Enum):
    RESUME_OR_START = "resume_or_start"
    RESUME_ONLY = "resume_only"
    START_ONLY = "start_only"
    REJECT = "reject"


@dataclass(frozen=True)
class ConversationRoute:
    address: ConversationAddress
    scope: ConversationScope = DEFAULT_SCOPE
    mode: ConversationRouteMode = ConversationRouteMode.RESUME_OR_START


@dataclass
class ConversationStartRequest:
    message: IncomingMessage
    scope: ConversationScope
    conversation_type: Optional[type] = None
    initial_facts: dict = field(default_factory=dict)


class ConversationMessageRouter:
    def route(self, message: IncomingMessage, context: Any) -> Optional[ConversationRoute]:
        raise NotImplementedError


class DefaultConversationMessageRouter(ConversationMessageRouter):
    def route(self, message: IncomingMessage, context: Any) -> ConversationRoute:
        return ConversationRoute(message.address)


class ConversationStartResolver:
    def supports_scope(self, scope: ConversationScope) -> bool:
        return scope.is_default

    def resolve(self, request: ConversationStartRequest) -> Optional[ConversationStartRequest]:
        raise NotImplementedError


class OrderedConversationStartResolver(ConversationStartResolver):
    order = 0


class ScopedConversationStartResolver(OrderedConversationStartResolver):
    def supports_scope(self, scope: ConversationScope) -> bool:
        return True


class ConversationStartRegistry:
    def __init__(self, resolvers: Optional[Iterable[ConversationStartResolver]] = None) -> None:
        self._resolvers: List[ConversationStartResolver] = sorted(
            resolvers or (), key=lambda resolver: getattr(resolver, "order", 0))

    def resolve(self, request: ConversationStartRequest) -> Optional[ConversationStartRequest]:
        for resolver in self._resolvers:
            if resolver.supports_scope(request.scope):
                result = resolver.resolve(request)
                if result is not None:
                    return result
        return None