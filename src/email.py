from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum

import aiosmtplib

from .env import EMAIL_PASSWORD, EMAIL_USERNAME


class HeaderPrefix(Enum):
    FULL = LONG = "[Machine Intelligence Laboratory]"
    INITIALS = SHORT = "[MIL]"


@dataclass
class Email:
    receiver_emails: list[str]
    subject: str
    html: str
    text: str | None = None
    cc_emails: list[str] | None = None
    header_prefix: HeaderPrefix | None = HeaderPrefix.INITIALS

    async def send(self) -> None:
        port = 587
        hostname = "smtp.ufl.edu"
        sender_email = EMAIL_USERNAME
        password = EMAIL_PASSWORD
        if not sender_email or not password:
            raise RuntimeError(
                "No email username and/or password found! Cannot send email.",
            )

        smtp_server = aiosmtplib.SMTP()
        await smtp_server.connect(hostname=hostname, port=port)
        await smtp_server.login(sender_email, password)
        custom_email = "bot@mil.ufl.edu"

        # Create a multipart message and set headers
        message = MIMEMultipart("alternative")
        message["From"] = custom_email
        message["To"] = ", ".join(self.receiver_emails)
        message["Subject"] = (
            f"{self.header_prefix.value} {self.subject}"
            if self.header_prefix
            else self.subject
        )

        # Turn these into plain/html MIMEText objects
        if self.text is None:
            # Attempt to convert HTML to text
            self.text = (
                self.html.replace("<p>", " ").replace("</p>", " ").replace("\n", " ")
            )

        text_footer = " --- This is an automated message. Replies will not be received."
        html_footer = "\n\n<p>---<br>This is an automated message. Replies will not be received.</p>"
        part1 = MIMEText(self.text + text_footer, "plain")
        part2 = MIMEText(self.html + html_footer, "html")
        message.attach(part1)
        message.attach(part2)

        await smtp_server.sendmail(
            custom_email,
            self.receiver_emails,
            message.as_string(),
        )
        await smtp_server.quit()


async def send_email(receiver_email, subject, html, text) -> bool:
    port = 587
    hostname = "smtp.ufl.edu"
    sender_email = EMAIL_USERNAME
    password = EMAIL_PASSWORD
    if not sender_email or not password:
        raise RuntimeError(
            "No email username and/or password found! Cannot send email.",
        )

    # message = f"Subject: {subject}\n\n{body}"
    smtp_server = aiosmtplib.SMTP()
    await smtp_server.connect(hostname=hostname, port=port)
    await smtp_server.login(sender_email, password)
    custom_email = "bot@mil.ufl.edu"

    # Create a multipart message and set headers
    message = MIMEMultipart("alternative")
    message["From"] = custom_email
    message["To"] = receiver_email
    message["Subject"] = subject

    # Turn these into plain/html MIMEText objects
    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")
    message.attach(part1)
    message.attach(part2)

    await smtp_server.sendmail(custom_email, receiver_email, message.as_string())
    await smtp_server.quit()
    return True
