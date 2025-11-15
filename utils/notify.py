from bson import ObjectId
from utils.db import db
from utils.mailer import send_email, tpl_reply_received, tpl_random_received
from utils.config import APP_BASE_URL, MAIL_DEBUG

def notify_reply_received(user_id: str, letter_id: str, debug_mail: bool = MAIL_DEBUG):
    # email, nickname, email_verified까지 가져오기
    user = db.user.find_one(
        {"_id": ObjectId(user_id)},
        {
            "email": 1,
            "nickname": 1,
            "email_verified": 1,
            "email_notify_enabled": 1,
        }
    )
    if not user or not user.get("email"):
        return False, "recipient not found or missing email"

    # 이메일 인증 안 된 경우: 메일 보내지 않음
    if not user.get("email_verified"):
        return False, "email not verified"
    
    # 이메일 알림 동의 안 한 경우: 메일 보내지 않음
    if not user.get("email_notify_enabled", False):
        return False, "email notifications disabled"

    # letter_id로 실제 제목 가져오고 싶으면 여기서 조회해도 됨
    html = tpl_reply_received(user.get("nickname", ""), "(제목)", APP_BASE_URL)
    ok, err = send_email(user["email"], "보낸 편지에 답장이 도착했어요", html)
    return ok, err

def notify_random_received(user_id: str, letter_id: str, debug_mail: bool = MAIL_DEBUG):
    # email, nickname, email_verified, email_notify_enabled까지 가져오기
    user = db.user.find_one(
        {"_id": ObjectId(user_id)},
        {
            "email": 1,
            "nickname": 1,
            "email_verified": 1,
            "email_notify_enabled": 1,
        }
    )
    if not user or not user.get("email"):
        return False, "recipient not found or missing email"

    # 이메일 인증 안 된 경우: 메일 보내지 않음
    if not user.get("email_verified"):
        return False, "email not verified"
    
    # 이메일 알림 동의 안 한 경우: 메일 보내지 않음
    if not user.get("email_notify_enabled", False):
        return False, "email notifications disabled"

    html = tpl_random_received(user.get("nickname", ""), "(제목)", APP_BASE_URL)
    ok, err = send_email(user["email"], "새 편지가 도착했어요 ✉️", html)
    return ok, err