import os
import asyncio
import sys
import argparse
import getpass
import logging
import time

import nio

logger = logging.getLogger("gordy")

from .bot import Bot, EventHandler


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

    password = os.getenv("GORDY_PASSWORD") or getpass.getpass("password?")

    if args.register:
        confirm_password = getpass.getpass("confirm password?")

        if confirm_password != password:
            logger.error("passwords do not match")
            return 1

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

    if args.register:
        logger.info("registering...")
        resp = await client.register(args.user, password)
        logger.info("registration response: %s", resp)

        if isinstance(resp, nio.RegistrationError):
            logger.error("error registering: ", resp.message)
            return 1

    logger.info("logging in as %s...", args.user)
    resp = await client.login(password)

    if isinstance(resp, nio.LoginError):
        logger.error("error logging in: ", resp.message)
        return 1

    logger.info("login response: %s", resp)

    if client.should_upload_keys:
        await client.keys_upload()

    logger.info("syncing...")

    await client.sync(full_state=True)

    joined_rooms = await client.joined_rooms()
    for room_id in joined_rooms.rooms:
        await bot.send_greeting_to_room(room_id)

    stop = asyncio.Event()

    while not stop.is_set():
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
    except Exception as e:
        logger.exception("An error occurred")
        rv = 1

    sys.exit(rv)
