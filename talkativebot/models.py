"""Message, identity, scope, and durable conversation-state models."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class ConversationScope:
    value: str = "default"

    def __post_init__(self) -> None:
        value = (self.value or "").strip()
        if not value:
            raise ValueError("Conversation scope must not be blank")
        object.__setattr__(self, "value", value)

    @property
    def is_default(self) -> bool:
        return self.value == "default"


DEFAULT_SCOPE = ConversationScope()


@dataclass(frozen=True)
class ConversationAddress:
    channel: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None

    @staticmethod
    def _present(value: Optional[str]) -> bool:
        return value is not None and bool(value.strip())

    def persistence_key(self) -> str:
        if self._present(self.conversation_id):
            return "{}:conversation:{}".format(self.channel, self.conversation_id)
        if self._present(self.session_id):
            return "{}:session:{}".format(self.channel, self.session_id)
        if self._present(self.user_id):
            return "{}:user:{}".format(self.channel, self.user_id)
        raise ValueError("Address requires a conversation, session, or user id")


@dataclass
class ExternalIdentity:
    provider: Optional[str] = None
    user_id: Optional[str] = None
    display_name: Optional[str] = None


@dataclass
class ReferralContext:
    source: Optional[str] = None
    campaign: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelInfo:
    name: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IncomingMessage:
    address: ConversationAddress
    text: str
    channel_info: Optional[ChannelInfo] = None
    external_identity: Optional[ExternalIdentity] = None
    referral: Optional[ReferralContext] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_payload: Any = None


@dataclass
class OutgoingMessage:
    address: ConversationAddress
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    channel_info: Optional[ChannelInfo] = None


@dataclass
class Facts:
    """Ordered, string-keyed state; assigning None removes a fact."""

    _values: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def put(self, key: str, value: Any) -> None:
        if value is None:
            self._values.pop(key, None)
        else:
            self._values[key] = value

    add = put

    def remove(self, key: str) -> Any:
        return self._values.pop(key, None)

    def as_map(self) -> Mapping[str, Any]:
        return dict(self._values)

    def replace(self, values: Mapping[str, Any]) -> None:
        self._values = deepcopy(dict(values))

    def snapshot(self) -> Dict[str, Any]:
        return deepcopy(self._values)


@dataclass
class PendingInteraction:
    address: ConversationAddress
    conversation_type: str
    topic_key: str
    question: Any
    facts: Dict[str, Any]
    interaction_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None


@dataclass(frozen=True)
class PendingInteractionKey:
    address_key: str
    scope_value: str = "default"

    @classmethod
    def from_address(cls, address: ConversationAddress,
                     scope: ConversationScope = DEFAULT_SCOPE) -> "PendingInteractionKey":
        return cls(address.persistence_key(), scope.value)

    @property
    def value(self) -> str:
        if self.scope_value == "default":
            return self.address_key
        return "{}|scope:{}".format(self.address_key, self.scope_value)