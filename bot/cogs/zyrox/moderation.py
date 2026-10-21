import discord
from utils.emoji import SWORD
from discord.ext import commands


class _moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Moderation commands"""
  
    def help_custom(self):
		      emoji = f'{SWORD} '
		      label = "Moderation Commands"
		      description = "Show you Commands of Moderation"
		      return emoji, label, description

    @commands.group()
    async def __Moderation__(self, ctx: commands.Context):
        """`audit` , `ban` , `clear` , `clear all` , `clear bots` , `clear contains` , `clear embeds` , `clear emoji` , `clear files` , `clear images` , `clear reactions` , `clear user` , `clearwarns` , `clone` , `deleteemoji` , `deletesticker` , `enlarge` , `give` , `hide` , `hideall` , `jail` , `jailhistory` , `kick` , `lock` , `lockall` , `mute` , `nick` , `nuke` , `prefix` , `purgebots` , `purgeuser` , `removerole` , `removerole all` , `removerole bots` , `removerole humans` , `removerole unverified` , `role` , `role all` , `role bots` , `role create` , `role delete` , `role humans` , `role rename` , `role temp` , `role unverified` , `roleicon` , `slowmode` , `snipe` , `steal` , `topcheck` , `topcheck disable` , `topcheck enable` , `unban` , `unbanall` , `unhide` , `unhideall` , `unjail` , `unlock` , `unlockall` , `unmute` , `unslowmode` , `warn`"""