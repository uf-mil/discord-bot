from __future__ import annotations

import asyncio
import datetime
import logging
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from .email import send_email
from .roles import TeamRolesView
from .views import MILBotModal, MILBotView

if TYPE_CHECKING:
    from .bot import MILBot

logger = logging.getLogger(__name__)


@dataclass
class VerificationCandidate:
    email: str
    member: discord.Member
    code: int
    welcoming: bool


class Verifier:
    def _generate_new_code(self) -> int:
        """
        Returns a new six-digit verification code.
        """
        return random.randint(100000, 999999)

    def request_verification(
        self,
        email: str,
        member: discord.Member,
        *,
        welcoming: bool,
    ) -> VerificationCandidate:
        """
        Requests a verification for the given email and member.
        """
        code = self._generate_new_code()
        logger.info(f"Generated new verification code {code} for {email}!")
        return VerificationCandidate(email, member, code, welcoming)

    async def send_verification_email(self, candidate: VerificationCandidate):
        """
        Sends a verification email to the candidate.
        """
        messages = self._generate_message(candidate.code)
        await send_email(
            candidate.email,
            "MIL Discord Verification Code",
            *messages,
        )

    def _generate_message(self, code: int) -> tuple[str, str]:
        return (
            f"""
            <html>
                <head></head>
                <body>
                    Welcome to the Machine Intelligence Laboratory Discord server!<br><br>
                    Your verification code is: <b>{code}</b><br><br>
                    Thanks,<br>Machine Intelligence Laboratory
            </html>
        """,
            f"""Welcome to the Machine Intelligence Laboratory Discord server!
    Your verification code is: {code}
    Thanks,
    Machine Intelligence Laboratory
    """,
        )


class VerificationCodeModal(MILBotModal):
    code = discord.ui.TextInput(
        label="Verification Code",
        placeholder="373737",
    )

    def __init__(self, bot: MILBot, candidate: VerificationCandidate):
        self.bot = bot
        self.candidate = candidate
        super().__init__(title="Enter verification code")

    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(interaction.user, discord.Member)

        # Check if the code is valid
        if int(self.code.value) != self.candidate.code:
            await interaction.response.send_message(
                "The verification code you entered is incorrect. Please try again.",
                ephemeral=True,
            )
            return

        roles = set(interaction.user.roles)
        roles.add(self.bot.verified_role)
        roles.discard(self.bot.unverified_role)
        await interaction.user.edit(
            roles=list(roles),
        )
        logger.info(
            f"Completed verification process for {interaction.user} with email {self.candidate.email}!",
        )
        if not self.candidate.welcoming:
            await interaction.response.send_message(
                "Your email has been successfully verified! Thank you so much!",
                ephemeral=True,
            )
            return
        else:
            await interaction.response.send_message(
                "Thanks for verifying yourself! You're almost done (we promise), but one last step! Choose one or two roles that best describe your interests in being a part of MIL. These will allow you to access specific channels and resources that are relevant to you. If you're not sure, you can always change your roles later. Click the button below to get started!",
                ephemeral=True,
                view=TeamRolesView(self.bot),
            )


class FinishEmailVerificationView(MILBotView):

    message: discord.Message | None = None

    def __init__(self, bot: MILBot, candidate: VerificationCandidate):
        super().__init__()
        self.bot = bot
        self.candidate = candidate
        self.message = None
        self.bot.tasks.create_task(self.make_button_available())

    async def make_button_available(self):
        await asyncio.sleep(60)
        self.resend_email.disabled = False
        if self.message:
            await self.message.edit(view=self)

    @discord.ui.button(
        label="Enter Code",
        style=discord.ButtonStyle.green,
    )
    async def enter_code(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_modal(
            VerificationCodeModal(self.bot, self.candidate),
        )

    @discord.ui.button(
        label="Resend Email",
        style=discord.ButtonStyle.secondary,
        disabled=True,
    )
    async def resend_email(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        self.candidate.code = self.bot.verifier._generate_new_code()
        await self.bot.verifier.send_verification_email(self.candidate)
        new_time = discord.utils.utcnow() + datetime.timedelta(minutes=1)
        button.disabled = True
        await interaction.response.edit_message(
            content=f"**A new verification email has been sent to your email address!** Please check your inbox and enter the verification code using the button below. If you do not receive an email, you can request a new code {discord.utils.format_dt(new_time, 'R')}.",
            view=self,
        )

        self.bot.tasks.create_task(self.make_button_available())


class EmailModal(MILBotModal):
    email = discord.ui.TextInput(
        label="Email",
        placeholder="albert.gator@ufl.edu",
    )

    def __init__(self, bot: MILBot, *, welcoming: bool):
        self.bot = bot
        self.welcoming = welcoming
        super().__init__(title="Enter your email")

    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(interaction.user, discord.Member)

        # Check for ufl.edu email
        if not self.email.value.endswith("@ufl.edu"):
            await interaction.response.send_message(
                "You must use a @ufl.edu email address to verify your identity.",
                ephemeral=True,
            )
            return

        candidate = self.bot.verifier.request_verification(
            self.email.value,
            interaction.user,
            welcoming=self.welcoming,
        )
        await self.bot.verifier.send_verification_email(candidate)
        one_minute = discord.utils.utcnow() + datetime.timedelta(minutes=1)
        view = FinishEmailVerificationView(self.bot, candidate)
        await interaction.response.send_message(
            f"A verification email has been sent to your email address! Please check your inbox and enter the verification code using the button below. If you do not receive an email, you can request a new code {discord.utils.format_dt(one_minute, 'R')}.",
            ephemeral=True,
            view=view,
        )
        view.message = await interaction.original_response()


class StartEmailVerificationView(MILBotView):
    def __init__(self, bot: MILBot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Verify Email",
        style=discord.ButtonStyle.green,
        custom_id="start_email_verification:verify",
    )
    async def verify_email(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        assert isinstance(interaction.user, discord.Member)
        if self.bot.verified_role in interaction.user.roles:
            await interaction.response.send_message(
                "You are already verified!",
                ephemeral=True,
            )
            return
        self.welcoming = self.bot.unverified_role not in interaction.user.roles
        await interaction.response.send_modal(
            EmailModal(self.bot, welcoming=self.welcoming),
        )
