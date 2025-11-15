from bson import ObjectId
from utils.db import db
from utils.mailer import send_email, tpl_reply_received, tpl_random_received
from utils.config import APP_BASE_URL, MAIL_DEBUG

def notify_reply_received(user_id: str, letter_id: str, debug_mail: bool = MAIL_DEBUG):
    # email, nickname, email_verified까지 가져오기
    user = db.user.find_one(
        {"_id": ObjectId(user_id)},
        {"email": 1, "nickname": 1, "email_verified": 1}
    )
    if not user or not user.get("email"):
        return False, "recipient not found or missing email"

    # ✅ 이메일 인증 안 된 경우: 메일 보내지 않음
    if not user.get("email_verified"):
        return False, "email not verified"

    html = tpl_reply_received(user.get("nickname", ""), "(제목)", APP_BASE_URL)
    ok, err = send_email(user["email"], "보낸 편지에 답장이 도착했어요", html)
    return ok, err


def notify_random_received(user_id: str, letter_id: str, debug_mail: bool = MAIL_DEBUG):
    # email, nickname, email_verified까지 가져오기
    user = db.user.find_one(
        {"_id": ObjectId(user_id)},
        {"email": 1, "nickname": 1, "email_verified": 1}
    )
    if not user or not user.get("email"):
        return False, "recipient not found or missing email"

    # ✅ 이메일 인증 안 된 경우: 메일 보내지 않음
    if not user.get("email_verified"):
        return False, "email not verified"

    html = tpl_random_received(user.get("nickname", ""), "(제목)", APP_BASE_URL)
    ok, err = send_email(user["email"], "새 편지가 도착했어요 ✉️", html)
    return ok, err

'''
from bson import ObjectId
from utils.db import db
from utils.mailer import send_email, tpl_reply_received, tpl_random_received
from utils.config import APP_BASE_URL

def _get_user_and_letter(user_id, letter_id):
    user = db.user.find_one({"_id": ObjectId(user_id)}, {"email":1,"nickname":1})
    letter = db.letter.find_one({"_id": ObjectId(letter_id)}, {"title":1})
    return user, letter


def notify_reply_received(user_id: str, letter_id: str, debug_mail: bool=False):
    user = db.users.find_one({"_id": ObjectId(user_id)}, {"email":1, "nickname":1})
    if not user:
        return False, f"recipient not found: {user_id}"
    if not user.get("email"):
        return False, f"recipient email missing: {user_id}"
    html = tpl_reply_received(user.get("nickname",""), "(제목)", APP_BASE_URL)
    return send_email(user["email"], "보낸 편지에 답장이 도착했어요", html, debug=debug_mail)

def notify_random_received(to_user_id, letter_id):
    user, letter = _get_user_and_letter(to_user_id, letter_id)
    if not user or not user.get("email"):
        return False, "no user/email"
    html = tpl_random_received(user.get("nickname","회원"), letter.get("title","(제목 없음)"), APP_BASE_URL)
    return send_email(user["email"], "새로운 편지가 도착했어요", html)
'''