"""Components V2 template store.

A "cv2 template" is a named, per-guild Components V2 layout that can be sent to
any channel, reused in welcome messages, and edited later. Templates are stored
as JSON in ``db/cv2.db`` so they survive restarts.

Schema (version 1)::

    {
        "version": 1,
        "accent_color": 16711680 | None,
        "blocks": [
            {"type": "text", "content": "..."},
            {"type": "separator", "divider": true, "spacing": "small"},
            {"type": "section", "text": ["..."], "thumbnail": "https://..."},
            {"type": "gallery", "items": ["https://...", "..."]},
            {"type": "row", "buttons": [BUTTON, ...]},
            {"type": "menu", "id": "e5f6a7b8", "placeholder": "Pick a role…",
             "min_values": 1, "max_values": 1, "disabled": false,
             "options": [OPTION, ...]}     # at most 25
        ]
    }

OPTION::

    {
        "label": "Giveaway",            # shown in the dropdown
        "value": "giveaway",            # returned on selection, unique per menu
        "description": "Get pinged…" | null,
        "emoji": "<:name:123> | 🎉 | null",
        "actions": [ACTION, ...]         # optional, at most 10, run when picked
    }

BUTTON::

    {
        "id": "a1b2c3d4",
        "label": "Get role",
        "style": "primary",
        "emoji": "<:name:123> | 🎉 | null",
        "disabled": false,
        "url": "https://..." | null,
        "actions": [ACTION, ...]        # at most 10, run in order
    }

ACTION::

    {"type": "role_add" | "role_remove" | "role_toggle",
     "role_ids": [123, ...]}
    {"type": "dm" | "ephemeral", "message": "..."}
    {"type": "channel_message", "channel_id": 123, "message": "..."}
    {"type": "link", "url": "https://..."}
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Iterable

import aiosqlite
import discord
from discord import ui

from utils.variables import Variables, build_variables
from utils.variables import render as render_variables

DB_PATH = "db/cv2.db"

SCHEMA_VERSION = 1

MAX_BLOCKS = 20
MAX_COMPONENTS = 40
MAX_ACTIONS = 10
MAX_ROW_BUTTONS = 5
MAX_GALLERY_ITEMS = 10
MAX_TEXT = 4000
MAX_LABEL = 80
MAX_MESSAGE = 2000
MAX_MENU_OPTIONS = 25
MAX_OPTION_LABEL = 100
MAX_OPTION_DESCRIPTION = 100
MAX_OPTION_VALUE = 100
MAX_PLACEHOLDER = 150

BLOCK_TYPES = ("text", "separator", "section", "gallery", "row", "menu")

ACTION_TYPES = (
    "role_add",
    "role_remove",
    "role_toggle",
    "dm",
    "ephemeral",
    "channel_message",
    "link",
)

ROLE_ACTION_TYPES = ("role_add", "role_remove", "role_toggle")

# Short names shared by the builder UI, the action panels and the help text.
ACTION_NAMES = {
    "link": "Link button (opens a URL)",
    "role_add": "Add role",
    "role_remove": "Remove role",
    "role_toggle": "Toggle role",
    "ephemeral": "Private reply",
    "dm": "Send a direct message",
    "channel_message": "Post in a channel",
}

STYLES = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}


class CV2Error(ValueError):
    """Raised when a template (or one of its parts) is invalid."""


# ── Small helpers ─────────────────────────────────────────────────────────────


def new_button_id() -> str:
    return secrets.token_hex(4)


def empty_template() -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "accent_color": None, "blocks": []}


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _media(value: Any, field: str) -> str:
    """Media fields may hold an http(s) URL or a greeting placeholder."""
    if not isinstance(value, str):
        raise CV2Error(f"{field} must be text.")
    value = value.strip()
    if not value:
        raise CV2Error(f"{field} cannot be empty.")
    if not (_is_url(value) or value.startswith("{")):
        raise CV2Error(f"{field} must start with http:// or https://.")
    return value


def _text(value: Any, field: str, *, limit: int = MAX_TEXT, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise CV2Error(f"{field} must be text.")
    value = value.strip()
    if not value and not allow_empty:
        raise CV2Error(f"{field} cannot be empty.")
    if len(value) > limit:
        raise CV2Error(f"{field} is too long (max {limit} characters).")
    return value


def _int(value: Any, field: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise CV2Error(f"{field} must be a whole number.") from None


def _parse_color(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        color = value
    else:
        raw = str(value).strip().lstrip("#")
        try:
            color = int(raw, 16)
        except ValueError:
            raise CV2Error("Accent color must be a hex value such as #FF0000.") from None
    if not 0 <= color <= 0xFFFFFF:
        raise CV2Error("Accent color must be between #000000 and #FFFFFF.")
    return color


def _parse_emoji(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        discord.PartialEmoji.from_str(value)
    except (ValueError, TypeError):
        raise CV2Error(f"`{value}` is not a valid emoji.") from None
    return value


def _parse_role_ids(value: Any) -> list[int]:
    if value is None:
        raise CV2Error("Role actions need at least one role.")
    if isinstance(value, (int, str)):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        raise CV2Error("Roles must be a list of role IDs.")

    ids: list[int] = []
    for item in value:
        if isinstance(item, str):
            item = item.strip().strip("<@&>")
        if item in ("", None):
            continue
        role_id = _int(item, "Role ID")
        if role_id not in ids:
            ids.append(role_id)
    if not ids:
        raise CV2Error("Role actions need at least one role.")
    return ids


def normalize_action(action: Any) -> dict[str, Any]:
    if not isinstance(action, dict):
        raise CV2Error("An action must be an object.")

    kind = str(action.get("type", "")).strip().lower()
    if kind not in ACTION_TYPES:
        raise CV2Error(f"Unknown action type `{kind or 'missing'}`.")

    if kind in ROLE_ACTION_TYPES:
        return {"type": kind, "role_ids": _parse_role_ids(action.get("role_ids") or action.get("roles"))}

    if kind in ("dm", "ephemeral"):
        return {"type": kind, "message": _text(action.get("message"), "Action message", limit=MAX_MESSAGE)}

    if kind == "channel_message":
        message = _text(action.get("message"), "Action message", limit=MAX_MESSAGE)
        channel_id = _int(action.get("channel_id"), "Channel ID")
        return {"type": kind, "channel_id": channel_id, "message": message}

    url = str(action.get("url") or "").strip()
    if not _is_url(url):
        raise CV2Error("Link actions need an http(s) URL.")
    return {"type": "link", "url": url}


def normalize_button(button: Any) -> dict[str, Any]:
    if not isinstance(button, dict):
        raise CV2Error("A button must be an object.")

    label = _text(button.get("label"), "Button label", limit=MAX_LABEL)
    emoji = _parse_emoji(button.get("emoji"))
    disabled = bool(button.get("disabled", False))

    url = button.get("url")
    raw_actions = button.get("actions") or []
    if not isinstance(raw_actions, list):
        raise CV2Error("Button actions must be a list.")

    if url:
        url = str(url).strip()
        if not _is_url(url):
            raise CV2Error("Button URLs must start with http:// or https://.")
        if raw_actions:
            raise CV2Error("A URL button cannot also run actions.")
        return {
            "id": button.get("id") or new_button_id(),
            "label": label,
            "style": "link",
            "emoji": emoji,
            "disabled": disabled,
            "url": url,
            "actions": [],
        }

    actions = [normalize_action(a) for a in raw_actions]
    if not actions:
        raise CV2Error("An action button needs at least one action (or a URL).")
    if len(actions) > MAX_ACTIONS:
        raise CV2Error(f"A button can run at most {MAX_ACTIONS} actions.")

    style = str(button.get("style") or "primary").lower()
    if style not in STYLES:
        style = "primary"

    return {
        "id": button.get("id") or new_button_id(),
        "label": label,
        "style": style,
        "emoji": emoji,
        "disabled": disabled,
        "url": None,
        "actions": actions,
    }


def normalize_menu_option(option: Any) -> dict[str, Any]:
    if not isinstance(option, dict):
        raise CV2Error("A menu option must be an object.")

    label = _text(option.get("label"), "Option label", limit=MAX_OPTION_LABEL)

    description = option.get("description")
    if description is not None and str(description).strip():
        description = str(description).strip()
        if len(description) > MAX_OPTION_DESCRIPTION:
            raise CV2Error(
                f"Option descriptions can hold at most {MAX_OPTION_DESCRIPTION} characters."
            )
    else:
        description = None

    # The value is what Discord sends back; default it to the label so a menu
    # written by hand only needs labels.
    value = str(option.get("value") or label).strip() or label
    if len(value) > MAX_OPTION_VALUE:
        raise CV2Error(f"Option values can hold at most {MAX_OPTION_VALUE} characters.")

    raw_actions = option.get("actions") or []
    if not isinstance(raw_actions, list):
        raise CV2Error("Option actions must be a list.")
    actions = [normalize_action(action) for action in raw_actions]
    if len(actions) > MAX_ACTIONS:
        raise CV2Error(f"A menu option can run at most {MAX_ACTIONS} actions.")

    return {
        "label": label,
        "value": value,
        "description": description,
        "emoji": _parse_emoji(option.get("emoji")),
        "actions": actions,
    }


def normalize_block(block: Any) -> dict[str, Any]:
    if not isinstance(block, dict):
        raise CV2Error("A block must be an object.")

    kind = str(block.get("type", "")).strip().lower()
    if kind not in BLOCK_TYPES:
        raise CV2Error(f"Unknown block type `{kind or 'missing'}`.")

    if kind == "text":
        return {"type": "text", "content": _text(block.get("content"), "Text")}

    if kind == "separator":
        spacing = str(block.get("spacing") or "small").lower()
        if spacing not in ("small", "large"):
            spacing = "small"
        return {"type": "separator", "divider": bool(block.get("divider", True)), "spacing": spacing}

    if kind == "gallery":
        raw_items = block.get("items") or []
        if isinstance(raw_items, str):
            raw_items = raw_items.splitlines()
        if not isinstance(raw_items, (list, tuple)):
            raise CV2Error("Gallery items must be a list of URLs.")
        items = [_media(item, "Gallery image") for item in raw_items if str(item).strip()]
        if not items:
            raise CV2Error("A gallery needs at least one image URL.")
        if len(items) > MAX_GALLERY_ITEMS:
            raise CV2Error(f"A gallery can hold at most {MAX_GALLERY_ITEMS} images.")
        return {"type": "gallery", "items": items}

    if kind == "section":
        raw_text = block.get("text") or []
        if isinstance(raw_text, str):
            raw_text = [raw_text]
        if not isinstance(raw_text, (list, tuple)):
            raise CV2Error("Section text must be a list.")
        texts = [_text(item, "Section text") for item in raw_text if str(item).strip()]
        if not texts:
            raise CV2Error("A section needs some text.")
        if len(texts) > 3:
            raise CV2Error("A section can hold at most 3 text blocks.")

        thumbnail = block.get("thumbnail")
        return {
            "type": "section",
            "text": texts,
            "thumbnail": _media(thumbnail, "Section thumbnail") if thumbnail else None,
        }

    if kind == "menu":
        raw_options = block.get("options") or []
        if not isinstance(raw_options, list):
            raise CV2Error("Menu options must be a list.")
        options = [normalize_menu_option(option) for option in raw_options]
        if not options:
            raise CV2Error("A menu needs at least one option.")
        if len(options) > MAX_MENU_OPTIONS:
            raise CV2Error(f"A menu can hold at most {MAX_MENU_OPTIONS} options.")

        # Discord requires unique values, so a repeated label gets a numeric suffix.
        seen: set[str] = set()
        for option in options:
            value = option["value"]
            suffix = 2
            while value in seen:
                tail = f"_{suffix}"
                value = option["value"][: MAX_OPTION_VALUE - len(tail)] + tail
                suffix += 1
            option["value"] = value
            seen.add(value)

        placeholder = _text(
            block.get("placeholder") or "",
            "Menu placeholder",
            limit=MAX_PLACEHOLDER,
            allow_empty=True,
        )

        max_values = _int(block.get("max_values", 1), "Menu max choices")
        if not 1 <= max_values <= len(options):
            raise CV2Error(
                f"A menu can allow between 1 and {len(options)} choice(s)."
            )
        min_values = _int(block.get("min_values", 1), "Menu min choices")
        if not 0 <= min_values <= max_values:
            min_values = 1

        return {
            "type": "menu",
            "id": str(block.get("id") or new_button_id()),
            "placeholder": placeholder or None,
            "min_values": min_values,
            "max_values": max_values,
            "disabled": bool(block.get("disabled", False)),
            "options": options,
        }

    raw_buttons = block.get("buttons") or []
    if not isinstance(raw_buttons, list):
        raise CV2Error("Row buttons must be a list.")
    buttons = [normalize_button(b) for b in raw_buttons]
    if not buttons:
        raise CV2Error("A button row needs at least one button.")
    if len(buttons) > MAX_ROW_BUTTONS:
        raise CV2Error(f"A row can hold at most {MAX_ROW_BUTTONS} buttons.")
    return {"type": "row", "buttons": buttons}


def normalize_template(template: Any) -> dict[str, Any]:
    """Validate and return a clean copy of ``template``."""
    if not isinstance(template, dict):
        raise CV2Error("A template must be an object.")

    version = template.get("version", SCHEMA_VERSION)
    if _int(version, "Schema version") > SCHEMA_VERSION:
        raise CV2Error(
            f"This template uses schema version {version}; this bot understands {SCHEMA_VERSION}."
        )

    raw_blocks = template.get("blocks") or []
    if not isinstance(raw_blocks, list):
        raise CV2Error("`blocks` must be a list.")
    if len(raw_blocks) > MAX_BLOCKS:
        raise CV2Error(f"A layout can hold at most {MAX_BLOCKS} blocks.")

    blocks = [normalize_block(block) for block in raw_blocks]

    data = {
        "version": SCHEMA_VERSION,
        "accent_color": _parse_color(template.get("accent_color")),
        "blocks": blocks,
    }

    if _component_count(data) > MAX_COMPONENTS:
        raise CV2Error(f"A layout can hold at most {MAX_COMPONENTS} components.")
    return data


def _component_count(data: dict[str, Any]) -> int:
    count = 1  # the container itself
    for block in data["blocks"]:
        kind = block["type"]
        if kind == "section":
            count += 1 + len(block["text"]) + (1 if block["thumbnail"] else 0)
        elif kind == "gallery":
            count += 1 + len(block["items"])
        elif kind == "row":
            count += 1 + len(block["buttons"])
        elif kind == "menu":
            count += 2  # action row + the select itself
        else:
            count += 1
    return count


# ── Rendering ─────────────────────────────────────────────────────────────────


def render_text(text: str, placeholders: dict[str, Any] | None = None) -> str:
    """Replace ``{name}`` placeholders, leaving unknown ones untouched."""
    return render_variables(text, placeholders or {})


def placeholders_for(
    user: discord.abc.User | discord.Member,
    guild: discord.Guild | None = None,
    channel: discord.abc.GuildChannel | None = None,
    bot: Any = None,
    prefix: str | None = None,
) -> Variables:
    """The placeholder set shared by welcome messages, layouts and buttons."""
    return build_variables(
        user=user, guild=guild, channel=channel, bot=bot, prefix=prefix
    )


def _build_button(button: dict[str, Any], placeholders, template_id: int | None) -> ui.Button:
    emoji = button.get("emoji")
    if button["url"]:
        return ui.Button(
            label=button["label"],
            url=render_text(button["url"], placeholders),
            emoji=emoji,
            disabled=button["disabled"],
        )

    custom_id = None
    disabled = button["disabled"]
    if template_id is not None:
        custom_id = f"cv2:{template_id}:{button['id']}"
    else:
        # Preview / unsaved layout: keep the buttons visible but inert.
        disabled = True

    return ui.Button(
        label=button["label"],
        style=STYLES[button["style"]],
        emoji=emoji,
        disabled=disabled,
        custom_id=custom_id,
    )


def _build_block(block: dict[str, Any], placeholders, template_id: int | None):
    kind = block["type"]

    if kind == "text":
        return ui.TextDisplay(render_text(block["content"], placeholders))

    if kind == "separator":
        spacing = (
            discord.SeparatorSpacing.large
            if block["spacing"] == "large"
            else discord.SeparatorSpacing.small
        )
        return ui.Separator(visible=block["divider"], spacing=spacing)

    if kind == "gallery":
        items = [
            discord.MediaGalleryItem(url)
            for url in (render_text(item, placeholders) for item in block["items"])
            if url.strip()
        ]
        # An image URL like {server_icon} can resolve to nothing. Discord
        # rejects empty media URLs, so show the links as text instead.
        if not items:
            return ui.TextDisplay("\n".join(block["items"]))
        return ui.MediaGallery(*items)

    if kind == "section":
        rendered = [render_text(text, placeholders) for text in block["text"]]
        # Discord requires a section accessory. Older templates (and hand-written
        # JSON) may not have a thumbnail, and placeholders such as {server_icon}
        # can resolve to an empty string, so fall back to plain text instead of
        # sending an empty media URL, which the API rejects.
        thumb_url = (
            render_text(block["thumbnail"], placeholders).strip()
            if block["thumbnail"]
            else ""
        )
        if not thumb_url:
            return ui.TextDisplay("\n\n".join(rendered))
        return ui.Section(
            *[ui.TextDisplay(text) for text in rendered],
            accessory=ui.Thumbnail(thumb_url),
        )

    if kind == "menu":
        options = [
            discord.SelectOption(
                label=render_text(option["label"], placeholders),
                value=option["value"],
                description=render_text(option["description"], placeholders)
                if option["description"]
                else None,
                emoji=option["emoji"],
            )
            for option in block["options"]
        ]
        # A preview has no saved template to resolve, so the menu is shown inert.
        return ui.ActionRow(
            ui.Select(
                placeholder=render_text(block["placeholder"], placeholders)
                if block["placeholder"]
                else None,
                min_values=block["min_values"],
                max_values=block["max_values"],
                options=options,
                custom_id=f"cv2m:{template_id or 0}:{block['id']}",
                disabled=block["disabled"] or template_id is None,
            )
        )

    buttons = [_build_button(button, placeholders, template_id) for button in block["buttons"]]
    return ui.ActionRow(*buttons)


def build_view(
    template: dict[str, Any],
    *,
    placeholders: dict[str, Any] | None = None,
    template_id: int | None = None,
    prefix_text: str | None = None,
) -> ui.LayoutView:
    """Render a template into a :class:`discord.ui.LayoutView` ready to send.

    ``prefix_text`` is used when a layout is inserted through ``{cv2:name}``:
    a Components V2 message cannot carry plain content, so any text that came
    with the token is shown as a text block on top of the container.
    """
    data = normalize_template(template)

    view = ui.LayoutView(timeout=None)
    container = ui.Container(accent_color=data["accent_color"])

    if prefix_text and prefix_text.strip():
        if _component_count(data) + 2 > MAX_COMPONENTS:
            raise CV2Error(
                "This layout is already at the component limit, so the text around "
                "`{cv2:...}` cannot be added. Trim the layout or the message."
            )
        container.add_item(ui.TextDisplay(prefix_text.strip()[:MAX_TEXT]))
        container.add_item(ui.Separator())

    for block in data["blocks"]:
        container.add_item(_build_block(block, placeholders, template_id))
    if not data["blocks"]:
        container.add_item(ui.TextDisplay("*This layout is empty.*"))
    view.add_item(container)
    return view


def describe_block(block: dict[str, Any]) -> str:
    """Short one-line description used by the builder and the listing command."""
    kind = block["type"]
    if kind == "text":
        snippet = block["content"].replace("\n", " ")[:60]
        return f"Text · {snippet}"
    if kind == "separator":
        bits = ["divider" if block["divider"] else "spacer", block["spacing"]]
        return f"Separator · {', '.join(bits)}"
    if kind == "section":
        extra = " + thumbnail" if block["thumbnail"] else ""
        return f"Section · {block['text'][0].replace(chr(10), ' ')[:50]}{extra}"
    if kind == "gallery":
        return f"Gallery · {len(block['items'])} image(s)"
    if kind == "menu":
        labels = ", ".join(option["label"] for option in block["options"][:3])
        with_actions = sum(1 for option in block["options"] if option.get("actions"))
        extra = f" · {with_actions} with actions" if with_actions else ""
        return f"Menu · {len(block['options'])} option(s) · {labels[:40]}{extra}"
    actions = sum(len(button.get("actions") or []) for button in block["buttons"])
    return f"Buttons · {len(block['buttons'])} button(s) · {actions} action(s)"


def describe_action(action: dict[str, Any]) -> str:
    """One-line label for an action, used by the builder's action panels."""
    kind = action["type"]
    label = ACTION_NAMES.get(kind, kind)
    if kind in ROLE_ACTION_TYPES:
        roles = ", ".join(f"<@&{role_id}>" for role_id in action["role_ids"])
        return f"{label} · {roles}"
    if kind == "channel_message":
        snippet = " ".join(action["message"].split())[:50]
        return f"{label} · <#{action['channel_id']}> · {snippet}"
    if kind in ("dm", "ephemeral"):
        snippet = " ".join(action["message"].split())[:60]
        return f"{label} · {snippet}"
    return f"{label} · {action.get('url', '')}"


# ── Persistence ───────────────────────────────────────────────────────────────


async def init_db() -> None:
    os.makedirs("db", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS cv2_templates (
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
    data = json.loads(row["data"])
    return {
        "id": row["id"],
        "guild_id": row["guild_id"],
        "name": row["name"],
        "data": data,
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def save_template(
    guild_id: int,
    name: str,
    data: dict[str, Any],
    author_id: int | None = None,
) -> tuple[int, bool]:
    """Create or update a template. Returns ``(id, created)``."""
    name = _text(name, "Template name", limit=60)
    clean = normalize_template(data)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM cv2_templates WHERE guild_id = ? AND name = ?",
            (guild_id, name),
        ) as cursor:
            existing = await cursor.fetchone()

        if existing:
            await db.execute(
                "UPDATE cv2_templates SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(clean), now, existing["id"]),
            )
            await db.commit()
            return existing["id"], False

        cursor = await db.execute(
            "INSERT INTO cv2_templates (guild_id, name, data, created_by, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, name, json.dumps(clean), author_id, now, now),
        )
        await db.commit()
        return cursor.lastrowid, True


async def get_template(guild_id: int, name: str) -> dict[str, Any] | None:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM cv2_templates WHERE guild_id = ? AND name = ?",
            (guild_id, name),
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def get_template_by_id(template_id: int, guild_id: int | None = None) -> dict[str, Any] | None:
    await init_db()
    query = "SELECT * FROM cv2_templates WHERE id = ?"
    args: list[Any] = [template_id]
    if guild_id is not None:
        query += " AND guild_id = ?"
        args.append(guild_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, args) as cursor:
            row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def list_templates(guild_id: int) -> list[dict[str, Any]]:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM cv2_templates WHERE guild_id = ? ORDER BY name COLLATE NOCASE",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_dict(row) for row in rows]


async def delete_template(guild_id: int, name: str) -> bool:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM cv2_templates WHERE guild_id = ? AND name = ?",
            (guild_id, name),
        )
        await db.commit()
        return cursor.rowcount > 0


async def template_names(guild_id: int, limit: int = 25) -> list[str]:
    templates = await list_templates(guild_id)
    return [t["name"] for t in templates][:limit]


async def send_template(
    destination: discord.abc.Messageable,
    template: dict[str, Any],
    *,
    template_id: int | None = None,
    placeholders: dict[str, Any] | None = None,
    **send_kwargs: Any,
) -> discord.Message:
    """Render ``template`` and send it to ``destination``."""
    view = build_view(template, placeholders=placeholders, template_id=template_id)
    return await destination.send(view=view, **send_kwargs)
