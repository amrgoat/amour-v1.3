from utils.branding import support_button as make_support_button, support_link
import discord
from utils.emoji import ARROWRED, ZMODULE
from discord.utils import *
from core import zyrox, Cog
from utils.Tools import *
from utils.config import BotName
from discord.ext import commands
from discord.ui import Button, View

class Autorole(Cog):
    def __init__(self, bot: zyrox):
       self.bot = bot


    @commands.Cog.listener(name="on_guild_join")
    async def send_msg_to_adder(self, guild: discord.Guild):
        async for entry in guild.audit_logs(limit=3):
            if entry.action == discord.AuditLogAction.bot_add:
                embed = discord.Embed(
                   description=f"{ZMODULE} **Thanks for adding me.**\n\n{ARROWRED} My default prefix is `>`\n{ARROWRED}> Use the `>help` command to see a list of commands\n{ARROWRED} For detailed guides, FAQ and information, visit our **{support_link('Support Server')}**",
                    color=0xFF0000
               )
                embed.set_thumbnail(url=entry.user.avatar.url if entry.user.avatar else entry.user.default_avatar.url)
                embed.set_author(name=f"{guild.name}", icon_url=guild.me.display_avatar.url)
               
                support_btn = make_support_button()
                vote_button = Button(label='Vote for Me', style=discord.ButtonStyle.link, url=f'https://top.gg/bot/{self.bot.user.id}/vote')
                view = View()
                if support_btn is not None:
                    view.add_item(support_btn)
                #view.add_item(website_button)
                #view.add_item(vote_button)
                if guild.icon:
                    embed.set_author(name=guild.name, icon_url=guild.icon.url)
                try:
                    await entry.user.send(embed=embed, view=view)
                except Exception as e:
                    print(e)
