"""Shared SMTP transport; no credential values enter reports or error messages."""
import smtplib,ssl
from .settings import settings

def send_smtp(message):
    factory=smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
    options={'context':ssl.create_default_context()} if settings.smtp_ssl else {}
    with factory(settings.smtp_host,settings.smtp_port,timeout=20,**options) as smtp:
        if settings.smtp_starttls and not settings.smtp_ssl:
            smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
        if settings.smtp_username:smtp.login(settings.smtp_username,settings.smtp_password)
        rejected=smtp.send_message(message)
        if rejected:raise smtplib.SMTPRecipientsRefused(rejected)
