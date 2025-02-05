from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from .env import WIKI_PASSWORD, WIKI_USERNAME

if TYPE_CHECKING:
    from .bot import MILBot

logger = logging.getLogger(__name__)


class MILWiki:

    URL = "https://milwiki.cbrxyz.com/"

    def __init__(self, bot: MILBot):
        self.bot = bot

    def make_request(self, params: dict[str, Any]) -> str:
        param_string = "&".join(f"{key}={value}" for key, value in params.items())
        return f"{self.URL}/w/api.php?{param_string}"

    async def get_login_token(self) -> str:
        async with self.bot.session.get(
            self.make_request(
                {
                    "action": "query",
                    "meta": "tokens",
                    "type": "login",
                    "format": "json",
                },
            ),
        ) as response:
            if not response.ok:
                logger.error("Failed to get login token")
            response.raise_for_status()
            data = await response.json()
            return data["query"]["tokens"]["logintoken"]

    async def login(
        self,
        username: str | None = None,
        password: str | None = None,
    ) -> str:
        if not (username or WIKI_USERNAME) or not (password or WIKI_PASSWORD):
            raise ValueError("Username and password must be provided to login!")
        username = username or WIKI_USERNAME
        password = password or WIKI_PASSWORD
        token = await self.get_login_token()
        async with self.bot.session.post(
            self.make_request(
                {
                    "action": "login",
                    "lgname": username,
                    "format": "json",
                },
            ),
            data={
                "lgpassword": password,
                "lgtoken": token,
            },
        ) as response:
            if not response.ok:
                logger.error("Failed to login")
            response.raise_for_status()
            data = await response.json()
            return data["login"]["result"]

    async def get_user_contributions(
        self,
        username: str,
        start: datetime.datetime | None = None,
        end: datetime.datetime | None = None,
    ) -> list[dict[str, Any]]:
        params = {
            "action": "query",
            "list": "usercontribs",
            "ucuser": username,
            "uclimit": 50,
            "format": "json",
            "ucprop": "ids|title|timestamp|comment|size|sizediff",
        }
        if start:
            params["ucstart"] = start.isoformat()
        if end:
            params["ucend"] = end.isoformat()
        async with self.bot.session.get(
            self.make_request(params),
        ) as response:
            if not response.ok:
                logger.error(f"Failed to get user contributions for {username}")
            response.raise_for_status()
            return (await response.json())["query"]["usercontribs"]
