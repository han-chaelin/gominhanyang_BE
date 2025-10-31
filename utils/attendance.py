from datetime import datetime, timezone
from bson import ObjectId
import pytz
from utils.db import db

KST = pytz.timezone("Asia/Seoul")

def local_date_str(ts=None) -> str:
    ts = ts or datetime.now(timezone.utc)
    return ts.astimezone(KST).strftime("%Y-%m-%d")

def mark_attendance_login(user_id):
    """유저 한 문서에 days.<YYYY-MM-DD>로 로그인 출석을 누적(파이프라인 업데이트)."""
    uid = ObjectId(user_id) if isinstance(user_id, str) else user_id
    day = local_date_str()
    now = datetime.now(timezone.utc)

    db.attendance.update_one(
        {"user_id": uid},
        [
            {
                "$set": {
                    "user_id":   {"$ifNull": ["$user_id",   uid]},
                    "created_at":{"$ifNull": ["$created_at", now]},
                    "updated_at": now,

                    # 날짜 블록 병합(없으면 초기화)
                    f"days.{day}": {
                        "$let": {
                            "vars": { "d": { "$ifNull": [ f"$days.{day}", {} ] } },
                            "in": {
                                "attended": True,
                                "actions": {
                                    "$setUnion": [
                                        { "$ifNull": ["$$d.actions", []] },
                                        ["login"]
                                    ]
                                },
                                "counts": {
                                    "login": {
                                        "$add": [
                                            { "$ifNull": ["$$d.counts.login", 0] },
                                            1
                                        ]
                                    }
                                },
                                "first_action_at": { "$ifNull": ["$$d.first_action_at", now] },
                                "last_action_at":  now
                            }
                        }
                    },

                    # days_index도 안전하게 배열로 유지
                    "days_index": {
                        "$setUnion": [
                            { "$ifNull": ["$days_index", []] },
                            [day]
                        ]
                    }
                }
            }
        ],
        upsert=True
    )

def attended_today(user_id) -> bool:
    uid = ObjectId(user_id) if isinstance(user_id, str) else user_id
    day = local_date_str()
    doc = db.attendance.find_one(
        {"user_id": uid, f"days.{day}.attended": True},
        {"_id": 1}
    )
    return bool(doc)

def record_attendance(user_id: str | ObjectId) -> bool:
    """
    로그인 성공 직후 호출용: 출석 마킹(upsert)하고,
    오늘 출석 여부 불리언을 바로 반환한다.
    """
    mark_attendance_login(user_id)
    return attended_today(user_id)

def get_today_attendance_doc(user_id):
    """상세 문서(오늘) 반환: 없으면 None."""
    uid = ObjectId(user_id) if isinstance(user_id, str) else user_id
    day = local_date_str()
    return db.attendance.find_one(
        {"user_id": uid},
        {f"days.{day}": 1, "_id": 0}
    )

'''
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
            },
            "$set": {"last_action_at": now},
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

def record_attendance(user_id: str | ObjectId) -> bool:
    """
    로그인 성공 직후 호출용: 출석 마킹(upsert)하고,
    오늘 출석 여부 불리언을 바로 반환한다.
    """
    mark_attendance_login(user_id)
    return attended_today(user_id)

# 상세 문서 헬퍼
def get_today_attendance_doc(user_id):
    uid = ObjectId(user_id) if isinstance(user_id, str) else user_id
    day = local_date_str()
    return db.attendance.find_one(
        {"user_id": uid, "date": day},
        {"_id": 0, "date": 1, "attended": 1, "actions": 1, "counts": 1,
         "first_action_at": 1, "last_action_at": 1}
    )

def attended_today(user_id) -> bool:
    return bool(get_today_attendance_doc(user_id))
'''