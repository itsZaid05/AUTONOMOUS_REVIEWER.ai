"""Shared SMTP transport; no credential values enter reports or error messages."""
import smtplib,ssl
from .settings import settings

def send_smtp(message):
    if settings.mail_mode.upper()=='DEMO':
        if settings.smtp_host not in ['mailpit','127.0.0.1','localhost'] or settings.smtp_port!=1025 or settings.smtp_username or settings.smtp_ssl or settings.smtp_starttls:
            raise ValueError('DEMO delivery is restricted to local Mailpit port 1025 without relay credentials')
        import httpx
        from urllib.parse import urlparse
        local=urlparse(settings.mailpit_api_url)
        if local.hostname not in ['mailpit','127.0.0.1','localhost'] or local.scheme!='http' or local.port!=8025:raise ValueError('DEMO Mailpit verification must use its local HTTP API')
        response=httpx.get(settings.mailpit_api_url.rstrip('/')+'/api/v1/info',timeout=10,trust_env=False)
        response.raise_for_status()
        if not isinstance(response.json(),dict) or not {'Version','Database','Messages'}<=set(response.json()):raise ValueError('Mailpit identity check failed')
    elif settings.mail_mode.upper()!='LIVE':raise ValueError('Unknown mail mode')
    factory=smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
    options={'context':ssl.create_default_context()} if settings.smtp_ssl else {}
    with factory(settings.smtp_host,settings.smtp_port,timeout=20,**options) as smtp:
        if settings.smtp_starttls and not settings.smtp_ssl:
            smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
        if settings.smtp_username:smtp.login(settings.smtp_username,settings.smtp_password)
        rejected=smtp.send_message(message)
        if rejected:raise smtplib.SMTPRecipientsRefused(rejected)
