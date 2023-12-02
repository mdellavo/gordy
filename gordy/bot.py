import asyncio
import collections
import random
import logging
import time
from typing import IO
from contextlib import contextmanager

import nio

logger = logging.getLogger("gordy")


GREETINGS = [
    "hi", "high", "hello", "sirs", "pals", "buddies", "friends", "amigos",
    "compadres", "mates", "chums", "confidants", "brothers", "ÜŔ ŮŔ Æ Æ Æ",
    "good day", "waddup", "howdy", "whats good fam"
]

COMMAND_PREFIX = "!"
GREETING_TIMEOUT = 5 * 60


class Timer:
    def __init__(self):
        self.time_start = None
        self.time_stop = None

    def start(self):
        self.time_start = time.perf_counter_ns()

    def stop(self):
        self.time_stop = time.perf_counter_ns()

    @property
    def elapsed(self):
        if not (self.time_start and self.time_stop):
            return None

        return (self.time_stop - self.time_start) / 1_000_000


@contextmanager
def timed():
    timer = Timer()
    timer.start()

    yield timer

    timer.stop()


class Bot:

    def __init__(self, client, command_prefix=COMMAND_PREFIX):
        self.client = client
        self.command_prefix = command_prefix
        self.state = {}
        self.last_greeting = {}
        self.state = collections.defaultdict(dict)

    async def process_event(self, room: nio.MatrixRoom, event: nio.Event) -> None:
        if isinstance(event, nio.RoomMessageText):
            await self.process_message(room, event)

    async def process_message(self, room: nio.MatrixRoom, event: nio.Event) -> None:
        if event.sender == self.client.user_id:
            return

        is_greeting = event.body.strip() in GREETINGS
        if is_greeting:
            await self.send_greeting_to_room(room.room_id)

        if event.body.startswith(self.command_prefix):
            parts = event.body[1:].split()
            command_name = parts[0] if parts else None
            if command_name:
                try:
                    await run_command(command_name, self, room, event)
                except asyncio.TimeoutError:
                    logger.error("command %s timed out: %s", command_name, parts)

    async def send_typing(self, room_id: str, state=True, timeout=10_000):
        await self.client.room_typing(room_id, typing_state=state, timeout=timeout)

    async def send_message_to_room(self, room_id: str, message: str):

        content = {
            "msgtype": "m.text",
            "format": "org.matrix.custom.html",
            "body": message,
            "formatted_body": message,
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

    async def send_greeting_to_room(self, room_id: str):

        now = time.time()
        last_greeting = self.last_greeting.get(room_id, 0)

        delta = now - last_greeting
        if delta > GREETING_TIMEOUT:
            greet = random.choice(GREETINGS)
            await self.send_message_to_room(room_id, greet)
            self.last_greeting[room_id] = now

    async def send_image_to_room(self, room_id: str, f: IO[bytes], content_type: str, filename: str, size: int, width: int, height: int):
        resp, maybe_keys = await self.client.upload(
            f,
            content_type=content_type,
            filename=filename,
            filesize=size
        )

        if isinstance(resp, nio.UploadResponse):
            print("Image was uploaded successfully to server. ")
        else:
            print(f"Failed to upload image. Failure response: {resp}")

        content = {
            "body": filename,  # descriptive title
            "info": {
                "size": size,
                "mimetype": content_type,
                "thumbnail_info": None,
                "w": width,
                "h": height,
                "thumbnail_url": None,
            },
            "msgtype": "m.image",
            "url": resp.content_uri,
        }

        try:
            await self.client.room_send(room_id, message_type="m.room.message", content=content, ignore_unverified_devices=True)
            print("Image was sent successfully")
        except Exception as e:
            print(f"Image send of file {filename} failed: {e}")



async def run_command(command_name: str, bot: Bot, room: nio.MatrixRoom, event: nio.Event):
    from .commands import Command

    if not command_name:
        return

    command_class = Command.get_command_class(command_name)

    if not command_class:
        return

    command = command_class(bot)

    with timed() as timer:
        try:
            await command.run(room, event)
        except Exception:
            logger.exception("Error running command")

    logger.info("command %s took %.02fms", command_name, timer.elapsed)


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
