from __future__ import annotations
from core import zyrox
from colorama import Fore, Style, init


from .commands.help import Help
from .commands.general import General
from .commands.welcome import Welcomer
from .commands.extra import Extra
from .commands.owner import Owner
from .commands.voice import Voice
from .commands.afk import afk
from .commands.ignore import Ignore
from .commands.Media import Media
from .commands.Invc import Invcrole
from .commands.giveaway import Giveaway
from .commands.Embed import Embed
from .commands.steal import Steal
from .commands.timer import Timer
from .commands.blacklist import Blacklist
from .commands.block import Block
from .commands.tracking import Tracking
from .commands.owner import Badges
#from .commands.map import Map
from .commands.autoresponder import AutoResponder
from .commands.customrole import Customrole
from .commands.autorole import AutoRole
from .commands.translate import TranslateCog
from .commands.jail import Jail
from .commands.autoreact import AutoReaction
from .commands.stats import Stats
from .commands.emergency import Emergency
from .commands.notify import NotifCommands
from .commands.status import Status
from .commands.np import NoPrefix
from .commands.owner2 import Global
from .commands.vanityroles import VanityRoles
from .commands.messages import Messages
from .commands.fastgreet import FastGreet
from .commands.counting import Counting
from .commands.j2c import JoinToCreate
from .commands.dms import StaffDMCog
from .commands.booster import Booster
from .commands.leveling import Leveling
from .commands.stickymessage import StickyMessage
from .commands.verification import Verification
from .commands.calc import calculator
from .commands.cv2 import CV2Messages
from .commands.joindm import joindm
from .commands.Birthday import Birthdays
from .commands.nitro import Nitro
from .commands.image import ImageCommands
from .commands.youtube import Youtube
#____________ Events _____________

#from .events.autoblacklist import AutoBlacklist
from .events.Errors import Errors
from .events.on_guild import Guild
from .events.autorole import Autorole2
from .events.auto import Autorole
from .events.greet2 import greet
from .events.mention import Mention
from .events.react import React
from .events.autoreact import AutoReactListener
#from .events.topgg import TopGG
from .events.stickymessage import StickyMessageListener

########-------HELP-------########
from .zyrox.extra import _extra
from .zyrox.general import _general
from .zyrox.moderation import _moderation
#from .zyrox.inviteTracker import _inviteTracker
from .zyrox.ignore import _ignore
from .zyrox.server import _server
from .zyrox.voice import _voice 
from .zyrox.welcome import _welcome 
from .zyrox.giveaway import _giveaway
#from .axon.vanityroles import Vanityroles69999
from .zyrox.vanity import _vanity
from .zyrox.inviteTracker import inviteTracker 
from .zyrox.counting import _Counting
from .zyrox.j2c import _J2C
from .zyrox.booster import __boost 
from .zyrox.leveling import _leveling
from .zyrox.sticky import _sticky
from .zyrox.verify import _verify
from .zyrox.joindm import _joindm
from .zyrox.birth import _birth
from .zyrox.cv2 import _cv2


from .moderation.ban import Ban
from .moderation.unban import Unban
from .moderation.timeout import Mute
from .moderation.unmute import Unmute
from .moderation.lock import Lock
from .moderation.unlock import Unlock
from .moderation.hide import Hide
from .moderation.unhide import Unhide
from .moderation.kick import Kick
from .moderation.warn import Warn
from .moderation.role import Role
from .moderation.message import Message
from .moderation.moderation import Moderation
from .moderation.topcheck import TopCheck
from .moderation.snipe import Snipe


from utils.config import BotName

async def setup(bot: zyrox):
  cogs_to_load = [
        Help, General, Moderation, Welcomer, Extra,
        Voice, Owner, Customrole, afk, Embed, CV2Messages, Media, Ignore,
        Invcrole, Steal, Timer,
        Blacklist, Block, Badges, Guild, Errors, Autorole2, Autorole, greet, AutoResponder,
        Mention, AutoRole, React,
        Stats, Status, NoPrefix, AutoReaction, AutoReactListener, Ban, Unban, Mute, Unmute, Lock, Unlock, Hide, Unhide, Kick, Warn, Role, Message, Moderation, TopCheck, Snipe, Global, VanityRoles, Messages, TranslateCog, FastGreet, Jail, inviteTracker,Counting
    ]


  await bot.add_cog(Help(bot))
  await bot.add_cog(General(bot))
  await bot.add_cog(Welcomer(bot))
  await bot.add_cog(Tracking(bot))
  await bot.add_cog(Extra(bot))
  await bot.add_cog(Voice(bot))
  await bot.add_cog(Owner(bot))
  await bot.add_cog(Customrole(bot))
  await bot.add_cog(afk(bot))
  await bot.add_cog(Embed(bot))
  await bot.add_cog(CV2Messages(bot))
  await bot.add_cog(Media(bot))
  await bot.add_cog(Ignore(bot))
  await bot.add_cog(Invcrole(bot))
  await bot.add_cog(Giveaway(bot))
  await bot.add_cog(Steal(bot))
  await bot.add_cog(Booster(bot))
  await bot.add_cog(Timer(bot))
  await bot.add_cog(Blacklist(bot))
  await bot.add_cog(Block(bot))
  await bot.add_cog(Badges(bot))
  await bot.add_cog(Stats(bot))
  await bot.add_cog(Emergency(bot))
  await bot.add_cog(Status(bot))
  await bot.add_cog(NoPrefix(bot))
  await bot.add_cog(Global(bot))
 # await bot.add_cog(Map(bot))
  await bot.add_cog(VanityRoles(bot))
  await bot.add_cog(Messages(bot))
  await bot.add_cog(TranslateCog(bot))
  await bot.add_cog(FastGreet(bot))
  await bot.add_cog(Jail(bot))
  await bot.add_cog(JoinToCreate(bot))
  await bot.add_cog(StaffDMCog(bot))
  await bot.add_cog(Leveling(bot))
  await bot.add_cog(StickyMessage(bot))
  await bot.add_cog(Verification(bot))
  await bot.add_cog(calculator(bot))
  await bot.add_cog(joindm(bot))
  await bot.add_cog(Birthdays(bot))
  await bot.add_cog(Nitro(bot))
  await bot.add_cog(ImageCommands(bot))
  await bot.add_cog(Youtube(bot))

  await bot.add_cog(_extra(bot))
  await bot.add_cog(_general(bot))
  await bot.add_cog(_moderation(bot))
  await bot.add_cog(_ignore(bot))
  await bot.add_cog(_server(bot))
  await bot.add_cog(_voice(bot))   
  await bot.add_cog(_welcome(bot))
  await bot.add_cog(_giveaway(bot))
  await bot.add_cog(_vanity(bot))
  await bot.add_cog(inviteTracker(bot))
  await bot.add_cog(Counting(bot))
  await bot.add_cog(_Counting(bot))
  await bot.add_cog(_J2C(bot))
  await bot.add_cog(__boost(bot))
  await bot.add_cog(_leveling(bot))
  await bot.add_cog(_sticky(bot))
  await bot.add_cog(_verify(bot))
  await bot.add_cog(_joindm(bot))
  await bot.add_cog(_birth(bot))
  await bot.add_cog(_cv2(bot))


  
  #await bot.add_cog(AutoBlacklist(bot))
  await bot.add_cog(Guild(bot))
  await bot.add_cog(Errors(bot))
  await bot.add_cog(Autorole2(bot))
  await bot.add_cog(Autorole(bot))
  await bot.add_cog(greet(bot))
  await bot.add_cog(AutoResponder(bot))
  await bot.add_cog(Mention(bot))
  await bot.add_cog(AutoRole(bot))
  await bot.add_cog(React(bot))
  await bot.add_cog(AutoReaction(bot))
  await bot.add_cog(AutoReactListener(bot))
  await bot.add_cog(NotifCommands(bot))
  await bot.add_cog(StickyMessageListener(bot))






  await bot.add_cog(Ban(bot))
  await bot.add_cog(Unban(bot))
  await bot.add_cog(Mute(bot))
  await bot.add_cog(Unmute(bot))
  await bot.add_cog(Lock(bot))
  await bot.add_cog(Unlock(bot))
  await bot.add_cog(Hide(bot))
  await bot.add_cog(Unhide(bot))
  await bot.add_cog(Kick(bot))
  await bot.add_cog(Warn(bot))
  await bot.add_cog(Role(bot))
  await bot.add_cog(Message(bot))
  await bot.add_cog(Moderation(bot))
  await bot.add_cog(TopCheck(bot))
  await bot.add_cog(Snipe(bot))
  


  for cog in cogs_to_load:
    print(Fore.RED + Style.BRIGHT + f"Loaded cog: {cog.__name__}")
  print(Fore.RED + Style.BRIGHT + f"All {BotName} Cogs loaded successfully.")
