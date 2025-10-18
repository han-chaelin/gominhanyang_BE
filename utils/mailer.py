import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from utils.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM, EMAIL_USE_TLS, APP_BASE_URL

def send_email(to_email: str, subject: str, html: str):
    if not to_email:
        return False, "no recipient"
    if not SMTP_HOST:
        return False, "SMTP_HOST not set"
    if not SMTP_PORT:
        return False, "SMTP_PORT not set"

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM or SMTP_USER or ""
    msg["To"] = to_email

    try:
        # 465면 SSL, 587이면 STARTTLS가 일반적
        if str(SMTP_PORT) == "465":
            smtp = smtplib.SMTP_SSL(SMTP_HOST, int(SMTP_PORT), timeout=10)
            smtp.ehlo()
        else:
            smtp = smtplib.SMTP(SMTP_HOST, int(SMTP_PORT), timeout=10)
            smtp.ehlo()
            if EMAIL_USE_TLS:
                smtp.starttls()
                smtp.ehlo()

        if SMTP_USER and SMTP_PASSWORD:
            smtp.login(SMTP_USER, SMTP_PASSWORD)

        # 연결이 정말 되었는지 간단 체크 (sock 유무)
        if getattr(smtp, "sock", None) is None:
            try:
                smtp.connect(SMTP_HOST, int(SMTP_PORT))
                if EMAIL_USE_TLS and str(SMTP_PORT) != "465":
                    smtp.starttls(); smtp.ehlo()
            except Exception as e:
                smtp.quit()
                return False, f"connect() failed: {e}"

        smtp.sendmail(msg["From"], [to_email], msg.as_string())
        smtp.quit()
        return True, None
    except Exception as e:
        try:
            smtp.quit()
        except:
            pass
        return False, str(e)


'''def send_email(to_email: str, subject: str, html: str):
    if not to_email:
        return False, "no recipient"
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    try:
        smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
        if EMAIL_USE_TLS:
            smtp.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.sendmail(EMAIL_FROM, [to_email], msg.as_string())
        smtp.quit()
        return True, None
    except Exception as e:
        return False, str(e)
'''

# 메일 템플릿 함수
def tpl_reply_received(nickname: str, letter_title: str, app_url: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    return f"""
    <h3>{nickname}님, 보낸 편지에 <b>답장</b>이 도착했어요.</h3>
    <p><b>제목:</b> {letter_title}</p>
    <p><a href="{app_url}/letters/sent">답장 보러가기</a></p>
    <hr><small>발송시각: {ts}</small>
    """

def tpl_random_received(nickname: str, letter_title: str, app_url: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    return f"""
    <h3>{nickname}님께 <b>새 편지</b>가 도착했어요 ✉️</h3>
    <p><b>제목:</b> {letter_title}</p>
    <p><a href="{app_url}/letters/inbox">편지 보러가기</a></p>
    <hr><small>발송시각: {ts}</small>
    """
