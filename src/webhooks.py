from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from discord.ext import commands
from discord.ext.ipc.objects import ClientPayload
from discord.ext.ipc.server import Server

from src.env import IPC_PORT

if TYPE_CHECKING:
    from .bot import MILBot


class Webhooks(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot
        self.ipc = Server(
            bot,
            standard_port=int(IPC_PORT) if IPC_PORT else 1025,
            secret_key="37",
        )
        # Map from github username to real name
        self._real_names: dict[str, tuple[str, datetime.datetime]] = {}

    async def cog_load(self):
        await self.ipc.start()

    async def cog_unload(self):
        await self.ipc.stop()

    async def real_name(self, username: str) -> str:
        cache = self._real_names.get(username)
        if not cache or cache[1] > datetime.datetime.now() + datetime.timedelta(
            hours=4,
        ):
            # Call API
            user = await self.bot.github.get_user(username)
            self._real_names[username] = (
                user["name"] or user["login"],
                datetime.datetime.now(),
            )
        return self._real_names[username][0]

    @Server.route()
    async def ping(self, payload: ClientPayload):
        return "Pong!"

    def url(self, obj: dict[str, str], html=False) -> str:
        return f"<{obj['url']}>" if not html else f"<{obj['html_url']}>"

    @Server.route()
    async def commit_created(self, payload: ClientPayload):
        gh = payload.github_data
        # If push to master, send message to github-updates in the form of:
        # [User A](link) [pushed](commit_url) 1 commit to [branch_name](link) in [repo_name](link): "commit message"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pushed = (
            f"[{'force-' if gh['forced'] else ''}pushed]({self.url(gh['head_commit'])})"
        )
        branch = (
            f"[{gh['ref'].split('/')[-1]}]({self.url(gh['repository'], html=True)})"
        )
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        message = f"\"{gh['head_commit']['message']}\""
        await self.bot.github_updates_channel.send(
            f"{name} {pushed} 1 commit to {branch} in {repo}: {message}",
        )

    @Server.route()
    async def star_created(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) starred [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'],html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        await self.bot.github_updates_channel.send(f"{name} added a star to {repo}")

    @Server.route()
    async def issue_opened(self, payload: ClientPayload):
        # Send a message to github-updates in the form of:
        # [User A](link) opened issue [#XXX](link) in [repo_name](link): "issue title"
        gh = payload.github_data
        name = (
            f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'])})"
        )
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        title = f"\"{gh['issue']['title']}\""
        await self.bot.github_updates_channel.send(
            f"{name} opened issue {issue} in {repo}: {title}",
        )

    @Server.route()
    async def issue_closed(self, payload: ClientPayload):
        # Send a message to github-updates in the form of:
        # [User A](link) closed issue [#XXX](link) as "completed/not-planned" in [repo_name](link): "issue title"
        gh = payload.github_data
        name = (
            f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'])})"
        )
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        state = (
            "completed"
            if gh["issue"]["state_reason"] != "not_planned"
            else "not planned"
        )
        title = f"\"{gh['issue']['title']}\""
        await self.bot.github_updates_channel.send(
            f"{name} closed issue {issue} as {state} in {repo}: {title}",
        )

    @Server.route()
    async def organization_member_invited(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to software-leadership in the form of:
        # [User A](link) invited [User B](link) to [organization_name](link) in the following teams: {Team A, Team B}
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        invited = f"[{await self.real_name(gh['user']['login'])}]({self.url(gh['user'], html=True)})"
        org = f"[{gh['organization']['login']}]({self.url(gh['organization'])})"
        teams_resp = await self.bot.github.fetch(
            gh["invitation"]["invitation_teams_url"],
        )
        teams = ", ".join(
            [f"[{team['name']}]({self.url(team, html=True)})" for team in teams_resp],
        )
        await self.bot.software_leaders_channel.send(
            f"{name} invited {invited} to {org} in the following teams: {{{teams}}}",
        )

    @Server.route()
    async def organization_member_added(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to software-leadership in the form of:
        # [User A](link) accepted an invitation to join [organization_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        org = f"[{gh['organization']['login']}]({self.url(gh['organization'], html=True)})"
        await self.bot.software_leaders_channel.send(
            f"{name} accepted an invitation to join {org}",
        )

    @Server.route()
    async def organization_member_removed(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to software-leadership in the form of:
        # [User A](link) was removed from [organization_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        org = f"[{gh['organization']['login']}]({self.url(gh['organization'], html=True)})"
        await self.bot.software_leaders_channel.send(f"{name} was removed from {org}")

    @Server.route()
    async def pull_request_opened(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) opened pull request [#XXX](link) in [repo_name](link): "pull request title"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        title = f"\"{gh['pull_request']['title']}\""
        await self.bot.github_updates_channel.send(
            f"{name} opened pull request {pr} in {repo}: {title}",
        )

    @Server.route()
    async def pull_request_closed(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) closed pull request [#XXX](link) as "completed/not-planned" in [repo_name](link): "pull request title"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        title = f"\"{gh['pull_request']['title']}\""
        await self.bot.github_updates_channel.send(
            f"{name} closed pull request {pr} in {repo}: {title}",
        )

    @Server.route()
    async def pull_request_review_requested(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) requested a review from [User B](link) on pull request [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        requested = f"[{await self.real_name(gh['requested_reviewer']['login'])}]({self.url(gh['requested_reviewer'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        await self.bot.github_updates_channel.send(
            f"{name} requested a review from {requested} on pull request {pr} in {repo}",
        )

    @Server.route()
    async def pull_request_review_submitted(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) submitted a review on pull request [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        await self.bot.github_updates_channel.send(
            f"{name} submitted a review on pull request {pr} in {repo}",
        )


async def setup(bot: MILBot):
    await bot.add_cog(Webhooks(bot))
