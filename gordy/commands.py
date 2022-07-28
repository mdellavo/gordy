import abc

from .bot import Bot

import nio
import requests


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
