"""Embeds: interactive builder, saved templates and variable support.

Bare ``embed`` opens the builder, exactly as before. Templates can be saved per
server and reused with ``embed send <name>`` or inserted into any text with
``{embed:<name>}`` (welcome messages included).

Every text and icon field accepts the variables from ``utils/variables.py`` —
including ``{user_avatar}``, ``{server_icon}`` and ``{bot_avatar}`` in the
thumbnail, image, author icon and footer icon.
"""

from __future__ import annotations

import io
import json
import re
from typing import Any, Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.embed_store import (
    EmbedError,
    FIELD_LABELS,
    delete_embed,
    embed_names,
    empty_embed,
    get_embed,
    init_db,
    list_embeds,
    normalize_embed,
    render_embed,
    save_embed,
)
from utils.emoji import CROSS, TICK
from utils.Tools import blacklist_check, ignore_check
from utils.varhelp import VariablesView, variables_embed
from utils.variables import build_variables, find_template_tokens, render

RED = 0xFF0000

# Fields that read better as a paragraph box.
LONG_FIELDS = ("message", "description")

EDIT_OPTIONS = [
    ("message", "Message content", "Text sent above the embed"),
    ("title", "Title", "Embed title"),
    ("description", "Description", "Main body text"),
    ("color", "Color", "Hex color such as #FF0000"),
    ("author_name", "Author name", "Small text above the title"),
    ("author_icon", "Author icon", "URL or {user_avatar}"),
    ("footer_text", "Footer text", "Small text at the bottom"),
    ("footer_icon", "Footer icon", "URL or {server_icon}"),
    ("thumbnail", "Thumbnail", "Small image on the right"),
    ("image", "Image", "Large image at the bottom"),
    ("timestamp", "Timestamp", "Toggle the time on the embed"),
    ("add_field", "Add field", "Name/value pair inside the embed"),
    ("clear_fields", "Clear fields", "Remove every field from the embed"),
]


def _short(text: str, limit: int = 70) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def embed_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if interaction.guild_id is None:
        return []
    names = await embed_names(interaction.guild_id)
    return [
        app_commands.Choice(name=name, value=name)
        for name in names
        if current.lower() in name.lower()
    ][:25]


# ── Modals ────────────────────────────────────────────────────────────────────


class _EmbedModal(ui.Modal):
    def __init__(self, builder: "EmbedBuilder", *, title: str):
        super().__init__(title=title, timeout=600)
        self.builder = builder

    async def _author_ok(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.builder.ctx.author.id:
            await interaction.response.send_message(
                "This builder belongs to someone else.", ephemeral=True
            )
            return False
        return True

    async def _finish(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self.builder.refresh()


class FieldModal(_EmbedModal):
    def __init__(self, builder: "EmbedBuilder", field: str):
        label = FIELD_LABELS.get(field, field)
        super().__init__(builder, title=f"Edit {label}")
        self.field = field
        current = builder.data.get(field) or ""
        if field == "color" and isinstance(builder.data.get("color"), int):
            current = f"#{builder.data['color']:06X}"

        self.value = ui.TextInput(
            style=discord.TextStyle.paragraph if field in LONG_FIELDS else discord.TextStyle.short,
            default=str(current) or None,
            max_length=4000 if field in LONG_FIELDS else 1024,
            required=field in LONG_FIELDS,
        )
        self.add_item(
            ui.Label(
                text=label,
                description="Variables like {user_name}, {server_icon} and {channel} work here.",
                component=self.value,
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        if not await self._author_ok(interaction):
            return
        raw = self.value.value or ""
        try:
            if self.field == "color":
                self.builder.data["color"] = raw.strip() or None
                normalize_embed(self.builder.data)
            else:
                self.builder.data[self.field] = raw
                normalize_embed(self.builder.data)
        except EmbedError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await self._finish(interaction)


class AddFieldModal(_EmbedModal):
    def __init__(self, builder: "EmbedBuilder"):
        super().__init__(builder, title="Add an embed field")
        self.name = ui.TextInput(max_length=256, required=True)
        self.value = ui.TextInput(style=discord.TextStyle.paragraph, max_length=1024, required=True)
        self.inline = ui.TextInput(placeholder="yes or no", default="no", max_length=3, required=False)
        self.add_item(ui.Label(text="Field name", component=self.name))
        self.add_item(ui.Label(text="Field value", component=self.value))
        self.add_item(ui.Label(text="Inline?", component=self.inline))

    async def on_submit(self, interaction: discord.Interaction):
        if not await self._author_ok(interaction):
            return
        inline = (self.inline.value or "no").strip().lower() in ("yes", "y", "true", "1")
        data = dict(self.builder.data)
        data["fields"] = list(data.get("fields", [])) + [
            {"name": self.name.value, "value": self.value.value, "inline": inline}
        ]
        try:
            clean = normalize_embed(data)
        except EmbedError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        self.builder.data = clean
        await self._finish(interaction)


class SaveNameModal(_EmbedModal):
    def __init__(self, builder: "EmbedBuilder"):
        super().__init__(builder, title="Save embed")
        self.name = ui.TextInput(
            placeholder="rules-embed",
            max_length=60,
            required=True,
        )
        self.add_item(
            ui.Label(
                text="Template name",
                description="Reuse it with `embed send <name>` or `{embed:<name>}`.",
                component=self.name,
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        if not await self._author_ok(interaction):
            return
        await self.builder.save_as(interaction, self.name.value.strip())


class OverwriteView(ui.View):
    def __init__(self, builder: "EmbedBuilder", name: str):
        super().__init__(timeout=120)
        self.builder = builder
        self.name = name

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.builder.ctx.author.id:
            await interaction.response.send_message(
                "This builder belongs to someone else.", ephemeral=True
            )
            return False
        return True

    @ui.button(label="Overwrite", style=discord.ButtonStyle.danger)
    async def overwrite(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content=f"Overwriting `{self.name}`…", view=None)
        await self.builder.persist(interaction, self.name)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Save cancelled.", view=None)


# ── Builder ───────────────────────────────────────────────────────────────────


class EmbedBuilder(ui.LayoutView):
    def __init__(
        self,
        ctx: commands.Context,
        data: dict[str, Any] | None = None,
        *,
        name: str | None = None,
        template_id: int | None = None,
    ):
        super().__init__(timeout=900)
        self.ctx = ctx
        self.bot = ctx.bot
        self.data = data or empty_embed()
        self.name = name
        self.template_id = template_id
        self.target_channel_id: int | None = None
        self.message: discord.Message | None = None
        self.rebuild()

    # -- helpers ------------------------------------------------------------

    def placeholders(self, channel: Any = None):
        return build_variables(
            user=self.ctx.author,
            guild=self.ctx.guild,
            channel=channel or self.ctx.channel,
            bot=self.bot,
            prefix=getattr(self.ctx, "prefix", None),
        )

    def summary(self) -> str:
        data = self.data
        lines = [f"**Name:** `{self.name}`" if self.name else "**Name:** *not saved yet*"]
        lines.append(f"**Color:** `#{data['color']:06X}`" if isinstance(data.get("color"), int) else "**Color:** default")
        for key, label in (("message", "Message"), ("title", "Title"), ("description", "Description")):
            if data.get(key):
                lines.append(f"**{label}:** {_short(data[key], 70)}")
        for key, label in (
            ("author_name", "Author"),
            ("author_icon", "Author icon"),
            ("footer_text", "Footer"),
            ("footer_icon", "Footer icon"),
            ("thumbnail", "Thumbnail"),
            ("image", "Image"),
        ):
            if data.get(key):
                lines.append(f"**{label}:** {_short(data[key], 60)}")
        if data.get("fields"):
            lines.append(f"**Fields:** {len(data['fields'])}")
        if data.get("timestamp"):
            lines.append("**Timestamp:** on")
        if len(lines) == 1:
            lines.append("")
            lines.append("*Nothing set yet — pick a field below to start.*")
        text = "\n".join(lines)
        return text if len(text) <= 3800 else text[:3790] + "…"

    def rebuild(self) -> None:
        self.clear_items()
        container = ui.Container(accent_color=self.data.get("color"))

        container.add_item(ui.TextDisplay("# Embed builder"))
        container.add_item(ui.TextDisplay(self.summary()))

        select = ui.Select(
            placeholder="Edit a field…",
            options=[
                discord.SelectOption(label=label, value=value, description=description)
                for value, label, description in EDIT_OPTIONS
            ],
        )
        select.callback = self.edit_field
        container.add_item(ui.ActionRow(select))

        channel_select = ui.ChannelSelect(
            placeholder="Send target channel (defaults to here)",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        )
        channel_select.callback = self.pick_channel
        container.add_item(ui.ActionRow(channel_select))

        variables = ui.Button(label="Variables", style=discord.ButtonStyle.secondary)
        variables.callback = self.show_variables
        preview = ui.Button(label="Preview", style=discord.ButtonStyle.secondary)
        preview.callback = self.preview_embed
        save = ui.Button(label="Save", style=discord.ButtonStyle.success)
        save.callback = self.save_embed
        send = ui.Button(label="Send", style=discord.ButtonStyle.primary)
        send.callback = self.send_embed
        close = ui.Button(label="Close", style=discord.ButtonStyle.danger)
        close.callback = self.close_builder
        container.add_item(ui.ActionRow(variables, preview, save, send, close))

        self.add_item(container)

    async def refresh(self) -> None:
        self.rebuild()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    # -- callbacks ----------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "This builder belongs to someone else.", ephemeral=True
            )
            return False
        return True

    async def edit_field(self, interaction: discord.Interaction):
        choice = interaction.data["values"][0] if interaction.data else ""

        if choice == "add_field":
            await interaction.response.send_modal(AddFieldModal(self))
            return
        if choice == "clear_fields":
            self.data["fields"] = []
            self.rebuild()
            await interaction.response.edit_message(view=self)
            return
        if choice == "timestamp":
            self.data["timestamp"] = not self.data.get("timestamp")
            self.rebuild()
            await interaction.response.edit_message(view=self)
            return
        if choice in FIELD_LABELS:
            await interaction.response.send_modal(FieldModal(self, choice))
            return
        await interaction.response.send_message("Unknown option.", ephemeral=True)

    async def show_variables(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=variables_embed(0), view=VariablesView(interaction.user), ephemeral=True
        )

    async def preview_embed(self, interaction: discord.Interaction):
        try:
            embed = render_embed(self.data, self.placeholders())
        except EmbedError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def pick_channel(self, interaction: discord.Interaction):
        try:
            channel_id = int(interaction.data["values"][0])
        except (KeyError, IndexError, TypeError, ValueError):
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            await interaction.response.send_message("I can't see that channel.", ephemeral=True)
            return
        self.target_channel_id = channel.id
        await interaction.response.send_message(
            f"Embeds will be sent to {channel.mention}.", ephemeral=True
        )

    async def save_embed(self, interaction: discord.Interaction):
        if not (self.data.get("title") or self.data.get("description") or self.data.get("message")):
            await interaction.response.send_message(
                "Add at least a title, description or message before saving.", ephemeral=True
            )
            return
        if self.name:
            await self.persist(interaction, self.name)
        else:
            await interaction.response.send_modal(SaveNameModal(self))

    async def save_as(self, interaction: discord.Interaction, name: str) -> None:
        existing = await get_embed(self.ctx.guild.id, name)
        if existing and existing["id"] != self.template_id:
            await interaction.response.send_message(
                f"A saved embed named `{existing['name']}` already exists. Overwrite it?",
                view=OverwriteView(self, existing["name"]),
                ephemeral=True,
            )
            return
        await self.persist(interaction, name)

    async def persist(self, interaction: discord.Interaction, name: str) -> None:
        try:
            template_id, created = await save_embed(
                self.ctx.guild.id, name, self.data, self.ctx.author.id
            )
        except EmbedError as exc:
            if interaction.response.is_done():
                await interaction.followup.send(str(exc), ephemeral=True)
            else:
                await interaction.response.send_message(str(exc), ephemeral=True)
            return

        self.template_id = template_id
        self.name = name
        await self.refresh()
        text = f"{TICK} Saved as `{name}`." if created else f"{TICK} Updated `{name}`."
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)

    async def send_embed(self, interaction: discord.Interaction):
        channel = self.bot.get_channel(self.target_channel_id or self.ctx.channel.id)
        if channel is None:
            await interaction.response.send_message(
                "I can't see the target channel.", ephemeral=True
            )
            return
        try:
            placeholders = self.placeholders(channel)
            embed = render_embed(self.data, placeholders)
        except EmbedError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        text, _, _ = find_template_tokens(self.data.get("message", ""))
        content = render(text, placeholders) or None
        try:
            await channel.send(content=content, embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"I can't send messages in {channel.mention}.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"{TICK} Sent to {channel.mention}.", ephemeral=True)

    async def close_builder(self, interaction: discord.Interaction):
        self.stop()
        view = ui.LayoutView(timeout=None)
        view.add_item(
            ui.Container(
                ui.TextDisplay("# Embed builder closed"),
                ui.TextDisplay("Saved embeds stay available with `embed list`."),
            )
        )
        await interaction.response.edit_message(view=view)

    async def on_timeout(self):
        if self.message is None:
            return
        try:
            view = ui.LayoutView(timeout=None)
            view.add_item(
                ui.Container(
                    ui.TextDisplay("# Builder timed out"),
                    ui.TextDisplay("Run `embed` again to continue."),
                )
            )
            await self.message.edit(view=view)
        except discord.HTTPException:
            pass


# ── Cog ───────────────────────────────────────────────────────────────────────


class Embed(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        await init_db()

    @commands.hybrid_group(name="embed", invoke_without_command=True, help="Build, save and send embeds.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 7, commands.BucketType.user)
    async def embed(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self.open_builder(ctx)

    async def open_builder(self, ctx: commands.Context, name: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send("Embeds are server-only.")
            return

        data = None
        template_id = None
        if name:
            row = await get_embed(ctx.guild.id, name)
            if row is None:
                await ctx.send(
                    embed=discord.Embed(
                        description=f"No saved embed named `{name}`. Use `{ctx.prefix}embed list`.",
                        color=RED,
                    )
                )
                return
            data = row["data"]
            template_id = row["id"]
            name = row["name"]

        builder = EmbedBuilder(ctx, data, name=name, template_id=template_id)
        builder.message = await ctx.send(view=builder)

    @embed.command(name="build", help="Create an embed, or edit a saved one by name.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_messages=True)
    @app_commands.autocomplete(name=embed_autocomplete)
    async def embed_build(self, ctx: commands.Context, *, name: Optional[str] = None):
        await self.open_builder(ctx, name)

    @embed.command(name="send", help="Send a saved embed.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_messages=True)
    @app_commands.autocomplete(name=embed_autocomplete)
    async def embed_send(
        self,
        ctx: commands.Context,
        name: str,
        channel: Optional[discord.TextChannel] = None,
    ):
        row = await get_embed(ctx.guild.id, name)
        if row is None:
            return await ctx.send(
                embed=discord.Embed(description=f"No saved embed named `{name}`.", color=RED)
            )
        channel = channel or ctx.channel
        placeholders = build_variables(
            user=ctx.author, guild=ctx.guild, channel=channel, bot=self.bot, prefix=ctx.prefix
        )
        try:
            embed = render_embed(row["data"], placeholders)
        except EmbedError as exc:
            return await ctx.send(embed=discord.Embed(description=str(exc), color=RED))

        text, _, _ = find_template_tokens(row["data"].get("message", ""))
        content = render(text, placeholders) or None
        try:
            await channel.send(content=content, embed=embed)
        except discord.Forbidden:
            return await ctx.send(
                embed=discord.Embed(description=f"I can't send messages in {channel.mention}.", color=RED)
            )
        if channel.id != ctx.channel.id:
            await ctx.send(f"{TICK} Sent `{row['name']}` to {channel.mention}.")

    @embed.command(name="preview", help="Privately preview a saved embed.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_messages=True)
    @app_commands.autocomplete(name=embed_autocomplete)
    async def embed_preview(self, ctx: commands.Context, *, name: str):
        row = await get_embed(ctx.guild.id, name)
        if row is None:
            return await ctx.send(
                embed=discord.Embed(description=f"No saved embed named `{name}`.", color=RED)
            )
        placeholders = build_variables(
            user=ctx.author, guild=ctx.guild, channel=ctx.channel, bot=self.bot, prefix=ctx.prefix
        )
        try:
            embed = render_embed(row["data"], placeholders)
        except EmbedError as exc:
            return await ctx.send(embed=discord.Embed(description=str(exc), color=RED))
        await ctx.send(embed=embed, ephemeral=True)

    @embed.command(name="list", help="List saved embeds.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_messages=True)
    async def embed_list(self, ctx: commands.Context):
        rows = await list_embeds(ctx.guild.id)
        if not rows:
            return await ctx.send(
                embed=discord.Embed(
                    description=f"No saved embeds yet. Run `{ctx.prefix}embed` and press **Save**.",
                    color=RED,
                )
            )
        embed = discord.Embed(
            title=f"Saved embeds · {ctx.guild.name}",
            description=f"{len(rows)} saved embed(s). Use `{ctx.prefix}embed send <name>` or `{{embed:<name>}}`.",
            color=RED,
        )
        for row in rows[:20]:
            embed.add_field(
                name=row["name"],
                value=(
                    f"{row['updated_at'][:16].replace('T', ' ')} · "
                    f"{_short(row['data'].get('title') or row['data'].get('description') or 'untitled', 50)}"
                ),
                inline=True,
            )
        if len(rows) > 20:
            embed.set_footer(text=f"Showing 20 of {len(rows)} embeds.")
        await ctx.send(embed=embed)

    @embed.command(name="edit", help="Open a saved embed in the builder.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_messages=True)
    @app_commands.autocomplete(name=embed_autocomplete)
    async def embed_edit(self, ctx: commands.Context, *, name: str):
        await self.open_builder(ctx, name)

    @embed.command(name="delete", help="Delete a saved embed.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_messages=True)
    @app_commands.autocomplete(name=embed_autocomplete)
    async def embed_delete(self, ctx: commands.Context, *, name: str):
        row = await get_embed(ctx.guild.id, name)
        if row is None:
            return await ctx.send(
                embed=discord.Embed(description=f"No saved embed named `{name}`.", color=RED)
            )
        view = ConfirmDeleteView(ctx, row["name"])
        await ctx.send(
            embed=discord.Embed(
                title="Delete saved embed?",
                description=f"`{row['name']}` will be removed. Messages already sent stay in place.",
                color=RED,
            ),
            view=view,
        )

    @embed.command(name="export", help="Download a saved embed as JSON.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_messages=True)
    @app_commands.autocomplete(name=embed_autocomplete)
    async def embed_export(self, ctx: commands.Context, *, name: str):
        row = await get_embed(ctx.guild.id, name)
        if row is None:
            return await ctx.send(
                embed=discord.Embed(description=f"No saved embed named `{name}`.", color=RED)
            )
        payload = json.dumps(row["data"], indent=2, ensure_ascii=False)
        file = discord.File(
            io.BytesIO(payload.encode("utf-8")),
            filename=f"{re.sub(r'[^A-Za-z0-9_-]+', '-', row['name'])}.embed.json",
        )
        await ctx.send(file=file)

    @embed.command(name="import", help="Upload a saved embed from JSON.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(manage_messages=True)
    async def embed_import(
        self,
        ctx: commands.Context,
        name: str,
        attachment: Optional[discord.Attachment] = None,
    ):
        if attachment is None:
            if ctx.message.attachments:
                attachment = ctx.message.attachments[0]
            else:
                return await ctx.send(
                    embed=discord.Embed(
                        description="Attach a `.json` embed, or reply to one.", color=RED
                    )
                )
        if attachment.size > 256 * 1024:
            return await ctx.send(embed=discord.Embed(description="That file is too large.", color=RED))

        raw = await attachment.read()
        try:
            data = normalize_embed(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return await ctx.send(
                embed=discord.Embed(description="That file is not valid JSON.", color=RED)
            )
        except EmbedError as exc:
            return await ctx.send(embed=discord.Embed(description=str(exc), color=RED))

        if await get_embed(ctx.guild.id, name):
            return await ctx.send(
                embed=discord.Embed(
                    description=f"`{name}` already exists. Delete it or choose another name.",
                    color=RED,
                )
            )

        try:
            _, created = await save_embed(ctx.guild.id, name, data, ctx.author.id)
        except EmbedError as exc:
            return await ctx.send(embed=discord.Embed(description=str(exc), color=RED))

        await ctx.send(
            f"{TICK} Imported `{name}`."
            if created
            else f"{TICK} Updated `{name}`."
        )


class ConfirmDeleteView(ui.View):
    def __init__(self, ctx: commands.Context, name: str):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.name = name

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Only the command author can confirm this.", ephemeral=True
            )
            return False
        return True

    @ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        deleted = await delete_embed(self.ctx.guild.id, self.name)
        text = (
            f"{TICK} Deleted `{self.name}`."
            if deleted
            else f"{CROSS} `{self.name}` was already gone."
        )
        await interaction.response.edit_message(
            embed=discord.Embed(description=text, color=RED), view=None
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(description="Delete cancelled.", color=RED), view=None
        )
