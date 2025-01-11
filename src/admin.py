from __future__ import annotations

import asyncio
import contextlib
import io
import textwrap
import traceback
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from .bot import MILBot


class Admin(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot

    def cleanup_code(self, content: str) -> str:
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])

        # remove `foo`
        return content.strip("` \n")

    @commands.command()
    @commands.has_role("Leaders")
    async def hash(self, ctx: commands.Context):
        process = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        await ctx.send(f"hash: `{stdout.decode('utf-8').strip()}`")

    @commands.command(name="clearrole")
    @commands.has_role("Leaders")
    async def clear_role(self, ctx: commands.Context, role_name: str):
        role = discord.utils.get(self.bot.active_guild.roles, name=role_name)
        if role is None:
            await ctx.reply(f"Cannot find role: `{role_name}`")
            return

        names = [
            f"* {member.display_name} (@{member.global_name})"
            for member in role.members
        ]
        for member in role.members:
            await member.remove_roles(role)
        new_line_names = "\n".join(names)
        await ctx.reply(f"Removed role `{role_name}` from:\n{new_line_names}")

    @commands.command(hidden=True, name="eval")
    @commands.is_owner()
    async def _eval(self, ctx: commands.Context, *, body: str):
        """Evaluates a code"""

        env = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
        }

        env.update(globals())

        body = self.cleanup_code(body)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f"```py\n{e.__class__.__name__}: {e}\n```")

        func = env["func"]
        try:
            with contextlib.redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            await ctx.send(f"```py\n{value}{traceback.format_exc()}\n```")
        else:
            value = stdout.getvalue()
            with contextlib.suppress(Exception):
                await ctx.message.add_reaction("\u2705")

            if ret is None:
                if value:
                    await ctx.send(f"```py\n{value}\n```")
            else:
                await ctx.send(f"```py\n{value}{ret}\n```")


async def setup(bot: MILBot):
    await bot.add_cog(Admin(bot))
