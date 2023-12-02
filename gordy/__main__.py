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

    parser = argparse.ArgumentParser(description='gordy')
    parser.add_argument("--debug", action="store_true", help="enable debug logging")
    parser.add_argument("--homeserver", required=True, help="homeserver to connect to")
    parser.add_argument("--user", required=True, help="user to login as")
    parser.add_argument("--register", help="register new user", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='[%(asctime)s] %(levelname)s/%(name)s - %(message)s',
    )

    for logger_name in ["peewee", "requests", "urllib3.connectionpool"]:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    logger.info("connecting to %s...", args.homeserver)

    password = os.getenv("GORDY_PASSWORD") or getpass.getpass("password?")

    if args.register:
        confirm_password = getpass.getpass("confirm password?")

        if confirm_password != password:
            logger.error("passwords do not match")
            return 1

    store_path = os.path.join(os.getenv("HOME", "/"), ".gordy")
    if not os.path.exists(store_path):
        os.makedirs(store_path, exist_ok=True)

    client_config = nio.AsyncClientConfig(
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

        if not isinstance(resp, nio.RegisterResponse):
            logger.error("error registering: %s", resp.message)
            await client.close()
            return 1
        logger.info("registered: %s", resp)

    logger.info("logging in as %s...", args.user)
    resp = await client.login(password)

    if isinstance(resp, nio.LoginError):
        logger.error("error logging in: %s", resp.message)
        await client.close()
        return 1

    logger.info("login response: %s", resp)

    if client.should_upload_keys:
        await client.keys_upload()

    stop = asyncio.Event()

    async def after_first_sync():
        await client.synced.wait()

        trusted_users = set()
        trusted = {}
        for room in client.rooms.values():
            for user_id in room.users.keys():
                trusted_users.add(user_id)
                for device_id, olm_device in client.device_store[user_id].items():
                    trusted = {device_id: olm_device}

        for device in trusted.values():
            client.verify_device(device)

        print("Trusted users:", trusted_users)

    async def sync_forever():
        while not stop.is_set():
            try:
                logger.info("syncing...")
                await client.sync_forever(30_000, full_state=True)
            except asyncio.exceptions.TimeoutError:
                logger.warning("Unable to connect to homeserver, retrying in 5s...")
                time.sleep(5)
            finally:
                await client.close()

    after_first_sync_task = asyncio.ensure_future(after_first_sync())
    sync_forever_task = asyncio.ensure_future(sync_forever())

    await asyncio.gather(
        # The order here IS significant! You have to register the task to trust
        # devices FIRST since it awaits the first sync
        after_first_sync_task,
        sync_forever_task,
    )

    return 0


if __name__ == "__main__":

    try:
        rv = asyncio.run(main())
    except Exception as e:
        logger.exception("An error occurred")
        rv = 1

    sys.exit(rv)
