"""Placeholder variables for messages, embeds and Components V2 layouts.

The names follow Mimu's variable catalog (``{user_name}``, ``{server_icon}``,
``{server_membercount_ordinal}`` …), so anything written for Mimu works here.
Tokens are matched case-insensitively and unknown tokens are left untouched.

Template functions
------------------
Two tokens insert a *saved* layout instead of a value:

``{embed:<name>}``
    Attaches the saved embed called ``<name>`` to the outgoing message.
``{cv2:<name>}``
    Sends the saved Components V2 layout called ``<name>``. Because a
    Components V2 message cannot carry plain content or embeds, any leftover
    text is shown as a text block at the top of the container.

Every user variable also accepts a target, e.g. ``{user_name:123456789012345678}``
or ``{user_avatar:@someone}``.
"""

from __future__ import annotations

import datetime as dt
import random
import re
from typing import Any, Mapping

import discord

TOKEN_RE = re.compile(r"\{([A-Za-z0-9_]+)(?::([^{}]*))?\}")
TEMPLATE_TOKEN_RE = re.compile(r"\{(embed|cv2):([^{}]{1,60})\}", re.IGNORECASE)

# Ordered (token, description) pairs used by the "Variables" help buttons.
VARIABLE_DOCS: tuple[tuple[str, str], ...] = (
    ("{user}", "Mentions the user."),
    ("{user_name}", "The user's username."),
    ("{user_displayname}", "The user's display name in this server."),
    ("{user_nick}", "The user's nickname (falls back to the display name)."),
    ("{user_tag}", "Username and discriminator (legacy tag format)."),
    ("{user_id}", "The user's ID."),
    ("{user_avatar}", "The user's avatar URL — works in embed images and CV2 thumbnails."),
    ("{user_displaycolor}", "The member's role colour as hex, e.g. #5865F2."),
    ("{user_joindate}", "When the member joined this server."),
    ("{user_createdate}", "When the user's account was created."),
    ("{user_boostsince}", "When the member started boosting, or Not a Booster."),
    ("{server_name}", "The server's name."),
    ("{server_id}", "The server's ID."),
    ("{server_icon}", "The server's icon URL — or the default icon when it has none."),
    ("{server_banner}", "The server's banner URL, or the icon URL when it has none."),
    ("{server_membercount}", "Total member count."),
    ("{server_membercount_ordinal}", "Total member count as an ordinal, e.g. 203rd."),
    ("{server_membercount_nobots}", "Member count excluding bots."),
    ("{server_membercount_nobots_ordinal}", "Non-bot count as an ordinal."),
    ("{server_botcount}", "Number of bots."),
    ("{server_botcount_ordinal}", "Bot count as an ordinal."),
    ("{server_rolecount}", "Number of roles."),
    ("{server_channelcount}", "Number of channels of every type."),
    ("{server_owner}", "Mentions the server owner."),
    ("{server_owner_id}", "The server owner's ID."),
    ("{server_createdate}", "When the server was created."),
    ("{server_randommember}", "Mentions a random member."),
    ("{server_randommember_tag}", "A random member's tag."),
    ("{server_randommember_nobots}", "Mentions a random non-bot member."),
    ("{server_boostlevel}", "Boost level, 0 to 3."),
    ("{server_boostcount}", "Number of boosts."),
    ("{server_nextboostlevel}", "The next boost level, or Max Level Reached."),
    ("{server_nextboostlevel_required}", "Boosts needed for the next level."),
    ("{server_nextboostlevel_until_required}", "Boosts still missing for the next level."),
    ("{server_prefix}", "This server's command prefix."),
    ("{channel}", "Mentions the channel the message is sent in."),
    ("{channel_name}", "The channel's name."),
    ("{channel_id}", "The channel's ID."),
    ("{channel_createdate}", "When the channel was created."),
    ("{channel_topic}", "The channel's topic."),
    ("{role:NAME}", "Mentions a role by name or ID — the only token with an argument."),
    ("{bot}", "Mentions the bot."),
    ("{bot_name}", "The bot's own Discord name."),
    ("{bot_avatar}", "The bot's avatar URL."),
    ("{date}", "The current date and time."),
    ("{time}", "The current time, UTC."),
    ("{timestamp}", "A Discord timestamp of right now."),
    ("{newline}", "A line break."),
    ("{embed:name}", "Inserts a saved embed (see `embed list`)."),
    ("{cv2:name}", "Inserts a saved Components V2 layout (see `cv2 list`)."),
)

DEFAULT_SERVER_ICON = "https://cdn.discordapp.com/embed/avatars/0.png"


class Variables(dict):
    """A plain dict of placeholder values that remembers its guild.

    Carrying the guild lets :func:`render` resolve targeted tokens such as
    ``{user_name:123456789012345678}`` without every caller passing it again.
    """

    guild: discord.Guild | None = None

_NEXT_TIER_BOOSTS = {0: 2, 1: 7, 2: 14}


def ordinal(number: int) -> str:
    """``1`` → ``1st``, ``203`` → ``203rd``."""
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def format_date(value: dt.datetime | None) -> str:
    if value is None:
        return "Unknown"
    return value.strftime("%A, %B %d, %Y")


def _icon(url: str | None, fallback: str = DEFAULT_SERVER_ICON) -> str:
    return url or fallback


def _asset_url(asset: Any, fallback: str = DEFAULT_SERVER_ICON) -> str:
    if asset is None:
        return fallback
    return getattr(asset, "url", None) or fallback


def resolve_target(guild: discord.Guild | None, target: str) -> discord.abc.User | None:
    """Resolve ``{user_name:...}`` arguments: a snowflake, a mention or a name."""
    target = (target or "").strip()
    if not target or guild is None:
        return None
    digits = re.sub(r"\D", "", target)
    if digits:
        member = guild.get_member(int(digits))
        if member is not None:
            return member
        cached = guild.get_member_named(target.lstrip("@#"))
        if cached is not None:
            return cached
        return None
    return guild.get_member_named(target.lstrip("@#"))


def _user_values(
    user: discord.abc.User | discord.Member | None,
    guild: discord.Guild | None,
) -> dict[str, str]:
    if user is None:
        return {}

    mention = getattr(user, "mention", None) or getattr(user, "name", "user")
    display_name = getattr(user, "display_name", None) or getattr(user, "name", "")
    # Duck-typed on purpose: a member always carries joined_at, a plain user
    # object (DM context) does not.
    member = user if hasattr(user, "joined_at") else None

    values: dict[str, str] = {
        "user": mention,
        "user_mention": mention,
        "user_name": getattr(user, "name", ""),
        "user_displayname": display_name,
        "user_display_name": display_name,
        "user_nick": getattr(user, "nick", None) or display_name,
        "user_tag": str(user),
        "user_id": str(user.id),
        "user_avatar": user.display_avatar.url,
        "user_avatar_url": user.display_avatar.url,
        "user_icon": user.display_avatar.url,
        "user_createdate": format_date(getattr(user, "created_at", None)),
    }

    if member is not None:
        colour = getattr(member, "colour", None)
        values["user_displaycolor"] = f"#{colour.value:06X}" if colour else "#000000"
        values["user_joindate"] = format_date(member.joined_at)
        boosted = member.premium_since
        values["user_boostsince"] = format_date(boosted) if boosted else "Not a Booster"
    else:
        values["user_displaycolor"] = "#000000"
        values["user_joindate"] = "Unknown"
        values["user_boostsince"] = "Not a Booster"

    return values


def _server_values(guild: discord.Guild | None, prefix: str | None) -> dict[str, str]:
    if guild is None:
        return {}

    member_count = guild.member_count or len(guild.members)
    members = guild.members or []
    bots = sum(1 for m in members if m.bot)
    humans = max(member_count - bots, 0) if members else member_count

    tier = guild.premium_tier
    boosts = guild.premium_subscription_count or 0
    if tier >= 3:
        next_level = required = until = "Max Level Reached"
    else:
        next_level = str(tier + 1)
        needed = _NEXT_TIER_BOOSTS.get(tier, 14)
        required = str(needed)
        until = str(max(needed - boosts, 0))

    owner = guild.owner
    candidates = [m for m in members if not m.bot]
    random_member = random.choice(members) if members else None
    random_human = random.choice(candidates) if candidates else None

    values = {
        "server_name": guild.name,
        "server_id": str(guild.id),
        "server_icon": _asset_url(guild.icon),
        "server_icon_url": _asset_url(guild.icon),
        "server_banner": _asset_url(guild.banner, _asset_url(guild.icon)),
        "server_membercount": str(member_count),
        "server_membercount_ordinal": ordinal(member_count),
        "server_membercount_nobots": str(humans),
        "server_membercount_nobots_ordinal": ordinal(humans),
        "server_botcount": str(bots),
        "server_botcount_ordinal": ordinal(bots),
        "server_rolecount": str(len(guild.roles)),
        "server_channelcount": str(len(guild.channels)),
        "server_owner": owner.mention if owner else "Unknown",
        "server_owner_id": str(owner.id) if owner else "Unknown",
        "server_createdate": format_date(guild.created_at),
        "server_boostlevel": str(tier),
        "server_boostcount": str(boosts),
        "server_nextboostlevel": next_level,
        "server_nextboostlevel_required": required,
        "server_nextboostlevel_until_required": until,
    }
    if random_member is not None:
        values["server_randommember"] = random_member.mention
        values["server_randommember_tag"] = str(random_member)
    if random_human is not None:
        values["server_randommember_nobots"] = random_human.mention
    if prefix:
        values["server_prefix"] = prefix
    return values


def _channel_values(channel: Any) -> dict[str, str]:
    if channel is None:
        return {}
    values = {
        "channel": getattr(channel, "mention", ""),
        "channel_name": getattr(channel, "name", ""),
        "channel_id": str(getattr(channel, "id", "")),
        "channel_topic": getattr(channel, "topic", None) or "No topic",
        "channel_createdate": format_date(getattr(channel, "created_at", None)),
    }
    return values


def _message_values(message: discord.Message | None, bot: Any = None) -> dict[str, str]:
    if message is None:
        return {}
    values = {
        "message_id": str(message.id),
        "message_content": message.content or "",
        "message_link": message.jump_url,
    }
    return values


def _bot_values(bot: Any) -> dict[str, str]:
    if bot is None or getattr(bot, "user", None) is None:
        return {}
    user = bot.user
    return {
        "bot": user.mention,
        "bot_mention": user.mention,
        "bot_name": user.display_name,
        "bot_avatar": user.display_avatar.url,
        "bot_icon": user.display_avatar.url,
        "bot_id": str(user.id),
    }


def build_variables(
    *,
    user: discord.abc.User | discord.Member | None = None,
    guild: discord.Guild | None = None,
    channel: Any = None,
    message: discord.Message | None = None,
    bot: Any = None,
    prefix: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Variables:
    """Collect every placeholder this context can resolve."""
    values: dict[str, str] = {}
    values.update(_bot_values(bot))
    values.update(_user_values(user, guild))
    values.update(_server_values(guild, prefix))
    values.update(_channel_values(channel))
    values.update(_message_values(message, bot))

    now = discord.utils.utcnow()
    values.update(
        {
            "date": format_date(now) + f" at {now.strftime('%H:%M')} UTC",
            "time": now.strftime("%H:%M:%S UTC"),
            "timestamp": discord.utils.format_dt(now),
            "newline": "\n",
        }
    )

    if extra:
        values.update({str(k).lower(): str(v) for k, v in extra.items()})

    wrapped = Variables(values)
    wrapped.guild = guild
    return wrapped


def _role_mention(guild: discord.Guild | None, target: str) -> str | None:
    if guild is None or not target:
        return None
    digits = re.sub(r"\D", "", target)
    role = guild.get_role(int(digits)) if digits else None
    if role is None:
        wanted = target.strip().lstrip("@")
        role = discord.utils.find(lambda r: r.name.lower() == wanted.lower(), guild.roles)
    return role.mention if role else None


def render(
    text: str | None,
    variables: Mapping[str, str],
    *,
    guild: discord.Guild | None = None,
) -> str:
    """Replace ``{token}`` placeholders, leaving unknown tokens alone."""
    if not text:
        return ""
    if guild is None:
        guild = getattr(variables, "guild", None)

    lowered = {str(k).lower(): str(v) for k, v in variables.items()}

    def replace(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        target = match.group(2)

        if name in ("embed", "cv2"):
            # Template functions are handled by find_template_tokens().
            return match.group(0)
        if target is not None and name == "role":
            mention = _role_mention(guild, target)
            return mention if mention else match.group(0)
        if target is not None:
            resolved = resolve_target(guild, target)
            if resolved is None:
                return match.group(0)
            value = _user_values(resolved, guild).get(name)
            return value if value is not None else match.group(0)

        value = lowered.get(name)
        return match.group(0) if value is None else value

    return TOKEN_RE.sub(replace, text)


def resolve(
    text: str | None,
    *,
    user: discord.abc.User | discord.Member | None = None,
    guild: discord.Guild | None = None,
    channel: Any = None,
    message: discord.Message | None = None,
    bot: Any = None,
    prefix: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """One-shot helper: collect placeholders for this context and render."""
    variables = build_variables(
        user=user, guild=guild, channel=channel, message=message, bot=bot, prefix=prefix, extra=extra
    )
    return render(text, variables, guild=guild)


def find_template_tokens(text: str | None) -> tuple[str, str | None, str | None]:
    """Split ``{embed:name}`` / ``{cv2:name}`` out of ``text``.

    Returns ``(remaining_text, embed_name, cv2_name)``.
    """
    if not text:
        return "", None, None

    found: dict[str, str] = {}

    def strip(match: re.Match[str]) -> str:
        kind = match.group(1).lower()
        name = match.group(2).strip()
        if name and kind not in found:
            found[kind] = name
        return ""

    remaining = TEMPLATE_TOKEN_RE.sub(strip, text)
    return " ".join(remaining.split()).strip() or "", found.get("embed"), found.get("cv2")


def describe_variables(page: int = 0, page_size: int = 25) -> tuple[list[tuple[str, str]], int]:
    """A page of (token, description) pairs plus the total page count."""
    total_pages = max(1, (len(VARIABLE_DOCS) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return list(VARIABLE_DOCS[start : start + page_size]), total_pages
