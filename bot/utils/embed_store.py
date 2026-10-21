"""Saved embed templates.

Embeds are saved per server by name (``embed save``) and can be reused with
``embed send <name>`` or inserted into any text through ``{embed:<name>}``.

Every text and image field is run through the placeholder engine in
``utils/variables.py``, so icons work the same way as in Components V2:
``{user_avatar}``, ``{server_icon}`` and ``{bot_avatar}`` in a thumbnail,
image, author icon or footer icon.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import discord

from utils.variables import render

DB_PATH = "db/embeds.db"

MAX_FIELDS = 25
LIMITS = {
    "message": 2000,
    "title": 256,
    "description": 4096,
    "footer_text": 2048,
    "author_name": 256,
}

FIELD_LABELS = {
    "message": "Message content",
    "title": "Title",
    "description": "Description",
    "color": "Color (hex)",
    "author_name": "Author name",
    "author_icon": "Author icon URL",
    "footer_text": "Footer text",
    "footer_icon": "Footer icon URL",
    "thumbnail": "Thumbnail URL",
    "image": "Image URL",
    "timestamp": "Timestamp (yes/no)",
}

ICON_FIELDS = ("author_icon", "footer_icon", "thumbnail", "image")


class EmbedError(ValueError):
    """Raised when an embed template is invalid."""


def empty_embed() -> dict[str, Any]:
    return {
        "message": "",
        "title": "",
        "description": "",
        "color": None,
        "footer_text": "",
        "footer_icon": "",
        "author_name": "",
        "author_icon": "",
        "thumbnail": "",
        "image": "",
        "timestamp": False,
        "fields": [],
    }


def _text(value: Any, field: str, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise EmbedError(f"{field} must be text.")
    value = value.strip()
    if len(value) > limit:
        raise EmbedError(f"{field} is too long (max {limit} characters).")
    return value


def _media(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise EmbedError(f"{field} must be text.")
    value = value.strip()
    if not value:
        return ""
    if not (
        value.startswith("http://")
        or value.startswith("https://")
        or value.startswith("{")
        or value.startswith("attachment://")
    ):
        raise EmbedError(f"{field} must be an http(s) URL or a placeholder like {{user_avatar}}.")
    return value


def _color(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        color = value
    else:
        try:
            color = int(str(value).strip().lstrip("#"), 16)
        except ValueError:
            raise EmbedError("Color must be a hex value such as #FF0000.") from None
    if not 0 <= color <= 0xFFFFFF:
        raise EmbedError("Color must be between #000000 and #FFFFFF.")
    return color


def normalize_embed(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise EmbedError("An embed must be an object.")

    clean = empty_embed()
    for key, limit in LIMITS.items():
        clean[key] = _text(data.get(key), FIELD_LABELS.get(key, key), limit)
    for key in ICON_FIELDS:
        clean[key] = _media(data.get(key), FIELD_LABELS.get(key, key))
    clean["color"] = _color(data.get("color"))
    clean["timestamp"] = bool(data.get("timestamp", False))

    raw_fields = data.get("fields") or []
    if not isinstance(raw_fields, list):
        raise EmbedError("`fields` must be a list.")
    if len(raw_fields) > MAX_FIELDS:
        raise EmbedError(f"An embed can hold at most {MAX_FIELDS} fields.")
    for entry in raw_fields:
        if not isinstance(entry, dict):
            raise EmbedError("Each field must be an object.")
        name = _text(entry.get("name"), "Field name", 256)
        value = _text(entry.get("value"), "Field value", 1024)
        if not name or not value:
            raise EmbedError("Every field needs a name and a value.")
        clean["fields"].append(
            {"name": name, "value": value, "inline": bool(entry.get("inline", False))}
        )

    if not any(
        clean[key]
        for key in (
            "message",
            "title",
            "description",
            "author_name",
            "footer_text",
            "thumbnail",
            "image",
        )
    ) and not clean["fields"]:
        raise EmbedError(
            "An embed needs at least a title, description, message, field, author, footer or image."
        )

    return clean


def render_embed(data: dict[str, Any], placeholders: dict[str, Any] | None = None) -> discord.Embed:
    """Resolve placeholders and build a real :class:`discord.Embed`."""
    clean = normalize_embed(data)
    variables = placeholders or {}
    guild = getattr(variables, "guild", None)

    def r(text: str) -> str:
        return render(text, variables, guild=guild)

    embed = discord.Embed(
        title=r(clean["title"]) or None,
        description=r(clean["description"]) or None,
        color=discord.Color(clean["color"] if clean["color"] is not None else 0xFF0000),
    )
    if clean["timestamp"]:
        embed.timestamp = discord.utils.utcnow()

    footer_text = r(clean["footer_text"])
    footer_icon = r(clean["footer_icon"])
    if footer_text or footer_icon:
        embed.set_footer(text=footer_text or None, icon_url=footer_icon or None)

    author_name = r(clean["author_name"])
    author_icon = r(clean["author_icon"])
    if author_name or author_icon:
        embed.set_author(name=author_name or None, icon_url=author_icon or None)

    if clean["thumbnail"]:
        embed.set_thumbnail(url=r(clean["thumbnail"]))
    if clean["image"]:
        embed.set_image(url=r(clean["image"]))

    for field in clean["fields"]:
        embed.add_field(name=r(field["name"]), value=r(field["value"]), inline=field["inline"])

    return embed


def describe_embed(data: dict[str, Any]) -> str:
    bits = []
    if data.get("title"):
        bits.append(data["title"][:40])
    if data.get("description"):
        bits.append(data["description"][:40])
    if data.get("image") or data.get("thumbnail"):
        bits.append("with image")
    return " · ".join(bits) if bits else "empty embed"


# ── Persistence ───────────────────────────────────────────────────────────────


async def init_db() -> None:
    os.makedirs("db", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS embed_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT COLLATE NOCASE NOT NULL,
                data TEXT NOT NULL,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(guild_id, name)
            )
            """
        )
        await db.commit()


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "guild_id": row["guild_id"],
        "name": row["name"],
        "data": json.loads(row["data"]),
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def save_embed(
    guild_id: int,
    name: str,
    data: dict[str, Any],
    author_id: int | None = None,
) -> tuple[int, bool]:
    name = (name or "").strip()
    if not name:
        raise EmbedError("An embed needs a name.")
    if len(name) > 60:
        raise EmbedError("That name is too long (max 60 characters).")
    clean = normalize_embed(data)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM embed_templates WHERE guild_id = ? AND name = ?", (guild_id, name)
        ) as cursor:
            existing = await cursor.fetchone()

        if existing:
            await db.execute(
                "UPDATE embed_templates SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(clean), now, existing["id"]),
            )
            await db.commit()
            return existing["id"], False

        cursor = await db.execute(
            "INSERT INTO embed_templates (guild_id, name, data, created_by, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, name, json.dumps(clean), author_id, now, now),
        )
        await db.commit()
        return cursor.lastrowid, True


async def get_embed(guild_id: int, name: str) -> dict[str, Any] | None:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM embed_templates WHERE guild_id = ? AND name = ?", (guild_id, name)
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def list_embeds(guild_id: int) -> list[dict[str, Any]]:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM embed_templates WHERE guild_id = ? ORDER BY name COLLATE NOCASE",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_dict(row) for row in rows]


async def delete_embed(guild_id: int, name: str) -> bool:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM embed_templates WHERE guild_id = ? AND name = ?", (guild_id, name)
        )
        await db.commit()
        return cursor.rowcount > 0


async def embed_names(guild_id: int, limit: int = 25) -> list[str]:
    return [row["name"] for row in await list_embeds(guild_id)][:limit]
