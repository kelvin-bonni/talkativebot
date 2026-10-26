"""Simple stdin/stdout channel adapters."""

from typing import Callable, Optional

from .models import ConversationAddress, IncomingMessage, OutgoingMessage


class ConsoleOutputChannel:
    name = "console"

    def __init__(self, writer: Optional[Callable[[str], None]] = None) -> None:
        self.writer = writer or print

    def send(self, message: OutgoingMessage) -> None:
        self.writer(message.text)


class ConsoleInputChannel:
    def __init__(self, handler: object,
                 address: Optional[ConversationAddress] = None) -> None:
        self.handler = handler
        self.address = address or ConversationAddress("console", "console-user", "console-session")

    def handle_line(self, text: str) -> object:
        return self.handler.handle(IncomingMessage(self.address, text))