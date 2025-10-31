from datetime import datetime, timezone
from bson import ObjectId
import pytz
from utils.db import db

KST = pytz.timezone("Asia/Seoul")

def local_date_str(ts: datetime | None = None) -> str:
    """Asia/Seoul 기준 YYYY-MM-DD 문자열"""
    ts = ts or datetime.now(timezone.utc)
    return ts.astimezone(KST).strftime("%Y-%m-%d")

def mark_attendance_login(user_id: str | ObjectId, ts: datetime | None = None) -> None:
    """로그인 성공 시 하루 1회 출석 처리 (KST 기준 날짜로 upsert)."""
    day = local_date_str(ts)
    now = datetime.now(timezone.utc)  
    uid = ObjectId(user_id) if isinstance(user_id, str) else user_id

    db.attendance.update_one(
        {"user_id": uid, "date": day},
        {
            "$setOnInsert": {
                "user_id": uid,
                "date": day,
                "attended": True,
                "first_action_at": now,
                "counts": {"login": 0},
                "actions": []
            },
            "$set": {"last_action_at": now, "attended": True},
            "$addToSet": {"actions": "login"},
            "$inc": {"counts.login": 1}
        },
        upsert=True
    )

def attended_today(user_id: str | ObjectId) -> bool:
    """오늘(한국시간) 이미 출석(로그인)했는지 여부"""
    uid = ObjectId(user_id) if isinstance(user_id, str) else user_id
    day = local_date_str()
    doc = db.attendance.find_one({"user_id": uid, "date": day}, {"_id": 1})
    return bool(doc)