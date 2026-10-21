import discord
from utils.emoji import ZMODULE
from discord.ext import commands


class _general(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """General commands"""

    def help_custom(self):
              emoji = ZMODULE
              label = "General Commands"
              description = "Show you Commands of General"
              return emoji, label, description

    @commands.group()
    async def __General__(self, ctx: commands.Context):
        """`avatar` , `hack` , `hash` , `invite` , `membercount` , `poll` , `rickroll` , `servericon` , `token` , `urban` , `users` , `wizz` , `status` , `afk` , `snipe` , `calculator` , `list` , `list activedeveloper` , `list admins` , `list bans` , `list boosters` , `list bots` , `list createdat` , `list early` , `list emojis` , `list inrole` , `list invoice` , `list joinedat` , `list mods` , `list roles`"""