from typing import Optional, Dict, Type

import abc
import random
from io import StringIO, BytesIO

from .bot import Bot

import nio
import aiohttp
from lxml import etree
from imdb import Cinemagoer

from . import pp


class Command(metaclass=abc.ABCMeta):
    """

    Base class for commands.

    """

    NAME: Optional[str] = None

    def __init_subclass__(cls) -> None:
        if cls.NAME:
            COMMANDS[cls.NAME] = cls

    @classmethod
    def get_command_class(cls, name):
        return COMMANDS.get(name)

    def __init__(self, bot: Bot):
        self.bot = bot

    @abc.abstractmethod
    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):
        pass

    @property
    def state(self):
        return self.bot.state[self.NAME]


COMMANDS: Dict[str, Type[Command]] = {}


class HelpCommand(Command):
    """
    Print help
    """

    NAME = "help"

    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):
        parts = []

        for command_name, command in COMMANDS.items():
            doc_str = (command.__doc__ or "").strip()

            line = f"{command_name} - {doc_str}"
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
    """A celebration of pp's."""

    NAME = "pp"

    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):
        f = BytesIO()
        images = pp.generate_pp(f)
        duration = [pp.PER_FRAME_DURATION for _ in images]
        duration[-1] = pp.END_FRAME_DURATION
        images[0].save(
            f, format="GIF", append_images=images[1:], save_all=True, duration=duration, loop=0, disposal=2
        )
        width, height = images[0].size
        size = f.tell()
        f.seek(0)

        await self.bot.send_image_to_room(room.room_id, f, "image/gif", "pp.gif", size, width, height)


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

    SEARCH_API = "https://consumer-api.leafly.com/api/search/v1"
    STRAIN_URL_PREFIX = "https://www.leafly.com/strains/"

    def split_akas(self, subtitle):
        return subtitle.lstrip("aka ").split(", ")

    def match(self, strain, query):
        name = strain.get("name") or ""
        subtitle = strain.get("subtitle") or ""

        names = [name] + self.split_akas(subtitle)
        for name in names:
            if name.lower() == query.lower():
                return True

        return False

    async def run(self, room: nio.MatrixRoom, event: nio.RoomMessageText):
        await self.bot.send_typing(room.room_id)

        query = " ".join(event.body[1:].split()[1:])
        params = {
            "q": query,
            "filter[all_strains]": "true",
            "skip": 0,
            "skip_aggs": "true",
            "take": 5,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(self.SEARCH_API, params=params) as response:
                json = await response.json()

        hits = json.get("hits", {})
        strains = hits.get("strain", [])

        matched = None
        for strain in strains:
            if self.match(strain, query):
                matched = strain

        if not matched:
            return

        name = matched.get("name") or ""
        subtitle = matched.get("subtitle") or ""
        slug = matched.get("slug") or ""
        url = self.STRAIN_URL_PREFIX + slug

        phenotype = matched.get("phenotype") or ""
        description = matched.get("shortDescriptionPlain") or ""
        image = matched.get("nugImage") or ""

        parts = [
            "<p>",
            f"<strong>{name}</strong> <em>{subtitle}</em><br>",
            f"({phenotype}) {description}<br>",
            f"<a href=\"{image}\">image</a> ",
            f"<a href=\"{url}\">url</a>",
            "</p>",
        ]
        msg = "".join(parts)
        await self.bot.send_message_to_room(room.room_id, msg)
