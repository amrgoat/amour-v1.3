import discord
import aiosqlite
import json
import asyncio
import os
from discord.ext import commands
from typing import Optional

RED_THEME_COLOR = 0xFF0000

class StickyMessage(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        asyncio.create_task(self.setup_database())

    async def setup_database(self):
        if not os.path.exists("db"):
            os.makedirs("db")
            
        async with aiosqlite.connect("db/stickymessages.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sticky_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_type TEXT DEFAULT 'plain',
                    message_content TEXT,
                    embed_data TEXT,
                    last_message_id INTEGER,
                    enabled BOOLEAN DEFAULT 1,
                    delay_seconds INTEGER DEFAULT 2,
                    auto_delete_after INTEGER DEFAULT 0,
                    ignore_bots BOOLEAN DEFAULT 1,
                    ignore_commands BOOLEAN DEFAULT 1,
                    trigger_count INTEGER DEFAULT 1,
                    current_count INTEGER DEFAULT 0,
                    UNIQUE(guild_id, channel_id)
                )
            """)
            await db.commit()

    @commands.group(aliases=['sticky', 'sm'], invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def stickymessage(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @stickymessage.command(name='setup')
    @commands.has_permissions(manage_messages=True)
    async def sticky_setup(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        async with aiosqlite.connect("db/stickymessages.db") as db:
            cursor = await db.execute("SELECT 1 FROM sticky_messages WHERE channel_id = ?", (channel.id,))
            if await cursor.fetchone():
                embed = discord.Embed(title="Setup Error", description=f"A sticky message already exists in {channel.mention}.", color=RED_THEME_COLOR)
                return await ctx.send(embed=embed)
        
        embed = discord.Embed(
            title="Sticky Message Setup",
            description=(
                f"Sticky messages for {channel.mention} are plain text and support "
                "placeholders like `{user}`, `{user_mention}` and `{server_name}`.\n\n"
                "Attach a saved embed with `{embed:name}` or a Components V2 layout "
                f"with `{{cv2:name}}`. Create them with `{ctx.prefix}embed build` and "
                f"`{ctx.prefix}cv2 build`."
            ),
            color=RED_THEME_COLOR,
        )
        await ctx.send(embed=embed, view=StickySetupView(ctx, channel))

    @stickymessage.command(name='remove', aliases=['delete', 'del'])
    @commands.has_permissions(manage_messages=True)
    async def sticky_remove(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        async with aiosqlite.connect("db/stickymessages.db") as db:
            cursor = await db.execute("SELECT last_message_id FROM sticky_messages WHERE channel_id = ?", (channel.id,))
            data = await cursor.fetchone()
            if not data:
                return await ctx.send(embed=discord.Embed(title="Not Found", description=f"No sticky message found in {channel.mention}.", color=RED_THEME_COLOR))
            
            if data[0]:
                try:
                    msg = await channel.fetch_message(data[0])
                    await msg.delete()
                except discord.NotFound:
                    pass
            
            await db.execute("DELETE FROM sticky_messages WHERE channel_id = ?", (channel.id,))
            await db.commit()

        embed = discord.Embed(title="Success", description=f"Sticky message in {channel.mention} has been removed.", color=RED_THEME_COLOR)
        await ctx.send(embed=embed)

    @stickymessage.command(name='list')
    @commands.has_permissions(manage_messages=True)
    async def sticky_list(self, ctx: commands.Context):
        async with aiosqlite.connect("db/stickymessages.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM sticky_messages WHERE guild_id = ?", (ctx.guild.id,))
            stickies = await cursor.fetchall()

        if not stickies:
            return await ctx.send(embed=discord.Embed(title="No Stickies Found", description="There are no active sticky messages on this server.", color=RED_THEME_COLOR))

        embed = discord.Embed(title=f"Sticky Messages in {ctx.guild.name}", color=RED_THEME_COLOR)
        for sticky in stickies:
            channel = self.bot.get_channel(sticky['channel_id'])
            status = "✅ Enabled" if sticky['enabled'] else "❌ Disabled"
            embed.add_field(
                name=f"#{channel.name if channel else 'Unknown Channel'}",
                value=f"**Type**: {sticky['message_type'].title()}\n**Status**: {status}\n**Delay**: {sticky['delay_seconds']}s",
                inline=True
            )
        await ctx.send(embed=embed)

    @stickymessage.command(name='edit')
    @commands.has_permissions(manage_messages=True)
    async def sticky_edit(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        async with aiosqlite.connect("db/stickymessages.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM sticky_messages WHERE channel_id = ?", (channel.id,))
            sticky_data = await cursor.fetchone()
        
        if not sticky_data:
            return await ctx.send(embed=discord.Embed(title="Not Found", description=f"No sticky message found in {channel.mention}.", color=RED_THEME_COLOR))

        embed = discord.Embed(title="Edit Sticky Message", description=f"Editing sticky for {channel.mention}. Choose an option:", color=RED_THEME_COLOR)
        await ctx.send(embed=embed, view=StickyEditView(ctx, channel, sticky_data))

class AuthorOnlyView(discord.ui.View):
    def __init__(self, ctx: commands.Context, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You are not authorized to use this.", ephemeral=True)
            return False
        return True
    
    async def on_timeout(self):
        try:
            for item in self.children:
                item.disabled = True
            if hasattr(self, 'message'):
                await self.message.edit(view=self)
        except discord.NotFound:
            pass

class StickySetupView(AuthorOnlyView):
    def __init__(self, ctx: commands.Context, channel: discord.TextChannel):
        super().__init__(ctx)
        self.channel = channel

    @discord.ui.button(label='Plain Text', style=discord.ButtonStyle.primary, emoji='📝')
    async def plain_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlainTextModal(self.ctx, self.channel))

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Cancelled", description="Sticky message setup has been cancelled.", color=RED_THEME_COLOR)
        await interaction.response.edit_message(embed=embed, view=None)

class PlainTextModal(discord.ui.Modal, title='Plain Text Sticky Message'):
    def __init__(self, ctx: commands.Context, channel: discord.TextChannel):
        super().__init__()
        self.ctx = ctx
        self.channel = channel

    message_content = discord.ui.TextInput(label='Message Content', style=discord.TextStyle.long, required=True, max_length=2000)
    delay_seconds = discord.ui.TextInput(label='Delay (seconds)', default='2', required=False, max_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            delay = int(self.delay_seconds.value or "2")
        except ValueError:
            delay = 2

        async with aiosqlite.connect("db/stickymessages.db") as db:
            await db.execute(
                "INSERT INTO sticky_messages (guild_id, channel_id, message_type, message_content, delay_seconds) VALUES (?, ?, ?, ?, ?)",
                (self.ctx.guild.id, self.channel.id, 'plain', self.message_content.value, delay)
            )
            await db.commit()

        embed = discord.Embed(title="Sticky Created", description=f"Successfully created a plain text sticky in {self.channel.mention}.", color=RED_THEME_COLOR)
        await interaction.response.edit_message(embed=embed, view=None)

class StickyEditView(AuthorOnlyView):
    def __init__(self, ctx: commands.Context, channel: discord.TextChannel, sticky_data):
        super().__init__(ctx)
        self.channel = channel
        self.sticky_data = sticky_data

    @discord.ui.button(label='Edit Content', style=discord.ButtonStyle.primary)
    async def edit_content(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.sticky_data['message_type'] == 'plain':
            await interaction.response.send_modal(EditPlainTextModal(self.ctx, self.channel, self.sticky_data))
        else:
            await interaction.response.send_modal(EditEmbedModal(self.ctx, self.channel, self.sticky_data))

    @discord.ui.button(label='Edit Settings', style=discord.ButtonStyle.secondary)
    async def edit_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditSettingsModal(self.ctx, self.channel, self.sticky_data))

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Cancelled", description="Editing has been cancelled.", color=RED_THEME_COLOR)
        await interaction.response.edit_message(embed=embed, view=None)

class EditPlainTextModal(discord.ui.Modal, title='Edit Plain Text Content'):
    def __init__(self, ctx: commands.Context, channel: discord.TextChannel, sticky_data):
        super().__init__()
        self.ctx = ctx
        self.channel = channel
        self.message_content = discord.ui.TextInput(
            label='Message Content',
            style=discord.TextStyle.long,
            default=sticky_data['message_content'],
            max_length=2000
        )
        self.add_item(self.message_content)

    async def on_submit(self, interaction: discord.Interaction):
        async with aiosqlite.connect("db/stickymessages.db") as db:
            await db.execute(
                "UPDATE sticky_messages SET message_content = ? WHERE channel_id = ?",
                (self.message_content.value, self.channel.id)
            )
            await db.commit()
        embed = discord.Embed(title="Content Updated", description="The sticky message content has been updated.", color=RED_THEME_COLOR)
        await interaction.response.edit_message(embed=embed, view=None)

class EditEmbedModal(discord.ui.Modal, title='Edit Embed Content'):
    def __init__(self, ctx: commands.Context, channel: discord.TextChannel, sticky_data):
        super().__init__()
        self.ctx = ctx
        self.channel = channel
        embed_data = json.loads(sticky_data['embed_data'])
        
        # Never name these ``title``/``description``: ``Modal.title`` is the modal
        # heading (a str), so a TextInput there would overwrite it and
        # ``self.title.value`` would fail on submit.
        self.title_input = discord.ui.TextInput(label='Embed Title', default=embed_data.get('title', ''), required=False, max_length=256)
        self.description_input = discord.ui.TextInput(label='Embed Description', style=discord.TextStyle.long, default=embed_data.get('description', ''), required=True, max_length=4000)
        self.footer_input = discord.ui.TextInput(label='Embed Footer', default=embed_data.get('footer', ''), required=False, max_length=2048)

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction):
        embed_data = {
            "title": self.title_input.value, "description": self.description_input.value,
            "color": f"#{RED_THEME_COLOR:06x}", "footer": self.footer_input.value
        }
        async with aiosqlite.connect("db/stickymessages.db") as db:
            await db.execute(
                "UPDATE sticky_messages SET embed_data = ? WHERE channel_id = ?",
                (json.dumps(embed_data), self.channel.id)
            )
            await db.commit()
        embed = discord.Embed(title="Embed Updated", description="The sticky embed content has been updated.", color=RED_THEME_COLOR)
        await interaction.response.edit_message(embed=embed, view=None)
        
class EditSettingsModal(discord.ui.Modal, title='Edit Sticky Settings'):
    def __init__(self, ctx: commands.Context, channel: discord.TextChannel, sticky_data):
        super().__init__()
        self.ctx = ctx
        self.channel = channel

        self.delay_seconds = discord.ui.TextInput(label='Delay (seconds)', default=str(sticky_data['delay_seconds']), max_length=3)
        self.auto_delete_after = discord.ui.TextInput(label='Auto-delete (seconds, 0=off)', default=str(sticky_data['auto_delete_after']), max_length=4)
        self.trigger_count = discord.ui.TextInput(label='Trigger After X Msgs', default=str(sticky_data['trigger_count']), max_length=2)
        
        self.add_item(self.delay_seconds)
        self.add_item(self.auto_delete_after)
        self.add_item(self.trigger_count)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            delay = int(self.delay_seconds.value)
            auto_del = int(self.auto_delete_after.value)
            trigger = int(self.trigger_count.value)
        except ValueError:
            return await interaction.response.send_message("Please enter valid numbers.", ephemeral=True)

        async with aiosqlite.connect("db/stickymessages.db") as db:
            await db.execute(
                "UPDATE sticky_messages SET delay_seconds = ?, auto_delete_after = ?, trigger_count = ? WHERE channel_id = ?",
                (delay, auto_del, trigger, self.channel.id)
            )
            await db.commit()
        embed = discord.Embed(title="Settings Updated", description="The sticky message settings have been updated.", color=RED_THEME_COLOR)
        await interaction.response.edit_message(embed=embed, view=None)

async def setup(bot: commands.Bot):
    await bot.add_cog(StickyMessage(bot))