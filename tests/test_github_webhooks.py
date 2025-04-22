import json

import aiohttp
import pytest
import pytest_asyncio

from src.env import GITHUB_TOKEN
from src.github import GitHub
from src.webhooks import MembershipRemoved


@pytest_asyncio.fixture
async def fake_bot():
    class FakeBot:
        def __init__(self):
            self.session = aiohttp.ClientSession()
            self.github = GitHub(auth_token=GITHUB_TOKEN, bot=self)

    fake_bot = FakeBot()
    yield fake_bot
    await fake_bot.session.close()


@pytest.mark.asyncio
async def test_membership_removed(fake_bot):
    with open("payloads/membership_removed.json") as f:
        payload = json.loads(f.read())

    webhook_response = MembershipRemoved(payload, fake_bot)
    assert (
        await webhook_response.message()
        == "[cameron brown](<https://github.com/cbrxyz>) removed [Grymestone](<https://github.com/Grymestone>) from [software-leads](<https://github.com/orgs/uf-mil/teams/software-leads>) in [uf-mil](<https://api.github.com/orgs/uf-mil>)"
    )
