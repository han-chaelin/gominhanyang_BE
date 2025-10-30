import smtplib, ssl, socket
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

def _bool(v):
    return v if isinstance(v, bool) else str(v).lower() == "true"

def send_email(to_email: str, subject: str, html: str, *, debug: bool=False, retries: int=2):
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

    use_tls = _bool(EMAIL_USE_TLS)
    port = int(SMTP_PORT)
    envelope_from = (SMTP_USER or parseaddr(msg["From"])[1] or "").strip()
    to_addr = (parseaddr(to_email)[1] or to_email).strip()

    last_err = None
    for attempt in range(retries + 1):
        try:
            if str(port) == "465":
                context = ssl.create_default_context()
                smtp = smtplib.SMTP_SSL(SMTP_HOST, port, timeout=10, context=context)
                smtp.ehlo()
            else:
                smtp = smtplib.SMTP(SMTP_HOST, port, timeout=10)
                if debug:
                    smtp.set_debuglevel(1)
                smtp.ehlo()
                if use_tls:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    smtp.ehlo()

            if SMTP_USER and SMTP_PASSWORD:
                smtp.login(SMTP_USER, SMTP_PASSWORD)

            # 연결 살아있는지 체크
            try:
                smtp.noop()
            except Exception:
                smtp.ehlo()

            smtp.sendmail(envelope_from, [to_addr], msg.as_string())
            smtp.quit()
            return True, None

        except (smtplib.SMTPServerDisconnected, smtplib.SMTPDataError,
                smtplib.SMTPConnectError, socket.timeout, OSError) as e:
            last_err = e
            try:
                smtp.quit()
            except Exception:
                pass
            # 일시 오류 재시도 (작게 backoff)
            if attempt < retries:
                continue
            return False, f"{type(e).__name__}: {e}"

        except Exception as e:
            last_err = e
            try:
                smtp.quit()
            except Exception:
                pass
            return False, f"{type(e).__name__}: {e}"

    return False, str(last_err) if last_err else "unknown error"

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
