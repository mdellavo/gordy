import abc
import os
import asyncio
import sys
import argparse
import getpass
import logging
from typing import Any
import random
import time

import nio
import requests

logger = logging.getLogger("gordy")

GREETINGS = [
    "hi", "high", "hello", "sirs", "pals", "buddies", "friends", "amigos",
    "compadres", "mates", "chums", "confidants", "brothers", "ÜŔ ŮŔ Æ Æ Æ",
    "good day", "sup playas",
]

COMMAND_PREFIX = "!"

class Bot:

    def __init__(self, client, command_prefix=COMMAND_PREFIX):
        self.client = client
        self.command_prefix = COMMAND_PREFIX

    async def process_event(self, room: nio.MatrixRoom, event: nio.Event) -> None:
        if isinstance(event, nio.RoomMessageText):
            await self.process_message(room, event)

    async def process_message(self, room: nio.MatrixRoom, event: nio.Event) -> None:
        if event.sender == self.client.user_id:
            return

        if event.body in GREETINGS:
            greet = random.choice(GREETINGS)
            await self.send_message_to_room(room.room_id, greet)

        if event.body.startswith(self.command_prefix):
            parts = event.body[1:].split()
            command_name = parts[0] if parts else None
            command_class = Command.get_command_class(command_name) if command_name else None
            if command_class:
                command = command_class(self)

                try:
                    await command.run(room, event)
                except Exception:
                    logger.exception("Error running command")

    async def send_message_to_room(self, room_id, message):

        content = {
            "msgtype": "m.text",
            "format": "org.matrix.custom.html",
            "body": message,
        }

        try:
            return await self.client.room_send(
                room_id,
                "m.room.message",
                content,
                ignore_unverified_devices=True,
            )
        except nio.SendRetryError:
            logger.exception("Unable to send message response to %s", room_id)


class Command(metaclass=abc.ABCMeta):

    COMMANDS = {}

    NAME = None

    def __init_subclass__(cls) -> None:
        cls.COMMANDS[cls.NAME] = cls

    @classmethod
    def get_command_class(cls, name):
        return cls.COMMANDS.get(name)

    def __init__(self, bot: Bot):
        self.bot = bot

    @abc.abstractmethod
    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):
        pass


class UrbanDictionaryCommand(Command):
    NAME = "ud"

    URL = "https://api.urbandictionary.com/v0/define"
    RANDOM_URL = "https://api.urbandictionary.com/v0/random"

    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):
        query = event.body[1:].split()[1:]
        if query:
            response = requests.get(self.URL, {"term": query})
        else:
            response = requests.get(self.RANDOM_URL)

        response.raise_for_status()

        json = response.json()
        entry = json["list"][0]
        definition = entry["definition"]
        word = entry["word"]
        msg = f"{word} - {definition}"

        await self.bot.send_message_to_room(room.room_id, msg)


class EventHandler:

    def __init__(self, client: nio.AsyncClient, bot: Bot):
        self.client = client
        self.bot = bot

    def on_to_device(self, event: nio.KeyVerificationEvent):
        logger.debug("on_to_device: %s", event)

    async def on_message(self, room: nio.MatrixRoom, event: nio.RoomMessageText) -> None:
        logger.debug("on_message: roon=%s / event=%s", room, event)

        await self.bot.process_event(room, event)

    async def on_invite(self, room: nio.MatrixRoom, event: nio.InviteMemberEvent) -> None:

        if event.state_key != self.client.user_id:
            return

        logger.debug("on_invite: roon=%s / event=%s", room, event)

        result = await self.client.join(room.room_id)
        if isinstance(result, nio.JoinError):
            logger.error("Error joining %s: %s", room.room_id, result)
            return

        logger.info("Joined %s", room.room_id)

    async def on_decryption_failure(self, room: nio.MatrixRoom, event: nio.MegolmEvent):
        logger.debug("on_decryption_failure: roon=%s / event=%s", room, event)

    async def on_unknown(self, room: nio.MatrixRoom, event: nio.UnknownEvent):
        logger.debug("on_unknown: roon=%s / event=%s", room, event)


async def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format='[%(asctime)s] %(levelname)s/%(name)s - %(message)s',
    )

    for logger_name in ["peewee", "requests"]:
        logging.getLogger(logger_name).setLevel(logging.ERROR)


    parser = argparse.ArgumentParser(description='gordy')
    parser.add_argument("--homeserver", required=True, help="homeserver to connect to")
    parser.add_argument("--user", required=True, help="user to login as")
    parser.add_argument("--register", help="register new user", action="store_true")
    args = parser.parse_args()

    logger.info("connecting to %s...", args.homeserver)

    password = getpass.getpass("password?")

    if args.register:
        confirm_password = getpass.getpass("confirm password?")

    store_path = os.path.join("data", "store")
    if not os.path.exists(store_path):
        os.makedirs(store_path, exist_ok=True)

    client_config = nio.AsyncClientConfig(
        max_limit_exceeded=0,
        max_timeouts=0,
        store_sync_tokens=True,
        encryption_enabled=True,
    )
    client = nio.AsyncClient(
        args.homeserver,
        user=args.user,
        config=client_config,
        store_path=store_path,
    )

    bot = Bot(client)
    handler = EventHandler(client, bot)

    client.add_to_device_callback(handler.on_to_device, (nio.KeyVerificationEvent,))
    client.add_event_callback(handler.on_message, (nio.RoomMessageText,))
    client.add_event_callback(handler.on_invite, (nio.InviteMemberEvent,))
    client.add_event_callback(handler.on_decryption_failure, (nio.MegolmEvent,))
    client.add_event_callback(handler.on_unknown, (nio.UnknownEvent,))

    logger.info("registering...")
    resp = await client.register(args.user, password)
    print(resp)  # FIXME

    logger.info("logging in as %s...", args.user)
    resp = await client.login(password)
    print(resp)  # FIXME

    if client.should_upload_keys:
        await client.keys_upload()

    logger.info("syncing...")

    await client.sync(full_state=True)

    joined_rooms = await client.joined_rooms()
    for room_id in joined_rooms.rooms:
        greet = random.choice(GREETINGS)
        await bot.send_message_to_room(room_id, greet)

    running = True
    while running:
        try:
            await client.sync_forever(30_000)
        except asyncio.exceptions.TimeoutError:
            logger.warning("Unable to connect to homeserver, retrying in 15s...")
            time.sleep(5)
        finally:
            await client.close()

    return 0


if __name__ == "__main__":

    try:
        rv = asyncio.run(main())
    except KeyboardInterrupt:
        rv = 0
    except Exception as e:
        logger.exception("An error occurred")
        rv = 1

    sys.exit(rv)
