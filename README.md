# TalkativeBot for Python

A Python conversation-state engine inspired by the Java project [kelvin-bonni/talkativebot](https://github.com/kelvin-bonni/talkativebot). It routes incoming messages, starts or resumes conversations, asks text or single-choice questions, and stores pending interactions so a conversation can continue when a reply arrives.

TalkativeBot is not a workflow/BPMN engine, chatbot platform, or AI framework. Conversation logic is kept separate from transport and can be connected to your own channels and services.

## Features

- Conversation and topic abstractions with explicit next-topic links and order-based fallback.
- Start resolvers, message routing modes, and conversation scopes.
- Choice selection by option value or case-insensitive option label; text answers are also supported.
- Pending-interaction persistence through in-memory, SQLite, or a supplied Redis-compatible client.
- Console input/output adapters and a checkout conversation example.
- Replaceable routing, start resolution, storage, and output-channel components.

## Requirements

- Python 3.7 or newer.
- No third-party runtime dependencies for the core package.
- The Redis adapter requires a Redis client compatible with the `redis-py` client API, provided by the application.

## Run the example

From the project root, run:

```sh
python -m examples.checkout
```

Type `start`, `checkout`, or `/start` to begin the sample checkout. Answer each prompt with the displayed option number or label; enter an address for the free-text prompt. Use Ctrl-D to exit.

## Run tests

```sh
python -m unittest discover -s tests -v
```

## Basic usage

Implement a conversation by subclassing `AbstractConversation`, and implement topics by subclassing `AbstractTopic`. Mark topic classes with `@topic(...)`. A topic implements `do_play(facts)` to ask a question or perform an action, then `on_input(answer)` to process the reply. Register topic classes explicitly through `TopicScanner`; the Python port does not automatically scan application packages.

Configure a `ConversationStartResolver` to associate an incoming message with a conversation class, and register an `OutputChannel` for the corresponding `ConversationAddress.channel`. Then construct `TalkativeBot` with a `ConversationStartRegistry`, `OutputChannelRegistry`, and `TopicScanner`. The runnable [checkout example](examples/checkout.py) demonstrates this wiring.

`TalkativeBot.handle(IncomingMessage(...))` resumes a matching pending interaction before trying to start a conversation by default. `ConversationRouteMode` can change this behavior to resume-only, start-only, or reject. Start resolvers are ordered by their `order` attribute; unscoped resolvers apply only to the default scope.

The bot saves a pending question before sending it. Invalid choice input raises `ValueError` and leaves the pending interaction intact. The in-memory store is the default; use `SQLitePendingInteractionStore` for local durable storage or `RedisPendingInteractionStore(client)` with a compatible client for Redis. Both scoped keys and optional TTLs are supported by the built-in stores.

## Scope and limitations

This is a port of the framework-independent conversation concepts, not a feature-complete Python equivalent of every original Java module. Spring Boot auto-configuration, JPA persistence, Spring Cloud Stream integration, REST/third-party chat adapters, and multiple-choice/custom question types are not included. SQLite and Redis are standalone Python implementations and do not share data formats with the Java stores. Add adapters by implementing the storage or channel interfaces used by the package.