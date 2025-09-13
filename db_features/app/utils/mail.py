import smtplib, ssl
from email.message import EmailMessage
from flask import current_app

def send_email(to: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config["MAIL_USERNAME"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    host = current_app.config["MAIL_SERVER"]
    port = current_app.config["MAIL_PORT"]
    user = current_app.config["MAIL_USERNAME"]
    pwd  = current_app.config["MAIL_PASSWORD"]
    use_ssl = current_app.config.get("MAIL_USE_SSL", True)
    use_tls = current_app.config.get("MAIL_USE_TLS", False)

    if use_ssl:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx) as s:
            s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as s:
            if use_tls:
                s.starttls(context=ssl.create_default_context())
            s.login(user, pwd)
            s.send_message(msg)

