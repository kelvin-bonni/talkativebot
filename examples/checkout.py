"""Runnable console checkout example: python -m examples.checkout"""

from talkativebot import (AbstractConversation, AbstractTopic, ConversationAddress,
                          ConversationStartRegistry, ConversationStartResolver,
                          IncomingMessage, Option, OutputChannelRegistry, Question,
                          TalkativeBot, TopicScanner, topic)
from talkativebot.console import ConsoleOutputChannel


class CheckoutConversation(AbstractConversation):
    def on_topic_played(self, played_topic):
        return "Played topic: {}".format(played_topic.get_key())

    def on_conversation_closed(self):
        print("Facts:", self.facts.as_map())
        return "Conversation closed"


@topic(key="greetings", order=0, next="cart_review")
class GreetingsTopic(AbstractTopic):
    def do_play(self, facts):
        self.ask(Question.choice("Would you like to check out?", [Option(1, "Check out"), Option(2, "Not yet")]))

    def on_input(self, answer):
        if answer.get_value() == 1:
            self.conversation.facts.put("agreed_to_checkout", True)
            self.close()
        else:
            self.conversation.abandon()


@topic(key="cart_review", order=1, next="delivery_method")
class CartReviewTopic(AbstractTopic):
    def do_play(self, facts):
        self.ask(Question.choice("Have you reviewed your cart?", [Option(1, "Yes"), Option(2, "Not Yet")]))

    def on_input(self, answer):
        self.conversation.facts.put("cart_reviewed", True)
        self.conversation.facts.put("proceed_to_checkout", answer.get_value() == 1)
        if answer.get_value() == 1:
            self.close()


@topic(key="delivery_method", order=2, next="shipping_address")
class DeliveryMethodTopic(AbstractTopic):
    def do_play(self, facts):
        self.ask(Question.choice("Choose delivery", [Option(1, "PICKUP"), Option(2, "HOME_DELIVERY")]))

    def on_input(self, answer):
        self.conversation.facts.put("delivery_method", answer.get_text())
        self.close()


@topic(key="shipping_address", order=3, next="payment_method")
class ShippingAddressTopic(AbstractTopic):
    def do_play(self, facts):
        self.ask(Question.text_input("What is your shipping address?"))

    def on_input(self, answer):
        self.conversation.facts.put("shipping_address", answer.get_text())
        self.close()


@topic(key="payment_method", order=4, next="complete_sale")
class PaymentMethodTopic(AbstractTopic):
    def do_play(self, facts):
        self.ask(Question.choice("Choose payment", [Option(1, "CARD"), Option(2, "MOBILE_MONEY")]))

    def on_input(self, answer):
        self.conversation.facts.put("payment_method", answer.get_text())
        self.close()


class StartCheckout(ConversationStartResolver):
    def resolve(self, request):
        if request.message.text.strip().lower() in ("start", "/start", "checkout"):
            request.conversation_type = CheckoutConversation
            return request
        return None


def main():
    registry = ConversationStartRegistry([StartCheckout()])
    bot = TalkativeBot(start_registry=registry,
                       output_channels=OutputChannelRegistry([ConsoleOutputChannel()]),
                       topic_scanner=TopicScanner([GreetingsTopic, CartReviewTopic,
                                                   DeliveryMethodTopic, ShippingAddressTopic,
                                                   PaymentMethodTopic]))
    address = ConversationAddress("console", "console-user", "console-session")
    print("Enter start to begin; Ctrl-D to exit.")
    while True:
        try:
            line = input("> ")
        except EOFError:
            break
        bot.handle(IncomingMessage(address, line))


if __name__ == "__main__":
    main()