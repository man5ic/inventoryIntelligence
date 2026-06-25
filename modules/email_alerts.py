"""
Phase 4: Email Alert System
Sends automated email alerts using SMTP (stdlib smtplib).
Falls back gracefully if email is not configured.
"""
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Config (reads from environment or app config)
# ─────────────────────────────────────────────────────────────

def get_email_config(app_config: dict = None) -> dict:
    cfg = app_config or {}
    return {
        'smtp_host':   cfg.get('MAIL_SERVER',   os.getenv('MAIL_SERVER',   'smtp.gmail.com')),
        'smtp_port':   int(cfg.get('MAIL_PORT', os.getenv('MAIL_PORT',     '587'))),
        'use_tls':     cfg.get('MAIL_USE_TLS',  os.getenv('MAIL_USE_TLS',  'true')).lower() == 'true'
                       if isinstance(cfg.get('MAIL_USE_TLS', os.getenv('MAIL_USE_TLS', 'true')), str)
                       else cfg.get('MAIL_USE_TLS', True),
        'username':    cfg.get('MAIL_USERNAME', os.getenv('MAIL_USERNAME', '')),
        'password':    cfg.get('MAIL_PASSWORD', os.getenv('MAIL_PASSWORD', '')),
        'sender':      cfg.get('MAIL_DEFAULT_SENDER', os.getenv('MAIL_DEFAULT_SENDER', '')),
        'recipient':   cfg.get('ALERT_RECIPIENT',     os.getenv('ALERT_RECIPIENT',     '')),
    }


def is_email_configured(app_config: dict = None) -> bool:
    cfg = get_email_config(app_config)
    return bool(cfg['username'] and cfg['password'] and cfg['recipient'])


# ─────────────────────────────────────────────────────────────
# Email Builder
# ─────────────────────────────────────────────────────────────

def _build_alert_email(alert_result: dict, exec_summary: dict) -> tuple:
    """Returns (subject, html_body)."""
    crit  = alert_result.get('critical_count', 0)
    total = alert_result.get('total', 0)
    now   = datetime.now().strftime('%d %b %Y')

    if crit:
        subject = f"⚠️ CRITICAL: {crit} Inventory Alert{'s' if crit > 1 else ''} – {now}"
    else:
        subject = f"Inventory Intelligence Digest – {now}"

    # Build alert rows
    rows = ''
    priority_colors = {
        'CRITICAL': ('#FEE2E2', '#991B1B', '#DC2626'),
        'MEDIUM':   ('#FEF3C7', '#92400E', '#D97706'),
        'LOW':      ('#DBEAFE', '#1E40AF', '#2563EB'),
    }
    for alert in alert_result.get('alerts', []):
        bg, fg, badge_color = priority_colors.get(alert['priority'], ('#F8FAFC', '#334155', '#64748B'))
        mats = ', '.join(alert.get('materials', [])[:4])
        mats_row = f"<tr><td colspan='2' style='padding:4px 16px;font-size:12px;color:#64748B;'>Materials: {mats}</td></tr>" if mats else ''
        rows += f"""
        <tr style='background:{bg};'>
          <td style='padding:10px 16px;font-weight:bold;color:{fg};width:120px;'>
            <span style='background:{badge_color};color:white;padding:2px 8px;border-radius:9999px;font-size:11px;'>{alert['priority']}</span>
          </td>
          <td style='padding:10px 16px;color:#1E293B;'>
            <strong>{alert['title']}</strong><br/>
            <span style='font-size:13px;color:#475569;'>{alert['message']}</span>
          </td>
        </tr>
        {mats_row}
        """

    # Exec summary bullets
    bullet_rows = ''.join(
        f"<li style='margin-bottom:6px;color:#334155;'>{b}</li>"
        for b in exec_summary.get('bullets', [])[:5]
    )
    risk_rows = ''.join(
        f"<li style='margin-bottom:6px;color:#991B1B;'>⚠ {r}</li>"
        for r in exec_summary.get('risk_flags', [])
    )
    rec_rows = ''.join(
        f"<li style='margin-bottom:6px;color:#166534;'>✓ {r}</li>"
        for r in exec_summary.get('recommendations', [])
    )

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style='font-family:system-ui,sans-serif;background:#F1F5F9;margin:0;padding:20px;'>
      <div style='max-width:640px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);'>
        <!-- Header -->
        <div style='background:#1E3A5F;padding:24px;'>
          <h1 style='color:white;margin:0;font-size:20px;'>📦 Inventory Intelligence System</h1>
          <p style='color:#94A3B8;margin:4px 0 0;font-size:13px;'>Automated Alert Report · {now}</p>
        </div>

        <!-- Executive Headline -->
        <div style='padding:20px 24px;background:#EFF6FF;border-bottom:1px solid #BFDBFE;'>
          <p style='margin:0;font-size:15px;color:#1E40AF;font-weight:600;'>{exec_summary.get('headline','')}</p>
        </div>

        <!-- KPIs -->
        <div style='display:flex;gap:12px;padding:20px 24px;flex-wrap:wrap;'>
          <div style='flex:1;min-width:120px;background:#F8FAFC;border-radius:8px;padding:12px;text-align:center;'>
            <div style='font-size:22px;font-weight:bold;color:#1E3A5F;'>{total}</div>
            <div style='font-size:11px;color:#64748B;'>Active Alerts</div>
          </div>
          <div style='flex:1;min-width:120px;background:#FEE2E2;border-radius:8px;padding:12px;text-align:center;'>
            <div style='font-size:22px;font-weight:bold;color:#DC2626;'>{crit}</div>
            <div style='font-size:11px;color:#64748B;'>Critical</div>
          </div>
          <div style='flex:1;min-width:120px;background:#FEF3C7;border-radius:8px;padding:12px;text-align:center;'>
            <div style='font-size:22px;font-weight:bold;color:#D97706;'>{alert_result.get('medium_count',0)}</div>
            <div style='font-size:11px;color:#64748B;'>Medium</div>
          </div>
          <div style='flex:1;min-width:120px;background:#DBEAFE;border-radius:8px;padding:12px;text-align:center;'>
            <div style='font-size:22px;font-weight:bold;color:#2563EB;'>{alert_result.get('low_count',0)}</div>
            <div style='font-size:11px;color:#64748B;'>Low</div>
          </div>
        </div>

        <!-- Alerts -->
        <div style='padding:0 24px 20px;'>
          <h2 style='font-size:15px;color:#1E3A5F;margin-bottom:12px;'>Active Alerts</h2>
          <table style='width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;'>
            {rows}
          </table>
        </div>

        <!-- Executive Summary -->
        <div style='padding:0 24px 20px;'>
          <h2 style='font-size:15px;color:#1E3A5F;margin-bottom:8px;'>Business Summary</h2>
          <ul style='padding-left:20px;margin:0;'>{bullet_rows}</ul>
        </div>

        {'<div style="padding:0 24px 20px;"><h2 style="font-size:15px;color:#991B1B;margin-bottom:8px;">Risk Flags</h2><ul style="padding-left:20px;margin:0;">' + risk_rows + '</ul></div>' if risk_rows else ''}

        <div style='padding:0 24px 20px;'>
          <h2 style='font-size:15px;color:#166534;margin-bottom:8px;'>Recommended Actions</h2>
          <ul style='padding-left:20px;margin:0;'>{rec_rows}</ul>
        </div>

        <!-- Footer -->
        <div style='background:#F8FAFC;padding:16px 24px;border-top:1px solid #E2E8F0;'>
          <p style='margin:0;font-size:12px;color:#94A3B8;'>
            Inventory Intelligence System · Phase 4 · Auto-generated on {now}<br/>
            This is an automated alert. Do not reply to this email.
          </p>
        </div>
      </div>
    </body>
    </html>
    """
    return subject, html


# ─────────────────────────────────────────────────────────────
# Send
# ─────────────────────────────────────────────────────────────

def send_alert_email(alert_result: dict, exec_summary: dict, app_config: dict = None) -> dict:
    """
    Send an alert email.
    Returns {'success': bool, 'message': str}
    """
    if not is_email_configured(app_config):
        return {
            'success': False,
            'message': 'Email not configured. Set MAIL_USERNAME, MAIL_PASSWORD, and ALERT_RECIPIENT.'
        }

    cfg = get_email_config(app_config)
    subject, html_body = _build_alert_email(alert_result, exec_summary)

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = cfg['sender'] or cfg['username']
        msg['To']      = cfg['recipient']
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(cfg['smtp_host'], cfg['smtp_port'], timeout=15) as server:
            if cfg['use_tls']:
                server.starttls()
            server.login(cfg['username'], cfg['password'])
            server.sendmail(msg['From'], [cfg['recipient']], msg.as_string())

        return {'success': True, 'message': f"Alert email sent to {cfg['recipient']}"}
    except Exception as e:
        return {'success': False, 'message': f"Email failed: {str(e)}"}
