import discord
from utils.emoji import ZWRENCH
from discord.ext import commands


class _extra(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Utility commands"""
  
    def help_custom(self):
		      emoji = ZWRENCH
		      label = "Utility Commands"
		      description = "Show you Commands of Utility"
		      return emoji, label, description

    @commands.group()
    async def __Utility__(self, ctx: commands.Context):
        """`banner` , `banner server` , `banner user` , `boostcount` , `botinfo` , `channelinfo` , `github` , `joined-at` , `list` , `list activedeveloper` , `list admins` , `list bans` , `list boosters` , `list bots` , `list createdat` , `list early` , `list emojis` , `list inrole` , `list invoice` , `list joinedat` , `list mods` , `list roles` , `permissions` , `ping` , `report` , `roleinfo` , `serverinfo` , `stats` , `timer` , `uptime` , `userinfo` , `vcinfo`\n\n__**Media Commands**__\n`media` , `media setup` , `media remove` , `media config` , `media bypass` , `media bypass add` , `media bypass remove` , `media bypass show`"""