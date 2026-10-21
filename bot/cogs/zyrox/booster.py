import discord 
from utils.emoji import BOOST
from discord .ext import commands 


class __boost(commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 

    """Boost commands"""

    def help_custom (self ):
              emoji =BOOST
              label ="Boost Commands"
              description ="Show you the commands of boost"
              return emoji ,label ,description 

    @commands .group ()
    async def __Boost__ (self ,ctx :commands .Context ):
        """`boost` , `boost autodel` , `boost channel` , `boost channel add` , `boost channel remove` , `boost config` , `boost embed` , `boost image` , `boost message` , `boost ping` , `boost reset` , `boost test` , `boost thumbnail` , `boostrole` , `boostrole add` , `boostrole config` , `boostrole remove` , `boostrole reset`"""
        pass
