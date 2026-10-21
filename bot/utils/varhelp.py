"""The shared "Variables" help view.

Builders call :class:`VariablesView` so every place that accepts variables shows
the same paginated list, taken straight from ``utils/variables.py``.
"""

from __future__ import annotations

import discord
from discord.ui import Button, View

from utils.variables import describe_variables

RED = 0xFF0000


def variables_embed(page: int = 0) -> discord.Embed:
    entries, total_pages = describe_variables(page)
    embed = discord.Embed(
        title="Variables",
        description=(
            "Paste these into message text, embed fields, image/icon fields or "
            "Components V2 blocks — they are filled in when the message is sent."
            + (f"\nPage {page + 1} of {total_pages}." if total_pages > 1 else "")
        ),
        color=RED,
    )
    for token, description in entries:
        embed.add_field(name=token, value=description, inline=False)
    embed.set_footer(text="User variables also accept a target: {user_name:123456789012345678}")
    return embed


class VariablesView(View):
    def __init__(self, author: discord.abc.User, page: int = 0):
        super().__init__(timeout=180)
        self.author = author
        _, total = describe_variables(page)
        self.page = max(0, min(page, total - 1))
        self.total = total

        if total > 1:
            previous = Button(label="Previous", style=discord.ButtonStyle.secondary, disabled=self.page == 0)
            previous.callback = self.go_back
            following = Button(
                label="Next",
                style=discord.ButtonStyle.secondary,
                disabled=self.page >= total - 1,
            )
            following.callback = self.go_forward
            self.add_item(previous)
            self.add_item(following)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "Only the command author can use this button.", ephemeral=True
            )
            return False
        return True

    async def go_back(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        await self._show(interaction)

    async def go_forward(self, interaction: discord.Interaction):
        self.page = min(self.total - 1, self.page + 1)
        await self._show(interaction)

    async def _show(self, interaction: discord.Interaction):
        view = VariablesView(self.author, self.page)
        await interaction.response.edit_message(embed=variables_embed(self.page), view=view)
