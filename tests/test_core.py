import os
import tempfile
import unittest

from talkativebot import (AbstractConversation, AbstractTopic, ConversationAddress,
                          ConversationRoute, ConversationRouteMode, ConversationScope,
                          ConversationStartRegistry, ConversationStartResolver,
                          IncomingMessage, InMemoryPendingInteractionStore, Option,
                          OutputChannelRegistry, Question, SQLitePendingInteractionStore,
                          TalkativeBot, TopicScanner, topic)


class MemoryOutput:
    name = "test"

    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)


class FlowConversation(AbstractConversation):
    pass


@topic(key="first", order=0, next="second")
class FirstTopic(AbstractTopic):
    def do_play(self, facts):
        self.ask(Question.choice("Continue?", [Option(1, "Yes"), Option(2, "No")]))

    def on_input(self, answer):
        self.conversation.facts.put("answer", answer.get_text())
        self.close()


@topic(key="second", order=1)
class SecondTopic(AbstractTopic):
    def do_play(self, facts):
        self.ask(Question.text_input("Your name?"))

    def on_input(self, answer):
        self.conversation.facts.put("name", answer.get_text())
        self.close()


class StartResolver(ConversationStartResolver):
    def resolve(self, request):
        if request.message.text == "begin":
            request.conversation_type = FlowConversation
            return request
        return None


class TalkativeBotTests(unittest.TestCase):
    def setUp(self):
        self.output = MemoryOutput()
        self.address = ConversationAddress("test", "user-1", "session-1")
        self.store = InMemoryPendingInteractionStore()
        self.bot = TalkativeBot(pending_store=self.store,
                                output_channels=OutputChannelRegistry([self.output]),
                                start_registry=ConversationStartRegistry([StartResolver()]),
                                topic_scanner=TopicScanner([FirstTopic, SecondTopic]))

    def test_start_resume_and_text_answer(self):
        self.bot.handle(IncomingMessage(self.address, "begin"))
        pending = self.store.find_by_address(self.address)
        self.assertIsNotNone(pending)
        self.assertEqual("first", pending.topic_key)
        self.bot.handle(IncomingMessage(self.address, "1"))
        pending = self.store.find_by_address(self.address)
        self.assertEqual("second", pending.topic_key)
        self.bot.handle(IncomingMessage(self.address, "Ada"))
        self.assertIsNone(self.store.find_by_address(self.address))

    def test_invalid_choice_does_not_consume_pending(self):
        self.bot.handle(IncomingMessage(self.address, "begin"))
        with self.assertRaises(ValueError):
            self.bot.handle(IncomingMessage(self.address, "unknown"))
        self.assertIsNotNone(self.store.find_by_address(self.address))

    def test_scopes_coexist_and_default_key_is_compatible(self):
        self.bot.handle(IncomingMessage(self.address, "begin"))
        other_scope = ConversationScope("alternate")
        self.assertIsNotNone(self.store.find_by_address(self.address))
        self.assertIsNone(self.store.find_by_address(self.address, other_scope))
        self.assertEqual(self.address.persistence_key(),
                         self.store_key(self.address))

    def test_sqlite_store_round_trips_question_and_facts(self):
        handle, path = tempfile.mkstemp()
        os.close(handle)
        try:
            store = SQLitePendingInteractionStore(path)
            self.bot.handle(IncomingMessage(self.address, "begin"))
            interaction = self.store.find_by_address(self.address)
            store.save(interaction)
            restored = store.find_by_address(self.address)
            self.assertEqual(interaction.question, restored.question)
            self.assertEqual(interaction.facts, restored.facts)
        finally:
            os.unlink(path)

    @staticmethod
    def store_key(address):
        from talkativebot import PendingInteractionKey
        return PendingInteractionKey.from_address(address).value


if __name__ == "__main__":
    unittest.main()