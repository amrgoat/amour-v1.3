import discord
from utils.emoji import MUTE
from discord.ext import commands


class _voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Voice commands"""
  
    def help_custom(self):
		      emoji = MUTE
		      label = "Voice Commands"
		      description = "Show you Command Of Voice"
		      return emoji, label, description

    @commands.group()
    async def __Voice__(self, ctx: commands.Context):
        """`voice` , `voice deafen` , `voice deafenall` , `voice kick` , `voice kickall` , `voice lock` , `voice move` , `voice moveall` , `voice mute` , `voice muteall` , `voice private` , `voice pull` , `voice pullall` , `voice undeafen` , `voice undeafenall` , `voice unlock` , `voice unmute` , `voice unmuteall` , `voice unprivate`"""






