"""Runtime bot identity helpers.

Everything user-facing is branded from the running bot account itself — its own
name and its own avatar — instead of anything hardcoded in this repo.

Typical use::

    from utils.branding import bot_avatar, bot_invite, bot_name

    embed.set_author(name=bot_name(ctx.bot), icon_url=bot_avatar(ctx.bot))
    f"[Invite {bot_name(ctx.bot)}]({bot_invite(ctx.bot)})"

Call :func:`register` once at startup (see ``main.py``) so helpers also work in
places that have no client reference at hand.
"""

from __future__ import annotations

import os
from typing import Any, Optional

_CLIENT: Any = None

DEFAULT_NAME = os.getenv("brand_name", "").strip() or "Bot"


def register(bot: Any) -> None:
    """Remember the client so the helpers below can be used anywhere."""
    global _CLIENT
    _CLIENT = bot


def _resolve_client(bot: Any = None) -> Any:
    return bot if bot is not None else _CLIENT


def _user(bot: Any = None) -> Any:
    """The bot's own :class:`discord.User`, or ``None`` before login."""
    return getattr(_resolve_client(bot), "user", None)


def bot_name(bot: Any = None, fallback: Optional[str] = None) -> str:
    """The bot's own display name, falling back to ``brand_name`` from the env."""
    user = _user(bot)
    if user is not None:
        name = getattr(user, "display_name", None) or getattr(user, "name", None)
        if name:
            return str(name)
    return fallback if fallback is not None else DEFAULT_NAME


def bot_avatar(bot: Any = None) -> Optional[str]:
    """The bot's own avatar URL (``None`` before the client is ready)."""
    user = _user(bot)
    if user is None:
        return None
    url = getattr(getattr(user, "display_avatar", None), "url", None)
    return str(url) if url else None


# Alias: the avatar is the only "pfp" the bot should ever show.
bot_pfp = bot_avatar


def bot_id(bot: Any = None) -> Optional[int]:
    """The bot's user id, or ``None`` before login."""
    user = _user(bot)
    user_id = getattr(user, "id", None)
    if user_id is not None:
        return int(user_id)
    raw = os.getenv("CLIENT_ID", "").strip()
    return int(raw) if raw.isdigit() else None


def bot_invite(bot: Any = None, permissions: int = 8) -> str:
    """OAuth2 invite link built from the bot's own client id."""
    client_id = bot_id(bot)
    base = "https://discord.com/oauth2/authorize"
    if client_id is None:
        return base
    return (
        f"{base}?client_id={client_id}"
        f"&permissions={permissions}&scope=bot+applications.commands"
    )


def user_link(user_id: int, label: Optional[str] = None) -> str:
    """Markdown link to a Discord user profile."""
    return f"[{label or user_id}](https://discord.com/users/{user_id})"


def support_url() -> str:
    """Optional support server URL from the ``SUPPORT_SERVER`` env var."""
    return os.getenv("SUPPORT_SERVER", "").strip()


def support_link(text: str = "Support Server") -> str:
    """Markdown support-server link, or plain ``text`` when none is configured."""
    url = support_url()
    return f"[{text}]({url})" if url else text


def support_button(bot: Any = None):
    """A link button for the support server, or ``None`` when unset."""
    import discord

    url = support_url()
    if not url:
        return None
    return discord.ui.Button(label="Support", style=discord.ButtonStyle.link, url=url)
