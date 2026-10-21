import discord
from utils.emoji import ZMODULE
from discord.ext import commands


class _cv2(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Components V2 commands"""

    def help_custom(self):
              emoji = ZMODULE
              label = "Components V2"
              description = "Show you Commands of Components V2"
              return emoji, label, description

    @commands.group()
    async def __CV2__(self, ctx: commands.Context):
        """`cv2` , `cv2 build` , `cv2 delete` , `cv2 edit` , `cv2 export` , `cv2 import` , `cv2 list` , `cv2 preview` , `cv2 send`"""
