from flask import Blueprint, request, Response
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
def today(current_user):
    day = local_date_str()
    doc = get_today_attendance_doc(current_user["_id"])  # {"days": {"<day>": {...}}}

    if not doc or "days" not in doc or day not in doc["days"]:
        return _json({
            "date": day, "attended": False,
            "actions": [], "counts": {},
            "first_action_at": None, "last_action_at": None
        }, 200)

    block = doc["days"][day]
    return _json({
        "date": day,
        "attended": block.get("attended", False),
        "actions": block.get("actions", []),
        "counts": block.get("counts", {}),
        "first_action_at": block.get("first_action_at"),
        "last_action_at": block.get("last_action_at")
    }, 200)

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
def calendar_me(current_user):
    month = request.args.get("month")  # "YYYY-MM"
    start = request.args.get("start")
    end = request.args.get("end")
    uid = current_user["_id"]

    # 범위 계산
    if month:
        from datetime import datetime, timedelta
        y, m = map(int, month.split("-"))
        start_dt = KST.localize(datetime(y, m, 1))
        if m == 12: next_dt = KST.localize(datetime(y+1, 1, 1))
        else:       next_dt = KST.localize(datetime(y, m+1, 1))
        start = start_dt.strftime("%Y-%m-%d")
        end   = (next_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    elif not (start and end):
        return _json({"error": "month 또는 start/end를 지정하세요."}, 400)

    # 유저 1문서에서 days와 days_index만 가져오기
    doc = db.attendance.find_one(
        {"user_id": uid},
        {"days": 1, "days_index": 1, "_id": 0}
    ) or {}

    days = doc.get("days", {})
    # 월 전체 날짜 배열 생성
    dt_start = datetime.strptime(start, "%Y-%m-%d")
    dt_end   = datetime.strptime(end, "%Y-%m-%d")
    n = (dt_end - dt_start).days + 1
    dates = [(dt_start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]

    attended = []
    detail = {}
    for d in dates:
        if d in days and days[d].get("attended"):
            attended.append(d)
            detail[d] = {
                "actions": days[d].get("actions", []),
                "first_action_at": days[d].get("first_action_at"),
                "last_action_at": days[d].get("last_action_at"),
            }

    return _json({"dates": dates, "attended": attended, "detail": detail}, 200)