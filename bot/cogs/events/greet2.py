import asyncio
import logging

import aiosqlite
import discord
from discord.ext import commands

from utils.Tools import getConfig
from utils.greet_render import GreetingError, send_greeting

log = logging.getLogger("greet")


class greet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.join_queue = {}
        self.processing = set()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.guild.id not in self.join_queue:
            self.join_queue[member.guild.id] = []
        self.join_queue[member.guild.id].append(member)
        if member.guild.id not in self.processing:
            self.processing.add(member.guild.id)
            await self.process_queue(member.guild)

    async def process_queue(self, guild):
        while self.join_queue[guild.id]:
            member = self.join_queue[guild.id].pop(0)

            async with aiosqlite.connect("db/welcome.db") as db:
                async with db.execute(
                    "SELECT welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration FROM welcome WHERE guild_id = ?",
                    (guild.id,),
                ) as cursor:
                    row = await cursor.fetchone()
            if row is None:
                continue

            welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration = row
            welcome_channel = self.bot.get_channel(channel_id)
            if not welcome_channel:
                continue

            try:
                prefix = (await getConfig(guild.id)).get("prefix")
            except Exception:
                prefix = None

            try:
                messages = await send_greeting(
                    welcome_channel,
                    guild=guild,
                    member=member,
                    channel=welcome_channel,
                    welcome_type=welcome_type,
                    welcome_message=welcome_message,
                    embed_data=embed_data,
                    bot=self.bot,
                    prefix=prefix,
                )
            except GreetingError as exc:
                log.warning("greet skipped for guild %s: %s", guild.id, exc)
                continue
            except discord.Forbidden:
                continue
            except discord.HTTPException as exc:
                if exc.code == 50035 or exc.status == 429:
                    await asyncio.sleep(1)
                    self.join_queue[guild.id].append(member)
                    continue
                continue

            if auto_delete_duration:
                for message in messages:
                    try:
                        await message.delete(delay=auto_delete_duration)
                    except discord.HTTPException:
                        pass

            await asyncio.sleep(2)

        self.processing.discard(guild.id)
