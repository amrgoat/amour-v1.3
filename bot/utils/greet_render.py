"""Shared rendering for greet / welcome messages.

Both the join listener and ``greet test`` go through :func:`send_greeting` so a
preview can never drift from what members actually receive.

Supported per type:

``simple``
    A text message. It may also contain ``{embed:name}`` and ``{cv2:name}``.
``embed``
    The configured embed, with the same template tokens allowed in the message
    content field.
``cv2``
    A saved Components V2 layout, referenced by name in ``embed_data``.

Because a Components V2 message cannot carry plain content or embeds, a
``{cv2:name}`` token turns the message into that layout and any remaining text
is shown as a text block on top of the container.
"""

from __future__ import annotations

import json
from typing import Any

import discord

from utils.cv2_store import build_view, get_template
from utils.embed_store import EmbedError, get_embed, render_embed
from utils.variables import build_variables, find_template_tokens, render


class GreetingError(RuntimeError):
    """Raised when a greeting references something that no longer exists."""


def _loads(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


async def send_greeting(
    destination: discord.abc.Messageable,
    *,
    guild: discord.Guild,
    member: discord.abc.User | discord.Member,
    channel: Any = None,
    welcome_type: str,
    welcome_message: str | None = None,
    embed_data: Any = None,
    bot: Any = None,
    prefix: str | None = None,
    extra: dict[str, Any] | None = None,
) -> list[discord.Message]:
    """Render the configured greeting and send it. Returns every sent message."""
    variables = build_variables(
        user=member,
        guild=guild,
        channel=channel if channel is not None else destination,
        bot=bot,
        prefix=prefix,
        extra=extra,
    )

    # ── Components V2 layout ──────────────────────────────────────────────
    if welcome_type == "cv2":
        name = _loads(embed_data).get("template")
        row = await get_template(guild.id, name) if name else None
        if row is None:
            raise GreetingError(f"the saved layout `{name or 'unknown'}` no longer exists")
        view = build_view(row["data"], template_id=row["id"], placeholders=variables)
        return [await destination.send(view=view)]

    embed_info = _loads(embed_data) if welcome_type == "embed" else {}
    raw_message = (embed_info.get("message") if embed_info else welcome_message) or ""

    text, embed_name, cv2_name = find_template_tokens(raw_message)
    content = render(text, variables, guild=guild)

    # ── A saved layout inserted as a variable ─────────────────────────────
    if cv2_name:
        row = await get_template(guild.id, cv2_name)
        if row is None:
            raise GreetingError(f"the saved layout `{cv2_name}` no longer exists")
        view = build_view(
            row["data"],
            template_id=row["id"],
            placeholders=variables,
            prefix_text=content or None,
        )
        return [await destination.send(view=view)]

    # ── Embeds (the configured one, plus {embed:name} if present) ─────────
    embeds: list[discord.Embed] = []
    if embed_info:
        try:
            embeds.append(render_embed(embed_info, variables))
        except EmbedError as exc:
            raise GreetingError(str(exc)) from exc
    if embed_name:
        saved = await get_embed(guild.id, embed_name)
        if saved is None:
            raise GreetingError(f"the saved embed `{embed_name}` no longer exists")
        try:
            embeds.append(render_embed(saved["data"], variables))
        except EmbedError as exc:
            raise GreetingError(f"`{embed_name}`: {exc}") from exc

    if not content and not embeds:
        return []

    return [await destination.send(content=content or None, embeds=embeds or None)]
