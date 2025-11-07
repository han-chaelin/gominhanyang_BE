from flask import Blueprint, request, Response, current_app
from flasgger import swag_from
from datetime import datetime, timedelta
from bson import ObjectId
import pytz, json

from utils.db import db
from utils.auth import token_required
from utils.attendance import get_today_attendance_doc, local_date_str
# KST 타임존
KST = pytz.timezone("Asia/Seoul")

attendance_routes = Blueprint("attendance_routes", __name__, url_prefix="/attendance")

def _json(data, status=200):
    return Response(json.dumps(data, ensure_ascii=False, default=str),
                    content_type="application/json; charset=utf-8", status=status)

@attendance_routes.get("/today")
@token_required
@swag_from({
    "tags": ["Attendance"],
    "summary": "오늘 출석 여부 조회(로그인 기반)",
    "description": "한국시간 기준 오늘 날짜의 출석 상태를 반환합니다. 로그인 성공 시 자동 마킹됩니다.",
    "responses": {
        200: {
            "description": "성공",
            "content": {
                "application/json": {
                    "example": {
                        "date": "2025-11-01",
                        "attended": True,
                        "actions": ["login"],
                        "counts": {"login": 1},
                        "first_action_at": "2025-10-31T16:06:53.478Z",
                        "last_action_at": "2025-10-31T16:06:53.478Z"
                    }
                }
            }
        },
        401: {"description": "Unauthorized"},
        500: {"description": "Server Error"}
    }
})
def today():
    try:
        uid = ObjectId(getattr(request, "user_id"))  # 데코레이터가 세팅
        day = local_date_str()

        doc = db.attendance.find_one({"user_id": uid}, {f"days.{day}": 1, "_id": 0}) or {}
        block = (doc.get("days") or {}).get(day)

        if not block:
            return _json({
                "date": day, "attended": False,
                "actions": [], "counts": {},
                "first_action_at": None, "last_action_at": None
            }, 200)

        return _json({
            "date": day,
            "attended": bool(block.get("attended")),
            "actions": block.get("actions", []),
            "counts": block.get("counts", {}),
            "first_action_at": block.get("first_action_at"),
            "last_action_at": block.get("last_action_at"),
        }, 200)
    except Exception as e:
        current_app.logger.exception(e)
        return _json({"error": f"[attendance/today] {e}"}, 500)

@attendance_routes.get("/calendar")
@token_required
@swag_from({
    "tags": ["Attendance"],
    "summary": "월별 출석 달력 조회",
    "description": "달력 표시용 데이터. month=YYYY-MM 또는 start/end로 기간을 지정합니다.",
    "parameters": [
        {"name": "month", "in": "query", "schema": {"type": "string"}, "required": False, "example": "2025-11"},
        {"name": "start", "in": "query", "schema": {"type": "string"}, "required": False, "example": "2025-11-01"},
        {"name": "end", "in": "query", "schema": {"type": "string"}, "required": False, "example": "2025-11-30"}
    ],
    "responses": {
        200: {
            "description": "성공",
            "content": {
                "application/json": {
                    "example": {
                        "dates": ["2025-11-01","2025-11-02"],
                        "attended": ["2025-11-01"],
                        "detail": {
                            "2025-11-01": {
                                "actions": ["login"],
                                "first_action_at": "2025-10-31T16:06:53.478Z",
                                "last_action_at": "2025-10-31T16:06:53.478Z"
                            }
                        }
                    }
                }
            }
        },
        400: {"description": "month 또는 start/end 필요"},
        401: {"description": "Unauthorized"},
        500: {"description": "Server Error"}
    }
})
def calendar_me():
    try:
        month = (request.args.get("month") or "").strip()
        start = (request.args.get("start") or "").strip()
        end   = (request.args.get("end") or "").strip()

        if month:
            y, m = map(int, month.split("-"))
            start_dt = KST.localize(datetime(y, m, 1))
            next_dt  = KST.localize(datetime(y+1, 1, 1)) if m == 12 else KST.localize(datetime(y, m+1, 1))
            start, end = start_dt.strftime("%Y-%m-%d"), (next_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        elif not (start and end):
            return _json({"error": "month 또는 start/end를 지정하세요."}, 400)

        uid = ObjectId(getattr(request, "user_id"))

        doc = db.attendance.find_one({"user_id": uid}, {"days": 1, "_id": 0}) or {}
        days_obj = doc.get("days") or {}

        dt_start = datetime.strptime(start, "%Y-%m-%d")
        dt_end   = datetime.strptime(end,   "%Y-%m-%d")
        n = (dt_end - dt_start).days + 1
        dates = [(dt_start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]

        attended, detail = [], {}
        for d in dates:
            blk = days_obj.get(d)
            if blk and blk.get("attended"):
                attended.append(d)
                detail[d] = {
                    "actions": blk.get("actions", []),
                    "first_action_at": blk.get("first_action_at"),
                    "last_action_at": blk.get("last_action_at"),
                }

        return _json({"dates": dates, "attended": attended, "detail": detail}, 200)
    except Exception as e:
        current_app.logger.exception(e)
        return _json({"error": f"[attendance/calendar] {e}"}, 500)