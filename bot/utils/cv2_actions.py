"""Execution of Components V2 actions (button clicks and menu picks).

The rules implemented here follow Discord's interaction model:

* the interaction is deferred privately exactly once, so no initial response is
  ever sent twice;
* actions run in the configured order and a failure never stops later actions;
* successful side effects are kept (there is no rollback);
* the final summary is private and only lists changes that really happened;
* a role action that changes nothing is silent: no "you already have it", no
  "you don't have it" and no per-role failure line, so a button with twelve
  roles never answers with twelve complaints. Skipped and refused changes are
  written to the bot log instead, so setup problems stay diagnosable.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

import discord

from utils.cv2_store import ROLE_ACTION_TYPES, placeholders_for, render_text

logger = logging.getLogger(__name__)

MAX_SUMMARY = 1900


def _bullets(items: list[str], limit: int = 5) -> str:
    shown = items[:limit]
    extra = len(items) - len(shown)
    text = "\n".join(f"• {item}" for item in shown)
    if extra > 0:
        text += f"\n• …and {extra} more"
    return text


def _clip(text: str) -> str:
    return text if len(text) <= MAX_SUMMARY else text[: MAX_SUMMARY - 1] + "…"


async def _run_role_action(
    interaction: discord.Interaction,
    action: dict[str, Any],
    added: list[str],
    removed: list[str],
    errors: list[str],
) -> None:
    """Apply one role action.

    Only real changes are reported back to the member. A role that is already
    held (or already absent) is a silent no-op, and a role the bot cannot touch
    is logged instead of answered: role-only buttons should never reply with a
    wall of "not changed" lines.
    """
    guild = interaction.guild
    member = interaction.user
    if (
        guild is None
        or not hasattr(member, "roles")
        or not hasattr(member, "add_roles")
        or not hasattr(member, "remove_roles")
    ):
        errors.append("Role actions only work inside a server.")
        return

    me = guild.me
    for role_id in action["role_ids"]:
        role = guild.get_role(role_id)
        if role is None:
            logger.warning(
                "CV2 role action skipped: role %s in guild %s no longer exists",
                role_id,
                guild.id,
            )
            continue
        if role.is_default() or role.managed:
            logger.warning(
                "CV2 role action skipped: %s (%s) is the default or a managed role",
                role.name,
                role.id,
            )
            continue
        if not me.guild_permissions.manage_roles:
            logger.warning(
                "CV2 role action skipped in guild %s: the bot lacks Manage Roles",
                guild.id,
            )
            continue
        if role >= me.top_role:
            logger.warning(
                "CV2 role action skipped: %s (%s) is above the bot's highest role %s",
                role.name,
                role.id,
                me.top_role.name,
            )
            continue

        has_role = role in member.roles
        try:
            if action["type"] == "role_add":
                if has_role:
                    logger.debug("CV2 role action: %s already has %s", member.id, role.id)
                else:
                    await member.add_roles(role, reason="Components V2 button")
                    added.append(role.mention)
            elif action["type"] == "role_remove":
                if not has_role:
                    logger.debug("CV2 role action: %s does not have %s", member.id, role.id)
                else:
                    await member.remove_roles(role, reason="Components V2 button")
                    removed.append(role.mention)
            else:  # role_toggle
                if has_role:
                    await member.remove_roles(role, reason="Components V2 button")
                    removed.append(role.mention)
                else:
                    await member.add_roles(role, reason="Components V2 button")
                    added.append(role.mention)
        except discord.Forbidden:
            logger.warning(
                "CV2 role action refused for %s by Discord: missing permissions in guild %s",
                role.id,
                guild.id,
            )
        except discord.HTTPException as exc:
            logger.warning(
                "CV2 role action rejected for %s (HTTP %s) in guild %s",
                role.id,
                exc.status,
                guild.id,
            )


async def execute_actions(
    interaction: discord.Interaction,
    actions: Iterable[dict[str, Any]],
    *,
    label: str = "",
    template_name: str = "",
    heading: str | None = None,
) -> None:
    """Run every action in ``actions`` and report the outcome privately.

    ``label`` is the button label (or menu option label) used by the
    ``{button_label}`` placeholder, and ``heading`` is an optional first line
    for the private summary.
    """
    if interaction.guild is None:
        await interaction.response.send_message(
            "These components only work inside a server.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    prefix = None
    try:
        from utils.Tools import getConfig

        prefix = (await getConfig(interaction.guild.id)).get("prefix")
    except Exception:
        prefix = None

    base = placeholders_for(
        interaction.user,
        interaction.guild,
        interaction.channel,
        bot=getattr(interaction, "client", None),
        prefix=prefix,
    )
    base["button_label"] = label
    base["template_name"] = template_name

    added: list[str] = []
    removed: list[str] = []
    notes: list[str] = []
    errors: list[str] = []

    for action in actions:
        kind = action["type"]
        try:
            if kind in ROLE_ACTION_TYPES:
                await _run_role_action(interaction, action, added, removed, errors)

            elif kind == "dm":
                text = render_text(action["message"], base)
                try:
                    await interaction.user.send(text)
                    notes.append("I sent you a direct message.")
                except discord.Forbidden:
                    errors.append("I couldn't DM you — your privacy settings block me.")

            elif kind == "ephemeral":
                notes.append(render_text(action["message"], base))

            elif kind == "channel_message":
                channel = interaction.guild.get_channel(action["channel_id"])
                if channel is None or not hasattr(channel, "send"):
                    errors.append("The configured channel no longer exists.")
                    continue
                await channel.send(render_text(action["message"], base))
                notes.append(f"Message sent to {channel.mention}.")

            elif kind == "link":
                url = render_text(action["url"], base)
                if not url.startswith(("http://", "https://")):
                    errors.append("The configured link is not a valid URL.")
                else:
                    notes.append(f"Link: {url}")
        except discord.HTTPException as exc:
            errors.append(f"`{kind}` failed (Discord error {exc.status}).")
        except Exception as exc:  # never let one action break the rest
            errors.append(f"`{kind}` failed ({type(exc).__name__}).")

    lines: list[str] = []
    if heading:
        lines.append(heading)
    if added:
        lines.append("Your roles have been updated.")
        lines.append("**ROLE ADDED:** " + ", ".join(added))
    if removed:
        if not added:
            lines.append("Your roles have been updated.")
        lines.append("**ROLE REMOVED:** " + ", ".join(removed))
    if notes:
        lines.extend(notes)
    if errors:
        lines.append("**I couldn't complete everything:**")
        lines.append(_bullets(errors))

    if not lines:
        # Nothing changed and there is nothing to say. Role actions that were
        # already satisfied (or refused) stay completely silent, so the click
        # answers with no message at all instead of a list of non-changes.
        return

    await interaction.followup.send(_clip("\n".join(lines)), ephemeral=True)


async def execute_button(
    interaction: discord.Interaction,
    button: dict[str, Any],
    *,
    template_name: str = "",
) -> None:
    """Run every action attached to ``button`` and report the outcome privately."""
    await execute_actions(
        interaction,
        button.get("actions") or [],
        label=button.get("label", ""),
        template_name=template_name,
    )
