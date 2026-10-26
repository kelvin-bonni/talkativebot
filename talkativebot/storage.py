"""Pending interaction storage implementations."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Dict, Optional

from .models import (DEFAULT_SCOPE, ConversationAddress, ConversationScope,
                     PendingInteraction, PendingInteractionKey)


class InMemoryPendingInteractionStore:
    """Thread-safe one-pending-prompt-per-address-and-scope store."""

    def __init__(self, default_ttl: Optional[timedelta] = None) -> None:
        self.default_ttl = default_ttl
        self._items: Dict[str, PendingInteraction] = {}
        self._lock = RLock()

    def save(self, interaction: PendingInteraction,
             scope: ConversationScope = DEFAULT_SCOPE,
             ttl: Optional[timedelta] = None) -> None:
        key = PendingInteractionKey.from_address(interaction.address, scope).value
        lifetime = self.default_ttl if ttl is None else ttl
        interaction.expires_at = (datetime.now(timezone.utc) + lifetime
                                  if lifetime is not None and lifetime.total_seconds() > 0 else None)
        with self._lock:
            self._items[key] = interaction

    def find_by_address(self, address: ConversationAddress,
                        scope: ConversationScope = DEFAULT_SCOPE) -> Optional[PendingInteraction]:
        key = PendingInteractionKey.from_address(address, scope).value
        with self._lock:
            interaction = self._items.get(key)
            if interaction is not None and interaction.expires_at is not None:
                if interaction.expires_at <= datetime.now(timezone.utc):
                    del self._items[key]
                    return None
            return interaction

    def delete_by_address(self, address: ConversationAddress,
                          scope: ConversationScope = DEFAULT_SCOPE) -> None:
        key = PendingInteractionKey.from_address(address, scope).value
        with self._lock:
            self._items.pop(key, None)


class SQLitePendingInteractionStore:
    """SQLite-backed store for process restarts and small deployments."""

    def __init__(self, database: str = "talkativebot.sqlite3",
                 default_ttl: Optional[timedelta] = None) -> None:
        self.database = database
        self.default_ttl = default_ttl
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS pending_interactions (
                interaction_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                expires_at TEXT
            )""")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _encode(interaction: PendingInteraction) -> str:
        address = interaction.address
        payload = {
            "address": {"channel": address.channel, "user_id": address.user_id,
                        "session_id": address.session_id, "conversation_id": address.conversation_id},
            "conversation_type": interaction.conversation_type,
            "topic_key": interaction.topic_key,
            "question": {"text": interaction.question.text,
                         "type": interaction.question.type.value,
                         "options": [{"value": option.value, "text": option.text}
                                     for option in interaction.question.options]},
            "facts": interaction.facts,
            "interaction_id": interaction.interaction_id,
            "created_at": interaction.created_at.isoformat(),
        }
        return json.dumps(payload)

    @staticmethod
    def _decode(payload: str, expires_at: Optional[str]) -> PendingInteraction:
        from .questions import Option, Question, QuestionType
        data = json.loads(payload)
        address = ConversationAddress(**data["address"])
        q = data["question"]
        question = Question(q["text"], tuple(Option(**option) for option in q["options"]),
                            QuestionType(q["type"]))
        return PendingInteraction(
            address=address, conversation_type=data["conversation_type"], topic_key=data["topic_key"],
            question=question, facts=data["facts"], interaction_id=data.get("interaction_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(expires_at) if expires_at else None)

    def save(self, interaction: PendingInteraction,
             scope: ConversationScope = DEFAULT_SCOPE,
             ttl: Optional[timedelta] = None) -> None:
        key = PendingInteractionKey.from_address(interaction.address, scope).value
        lifetime = self.default_ttl if ttl is None else ttl
        expires = (datetime.now(timezone.utc) + lifetime
                   if lifetime is not None and lifetime.total_seconds() > 0 else None)
        with self._lock, self._connect() as connection:
            connection.execute("""INSERT OR REPLACE INTO pending_interactions
                (interaction_key, payload, expires_at) VALUES (?, ?, ?)""",
                               (key, self._encode(interaction), expires.isoformat() if expires else None))

    def find_by_address(self, address: ConversationAddress,
                        scope: ConversationScope = DEFAULT_SCOPE) -> Optional[PendingInteraction]:
        key = PendingInteractionKey.from_address(address, scope).value
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT payload, expires_at FROM pending_interactions WHERE interaction_key=?",
                                     (key,)).fetchone()
            if row is None:
                return None
            expires = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
            if expires is not None and expires <= datetime.now(timezone.utc):
                connection.execute("DELETE FROM pending_interactions WHERE interaction_key=?", (key,))
                return None
            return self._decode(row["payload"], row["expires_at"])

    def delete_by_address(self, address: ConversationAddress,
                          scope: ConversationScope = DEFAULT_SCOPE) -> None:
        key = PendingInteractionKey.from_address(address, scope).value
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM pending_interactions WHERE interaction_key=?", (key,))


class RedisPendingInteractionStore:
    """Redis store using a redis-py-compatible client supplied by the caller."""

    PREFIX = "talkativebot:pending-interaction:"

    def __init__(self, client: Any, default_ttl: Optional[timedelta] = None) -> None:
        self.client = client
        self.default_ttl = default_ttl

    def save(self, interaction: PendingInteraction,
             scope: ConversationScope = DEFAULT_SCOPE,
             ttl: Optional[timedelta] = None) -> None:
        key = self.PREFIX + PendingInteractionKey.from_address(interaction.address, scope).value
        lifetime = self.default_ttl if ttl is None else ttl
        value = SQLitePendingInteractionStore._encode(interaction)
        if lifetime is not None and lifetime.total_seconds() > 0:
            self.client.setex(key, int(lifetime.total_seconds()), value)
        else:
            self.client.set(key, value)

    def find_by_address(self, address: ConversationAddress,
                        scope: ConversationScope = DEFAULT_SCOPE) -> Optional[PendingInteraction]:
        key = self.PREFIX + PendingInteractionKey.from_address(address, scope).value
        payload = self.client.get(key)
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        ttl = self.client.ttl(key)
        expiry = datetime.now(timezone.utc) + timedelta(seconds=ttl) if ttl is not None and ttl > 0 else None
        return SQLitePendingInteractionStore._decode(payload, expiry.isoformat() if expiry else None)

    def delete_by_address(self, address: ConversationAddress,
                          scope: ConversationScope = DEFAULT_SCOPE) -> None:
        key = self.PREFIX + PendingInteractionKey.from_address(address, scope).value
        self.client.delete(key)