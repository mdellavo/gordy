import abc
import random
from io import StringIO

from .bot import Bot

import nio
import aiohttp
from lxml import etree
from imdb import Cinemagoer


class Command(metaclass=abc.ABCMeta):

    COMMANDS = {}

    NAME = None

    def __init_subclass__(cls) -> None:
        if cls.NAME:
            cls.COMMANDS[cls.NAME] = cls

    @classmethod
    def get_command_class(cls, name):
        return cls.COMMANDS.get(name)

    def __init__(self, bot: Bot):
        self.bot = bot

    @abc.abstractmethod
    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):
        pass


class HelpCommand(Command):
    """
    Print help
    """

    NAME = "help"

    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):
        parts = []

        for command_name, command in self.COMMANDS.items():
            line = f"{command_name} - {command.__doc__.strip()}"
            parts.append(line)

        msg = "<pre>" + "\n".join(parts) + "</pre>"
        await self.bot.send_message_to_room(room.room_id, msg)


class RandomCommand(Command):
    """
    Pick a random choice
    """

    NAME = "random"

    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):
        choices = event.body[1:].split()[1:]
        choice = random.choice(choices)
        await self.bot.send_message_to_room(room.room_id, choice)


class UrbanDictionaryCommand(Command):
    """
    Search UrbanDictionary
    """

    NAME = "ud"

    URL = "https://api.urbandictionary.com/v0/define"
    RANDOM_URL = "https://api.urbandictionary.com/v0/random"

    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):

        await self.bot.send_typing(room.room_id)

        query = event.body[1:].split()[1:]

        async with aiohttp.ClientSession() as session:
            if query:
                url = self.URL
                query_params = {"term": " ".join(query)}
            else:
                url = self.RANDOM_URL
                query_params = None

            async with session.get(url, params=query_params) as response:
                json = await response.json()

        if not json.get("list", []):
            return

        entry = json["list"][0]
        definition = entry["definition"]
        word = entry["word"]
        msg = f"<blockquote><strong>{word}</strong> - {definition}</blockquote>"

        await self.bot.send_message_to_room(room.room_id, msg)


class PPCommand(Command):
    """
    A celebrations of pp's
    """

    NAME = "pp"

    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):

        sack = "_" * random.randint(1, 5)
        balls = "(" + sack + ")"
        rod = "=" * random.randint(1, 10)
        hand = random.randint(1, 10)
        shaft = rod[:hand] + "✊" + rod[hand:]
        head = "D"
        skeet = "💦" * random.randint(1, 5)
        pp = balls + shaft + head + skeet

        msg = "<pre>" + pp + "</per>"

        await self.bot.send_message_to_room(room.room_id, msg)


class IMDBCommand(Command):
    """Search IMDB"""

    NAME = "imdb"

    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):

        await self.bot.send_typing(room.room_id)

        cg = Cinemagoer()

        query = " ".join(event.body[1:].split()[1:])
        movies = cg.search_movie(query)
        movie = movies[0]

        title = movie["long imdb title"]
        cover = movie["full-size cover url"]
        url = "https://www.imdb.com/title/tt{}/".format(movie.getID())

        parts = [
            "<p>",
            title,
            f"&nbsp;<a href=\"{cover}\">cover</a>",
            f"&nbsp;<a href=\"{url}\">url</a>",
            "</p>",
        ]

        msg = "".join(parts)
        await self.bot.send_message_to_room(room.room_id, msg)


def dump_node(node):
    result = etree.tostring(node,
                            pretty_print=True, method="html")
    print(result.decode("utf8"))


class StrainCommand(Command):
    """Search Leafly"""

    NAME = "strain"

    URL = "https://www.leafly.com/strains/"

    NAMESPACES = {
        "og": "https://ogp.me/ns#"
    }

    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):
        await self.bot.send_typing(room.room_id)

        async with aiohttp.ClientSession() as session:

            query = event.body[1:].split()[1:]
            url = self.URL + "/" + "-".join(query)

            async with session.get(url) as response:
                html = await response.text()

        parser = etree.HTMLParser()
        tree = etree.parse(StringIO(html), parser)
        head = tree.xpath('/html/head')[0]

        def og_node(name):
            nodes = head.xpath(f'meta[@property="og:{name}"]/@content', namespaces=self.NAMESPACES)
            return nodes[0] if nodes else None

        description = og_node("description")
        title = og_node("title").replace("Weed Strain Information | Leafly", "")
        image = og_node("image")
        url = og_node("url")

        if not description:
            return

        parts = [
            "<p>",
            title, " - ", description,
            f"&nbsp;<a href=\"{image}\">image</a>",
            f"&nbsp;<a href=\"{url}\">url</a>",
            "</p>",
        ]
        msg = "".join(parts)
        await self.bot.send_message_to_room(room.room_id, msg)
