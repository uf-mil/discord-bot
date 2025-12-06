from pathlib import Path

import pytest
import pytest_asyncio

from src.emoji import CustomEmoji, EmojiRegistry


@pytest_asyncio.fixture
async def fake_bot():
    class FakeBot:
        def __init__(self):
            pass

    fake_bot = FakeBot()
    yield fake_bot


@pytest.mark.asyncio
async def test_upload_no_existing(fake_bot):
    registry = EmojiRegistry(fake_bot)
    existing_emojis = []
    additions = await registry.upload(existing_emojis)
    assert len(additions) > 0  # Ensure that emojis are being added


@pytest.mark.asyncio
async def test_upload_fake_svg(fake_bot):
    registry = EmojiRegistry(fake_bot)
    existing_emojis = []

    svg_path = Path("src") / "assets" / "emojis" / CustomEmoji.X.value
    real_contents = svg_path.read_text()

    try:
        # Overwrite with invalid SVG contents
        svg_path.write_text("hello world")

        # Expect a ValueError when uploading
        with pytest.raises(ValueError):
            await registry.upload(existing_emojis)
    finally:
        # Always restore original contents, even if the assertion fails
        svg_path.write_text(real_contents)
