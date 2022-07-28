import random
import logging

import nio

logger = logging.getLogger("gordy")


GREETINGS = [
    "hi", "high", "hello", "sirs", "pals", "buddies", "friends", "amigos",
    "compadres", "mates", "chums", "confidants", "brothers", "ÜŔ ŮŔ Æ Æ Æ",
    "good day", "sup playas",
]

COMMAND_PREFIX = "!"


def get_command_class(name):
    from .commands import Command
    return Command.get_command_class(name) if name else None


class Bot:

    def __init__(self, client, command_prefix=COMMAND_PREFIX):
        self.client = client
        self.command_prefix = COMMAND_PREFIX
        self.state = {}

    async def process_event(self, room: nio.MatrixRoom, event: nio.Event) -> None:
        if isinstance(event, nio.RoomMessageText):
            await self.process_message(room, event)

    async def process_message(self, room: nio.MatrixRoom, event: nio.Event) -> None:
        if event.sender == self.client.user_id:
            return

        if event.body in GREETINGS:
            await self.send_greeting_to_room(room.room_id)

        if event.body.startswith(self.command_prefix):
            parts = event.body[1:].split()
            command_name = parts[0] if parts else None
            command_class = get_command_class(command_name)
            if command_class:
                command = command_class(self)

                try:
                    await command.run(room, event)
                except Exception:
                    logger.exception("Error running command")

    async def send_message_to_room(self, room_id: str, message: str):

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

    async def send_greeting_to_room(self, room_id: str):
        greet = random.choice(GREETINGS)
        await self.send_message_to_room(room_id, greet)


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
