import smtplib
import ssl
from email.message import EmailMessage


class SMTPEmailSender:
    def __init__(self, host, port, username, password, recipient, sender=None, security='ssl'):
        if not host or not username or not password or not recipient:
            raise ValueError('Configure servidor, usuário, senha e destinatário do SMTP.')
        if security not in ('ssl', 'starttls'):
            raise ValueError('SMTP_SECURITY deve ser ssl ou starttls.')
        if not 1 <= port <= 65535:
            raise ValueError('Porta SMTP inválida.')
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.recipient, self.sender, self.security = recipient, sender or username, security

    def send(self, answer):
        message = EmailMessage()
        message['Subject'] = 'ScrollAnswer: resposta'
        message['From'] = self.sender
        message['To'] = self.recipient
        message.set_content(answer)
        context = ssl.create_default_context()
        if self.security == 'ssl':
            with smtplib.SMTP_SSL(self.host, self.port, timeout=15, context=context) as smtp:
                smtp.login(self.username, self.password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(self.username, self.password)
                smtp.send_message(message)
