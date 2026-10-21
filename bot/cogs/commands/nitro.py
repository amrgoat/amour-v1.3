from utils.branding import support_button as make_support_button
import discord
from discord.ext import commands
from discord.ui import Button, View


class Nitro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if self.bot.user in message.mentions and (
            "nitro" in message.content.lower() or "$nitro" in message.content.lower()
        ):
            ctx = await self.bot.get_context(message)
            await self.bot.invoke(ctx)

    @commands.command(name="nitro")
    async def nitro(self, ctx):
        embed = discord.Embed(color=0x2B2D31)
        embed.add_field(
            name="A WILD NITRO GIFT APPEARS?",
            value="Expires in 12 hours\n\nClick the claim button for claiming Nitro",
            inline=False,
        )
        embed.set_image(
            url="https://media.tenor.com/ltVe8iMhgXcAAAAS/nitro-discord.gif"
        )

        view = View()
        claim_button = make_support_button()
        if claim_button is not None:
            view.add_item(claim_button)

        await ctx.send(embed=embed, view=view if view.children else None)
