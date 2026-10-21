import discord 
from utils.emoji import LEVEL_UP
from discord .ext import commands 


class _leveling (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    """Leveling commands"""

    def help_custom (self ):
		      emoji =LEVEL_UP
		      label ="Leveling Commands"
		      description ="Shows you the commands of leveling"
		      return emoji ,label ,description 

    @commands .group ()
    async def __Leveling__ (self ,ctx :commands .Context ):
        """`level` , `level blacklist` , `level blacklist add` , `level blacklist list` , `level blacklist remove` , `level channel` , `level cooldown` , `level disable` , `level enable` , `level leaderboard` , `level multiplier` , `level multiplier add` , `level multiplier list` , `level multiplier remove` , `level placeholders` , `level rank` , `level rewards` , `level rewards add` , `level rewards list` , `level rewards remove` , `level setcolor` , `level setmessage` , `level settings` , `level setxp` , `level stats` , `level thumbnail` , `listlevelroles` , `removelevelrole` , `resetxp` , `setlevel` , `setlevelrole` , `setxp`"""