import discord
from discord.ext import commands, tasks
import json
import datetime
import asyncio
import codecs
import logging
import os
import tempfile
from discord.ui import LayoutView, TextDisplay, Separator, Container
from utils.cv2 import CV2, build_container

class CV2(LayoutView):
    def __init__(self, title, *sections):
        super().__init__(timeout=None)
        items = [TextDisplay(f"**{title}**")]
        for s in sections:
            if s:
                items.append(Separator(visible=True))
                items.append(TextDisplay(str(s)))
        self.add_item(build_container(*items))

# Byte order marks, longest first: UTF-32 LE also starts with the UTF-16 LE BOM.
_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


def _decode_json_bytes(raw: bytes) -> str:
    """Decode a JSON file saved as UTF-8, UTF-16 or UTF-32, with or without a BOM."""
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            return raw.decode(encoding)
    # BOM-less UTF-16 (some Windows tools write it) shows up as NUL bytes.
    if b"\x00" in raw:
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
    for encoding in ("utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def read_db(filename):
    """Read a JSON database without crashing on a broken file.

    Editors and Windows tooling (PowerShell's ``Out-File``, for example) can
    save these files as UTF-16 with a BOM, which the old plain
    ``open(filename, 'r')`` + ``json.load`` rejected with
    ``UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff`` — that killed
    the ``check_birthdays`` background task. Files are read in binary and
    decoded by BOM, and an unreadable body now logs a warning and counts as
    empty instead of raising.
    """
    try:
        with open(filename, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        logging.warning("Could not read %s: %s", filename, exc)
        return {}

    if not raw.strip():
        return {}

    try:
        data = json.loads(_decode_json_bytes(raw))
    except (UnicodeDecodeError, ValueError) as exc:
        logging.warning("Ignoring unreadable JSON database %s: %s", filename, exc)
        return {}

    if not isinstance(data, dict):
        logging.warning(
            "Ignoring %s: expected a JSON object, got %s", filename, type(data).__name__
        )
        return {}
    return data


def write_db(filename, data):
    """Write the JSON database as UTF-8, atomically.

    The old version used the platform's default encoding, so a Windows host
    could rewrite the file as UTF-16 and break the next read. A temporary
    file plus ``os.replace`` keeps a half-written database from being read.
    """
    directory = os.path.dirname(os.path.abspath(filename))
    os.makedirs(directory, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, filename)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

class Birthdays(commands.Cog):
    """Handle birthday notifications and setup."""

    def __init__(self, client: commands.Bot):
        self.client = client
        self.check_birthdays.start()

    @commands.command(
        name="birthdaysetup",
        help="Set up the birthday log channel and role.")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def birthday_setup(self, ctx: commands.Context, channel: discord.TextChannel, role: discord.Role):
        db = read_db('jsondb/birthday_logs.json')
        guild_id = str(ctx.guild.id)
        
        if guild_id not in db:
            db[guild_id] = {"birthday_channel_id": channel.id, "birthday_role_id": role.id}
        else:
            db[guild_id]["birthday_channel_id"] = channel.id
            db[guild_id]["birthday_role_id"] = role.id
        
        write_db('jsondb/birthday_logs.json', db)
        
        await ctx.send(view=CV2("Birthday Setup", f"Birthday log channel set to {channel.mention} and birthday role set to {role.mention}."))

    @commands.command(
        name="setbirthday",
        help="Set your birthday.")
    @commands.guild_only()
    async def set_birthday(self, ctx: commands.Context):
        def check(msg):
            return msg.author.id == ctx.author.id and msg.channel.id == ctx.channel.id

        await ctx.send(view=CV2("Birthday Setup", "Please enter your birth day (DD):"))

        try:
            msg = await self.client.wait_for('message', timeout=60.0, check=check)
            day = msg.content.strip().zfill(2)
            
            if not day.isdigit() or int(day) not in range(1, 32):
                await ctx.send(view=CV2("Error", "Invalid day entered. Please enter a number between 01 and 31."))
                return

            await ctx.send(view=CV2("Birthday Setup", "Please enter your birth month (MM):"))
            msg = await self.client.wait_for('message', timeout=60.0, check=check)
            month = msg.content.strip().zfill(2)
            
            if not month.isdigit() or int(month) not in range(1, 13):
                await ctx.send(view=CV2("Error", "Invalid month entered. Please enter a number between 01 and 12."))
                return

            await ctx.send(view=CV2("Birthday Setup", "Please enter your birth year (YYYY):"))
            msg = await self.client.wait_for('message', timeout=60.0, check=check)
            year = msg.content.strip()
            
            if not year.isdigit() or len(year) != 4:
                await ctx.send(view=CV2("Error", "Invalid year entered. Please enter a valid year in YYYY format."))
                return

            date = f"{month}-{day}-{year}"
            db = read_db('jsondb/birthdays.json')
            db[str(ctx.author.id)] = date
            write_db('jsondb/birthdays.json', db)
            
            await ctx.send(view=CV2("Success", f"Your birthday has been set to {date}."))
        except asyncio.TimeoutError:
            await ctx.send(view=CV2("Error", "You took too long to respond. Please try again."))

    @commands.command(
        name="removebirthday",
        help="Remove your birthday.")
    @commands.guild_only()
    async def remove_birthday(self, ctx: commands.Context):
        db = read_db('jsondb/birthdays.json')
        
        if str(ctx.author.id) in db:
            del db[str(ctx.author.id)]
            write_db('jsondb/birthdays.json', db)
            await ctx.send(view=CV2("Success", "Your birthday has been removed."))
        else:
            await ctx.send(view=CV2("Error", "You have no birthday set."))

    @commands.command(
        name="listbirthdays",
        help="List all members who have their birthday today.")
    @commands.guild_only()
    async def list_birthdays(self, ctx: commands.Context):
        now = datetime.datetime.now()
        today_date = now.strftime("%m-%d")
        db = read_db('jsondb/birthdays.json')

        members_with_birthday = [ctx.guild.get_member(int(user_id)) for user_id, date in db.items() if date.startswith(today_date)]

        if members_with_birthday:
            mentions = ', '.join(member.mention for member in members_with_birthday if member)
            await ctx.send(view=CV2("Birthdays Today", f"Members with birthdays today: {mentions}"))
        else:
            await ctx.send(view=CV2("Birthdays", "No birthdays today."))

    @commands.command(
        name="birthday",
        help="Check your birthday.")
    @commands.guild_only()
    async def check_birthday(self, ctx: commands.Context):
        db = read_db('jsondb/birthdays.json')
        
        if str(ctx.author.id) in db:
            date = db[str(ctx.author.id)]
            await ctx.send(view=CV2("Your Birthday", f"Your birthday is set to {date}."))
        else:
            await ctx.send(view=CV2("Your Birthday", "You haven't set your birthday."))

    @tasks.loop(hours=24)
    async def check_birthdays(self):
        now = datetime.datetime.now()
        today_date = now.strftime("%m-%d")
        db = read_db('jsondb/birthdays.json')
        guild_settings = read_db('jsondb/birthday_logs.json')

        for user_id, birthday in db.items():
            # One malformed entry must not stop everyone else's birthday.
            if not isinstance(birthday, str) or not birthday.startswith(today_date):
                continue
            try:
                user = self.client.get_user(int(user_id))
            except (TypeError, ValueError):
                continue
            if user is None:
                continue

            for settings in guild_settings.values():
                if not isinstance(settings, dict):
                    continue
                channel_id = settings.get("birthday_channel_id")
                role_id = settings.get("birthday_role_id")
                if not channel_id:
                    continue
                try:
                    channel_id = int(channel_id)
                except (TypeError, ValueError):
                    continue
                channel = self.client.get_channel(channel_id)
                if channel is None:
                    continue
                try:
                    await channel.send(view=CV2("Happy Birthday! 🎉", f"Wishing {user.mention} a fantastic birthday!"))
                    role = discord.utils.get(channel.guild.roles, id=role_id)
                    if role:
                        await user.add_roles(role)
                except (discord.HTTPException, AttributeError) as exc:
                    logging.warning(
                        "Could not announce the birthday of %s in %s: %s",
                        user_id, channel_id, exc,
                    )
                break

    @check_birthdays.before_loop
    async def before_check_birthdays(self):
        await self.client.wait_until_ready()
        now = datetime.datetime.now()
        first_run = datetime.datetime.combine(now.date(), datetime.time(hour=0, minute=0))
        if now > first_run:
            first_run += datetime.timedelta(days=1)
        await asyncio.sleep((first_run - now).total_seconds())

async def setup(client: commands.Bot):
    await client.add_cog(Birthdays(client))
