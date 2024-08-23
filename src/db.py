from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    String,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase, mapped_column

if TYPE_CHECKING:
    from .bot import MILBot


logger = logging.getLogger(__name__)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class GitHubOauthMember(Base):
    __tablename__ = "github_oauth_member"

    discord_id = mapped_column(BigInteger, primary_key=True)
    device_code = mapped_column(String, nullable=False)
    access_token = mapped_column(String, nullable=True)


class Database(AsyncSession):
    def __init__(self, *, bot: MILBot, engine: AsyncEngine):
        self.bot = bot
        self.engine = engine
        super().__init__(bind=engine, expire_on_commit=False)

    async def __aenter__(self) -> Database:
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def add_github_oauth_member(
        self,
        discord_id: int,
        device_code: str,
        access_token: str,
    ):
        member = GitHubOauthMember(
            discord_id=discord_id,
            device_code=device_code,
            access_token=access_token,
        )
        await self.merge(member)
        await self.commit()

    async def get_github_oauth_member(
        self,
        discord_id: int,
    ) -> GitHubOauthMember | None:
        result = await self.execute(
            select(GitHubOauthMember).where(GitHubOauthMember.discord_id == discord_id),
        )
        response = result.scalars().first()
        return response


class DatabaseFactory:
    def __init__(self, *, engine: AsyncEngine, bot: MILBot):
        self.engine = engine
        self.bot = bot

    def __call__(self) -> Database:
        return Database(bot=self.bot, engine=self.engine)

    async def close(self):
        await self.engine.dispose()
