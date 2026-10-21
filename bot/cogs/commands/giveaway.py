from discord.ext import commands, tasks
import datetime, pytz, time as t
from discord.ui import Button, Select, View
import aiosqlite, random, re, typing
import sqlite3
import asyncio
import discord, logging
from utils.emoji import TADAA, TICK, guild_emoji, DOT, GIFT
from discord.utils import get
from utils.Tools import *
import os
import aiohttp
from utils.cv2 import CV2

# Giveaway message look — the banner is still looked up by name in the guild
# (:amour_giveaway:), while the gift and dot use the shared global emoji
# (`GIFT` / `DOT`) with a per-guild override when a server uploaded its own.
GIVEAWAY_EMOJI = "amour_giveaway"
GIVEAWAY_GIFT = "st_gift"
GIVEAWAY_DOT = "green_dot"
GIVEAWAY_COLOR = 0x2B2D31

GIVEAWAY_ADMIN_ID = 631428835405070347


def is_giveaway_admin(bot, user_id) -> bool:
    """True for the hardcoded giveaway admin and for the bot's own owners."""
    try:
        return int(user_id) == GIVEAWAY_ADMIN_ID or is_bot_owner(bot, user_id)
    except (TypeError, ValueError):
        return False


def giveaway_manager_check():
    """Manage Server (or Administrator) in the guild the giveaway lives in.

    Neither the hardcoded giveaway admin nor the bot-owner shortcut is granted
    here on purpose: that account is only meant to pick winners with `gsetw`.
    Ending a giveaway is ordinary server management, so it needs real guild
    permissions and cannot be run from DMs.
    """

    async def predicate(ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        perms = getattr(ctx.author, "guild_permissions", None)
        if perms is None or not (perms.manage_guild or perms.administrator):
            raise commands.MissingPermissions(["manage_guild"])
        return True

    return commands.check(predicate)


def _footer_time(timestamp: float) -> str:
    """Human readable end time for the footer.

    Discord renders ``<t:…>`` timestamps in message text, but not inside an
    embed footer, so the footer gets a plain date/time instead.
    """
    moment = datetime.datetime.fromtimestamp(float(timestamp), datetime.timezone.utc)
    clock = moment.strftime("%I:%M %p").lstrip("0")
    if moment.date() == datetime.datetime.now(datetime.timezone.utc).date():
        return f"Today at {clock}"
    return moment.strftime("%b %d, %Y at ") + clock


def giveaway_message(guild, prize, winners_text, ends_at, host_id, *, ended: bool):
    """Build the (content, embed) pair used for a giveaway message."""
    banner = guild_emoji(guild, GIVEAWAY_EMOJI, "🎉")
    gift = guild_emoji(guild, GIVEAWAY_GIFT, GIFT)
    dot = guild_emoji(guild, GIVEAWAY_DOT, DOT)

    state = "Giveaway Ended" if ended else "Giveaway Started"
    content = f"{banner} **{state}** {banner}"

    ends = int(float(ends_at))
    title = f"{gift} **{prize}** {gift}"
    if len(title) > 256:  # Discord's embed title limit
        title = title[:255] + "…"
    embed = discord.Embed(
        title=title,
        description=(
            f"{dot} Winners: {winners_text}\n"
            f"{dot} Ends: <t:{ends}:R> (<t:{ends}:f>)\n"
            f"{dot} Hosted by: <@{int(host_id)}>\n"
            f"{dot} React with {TADAA} to participate!"
        ),
        color=GIVEAWAY_COLOR,
    )
    embed.set_footer(text=f"Ends | {_footer_time(ends)}")
    return content, embed


db_folder = 'db'
db_file = 'giveaways.db'
db_path = os.path.join(db_folder, db_file)
connection = sqlite3.connect(db_path)

cursor = connection.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS Giveaway (
                    guild_id INTEGER,
                    host_id INTEGER,
                    start_time TIMESTAMP,
                    ends_at TIMESTAMP,
                    prize TEXT,
                    winners INTEGER,
                    message_id INTEGER,
                    channel_id INTEGER,
                    forced_winners TEXT,
                    PRIMARY KEY (guild_id, message_id)
                )''')

# Databases created before forced winners existed get the column added in place.
try:
    cursor.execute("ALTER TABLE Giveaway ADD COLUMN forced_winners TEXT")
except sqlite3.OperationalError:
    pass

connection.commit()
connection.close()

# Column order every SELECT in this cog uses.
GIVEAWAY_SELECT = (
    "SELECT ends_at, guild_id, message_id, host_id, winners, prize, channel_id, "
    "forced_winners FROM Giveaway"
)


def _giveaway_row(row) -> list:
    """Positional row padded to 8 columns so old/partial rows stay safe."""
    values = list(row or ())
    return values + [None] * (8 - len(values))


def _parse_id_list(raw) -> list[int]:
    """Comma/space separated ids -> de-duplicated ints (order kept)."""
    ids: list[int] = []
    for token in re.findall(r"\d{15,25}", str(raw or "")):
        uid = int(token)
        if uid not in ids:
            ids.append(uid)
    return ids


def _winner_text(forced_ids, participants, slots) -> str | None:
    """Winner mention list: forced winners first, otherwise a random draw.

    ``None`` means nobody can win (forced list empty and no participants).
    """
    if forced_ids:
        return ", ".join(f"<@{uid}>" for uid in forced_ids)
    if not participants:
        return None
    count = min(len(participants), max(int(slots), 1))
    return ", ".join(f"<@!{uid}>" for uid in random.sample(participants, k=count))

def convert(time):
    pos = ["s","m","h","d"]
    time_dict = {"s" : 1, "m" : 60, "h" : 3600 , "d" : 86400 , "f" : 259200}
    unit = time[-1]
    if unit not in pos:
        return
    try:
        val = int(time[:-1])
    except ValueError:
        return
    return val * time_dict[unit]

def WinnerConverter(winner):
    try:
        int(winner)
    except ValueError:
        try:
           return int(winner[:-1])
        except:
            return -4
    return winner

class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.connection = await aiosqlite.connect(db_path)
        self.cursor = await self.connection.cursor()
        await self.check_for_ended_giveaways() 
        self.GiveawayEnd.start()

    async def cog_unload(self) -> None:
        await self.connection.close()

    async def _participants(self, message) -> list[int]:
        """Everyone who reacted, without the bot's own reaction.

        A giveaway can end with no reactions at all (deleted reaction, raid, or
        a message edited by hand), so callers get an empty list instead of an
        IndexError/ValueError.
        """
        if not message.reactions:
            return []
        users = [user.id async for user in message.reactions[0].users()]
        if self.bot.user and self.bot.user.id in users:
            users.remove(self.bot.user.id)
        return users

    async def _delete_row(self, message_id: int, guild_id: int) -> None:
        await self.cursor.execute(
            "DELETE FROM Giveaway WHERE message_id = ? AND guild_id = ?",
            (int(message_id), int(guild_id)),
        )
        await self.connection.commit()

    async def _fetch_giveaway_message(self, channel, message_id: int, guild_id: int):
        """Fetch the giveaway message; drops the row and returns None if it's gone."""
        retries = 3
        for attempt in range(retries):
            try:
                return await channel.fetch_message(int(message_id))
            except discord.NotFound:
                await self._delete_row(message_id, guild_id)
                return None
            except aiohttp.ClientResponseError as e:
                if e.status == 503 and attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
        return None

    async def _notify_admin(self, text: str) -> None:
        """DM the hardcoded giveaway admin. Closed DMs are silently ignored."""
        try:
            user = self.bot.get_user(GIVEAWAY_ADMIN_ID)
            if user is None:
                user = await self.bot.fetch_user(GIVEAWAY_ADMIN_ID)
            await user.send(text)
        except (discord.HTTPException, AttributeError, TypeError):
            pass

    async def _panel(self, ctx, title: str, body: str):
        """CV2 panel in a guild, plain embed in DMs (CV2 needs a guild message)."""
        if ctx.guild is None:
            return await ctx.send(
                embed=discord.Embed(title=title, description=body, color=GIVEAWAY_COLOR)
            )
        return await ctx.send(view=CV2(title, body))

    async def check_for_ended_giveaways(self):
        await self.cursor.execute(GIVEAWAY_SELECT + " WHERE ends_at <= ?", (datetime.datetime.now().timestamp(),))
        ended_giveaways = await self.cursor.fetchall()
        for giveaway in ended_giveaways:
            await self.end_giveaway(giveaway)

    async def end_giveaway(self, giveaway):
        ends_raw, guild_id, message_id, host_id, slots, prize, channel_id, forced_raw = _giveaway_row(giveaway)
        try:
            current_time = datetime.datetime.now().timestamp()
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                await self._delete_row(message_id, guild_id)
                return

            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                return

            try:
                message = await self._fetch_giveaway_message(channel, message_id, guild_id)
                if message is None:
                    return

                # Winners forced with `gsetw` win here, whenever the giveaway ends.
                forced = _parse_id_list(forced_raw)
                participants = [] if forced else await self._participants(message)
                ends_at = float(ends_raw or current_time)
                winner = _winner_text(forced, participants, slots)

                if winner is None:
                    content, embed = giveaway_message(
                        guild, prize, "No valid participants",
                        ends_at, host_id, ended=True,
                    )
                    try:
                        await message.edit(content=content, embed=embed, view=None)
                    except discord.HTTPException:
                        pass
                    await self._delete_row(message_id, guild_id)
                    try:
                        await message.reply(f"No one won the **{prize}** giveaway, due to Not enough participants.")
                    except discord.HTTPException:
                        pass
                    await self._notify_admin(
                        f"⚪ **Giveaway ended with no winners** in **{guild.name}**\n"
                        f"Prize: **{prize}**\n{message.jump_url}"
                    )
                    return

                content, embed = giveaway_message(
                    guild, prize, winner, ends_at, host_id, ended=True
                )
                await message.edit(content=content, embed=embed, view=None)
                await self._delete_row(message_id, guild_id)
                try:
                    await message.reply(f"{TADAA} Congrats {winner}, you won **{prize}!**, Hosted by <@{int(host_id)}>")
                except discord.HTTPException:
                    pass

                forced_note = "\nWinners were forced with `gsetw`." if forced else ""
                await self._notify_admin(
                    f"🎉 **Giveaway ended** in **{guild.name}**\n"
                    f"Prize: **{prize}**\n"
                    f"Winner(s): {winner}{forced_note}\n{message.jump_url}"
                )

            except (discord.HTTPException, aiohttp.ClientResponseError) as e:
                logging.error(f"Error ending giveaway: {e}")

        except (IndexError, TypeError, ValueError):
            logging.error(f"Giveaway data is corrupted or missing: {giveaway}")
            try:
                await self._delete_row(message_id, guild_id)
            except Exception:
                pass

    @tasks.loop(seconds=5)
    async def GiveawayEnd(self):
        await self.cursor.execute(GIVEAWAY_SELECT + " WHERE ends_at <= ?", (datetime.datetime.now().timestamp(),))
        ends_raw = await self.cursor.fetchall()
        for giveaway in ends_raw:
            await self.end_giveaway(giveaway)




    @commands.hybrid_command(description="Starts a new giveaway.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    async def gstart(self, ctx,
                      time,
                      winners: int,
                      *,
                      prize: str):

        await self.cursor.execute("SELECT message_id, channel_id FROM Giveaway WHERE guild_id = ?", (ctx.guild.id,))
        re = await self.cursor.fetchall()

        if winners < 1:
            message = await ctx.send(view=CV2("❌ Error", "Winner count must be at least **1**."))
            await asyncio.sleep(5)
            await message.delete()
            return

        if winners >=  15:
            message = await ctx.send(view=CV2("⚠️ Access Denied", "Cannot exceed more than 15 winners."))
            await asyncio.sleep(5)
            await message.delete()
            return

        g_list = [i[0] for i in re]
        if len(g_list) >= 5:
            message = await ctx.send(view=CV2("⚠️ Access Denied", "You can only host upto 5 giveaways in this Guild."))
            await asyncio.sleep(5)
            await message.delete()
            return

        converted = self.convert(time)
        if converted / 60 >= 50400:
            message = await ctx.send(view=CV2("⚠️ Access Denied", "Time cannot exceed 31 days!"))
            await asyncio.sleep(5)
            await message.delete()
            return

        if converted == -1:
            message = await ctx.send(view=CV2("❌ Error", "Invalid time format"))
            await asyncio.sleep(5)
            await message.delete()
            return
        if converted == -2:
            message = await ctx.send(view=CV2("❌ Error", "Invalid time format. Please provide the time in numbers."))
            await asyncio.sleep(5)
            await message.delete()
            return

        ends = (datetime.datetime.now().timestamp() + converted)

        content, embed = giveaway_message(
            ctx.guild, prize, f"**{winners}**", ends, ctx.author.id, ended=False
        )

        message = await ctx.send(content=content, embed=embed)
        try:
           await ctx.message.delete()
        except:
            pass

        await self.cursor.execute("INSERT INTO Giveaway(guild_id, host_id, start_time, ends_at, prize, winners, message_id, channel_id) VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (ctx.guild.id, ctx.author.id, datetime.datetime.now(), ends, prize, winners, message.id, ctx.channel.id))

        await message.add_reaction(TADAA)
        await self.connection.commit()

        # The giveaway admin always hears about a new giveaway, whichever guild
        # it was hosted in, with a ready-to-copy `gsetw` line.
        await self._notify_admin(
            f"🎉 **Giveaway started** in **{ctx.guild.name}**\n"
            f"Prize: **{prize}**\n"
            f"Winners: **{winners}**\n"
            f"Ends: <t:{int(ends)}:R> (<t:{int(ends)}:f>)\n"
            f"Hosted by: <@{ctx.author.id}>\n"
            f"Channel: {ctx.channel.mention}\n\n"
            f"Quick set winner: `gsetw {message.id} <user id>`\n"
            f"{message.jump_url}"
        )

    
                                    

    @commands.Cog.listener("on_message_delete")
    async def GiveawayMessageDelete(self, message):
        if message.guild is None:
            return
        await self.cursor.execute("SELECT message_id FROM Giveaway WHERE guild_id = ?", (message.guild.id,))
        re = await self.cursor.fetchone()

        if message.author != self.bot.user:
            return

        if re is not None:
            if message.id == int(re[0]):
                await self.cursor.execute("DELETE FROM Giveaway WHERE channel_id = ? AND message_id = ? AND guild_id = ?", (message.channel.id, message.id, message.guild.id))

                print(f"Giveaway message deleted in {message.guild.name} - {message.guild.id}")
                await self.connection.commit()

    @commands.hybrid_command(name="gend", description="Ends a giveaway before its ending time.", help="Ends a giveaway before its ending time.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @giveaway_manager_check()
    async def gend(self, ctx, message_id = None):
        """End a running giveaway right now.

        Needs Manage Server: the hardcoded giveaway admin only gets `gsetw`.
        """
        if message_id is not None and not str(message_id).strip().isdigit():
            return await self._panel(ctx, "⚠️ Access Denied", "Invalid message ID provided.")

        if message_id is None:
            # Slash invocations have no message to reply to.
            reference = getattr(ctx.message, "reference", None)
            if reference is None:
                return await self._panel(
                    ctx, "End Giveaway",
                    "Reply to the giveaway message or pass its message ID.",
                )
            resolved = reference.resolved
            message_id = getattr(resolved, "id", None) or reference.message_id

        mid = int(message_id)
        current_time = datetime.datetime.now().timestamp()
        await self.cursor.execute(GIVEAWAY_SELECT + " WHERE message_id = ?", (mid,))
        row = await self.cursor.fetchone()
        if row is None:
            return await self._panel(ctx, "❌ Error", f"No running giveaway has message ID `{mid}`.")

        ends_raw, guild_id, db_message_id, host_id, slots, prize, channel_id, forced_raw = _giveaway_row(row)
        guild = self.bot.get_guild(int(guild_id)) or ctx.guild
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except discord.HTTPException:
                channel = None
        if channel is None:
            return await self._panel(
                ctx, "❌ Error",
                "I can't see the channel that giveaway was posted in. Check my permissions and try again.",
            )

        message = await self._fetch_giveaway_message(channel, db_message_id, guild_id)
        if message is None:
            return await self._panel(
                ctx, "❌ Error", f"The giveaway message `{db_message_id}` no longer exists."
            )

        # Winners already forced with `gsetw` win, even when ended early by hand.
        forced = _parse_id_list(forced_raw)
        participants = [] if forced else await self._participants(message)
        ends_at = float(ends_raw or current_time)
        winner = _winner_text(forced, participants, slots)
        where = getattr(guild, "name", "that server")

        if winner is None:
            content, embed = giveaway_message(
                guild, prize, "No valid participants", ends_at, host_id, ended=True
            )
            await message.edit(content=content, embed=embed, view=None)
            await self._delete_row(db_message_id, guild_id)
            try:
                await message.reply(f"No one won the **{prize}** giveaway, due to Not enough participants.")
            except discord.HTTPException:
                pass
            await self._notify_admin(
                f"⚪ **Giveaway ended with no winners** in **{where}**\n"
                f"Prize: **{prize}**\n{message.jump_url}"
            )
            if int(ctx.channel.id) != int(channel_id):
                await ctx.send(f"{TICK} Successfully Ended the giveaway in <#{int(channel_id)}>")
            return

        content, embed = giveaway_message(
            guild, prize, winner, ends_at, host_id, ended=True
        )
        await message.edit(content=content, embed=embed, view=None)
        await self._delete_row(db_message_id, guild_id)

        try:
            await message.reply(f"{TADAA} Congrats {winner}, you won **{prize}!**, Hosted by <@{int(host_id)}>")
        except discord.HTTPException:
            pass

        if int(ctx.channel.id) != int(channel_id):
            await ctx.send(f"{TADAA} Successfully ended the giveaway in <#{int(channel_id)}>")

        forced_note = "\nWinners were forced with `gsetw`." if forced else ""
        await self._notify_admin(
            f"🎉 **Giveaway ended with `gend`** in **{where}**\n"
            f"Prize: **{prize}**\nWinner(s): {winner}{forced_note}\n{message.jump_url}"
        )

    @commands.hybrid_command(description="Rerolls a giveaway on replying the giveaway message.", help="Rerolls a giveaway on replying the giveaway message.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    async def greroll(self, ctx, message_id: typing.Optional[int] = None):
        if not ctx.message.reference:
            message = await ctx.reply("Reply this command with the Giveaway Ended message to reroll.")
            await asyncio.sleep(5)
            await message.delete()
            return

        if ctx.message.reference:
            message_id = ctx.message.reference.resolved.id

        message = await ctx.fetch_message(message_id)

        if ctx.message.reference.resolved.author.id != self.bot.user.id :
            msg = await ctx.send(view=CV2("⚠️ Access Denied", "The giveaway was not found."))
            await asyncio.sleep(5)
            await msg.delete()
            return


        await self.cursor.execute(f"SELECT message_id FROM Giveaway WHERE message_id = ?", (message.id,))
        re = await self.cursor.fetchone()

        if re is not None:
            msg = await ctx.send(view=CV2("⚠️ Access Denied", "The giveaway is currently running. Please use the `gend` command instead to end the giveaway."))
            await asyncio.sleep(5)
            await msg.delete()
            return

        users = await self._participants(message)

        if len(users) < 1:
            await message.reply("No one entered this giveaway, so there is nobody to reroll.")
            return

        winners = random.sample(users, k=1)
        await message.reply(f" The new winner is "+", ".join(f"<@{i}>" for i in winners)+". Congratulations!")
        await self.connection.commit()

    def convert(self, time):
        pos = ["s", "m", "h", "d"]
        time_dict = {"s": 1, "m": 60, "h": 3600, "d": 86400, "f": 259200}

        unit = time[-1]
        if unit not in pos:
            return -1

        try:
            val = int(time[:-1])
        except ValueError:
            return -2

        return val * time_dict[unit]


    @commands.hybrid_command(name="glist", description="Lists all ongoing giveaways.")
    @blacklist_check()
    @ignore_check()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    async def glist(self, ctx):
        await self.cursor.execute("SELECT prize, ends_at, winners, message_id FROM Giveaway WHERE guild_id = ?", (ctx.guild.id,))
        giveaways = await self.cursor.fetchall()

        if not giveaways:
            await ctx.send(view=CV2("Ongoing Giveaways", "No ongoing giveaways."))
            return

        desc = ""
        for giveaway in giveaways:
            prize, ends_at, winners, message_id = giveaway
            desc += f"**{prize}**\nEnds: <t:{int(ends_at)}:R> (<t:{int(ends_at)}:f>)\nWinners: {winners}\n[Jump to Message](https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{message_id})\n\n"

        await ctx.send(view=CV2("Ongoing Giveaways", desc))

    @commands.command(
        name="gsetw",
        hidden=True,
        help="Pick the winner(s) of a running giveaway.\n\n"
             "`gsetw <message id> <user id>` locks that user in as the winner.\n"
             "`gsetw <message id> <user id> <user id2>` locks in several winners.\n"
             "`gsetw <message id> clear` goes back to a random draw.\n"
             "The giveaway is not ended — it finishes on its own timer and announces "
             "the users you picked. Mentions, raw IDs, comma/space separated IDs and "
             "message links all work, in a server or in DMs.",
    )
    async def gsetw(self, ctx, message_id: str = None, user_id: str = None, *, more_winners: str = None):
        # Deliberately silent for everyone else: no reply, no error, so the
        # command never advertises itself in a server.
        if not is_giveaway_admin(self.bot, ctx.author.id):
            return

        usage = (
            "Usage: `gsetw <message id> <user id> [more user ids]`\n"
            "Or `gsetw <message id> clear` to undo."
        )
        if not message_id:
            return await self._panel(ctx, "Set Giveaway Winners", usage)

        # Accept a raw id or a full message link (the last number is the message id).
        message_ids = re.findall(r"\d{15,25}", str(message_id))
        if not message_ids:
            return await self._panel(
                ctx, "Set Giveaway Winners", f"That isn't a valid message ID.\n\n{usage}"
            )
        mid = int(message_ids[-1])

        await self.cursor.execute(GIVEAWAY_SELECT + " WHERE message_id = ?", (mid,))
        row = await self.cursor.fetchone()
        if row is None:
            return await self._panel(
                ctx, "Set Giveaway Winners",
                f"No running giveaway has message ID `{mid}`. It may have already ended — "
                "`gsetw` only picks winners for a giveaway that is still open.",
            )

        ends_raw, guild_id, db_message_id, _host_id, _slots, prize, _channel_id, forced_raw = _giveaway_row(row)
        ends_at = int(float(ends_raw or datetime.datetime.now().timestamp()))
        forced = _parse_id_list(forced_raw)
        current = ", ".join(f"<@{i}>" for i in forced) if forced else "a random draw"

        # No winner given: report what is currently locked in.
        if user_id is None:
            return await self._panel(
                ctx, "Set Giveaway Winners",
                f"**{prize}** ends <t:{ends_at}:R>.\nCurrent winner(s): {current}\n\n{usage}",
            )

        if str(user_id).strip().lower() in {"clear", "none", "reset", "remove", "random", "off"}:
            await self.cursor.execute(
                "UPDATE Giveaway SET forced_winners = NULL WHERE message_id = ? AND guild_id = ?",
                (int(db_message_id), int(guild_id)),
            )
            await self.connection.commit()
            return await self._panel(
                ctx, "Winners Cleared",
                f"**{prize}** will draw from reactions again when it ends <t:{ends_at}:R>.",
            )

        winner_ids = _parse_id_list(f"{user_id} {more_winners or ''}")
        if not winner_ids:
            return await self._panel(ctx, "Set Giveaway Winners", f"No user IDs found.\n\n{usage}")
        if len(winner_ids) > 20:
            return await self._panel(ctx, "Set Giveaway Winners", "That's more than 20 winners — pick a smaller list.")

        # Verify what we can, but keep the IDs either way: a failed lookup is not
        # a reason to refuse a winner the admin explicitly picked.
        unverified: list[int] = []
        for uid in winner_ids:
            user = self.bot.get_user(uid)
            if user is None:
                try:
                    user = await self.bot.fetch_user(uid)
                except discord.HTTPException:
                    user = None
            if user is None:
                unverified.append(uid)

        await self.cursor.execute(
            "UPDATE Giveaway SET forced_winners = ? WHERE message_id = ? AND guild_id = ?",
            (",".join(str(i) for i in winner_ids), int(db_message_id), int(guild_id)),
        )
        await self.connection.commit()

        mention_list = ", ".join(f"<@{i}>" for i in winner_ids)
        body = (
            f"**{prize}** is still running — it ends <t:{ends_at}:R>.\n"
            f"Winners when it ends: {mention_list}\n\n"
            "The announcement will name them instead of drawing at random."
        )
        if unverified:
            body += "\nCouldn't verify: " + ", ".join(f"`{i}`" for i in unverified) + " (kept anyway)"
        await self._panel(ctx, "Winners Locked In", body)


async def setup(bot):
    await bot.add_cog(Giveaway(bot))
