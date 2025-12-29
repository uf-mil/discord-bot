import datetime

import pytest

from src.utils import capped_str, emoji_header, has_emoji, is_active, make_and, surround


def test_make_and():
    assert make_and([]) == ""
    assert make_and(["Dr. Schwartz"]) == "Dr. Schwartz"
    assert make_and(["Dr. Schwartz", "uf-mil-bot"]) == "Dr. Schwartz and uf-mil-bot"
    assert make_and(["1", "2", "3"]) == "1, 2, and 3"
    assert make_and([",", ",,", ",,,"]) == ",, ,,, and ,,,"


def test_surround():
    # replacing around the entire string
    assert surround("a", 0, 1, "x") == "xax"

    # replacing around part of the string
    assert surround("substring", 0, 3, "!") == "!sub!string"
    assert surround("xxxxx", 0, 2, "!") == "!xx!xxx"
    assert surround("rbt", 1, 2, "o") == "robot"

    # replacing multiple time
    assert surround(surround("xxxxx", 0, 2, "!"), 0, 2, "!") == "!!xx!!xxx"

    # testing start < end requirements
    with pytest.raises(ValueError):
        assert surround("a", 1, 0, "x")


def test_is_active():
    ################ active
    # in middle of semester
    SEMESTERS = [
        (
            datetime.date.today() - datetime.timedelta(days=1),
            datetime.date.today() + datetime.timedelta(days=1),
        ),
    ]
    assert is_active()

    # semester started today
    SEMESTERS = [
        (datetime.date.today(), datetime.date.today() + datetime.timedelta(days=1)),
    ]
    assert is_active()

    # semester ends today
    SEMESTERS = [
        (datetime.date.today() - datetime.timedelta(days=1), datetime.date.today()),
    ]
    assert is_active()

    # old semester ended
    SEMESTERS = [
        (
            datetime.date.today() - datetime.timedelta(days=3),
            datetime.date.today() - datetime.timedelta(days=2),
        ),
        (
            datetime.date.today() - datetime.timedelta(days=1),
            datetime.date.today() + datetime.timedelta(days=1),
        ),
    ]

    ########## inactive
    # past
    SEMESTERS = [
        (
            datetime.date.today() - datetime.timedelta(days=3),
            datetime.date.today() - datetime.timedelta(days=2),
        ),
    ]
    assert not is_active()

    # future
    SEMESTERS = [
        (
            datetime.date.today() + datetime.timedelta(days=3),
            datetime.date.today() + datetime.timedelta(days=4),
        ),
    ]
    assert not is_active()

    # none
    SEMESTERS = []  # noqa: F841
    assert not is_active()


def test_is_emoji():
    # simple emojis
    assert has_emoji("😀")
    assert has_emoji("🤖")
    assert has_emoji("🩷")

    # complex emojis (combos)
    assert has_emoji("🏳️‍🌈")
    assert has_emoji("👨‍💻")
    assert has_emoji("👩🏽‍🚀")

    # unicode
    assert not has_emoji("♡")
    assert not has_emoji("★")

    # text
    assert not has_emoji("x")
    assert not has_emoji("MIL")

    # empty string
    assert not has_emoji("")

    # two emojis (is fine)
    assert has_emoji("😀😀")


def test_emoji_header():
    assert emoji_header("🩷", "peace and love") == "🩷 __peace and love__"
    assert emoji_header("🤖", "MIL") == "🤖 __MIL__"
    with pytest.raises(ValueError):
        # not an emoji
        assert emoji_header("x", "oops")
        assert emoji_header("MIL", "🤖")


def test_capped_str():
    assert capped_str(["a", "b", "c"]) == "a\nb\nc"
