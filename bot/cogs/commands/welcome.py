import discord
from utils.emoji import ICONS_CHANNEL, ICONS_PLUS, TICK, ZTICK
from discord.ext import commands
from discord.ui import View, Select, Button
import aiosqlite
import asyncio
import json
from utils.Tools import *
from utils.cv2_store import get_template, list_templates
from utils.greet_render import GreetingError, send_greeting
from utils.varhelp import VariablesView, variables_embed
from utils.variables import find_template_tokens, resolve


class VariableButton(Button):
    def __init__(self, author):
        super().__init__(label="Variables", style=discord.ButtonStyle.secondary)
        self.author = author

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message(
                "Only the command author can use this button.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=variables_embed(0), view=VariablesView(self.author), ephemeral=True
        )

class Welcomer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._create_table())

    async def _create_table(self):
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS welcome (
                guild_id INTEGER PRIMARY KEY,
                welcome_type TEXT,
                welcome_message TEXT,
                channel_id INTEGER,
                embed_data TEXT,
                auto_delete_duration INTEGER
            )
            """)
            await db.commit()

    @commands.hybrid_group(invoke_without_command=True, name="greet", help="Shows all the greet commands.")
    @blacklist_check()
    @ignore_check()
    async def greet(self, ctx: commands.Context):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)

    @greet.command(name="setup", help="Configures a welcome message for new members joining the server. ")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    async def greet_setup(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT * FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
        
        if row:
            error = discord.Embed(description=f"A welcome message has already been set in {ctx.guild.name}. Use `{ctx.prefix}greet reset` to reconfigure.", color=0xFF0000)
            error.set_author(name="Error", icon_url="https://cdn.discordapp.com/emojis/1294218790082711553.png")
            return await ctx.send(embed=error)
            
        options_view = View(timeout=600)

        async def option_callback(interaction: discord.Interaction, button: Button):
            if interaction.user != ctx.author:
                await interaction.response.send_message("You cannot interact with this setup.", ephemeral=True)
                return
            await interaction.response.defer()

            if button.custom_id == "simple":
                await interaction.message.delete()
                await self.simple_setup(ctx)
            elif button.custom_id == "cancel":
                await interaction.message.delete()

        button_simple = Button(label="Text message", style=discord.ButtonStyle.success, custom_id="simple")
        button_simple.callback = lambda interaction: option_callback(interaction, button_simple)
        options_view.add_item(button_simple)

        button_cancel = Button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel")
        button_cancel.callback = lambda interaction: option_callback(interaction, button_cancel)
        options_view.add_item(button_cancel)

        embed = discord.Embed(
            title="Welcome Message Setup",
            description=(
                "Welcome messages are plain text with placeholders such as "
                "`{user}`, `{user_mention}`, `{server_name}` and `{member_count}`."
            ),
            color=0xFF0000
        )

        embed.add_field(
            name="Saved embeds and layouts",
            value=(
                f"Attach a saved embed with `{{embed:name}}` or a Components V2 "
                f"layout with `{{cv2:name}}` inside the message. Create them with "
                f"`{ctx.prefix}embed build` and `{ctx.prefix}cv2 build`."
            ),
            inline=False
        )

        embed.set_footer(text="Click below to enter the message.", icon_url=self.bot.user.display_avatar.url)
        

        await ctx.send(embed=embed, view=options_view)

    def _safe_format(self, ctx, text):
        """Preview/render text with the shared variable engine."""
        return resolve(
            text,
            user=ctx.author,
            guild=ctx.guild,
            channel=ctx.channel,
            bot=ctx.bot,
            prefix=getattr(ctx, "prefix", None),
        )

    def _template_note(self, text):
        """Strip {embed:name}/{cv2:name} and describe what will be attached."""
        stripped, embed_name, cv2_name = find_template_tokens(text)
        notes = []
        if embed_name:
            notes.append(f"embed `{embed_name}`")
        if cv2_name:
            notes.append(f"layout `{cv2_name}`")
        return stripped, (" + " + " + ".join(notes) if notes else "")

    async def simple_setup(self, ctx):
        setup_view = View(timeout=600)
        first = View(timeout=600)
        message_content = []

        def safe_format(text):
            return self._safe_format(ctx, text)

        async def update_preview(content):
            stripped, note = self._template_note(content)
            preview = safe_format(stripped) + note
            await preview_message.edit(content=f"**Preview:** {preview}", view=setup_view)

        first.add_item(VariableButton(ctx.author))

        preview_message = await ctx.send("__**Simple Message Setup**__ \nEnter your welcome message here:", view=first)

        async def submit_callback(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("You cannot interact with this setup.", ephemeral=True)
                return
            if message_content:
                await self._save_welcome_data(ctx.guild.id, "simple", message_content[0])
                await interaction.response.send_message(f"{TICK}> Welcome message setup completed!")
                for item in setup_view.children:
                    item.disabled = True
                await preview_message.edit(view=setup_view)
            else:
                await interaction.response.send_message("No message entered to submit.", ephemeral=True)

        async def edit_callback(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("You cannot interact with this setup.", ephemeral=True)
                return
            await interaction.response.defer()
            await ctx.send("Enter the updated welcome message:")
            try:
                msg = await self.bot.wait_for("message", timeout=600, check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                message_content.clear()
                message_content.append(msg.content)
                await update_preview(msg.content)
            except asyncio.TimeoutError:
                await ctx.send("Editing timed out.")

        async def cancel_callback(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("You cannot interact with this setup.", ephemeral=True)
                return
            await preview_message.delete()

        submit_button = Button(label="Submit", style=discord.ButtonStyle.success)
        submit_button.callback = submit_callback
        setup_view.add_item(submit_button)

        edit_button = Button(label="Edit", style=discord.ButtonStyle.primary)
        edit_button.callback = edit_callback
        setup_view.add_item(edit_button)
        setup_view.add_item(VariableButton(ctx.author))

        cancel_button = Button(emoji=ICONS_PLUS, style=discord.ButtonStyle.secondary)
        cancel_button.callback = cancel_callback
        setup_view.add_item(cancel_button)

        try:
            msg = await self.bot.wait_for("message", timeout=600, check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
            message_content.append(msg.content)
            await update_preview(msg.content)
        except asyncio.TimeoutError:
            await ctx.send("Setup timed out.")

    
    async def _save_welcome_data(self, guild_id, welcome_type, message, embed_data=None):
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute("""
            INSERT OR REPLACE INTO welcome (guild_id, welcome_type, welcome_message, embed_data)
            VALUES (?, ?, ?, ?)
            """, (guild_id, welcome_type, message, json.dumps(embed_data) if embed_data else None))
            await db.commit()

    async def _set_welcome(self, guild_id, welcome_type, message, embed_data=None):
        """Change the response type without dropping the channel / auto-delete settings."""
        payload = json.dumps(embed_data) if embed_data else None
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT 1 FROM welcome WHERE guild_id = ?", (guild_id,)) as cursor:
                exists = await cursor.fetchone()
            if exists:
                await db.execute(
                    "UPDATE welcome SET welcome_type = ?, welcome_message = ?, embed_data = ? WHERE guild_id = ?",
                    (welcome_type, message, payload, guild_id),
                )
            else:
                await db.execute(
                    "INSERT INTO welcome (guild_id, welcome_type, welcome_message, embed_data) VALUES (?, ?, ?, ?)",
                    (guild_id, welcome_type, message, payload),
                )
            await db.commit()

    def _cv2_options(self, rows):
        return [
            discord.SelectOption(
                label=row["name"][:100],
                value=row["name"],
                description=f"{len(row['data'].get('blocks', []))} block(s)",
            )
            for row in rows[:25]
        ]

    @greet.command(name="reset", aliases=["disable"], help="Resets and deletes the current welcome configuration for the server.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    async def greet_reset(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            cursor = await db.execute("SELECT 1 FROM welcome WHERE guild_id = ?", (ctx.guild.id,))
            is_set_up = await cursor.fetchone()

        if not is_set_up: 
            error = discord.Embed(description=f"No welcome message has been set for {ctx.guild.name}! Please set a welcome message first using `{ctx.prefix}greet setup`", color=0xFF0000)
            error.set_author(name="Greet is not configured!", icon_url="https://cdn.discordapp.com/emojis/1294218790082711553.png")
            return await ctx.send(embed=error)
            
        embed = discord.Embed(
            title="Are you sure?",
            description="This will remove all welcome configurations & data related to welcome messages for this server!",
            color=0xFF0000
        )

        yes_button = Button(label="Confirm", style=discord.ButtonStyle.danger)
        no_button = Button(label="Cancel", style=discord.ButtonStyle.secondary)

        async def yes_button_callback(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("Only the command author can confirm this action.", ephemeral=True)
                return

            async with aiosqlite.connect("db/welcome.db") as db:
                await db.execute("DELETE FROM welcome WHERE guild_id = ?", (ctx.guild.id,))
                await db.commit()

            embed.color = discord.Color(0xFF0000)
            embed.title = f"{TICK}> Success"
            embed.description = "Welcome message configuration has been successfully reset."
            await interaction.message.edit(embed=embed, view=None)

        async def no_button_callback(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("Only the command author can cancel this action.", ephemeral=True)
                return

            embed.color = discord.Color(0xFF0000)
            embed.title = "Cancelled"
            embed.description = "Greet Reset operation has been cancelled."
            await interaction.message.edit(embed=embed, view=None)

        yes_button.callback = yes_button_callback
        no_button.callback = no_button_callback

        view = View()
        view.add_item(yes_button)
        view.add_item(no_button)

        await ctx.send(embed=embed, view=view)
        

    @greet.command(name="channel", help="Sets the channel where welcome messages will be sent.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    async def greet_channel(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT welcome_type, channel_id FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                result = await cursor.fetchone()
                welcome_message = result[0] if result else None
                welcome_channel = ctx.guild.get_channel(result[1]) if result and result[1] else None

        if not welcome_message:
            error = discord.Embed(description=f"No welcome message has been set for {ctx.guild.name}! Please set a welcome message first using `{ctx.prefix}greet setup`", color=0xFF0000)
            error.set_author(name="Greet is not configured!", icon_url="https://cdn.discordapp.com/emojis/1294218790082711553.png")
            await ctx.send(embed=error)
            return

        channels = ctx.guild.text_channels
        chunk_size = 25
        chunks = [channels[i:i + chunk_size] for i in range(0, len(channels), chunk_size)]
        current_page = 0

        def generate_view(page):
            select_menu = Select(
                placeholder="Select a channel for welcome messages",
                options=[
                    discord.SelectOption(label=channel.name, emoji=ICONS_CHANNEL, value=str(channel.id))
                    for channel in chunks[page]
                ]
            )

            async def select_callback(interaction: discord.Interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("You are not authorized to set the welcome channel.", ephemeral=True)
                    return

                selected_channel_id = int(select_menu.values[0])
                selected_channel = ctx.guild.get_channel(selected_channel_id)

                async with aiosqlite.connect("db/welcome.db") as db:
                    await db.execute("UPDATE welcome SET channel_id = ? WHERE guild_id = ?", (selected_channel_id, ctx.guild.id))
                    await db.commit()

                embed.description = f"Current Welcome Channel: {selected_channel.mention}"
                await interaction.response.edit_message(embed=embed, view=None)
                await ctx.send(f"{TICK}> Welcome channel has been set to {selected_channel.mention}")

            select_menu.callback = select_callback

            next_button = Button(label="Next List of Channels", style=discord.ButtonStyle.secondary, disabled=page >= len(chunks) - 1)
            previous_button = Button(label="Previous", style=discord.ButtonStyle.secondary, disabled=page <= 0)

            async def next_callback(interaction: discord.Interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("You are not authorized to navigate these menus.", ephemeral=True)
                    return
                nonlocal current_page
                current_page += 1
                await interaction.response.edit_message(embed=embed, view=generate_view(current_page))

            async def previous_callback(interaction: discord.Interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("You are not authorized to navigate these menus.", ephemeral=True)
                    return
                nonlocal current_page
                current_page -= 1
                await interaction.response.edit_message(embed=embed, view=generate_view(current_page))

            next_button.callback = next_callback
            previous_button.callback = previous_callback

            view = View()
            view.add_item(select_menu)
            view.add_item(previous_button)
            view.add_item(next_button)
            return view

        embed = discord.Embed(
            title=f"Welcome Channel for {ctx.guild.name}",
            description=f"Current Welcome Channel: {welcome_channel.mention if welcome_channel else 'None'}",
            color=0xFF0000
        )
        embed.set_footer(text="Use the dropdown menu to select a channel. Navigate pages if needed.")

        await ctx.send(embed=embed, view=generate_view(current_page))



    @greet.command(name="test", help="Sends a test welcome message to preview the setup.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    async def greet_test(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT welcome_type, welcome_message, channel_id, embed_data FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()

        if row is None:
            error = discord.Embed(description=f"No welcome message has been set for {ctx.guild.name}! Please set a welcome message first using `{ctx.prefix}greet setup`", color=0xFF0000)
            error.set_author(name="Greet is not configured!", icon_url="https://cdn.discordapp.com/emojis/1294218790082711553.png")
            await ctx.send(embed=error)
            return

        welcome_type, welcome_message, channel_id, embed_data = row
        welcome_channel = self.bot.get_channel(channel_id)

        if not welcome_channel:
            error2 = discord.Embed(description=f"Welcome channel not set or invalid. Use `{ctx.prefix}greet channel` to set one.", color=0xFF0000)
            error2.set_author(name="Channel not set", icon_url="https://cdn.discordapp.com/emojis/1294218790082711553.png")
            await ctx.send(embed=error2)
            return

        try:
            await send_greeting(
                welcome_channel,
                guild=ctx.guild,
                member=ctx.author,
                channel=welcome_channel,
                welcome_type=welcome_type,
                welcome_message=welcome_message,
                embed_data=embed_data,
                bot=self.bot,
                prefix=ctx.prefix,
            )
        except GreetingError as exc:
            await ctx.send(
                embed=discord.Embed(
                    description=(
                        f"Can't render the welcome message — {exc}. "
                        f"Check `{ctx.prefix}cv2 list` / `{ctx.prefix}embed list`."
                    ),
                    color=0xFF0000,
                )
            )
        except discord.Forbidden:
            await ctx.send(
                embed=discord.Embed(
                    description=f"I can't send messages in {welcome_channel.mention}.", color=0xFF0000
                )
            )



    @greet.command(name="config", help="Shows the current welcome configuration.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    async def greet_config(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT * FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()

        if row:
            _, welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration = row
            response_type = {
                "simple": "Simple",
                "embed": "Embed",
                "cv2": "Components V2",
            }.get(welcome_type, welcome_type.title())

            embed = discord.Embed(
                title=f"Greet Configuration for {ctx.guild.name}",
                color=0xFF0000
            )

            embed.add_field(name="Response Type", value=response_type, inline=False)

            if welcome_type == "simple":
                details = f"Message Content: {welcome_message or 'None'}"
                embed.add_field(name="Details", value=details[:1024], inline=False)
            else:
                embed_details = json.loads(embed_data) if embed_data else {}
                formatted_embed_data = "\n".join(
                    f"{key.replace('_', ' ').title()}: {value or 'None'}" for key, value in embed_details.items()
                ) or "None"

                for i, chunk in enumerate([formatted_embed_data[i:i+1024] for i in range(0, len(formatted_embed_data), 1024)]):
                    embed.add_field(name=f"Layout Data Part {i+1}", value=chunk, inline=False)

            greet_channel = self.bot.get_channel(channel_id)
            channel_display = greet_channel.mention if greet_channel else "None"
            auto_delete_duration = f"{auto_delete_duration} seconds" if auto_delete_duration else "None"

            embed.add_field(name="Greet Channel", value=channel_display, inline=False)
            embed.add_field(name="Auto Delete Duration", value=auto_delete_duration, inline=False)
            await ctx.send(embed=embed)
        else:
            error = discord.Embed(
                description=f"No welcome message has been set for {ctx.guild.name}! Please set a welcome message first using `{ctx.prefix}greet setup`",
                color=0xFF0000
            )
            error.set_author(name="Greet is not configured!", icon_url="https://cdn.discordapp.com/emojis/1294218790082711553.png")
            await ctx.send(embed=error)


    @greet.command(name="autodelete", aliases=["autodel"], help="Sets the auto-delete duration for the welcome message.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    async def greet_autodelete(self, ctx, time: str):
        
        if time.endswith("s"):
            seconds = int(time[:-1])
            if 3 <= seconds <= 300:
                auto_delete_duration = seconds
            else:
                await ctx.send("Auto delete time should be between 3 seconds and 300 seconds.")
                return
        elif time.endswith("m"):
            minutes = int(time[:-1])
            if 1 <= minutes <= 5:
                auto_delete_duration = minutes * 60  
            else:
                await ctx.send("Auto delete time should be between 1 minute and 5 minutes.")
                return
        else:
            await ctx.send("Invalid time format. Please use 's' for seconds and 'm' for minutes.")
            return

        
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute("""
            UPDATE welcome
            SET auto_delete_duration = ?
            WHERE guild_id = ?
            """, (auto_delete_duration, ctx.guild.id))
            await db.commit()

        await ctx.send(f"{ZTICK} Auto delete duration has been set to **{auto_delete_duration}** seconds.")



    @greet.command(name="edit", help="Edits the current welcome message settings for the server.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    async def greet_edit(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT welcome_type, welcome_message, embed_data FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()

        if row is None:
            error = discord.Embed(description=f"No welcome message has been set for {ctx.guild.name}! Please set a welcome message first using `{ctx.prefix}greet setup`", color=0xFF0000)
            error.set_author(name="Greet is not configured!", icon_url="https://cdn.discordapp.com/emojis/1294218790082711553.png")
            await ctx.send(embed=error)
            return

        welcome_type, welcome_message, embed_data = row

        cancel_flag = False  

        if welcome_type == "cv2":
            info = json.loads(embed_data) if embed_data else {}
            current = info.get("template")
            rows = await list_templates(ctx.guild.id)
            if not rows:
                error = discord.Embed(
                    description=f"No Components V2 layouts saved yet. Create one with `{ctx.prefix}cv2 build`.",
                    color=0xFF0000,
                )
                return await ctx.send(embed=error)

            view = View(timeout=600)
            select = Select(placeholder="Choose a new layout", options=self._cv2_options(rows))

            async def switch_callback(interaction: discord.Interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message(
                        "You are not authorized to edit this welcome message.", ephemeral=True
                    )
                    return
                chosen = await get_template(ctx.guild.id, select.values[0])
                if chosen is None:
                    await interaction.response.send_message(
                        "That layout no longer exists.", ephemeral=True
                    )
                    return
                await self._set_welcome(
                    ctx.guild.id, "cv2", "", {"template": chosen["name"]}
                )
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        description=f"{TICK}> Welcome layout switched to `{chosen['name']}`.",
                        color=0x2ECC71,
                    ),
                    view=None,
                )

            select.callback = switch_callback
            view.add_item(select)
            await ctx.send(
                embed=discord.Embed(
                    title="Edit Components V2 welcome",
                    description=f"Current layout: `{current or 'None'}`",
                    color=0xFF0000,
                ),
                view=view,
            )
            return

        if welcome_type == "simple":
            embed = discord.Embed(
                title="Edit Welcome Message",
                description=f"**Response Type:** Simple\n**Message Content:** {welcome_message or 'None'}",
                color=0xFF0000
            )
            edit_button = Button(label="Edit", style=discord.ButtonStyle.primary)
            cancel_button = Button(label="Cancel", style=discord.ButtonStyle.danger)

            async def cancel_button_callback(interaction):
                nonlocal cancel_flag
                if interaction.user != ctx.author:
                    await interaction.response.send_message("You are not authorized to cancel the setup.", ephemeral=True)
                    return
                await interaction.response.send_message("Setup has been canceled.", ephemeral=True)
                cancel_flag = True  
                view.clear_items()  
                await interaction.message.edit(embed=embed, view=view)

            cancel_button.callback = cancel_button_callback

            async def edit_button_callback(interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("You are not authorized to edit the welcome message.", ephemeral=True)
                    return

                await interaction.response.send_message("Please provide the new welcome message:", ephemeral=True)
                try:
                    new_message = await self.bot.wait_for(
                        "message",
                        check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                        timeout=600
                    )
                    if cancel_flag:  
                        await ctx.send("Setup was canceled. No changes were made.")
                        return
                    await new_message.delete()
                    async with aiosqlite.connect("db/welcome.db") as db:
                        await db.execute("UPDATE welcome SET welcome_message = ? WHERE guild_id = ?", (new_message.content, ctx.guild.id))
                        await db.commit()

                    embed.description = f"**Response Type:** Simple\n**Message Content:** {new_message.content}"
                    edit_button.disabled = True
                    cancel_button.disabled = True
                    await interaction.message.edit(embed=embed, view=view)
                    await ctx.send("Welcome message has been successfully updated.")
                except asyncio.TimeoutError:
                    await ctx.send("You took too long to respond.")
                except Exception as e:
                    await ctx.send(f"An error occurred: {e}")

            edit_button.callback = edit_button_callback
            view = View()
            view.add_item(edit_button)
            view.add_item(VariableButton(ctx.author))
            view.add_item(cancel_button)
            
            await ctx.send(embed=embed, view=view)

        elif welcome_type == "embed":
            embed_data_json = json.loads(embed_data) if embed_data else {}
            formatted_embed_data = "\n".join(
                f"{key.replace('_', ' ').title()}: {value or 'None'}" for key, value in embed_data_json.items()
            ) or "None"
            embed = discord.Embed(
                title="Edit Welcome Message",
                description=f"**Response Type:** Embed\n**Embed Data:**\n```{formatted_embed_data}```",
                color=0xFF0000
            )

            select_menu = Select(
                placeholder="Select an embed field to edit",
                options=[
                    discord.SelectOption(label=field.replace('_', ' ').title(), value=field)
                    for field in embed_data_json.keys()
                ]
            )

            cancel_button = Button(label="Cancel", style=discord.ButtonStyle.danger)

            async def cancel_button_callback(interaction):
                nonlocal cancel_flag
                if interaction.user != ctx.author:
                    await interaction.response.send_message("You are not authorized to cancel the setup.", ephemeral=True)
                    return
                await interaction.response.send_message("Setup has been canceled.", ephemeral=True)
                cancel_flag = True  
                view.clear_items()  
                await interaction.message.edit(embed=embed, view=view)

            cancel_button.callback = cancel_button_callback

            async def select_callback(interaction):
                nonlocal cancel_flag
                if interaction.user != ctx.author:
                    await interaction.response.send_message("You are not authorized to edit this embed.", ephemeral=True)
                    return

                selected_option = select_menu.values[0]
                await interaction.response.defer()

                while not cancel_flag:  
                    try:
                        if selected_option == "message":
                            await ctx.send("Enter the welcome message content:")
                            msg = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                            embed_data_json["message"] = msg.content

                        elif selected_option == "title":
                            await ctx.send("Enter the embed title:")
                            msg = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                            embed_data_json["title"] = msg.content

                        elif selected_option == "description":
                            await ctx.send("Enter the embed description:")
                            msg = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                            embed_data_json["description"] = msg.content

                        elif selected_option == "color":
                            await ctx.send("Enter a hex color (e.g., #3498db or 3498db):")
                            msg = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                            color_code = msg.content.lstrip("#")
                            if all(c in "0123456789abcdefABCDEF" for c in color_code) and len(color_code) in {3, 6}:
                                embed_data_json["color"] = int(color_code.lstrip("#"), 16)
                            else:
                                await ctx.send("Invalid color code. Please enter a valid hex color.")
                                continue  

                        elif selected_option in ["footer_text", "footer_icon", "author_name", "author_icon", "thumbnail", "image"]:
                            await ctx.send(f"Enter the URL or text for {selected_option.replace('_', ' ')}:")
                            msg = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                            url_or_text = msg.content
                            if selected_option in ["footer_icon", "author_icon", "thumbnail", "image"]:
                                if url_or_text.startswith("http") or url_or_text in ["{user_avatar}", "{server_icon}"]:
                                    embed_data_json[selected_option] = url_or_text
                                else:
                                    await ctx.send("Invalid URL. Please enter a valid image URL or a supported placeholder ({user_avatar} or {server_icon}).")
                                    continue  
                            else:
                                embed_data_json[selected_option] = url_or_text

                        async with aiosqlite.connect("db/welcome.db") as db:
                            await db.execute("UPDATE welcome SET embed_data = ? WHERE guild_id = ?", (json.dumps(embed_data_json), ctx.guild.id))
                            await db.commit()

                        embed.description = f"**Response Type:** Embed\n**Embed Data:**\n```{json.dumps(embed_data_json, indent=4)}```"
                        await interaction.message.edit(embed=embed, view=None)
                        await ctx.send("Embed data has been successfully updated.")
                        break 
                    except asyncio.TimeoutError:
                        await ctx.send("You took too long to respond.")
                        break
                    except Exception as e:
                        await ctx.send(f"An error occurred: {e}")
                        break

            select_menu.callback = select_callback
            view = View()
            view.add_item(select_menu)
            view.add_item(VariableButton(ctx.author))
            view.add_item(cancel_button)
            
            await ctx.send(embed=embed, view=view)


