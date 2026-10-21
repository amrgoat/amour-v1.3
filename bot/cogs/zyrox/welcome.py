import discord
from utils.emoji import SEED
from discord.ext import commands


class _welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Welcome commands"""
  
    def help_custom(self):
		      emoji = SEED
		      label = "Welcomer Commands"
		      description = "Show you Command Of Welcomer"
		      return emoji, label, description

    @commands.group()
    async def __Welcomer__(self, ctx: commands.Context):
        """`greet` , `greet autodelete` , `greet channel` , `greet config` , `greet edit` , `greet reset` , `greet setup` , `greet test` , `fastgreet_add` , `fastgreet_list` , `fastgreet_remove`"""