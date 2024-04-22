from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from .env import EMAIL_PASSWORD, EMAIL_USERNAME


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
