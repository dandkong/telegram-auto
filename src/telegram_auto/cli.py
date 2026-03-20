import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from telethon import TelegramClient

DEFAULT_DOWNLOAD_DIR = "."
DEFAULT_SESSION = "telegram-auto-session"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def emit_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def compact(value: object) -> object:
    if isinstance(value, dict):
        result: dict[object, object] = {}
        for key, item in value.items():
            compacted = compact(item)
            if compacted is None:
                continue
            if isinstance(compacted, (list, dict)) and not compacted:
                continue
            result[key] = compacted
        return result

    if isinstance(value, list):
        result = [compact(item) for item in value]
        return [
            item
            for item in result
            if item is not None and not (isinstance(item, (list, dict)) and not item)
        ]

    return value


def ok(
    command: str, data: object, account: dict[str, object] | None = None
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": True,
        "command": command,
        "data": data,
    }
    if account is not None:
        payload["account"] = account
    return compact(payload)


def fail(exc: Exception) -> dict[str, object]:
    return compact(
        {
            "ok": False,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
    )


def load_local_env() -> None:
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {name}")
    return value.strip()


def load_proxy_from_env() -> tuple[str, str, int] | None:
    for env_name in ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        value = os.environ.get(env_name)
        if not value:
            continue

        parsed = urlparse(value)
        if not parsed.scheme or not parsed.hostname or not parsed.port:
            raise ValueError(
                f"Invalid proxy URL in {env_name}: expected scheme://host:port"
            )

        scheme = parsed.scheme.lower()
        if scheme.startswith("socks5"):
            proxy_type = "socks5"
        elif scheme.startswith("http"):
            proxy_type = "http"
        else:
            raise ValueError(f"Unsupported proxy scheme in {env_name}: {parsed.scheme}")

        return (proxy_type, parsed.hostname, parsed.port)

    return None


def load_session_name() -> str:
    load_local_env()
    return os.environ.get("TG_SESSION", DEFAULT_SESSION).strip() or DEFAULT_SESSION


def load_api_credentials() -> tuple[int, str]:
    load_local_env()
    api_id = int(require_env("TG_API_ID"))
    api_hash = require_env("TG_API_HASH")
    return api_id, api_hash


def load_credentials() -> tuple[int, str, str]:
    api_id, api_hash = load_api_credentials()
    session = load_session_name()
    return api_id, api_hash, session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telegram-auto",
        description="Telegram automation CLI with JSON-first output.",
    )
    resources = parser.add_subparsers(dest="resource", required=True)

    auth = resources.add_parser("auth", help="Authentication commands")
    auth_sub = auth.add_subparsers(dest="action", required=True)
    auth_sub.add_parser("login", help="Login interactively and persist session")
    auth_sub.add_parser("logout", help="Logout and invalidate the current session")
    auth_sub.add_parser(
        "status", help="Check whether the current session is authorized"
    )

    dialogs = resources.add_parser("dialogs", help="Dialog discovery commands")
    dialogs_sub = dialogs.add_subparsers(dest="action", required=True)
    dialogs_list = dialogs_sub.add_parser("list", help="List recent dialogs")
    dialogs_list.add_argument("--limit", type=int, default=20)

    messages = resources.add_parser("messages", help="Message commands")
    messages_sub = messages.add_subparsers(dest="action", required=True)
    messages_list = messages_sub.add_parser("list", help="List recent messages")
    messages_list.add_argument("--chat", required=True)
    messages_list.add_argument("--limit", type=int, default=5)
    messages_list.add_argument("--offset-id", type=int, default=0)
    messages_list.add_argument(
        "--reverse",
        action="store_true",
        help="Return messages from older to newer",
    )
    messages_list.add_argument("--reply-to", type=int)

    messages_search = messages_sub.add_parser("search", help="Search messages")
    messages_search.add_argument("--chat")
    messages_search.add_argument("--query", required=True)
    messages_search.add_argument("--limit", type=int, default=20)

    messages_send = messages_sub.add_parser("send", help="Send a new message")
    messages_send.add_argument("--chat", required=True)
    messages_send.add_argument("--text", required=True)

    messages_reply = messages_sub.add_parser("reply", help="Reply with text")
    messages_reply.add_argument("--chat", required=True)
    messages_reply.add_argument("--message-id", required=True, type=int)
    messages_reply.add_argument("--text", required=True)

    messages_send_file = messages_sub.add_parser(
        "send-file", help="Send a local file to a chat"
    )
    messages_send_file.add_argument("--chat", required=True)
    messages_send_file.add_argument("--path", required=True)
    messages_send_file.add_argument("--caption", default="")

    messages_forward = messages_sub.add_parser(
        "forward", help="Forward a message to a chat"
    )
    messages_forward.add_argument("--chat", required=True)
    messages_forward.add_argument("--from-chat", required=True)
    messages_forward.add_argument("--message-id", required=True, type=int)

    buttons = resources.add_parser("buttons", help="Button interaction commands")
    buttons_sub = buttons.add_subparsers(dest="action", required=True)
    buttons_click = buttons_sub.add_parser("click", help="Click a message button")
    buttons_click.add_argument("--chat", required=True)
    buttons_click.add_argument("--message-id", required=True, type=int)
    buttons_click.add_argument("--text", required=True, help="Button text")

    media = resources.add_parser("media", help="Media commands")
    media_sub = media.add_subparsers(dest="action", required=True)
    media_download = media_sub.add_parser("download", help="Download message media")
    media_download.add_argument("--chat", required=True)
    media_download.add_argument("--message-id", required=True, type=int)
    media_download.add_argument("--out", default=DEFAULT_DOWNLOAD_DIR)

    return parser


def serialize_entity(entity: object | None) -> dict[str, object] | None:
    if entity is None:
        return None

    username = getattr(entity, "username", None)
    first_name = getattr(entity, "first_name", None)
    last_name = getattr(entity, "last_name", None)
    title = getattr(entity, "title", None)
    name = (
        title
        or " ".join(part for part in (first_name, last_name) if part).strip()
        or username
    )

    return compact(
        {
            "id": getattr(entity, "id", None),
            "username": username,
            "name": name or None,
            "type": type(entity).__name__,
        }
    )


def infer_message_kind(message: object) -> str:
    if getattr(message, "action", None):
        return "service"
    if getattr(message, "poll", None):
        return "poll"
    if getattr(message, "geo", None):
        return "location"
    if getattr(message, "contact", None):
        return "contact"
    if getattr(message, "dice", None):
        return "dice"
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "video_note", None):
        return "video_note"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "gif", None):
        return "gif"
    if getattr(message, "sticker", None):
        return "sticker"
    if getattr(message, "audio", None):
        return "audio"
    if getattr(message, "document", None):
        return "document"
    if getattr(message, "media", None):
        return "media"
    if getattr(message, "raw_text", None):
        return "text"
    return "unknown"


def serialize_media(message: object) -> dict[str, object] | None:
    if not getattr(message, "media", None):
        return None

    file = getattr(message, "file", None)
    return compact(
        {
            "kind": infer_message_kind(message),
            "file_name": getattr(file, "name", None),
            "mime_type": getattr(file, "mime_type", None),
            "size": getattr(file, "size", None),
            "width": getattr(file, "width", None),
            "height": getattr(file, "height", None),
            "duration": getattr(file, "duration", None),
        }
    )


def serialize_buttons(message: object) -> list[dict[str, object]]:
    rows = getattr(message, "buttons", None) or []
    items: list[dict[str, object]] = []

    for row in rows:
        for button in row:
            raw_button = getattr(button, "button", button)
            payload = getattr(raw_button, "data", None)
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8", errors="replace")

            items.append(
                {
                    "text": getattr(button, "text", None)
                    or getattr(raw_button, "text", None),
                    "url": getattr(raw_button, "url", None),
                    "data": payload,
                }
            )

    compacted = compact(items)
    return compacted if isinstance(compacted, list) else []


def serialize_forward(message: object) -> dict[str, object] | None:
    forward = getattr(message, "forward", None)
    if forward is None:
        return None

    from_id = getattr(forward, "from_id", None)
    from_name = getattr(forward, "from_name", None)
    return compact(
        {
            "from_id": str(from_id) if from_id is not None else None,
            "from_name": from_name,
            "date": forward.date.isoformat()
            if getattr(forward, "date", None)
            else None,
        }
    )


def serialize_reactions(message: object) -> list[dict[str, object]] | None:
    reactions = getattr(message, "reactions", None)
    if reactions is None:
        return None

    result: list[dict[str, object]] = []
    for count in reactions.results:
        reaction_dict: dict[str, object] = {"count": getattr(count, "count", 0)}

        # Get reaction emoji/document
        reaction = getattr(count, "reaction", None)
        if reaction is None:
            continue

        # Custom emoji reaction
        if document_id := getattr(reaction, "document_id", None):
            reaction_dict["custom_emoji_id"] = document_id
        # Regular emoji reaction
        elif emoticon := getattr(reaction, "emoticon", None):
            reaction_dict["emoji"] = emoticon

        # Get recent reactors (user IDs who reacted)
        recent_reactors = getattr(count, "recent_reactors", None)
        if recent_reactors:
            reaction_dict["recent_reactors"] = [
                str(user_id) for user_id in recent_reactors
            ]

        result.append(compact(reaction_dict))

    return result if result else None


def serialize_message(
    message: object, chat: str | None = None, sender: object | None = None
) -> dict[str, object]:
    date = getattr(message, "date", None)
    return compact(
        {
            "id": getattr(message, "id", None),
            "chat": chat,
            "date": date.isoformat() if date else None,
            "sender": serialize_entity(sender or getattr(message, "sender", None)),
            "text": getattr(message, "text", None),
            "kind": infer_message_kind(message),
            "media": serialize_media(message),
            "grouped_id": getattr(message, "grouped_id", None),
            "reply_to_message_id": getattr(message, "reply_to_msg_id", None),
            "forward": serialize_forward(message),
            "buttons": serialize_buttons(message),
            "reactions": serialize_reactions(message),
        }
    )


def serialize_dialog(dialog: object) -> dict[str, object]:
    entity = getattr(dialog, "entity", None)
    username = getattr(entity, "username", None)
    return compact(
        {
            "id": getattr(entity, "id", None),
            "name": getattr(dialog, "name", None),
            "handle": f"@{username}" if username else None,
            "type": type(entity).__name__ if entity is not None else None,
            "unread_count": getattr(dialog, "unread_count", None),
            "pinned": bool(getattr(dialog, "pinned", False)),
        }
    )


def serialize_click_result(result: object) -> dict[str, object]:
    if result is None:
        return {"kind": "none"}
    if isinstance(result, bool):
        return {"kind": "bool", "value": result}
    if isinstance(result, (str, int, float)):
        return {"kind": type(result).__name__, "value": result}
    return compact({"kind": type(result).__name__})


def build_client(api_id: int, api_hash: str, session: str) -> TelegramClient:
    proxy = load_proxy_from_env()
    client_kwargs = {"proxy": proxy} if proxy else {}
    return TelegramClient(session, api_id, api_hash, **client_kwargs)


def get_session_file_paths(session: str) -> list[Path]:
    session_file = Path(f"{session}.session").resolve()
    return [session_file, session_file.with_name(f"{session}.session-journal")]


async def require_authorized(client: TelegramClient) -> None:
    if not await client.is_user_authorized():
        raise RuntimeError(
            "Session is not authorized. Run 'telegram-auto auth login' first."
        )


async def auth_status(client: TelegramClient, session: str) -> dict[str, object]:
    session_paths = get_session_file_paths(session)
    session_file = session_paths[0]
    session_exists = session_file.exists()
    if not session_exists:
        return {
            "authorized": False,
            "session": session,
            "session_file": str(session_file),
            "session_file_exists": False,
            "interactive_required": True,
            "recommended_command": "telegram-auto auth login",
            "account": None,
        }

    authorized = await client.is_user_authorized()
    me = await client.get_me() if authorized else None
    return {
        "authorized": authorized,
        "session": session,
        "session_file": str(session_file),
        "session_file_exists": True,
        "interactive_required": not authorized,
        "recommended_command": None if authorized else "telegram-auto auth login",
        "account": serialize_entity(me),
    }


async def auth_login(
    client: TelegramClient, session: str
) -> tuple[dict[str, object], dict[str, object]]:
    if await client.is_user_authorized():
        me = await client.get_me()
        account = serialize_entity(me)
        return (
            {
                "authorized": True,
                "already_authorized": True,
                "session": session,
                "session_file": str(Path(f"{session}.session").resolve()),
                "interactive_required": False,
            },
            account or {},
        )

    await client.start()
    me = await client.get_me()
    account = serialize_entity(me)
    return (
        {
            "authorized": True,
            "already_authorized": False,
            "session": session,
            "session_file": str(Path(f"{session}.session").resolve()),
            "interactive_required": True,
        },
        account or {},
    )


async def auth_logout(client: TelegramClient | None, session: str) -> dict[str, object]:
    remote_revoked = False
    remote_logout_error: dict[str, str] | None = None

    if client is not None:
        try:
            if await client.is_user_authorized():
                await client.log_out()
                remote_revoked = True
        except Exception as exc:
            remote_logout_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }

    deleted_files: list[str] = []
    session_file = None
    for path in get_session_file_paths(session):
        if session_file is None:
            session_file = path
        if path.exists():
            path.unlink()
            deleted_files.append(str(path))

    payload: dict[str, object] = {
        "session": session,
        "remote_revoked": remote_revoked,
        "local_cleared": remote_revoked or bool(deleted_files) or not session_file,
    }
    if remote_logout_error is not None:
        payload["error"] = remote_logout_error
    return payload


async def list_dialogs(client: TelegramClient, limit: int) -> dict[str, object]:
    dialogs: list[dict[str, object]] = []
    async for dialog in client.iter_dialogs(limit=limit):
        dialogs.append(serialize_dialog(dialog))
    return {"limit": limit, "dialogs": dialogs}


async def list_messages(
    client: TelegramClient,
    chat: str,
    limit: int,
    offset_id: int = 0,
    reverse: bool = False,
    reply_to: int | None = None,
) -> dict[str, object]:
    messages: list[dict[str, object]] = []
    iter_kwargs: dict[str, object] = {
        "limit": limit,
        "offset_id": offset_id,
        "reverse": reverse,
    }
    if reply_to is not None:
        iter_kwargs["reply_to"] = reply_to

    async for message in client.iter_messages(chat, **iter_kwargs):
        sender = await message.get_sender()
        messages.append(serialize_message(message, chat=chat, sender=sender))
    return {
        "chat": chat,
        "limit": limit,
        "offset_id": offset_id,
        "reverse": reverse,
        "reply_to": reply_to,
        "messages": messages,
    }


async def search_messages(
    client: TelegramClient,
    query: str,
    limit: int,
    chat: str | None = None,
) -> dict[str, object]:
    messages: list[dict[str, object]] = []
    async for message in client.iter_messages(chat, limit=limit, search=query):
        sender = await message.get_sender()
        messages.append(serialize_message(message, chat=chat, sender=sender))
    return {
        "chat": chat,
        "query": query,
        "limit": limit,
        "scope": "chat" if chat else "global",
        "messages": messages,
    }


async def send_message(
    client: TelegramClient, chat: str, text: str
) -> dict[str, object]:
    sent = await client.send_message(chat, text)
    sender = await sent.get_sender()
    return {
        "chat": chat,
        "message": serialize_message(sent, chat=chat, sender=sender),
    }


async def reply_message(
    client: TelegramClient, chat: str, message_id: int, text: str
) -> dict[str, object]:
    target = await client.get_messages(chat, ids=message_id)
    if not target:
        raise ValueError(f"Message {message_id} not found in chat '{chat}'")

    sent = await client.send_message(chat, text, reply_to=message_id)
    sender = await sent.get_sender()
    return {
        "chat": chat,
        "target_message_id": message_id,
        "message": serialize_message(sent, chat=chat, sender=sender),
    }


async def click_button(
    client: TelegramClient,
    chat: str,
    message_id: int,
    text: str,
) -> dict[str, object]:
    message = await client.get_messages(chat, ids=message_id)
    if not message:
        raise ValueError(f"Message {message_id} not found in chat '{chat}'")

    result = await message.click(text=text)
    button_selector = {"text": text}

    return {
        "chat": chat,
        "message_id": message_id,
        "button": button_selector,
        "result": serialize_click_result(result),
    }


async def download_media(
    client: TelegramClient, chat: str, message_id: int, out_dir: str
) -> dict[str, object]:
    message = await client.get_messages(chat, ids=message_id)
    if not message:
        raise ValueError(f"Message {message_id} not found in chat '{chat}'")
    if not message.media:
        raise ValueError(f"Message {message_id} has no media to download")

    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = await message.download_media(file=str(output_dir) + os.sep)
    if not downloaded:
        raise RuntimeError("Media download failed")

    sender = await message.get_sender()
    return {
        "chat": chat,
        "message_id": message_id,
        "path": downloaded,
        "message": serialize_message(message, chat=chat, sender=sender),
    }


async def send_file_to_chat(
    client: TelegramClient, chat: str, path: str, caption: str
) -> dict[str, object]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    sent = await client.send_file(chat, file=str(file_path), caption=caption)
    sender = await sent.get_sender()
    return {
        "chat": chat,
        "message": serialize_message(sent, chat=chat, sender=sender),
    }


async def forward_message(
    client: TelegramClient, chat: str, from_chat: str, message_id: int
) -> dict[str, object]:
    message = await client.get_messages(from_chat, ids=message_id)
    if not message:
        raise ValueError(f"Message {message_id} not found in chat '{from_chat}'")

    forwarded = await client.forward_messages(chat, message)
    sender = await forwarded.get_sender() if hasattr(forwarded, "get_sender") else None
    return {
        "chat": chat,
        "from_chat": from_chat,
        "from_message_id": message_id,
        "message": serialize_message(forwarded, chat=chat, sender=sender),
    }


async def run(args: argparse.Namespace) -> dict[str, object]:
    session = load_session_name()
    api_id, api_hash = load_api_credentials()
    if args.resource == "auth" and args.action == "status":
        session_file = get_session_file_paths(session)[0]
        if not session_file.exists():
            return ok(
                "auth.status",
                {
                    "authorized": False,
                    "session": session,
                    "session_file": str(session_file),
                    "session_file_exists": False,
                    "interactive_required": True,
                    "recommended_command": "telegram-auto auth login",
                    "account": None,
                },
            )

    client = build_client(api_id, api_hash, session)
    await client.connect()
    try:
        if args.resource == "auth" and args.action == "status":
            return ok("auth.status", await auth_status(client, session))

        if args.resource == "auth" and args.action == "login":
            data, account = await auth_login(client, session)
            return ok("auth.login", data, account)

        if args.resource == "auth" and args.action == "logout":
            return ok("auth.logout", await auth_logout(client, session))

        await require_authorized(client)
        me = await client.get_me()
        account = serialize_entity(me)

        if args.resource == "dialogs" and args.action == "list":
            return ok("dialogs.list", await list_dialogs(client, args.limit), account)

        if args.resource == "messages" and args.action == "list":
            return ok(
                "messages.list",
                await list_messages(
                    client,
                    args.chat,
                    args.limit,
                    args.offset_id,
                    args.reverse,
                    args.reply_to,
                ),
                account,
            )

        if args.resource == "messages" and args.action == "search":
            return ok(
                "messages.search",
                await search_messages(client, args.query, args.limit, args.chat),
                account,
            )

        if args.resource == "messages" and args.action == "send":
            return ok(
                "messages.send",
                await send_message(client, args.chat, args.text),
                account,
            )

        if args.resource == "messages" and args.action == "reply":
            return ok(
                "messages.reply",
                await reply_message(client, args.chat, args.message_id, args.text),
                account,
            )

        if args.resource == "messages" and args.action == "send-file":
            return ok(
                "messages.send-file",
                await send_file_to_chat(client, args.chat, args.path, args.caption),
                account,
            )

        if args.resource == "messages" and args.action == "forward":
            return ok(
                "messages.forward",
                await forward_message(
                    client, args.chat, args.from_chat, args.message_id
                ),
                account,
            )

        if args.resource == "buttons" and args.action == "click":
            return ok(
                "buttons.click",
                await click_button(client, args.chat, args.message_id, args.text),
                account,
            )

        if args.resource == "media" and args.action == "download":
            return ok(
                "media.download",
                await download_media(client, args.chat, args.message_id, args.out),
                account,
            )

        raise ValueError(f"Unsupported command: {args.resource}.{args.action}")
    finally:
        await client.disconnect()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        emit_json(asyncio.run(run(args)))
    except Exception as exc:
        emit_json(fail(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
