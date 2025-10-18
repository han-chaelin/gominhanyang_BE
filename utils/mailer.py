import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr, parseaddr
from datetime import datetime
from utils.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    EMAIL_FROM, EMAIL_USE_TLS, APP_BASE_URL
)

def _format_from_header(raw_from: str) -> str:
    """
    EMAIL_FROM가 '마음의 항해 <foo@bar.com>' 또는 'foo@bar.com' 어떤 형태든
    안전하게 UTF-8 인코딩된 From 헤더로 변환
    """
    name, addr = parseaddr(raw_from or "")
    if not addr:
        # EMAIL_FROM가 비어있으면 SMTP_USER 사용
        addr = SMTP_USER or ""
    # 한글/이모지 표시명을 RFC2047로 인코딩
    if name:
        return formataddr((str(Header(name, "utf-8")), addr))
    else:
        return addr  # 표시명이 없으면 주소만

def _format_to_header(to_email: str) -> str:
    # 혹시 사용자가 '이름 <addr>' 형태를 넘겨도 안전하게 포맷
    name, addr = parseaddr(to_email or "")
    if not addr:
        return ""
    return formataddr((str(Header(name, "utf-8")), addr)) if name else addr

def send_email(to_email: str, subject: str, html: str):
    if not to_email:
        return False, "no recipient"
    if not SMTP_HOST:
        return False, "SMTP_HOST not set"
    if not SMTP_PORT:
        return False, "SMTP_PORT not set"

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = str(Header(subject or "", "utf-8"))
    msg["From"] = _format_from_header(EMAIL_FROM or SMTP_USER or "")
    msg["To"] = _format_to_header(to_email)

    try:
        # 465면 SSL, 587이면 STARTTLS
        if str(SMTP_PORT) == "465":
            smtp = smtplib.SMTP_SSL(SMTP_HOST, int(SMTP_PORT), timeout=10)
            smtp.ehlo()
        else:
            smtp = smtplib.SMTP(SMTP_HOST, int(SMTP_PORT), timeout=10)
            smtp.ehlo()
            # 일부 환경에서 EMAIL_USE_TLS가 문자열("true"/"false")일 수 있어 bool로 보정
            use_tls = EMAIL_USE_TLS if isinstance(EMAIL_USE_TLS, bool) else str(EMAIL_USE_TLS).lower() == "true"
            if use_tls:
                smtp.starttls()
                smtp.ehlo()

        if SMTP_USER and SMTP_PASSWORD:
            smtp.login(SMTP_USER, SMTP_PASSWORD)

        # 연결이 정말 되었는지 간단 체크 (sock 유무)
        if getattr(smtp, "sock", None) is None:
            try:
                smtp.connect(SMTP_HOST, int(SMTP_PORT))
                use_tls = EMAIL_USE_TLS if isinstance(EMAIL_USE_TLS, bool) else str(EMAIL_USE_TLS).lower() == "true"
                if use_tls and str(SMTP_PORT) != "465":
                    smtp.starttls(); smtp.ehlo()
            except Exception as e:
                smtp.quit()
                return False, f"connect() failed: {e}"

        smtp.sendmail(msg["From"], [parseaddr(to_email)[1] or to_email], msg.as_string())
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
