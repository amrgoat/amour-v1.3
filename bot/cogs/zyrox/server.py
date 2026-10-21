import discord
from utils.emoji import WIFI
from discord.ext import commands

class _server(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Server commands"""
  
    def help_custom(self):
		      emoji = WIFI
		      label = "Server Commands"
		      description = "Show you Commands of Server"
		      return emoji, label, description

    @commands.group()
    async def __Setup__(self, ctx: commands.Context):
        """`setup` , `setup config` , `setup create` , `setup delete` , `setup friend` , `setup girl` , `setup guest` , `setup list` , `setup reqrole` , `setup reset` , `setup staff` , `setup vip` , `staff` , `girl` , `friend` , `vip` , `guest`\n\n__**Auto Role**__\n`autorole` , `autorole bots` , `autorole bots add` , `autorole bots remove` , `autorole config` , `autorole humans` , `autorole humans add` , `autorole humans remove` , `autorole reset` , `autorole reset all` , `autorole reset bots` , `autorole reset humans`\n\n__**Autoresponder**__\n`autoresponder` , `autoresponder config` , `autoresponder create` , `autoresponder delete` , `autoresponder edit`\n\n__**Auto React**__\n`react` , `react add` , `react list` , `react remove` , `react reset`\n\n__**VC Role**__\n`vcrole` , `vcrole add` , `vcrole config` , `vcrole remove`"""

