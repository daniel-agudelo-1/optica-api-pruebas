import os
import logging
import re
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        self.host     = os.environ.get('MAIL_SERVER', 'sandbox.smtp.mailtrap.io')
        self.port     = int(os.environ.get('MAIL_PORT', 2525))
        self.username = os.environ.get('MAIL_USERNAME')
        self.password = os.environ.get('MAIL_PASSWORD')
        self.sender   = os.environ.get('MAIL_DEFAULT_SENDER', 'no-reply@visualoutlet.com')
        self.use_tls  = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'

    def _esta_configurado(self) -> bool:
        return bool(self.username and self.password)

    def _enviar(self, destinatario_email: str, destinatario_nombre: str,
                asunto: str, html: str) -> bool:
        if not self._esta_configurado():
            logger.error("Mailtrap no configurado: MAIL_USERNAME o MAIL_PASSWORD ausentes")
            return False
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = asunto
            msg['From']    = f"Visual Outlet <{self.sender}>"
            msg['To']      = f"{destinatario_nombre} <{destinatario_email}>"
            msg.attach(MIMEText(html, 'html'))

            with smtplib.SMTP(self.host, self.port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.sender, destinatario_email, msg.as_string())

            logger.info(f"✅ Email enviado a {destinatario_email} | {asunto}")
            return True
        except Exception as e:
            logger.error(f"❌ Error enviando a {destinatario_email}: {e}")
            return False

    def enviar_codigo_verificacion(self, correo: str, nombre: str, codigo: str) -> bool:
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center" style="padding:40px 20px;">
              <table width="560" cellpadding="0" cellspacing="0"
                     style="background:#fff;border-radius:8px;overflow:hidden;
                            box-shadow:0 2px 8px rgba(0,0,0,0.08);">
                <tr><td style="background:#1a1a2e;padding:28px 40px;">
                  <h1 style="margin:0;color:#fff;font-size:22px;">Visual Outlet</h1>
                </td></tr>
                <tr><td style="padding:40px;">
                  <h2 style="margin:0 0 12px;color:#1a1a2e;">Hola, {nombre} 👋</h2>
                  <p style="margin:0 0 28px;color:#555;font-size:15px;line-height:1.6;">
                    Tu código de verificación es (caduca en <strong>15 minutos</strong>):
                  </p>
                  <div style="text-align:center;margin:0 0 32px;">
                    <span style="display:inline-block;background:#f0f0ff;
                                 border:2px dashed #5b5fc7;border-radius:10px;
                                 padding:18px 48px;font-size:36px;font-weight:700;
                                 letter-spacing:12px;color:#3730a3;">
                      {codigo}
                    </span>
                  </div>
                  <p style="margin:0;color:#999;font-size:13px;">
                    Si no solicitaste este registro, ignora este mensaje.
                  </p>
                </td></tr>
                <tr><td style="background:#f8f8f8;padding:20px 40px;
                               border-top:1px solid #eee;text-align:center;">
                  <p style="margin:0;color:#bbb;font-size:12px;">
                    © 2025 Visual Outlet · Correo automático, no responder.
                  </p>
                </td></tr>
              </table>
            </td></tr>
          </table>
        </body>
        </html>
        """
        # Asíncrono: no bloquea el worker mientras Mailtrap responde
        thread = threading.Thread(
            target=self._enviar,
            args=(correo, nombre, "Código de verificación — Visual Outlet", html),
            daemon=True
        )
        thread.start()
        return True

    def enviar_codigo_reset(self, correo: str, nombre: str, codigo: str) -> bool:
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center" style="padding:40px 20px;">
              <table width="560" cellpadding="0" cellspacing="0"
                     style="background:#fff;border-radius:8px;overflow:hidden;
                            box-shadow:0 2px 8px rgba(0,0,0,0.08);">
                <tr><td style="background:#1a1a2e;padding:28px 40px;">
                  <h1 style="margin:0;color:#fff;font-size:22px;">Visual Outlet</h1>
                </td></tr>
                <tr><td style="padding:40px;">
                  <h2 style="margin:0 0 12px;color:#1a1a2e;">Restablecer contraseña</h2>
                  <p style="margin:0 0 8px;color:#555;font-size:15px;line-height:1.6;">
                    Hola <strong>{nombre}</strong>, tu código es
                    (caduca en <strong>15 minutos</strong>):
                  </p>
                  <div style="text-align:center;margin:0 0 32px;">
                    <span style="display:inline-block;background:#fff5f0;
                                 border:2px dashed #ea580c;border-radius:10px;
                                 padding:18px 48px;font-size:36px;font-weight:700;
                                 letter-spacing:12px;color:#c2410c;">
                      {codigo}
                    </span>
                  </div>
                  <p style="margin:0;color:#999;font-size:13px;">
                    Si no solicitaste este cambio, ignora este mensaje.
                  </p>
                </td></tr>
                <tr><td style="background:#f8f8f8;padding:20px 40px;
                               border-top:1px solid #eee;text-align:center;">
                  <p style="margin:0;color:#bbb;font-size:12px;">
                    © 2025 Visual Outlet · Correo automático, no responder.
                  </p>
                </td></tr>
              </table>
            </td></tr>
          </table>
        </body>
        </html>
        """
        # Sincrónico: necesitamos saber si falló antes de guardar el código en memoria
        return self._enviar(correo, nombre, "Restablecer contraseña — Visual Outlet", html)


email_service = EmailService()

def enviar_codigo_verificacion(correo, nombre, codigo):
    return email_service.enviar_codigo_verificacion(correo, nombre, codigo)

def enviar_codigo_reset(correo, nombre, codigo):
    return email_service.enviar_codigo_reset(correo, nombre, codigo)