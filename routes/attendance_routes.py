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
    "description": "출석한 날짜와 해당 날짜의 상세 정보만 반환합니다. month=YYYY-MM 또는 start/end로 기간을 지정합니다.",
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
                        "attended": ["2025-11-01","2025-11-10","2025-11-11"],
                        "detail": {
                            "2025-11-01": {
                                "actions": ["login"],
                                "first_action_at": "2025-11-01 08:34:21",
                                "last_action_at": "2025-11-01 09:05:11"
                            },
                            "2025-11-10": {
                                "actions": ["login"],
                                "first_action_at": "2025-11-10 09:24:48",
                                "last_action_at": "2025-11-10 09:27:55"
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

        # 기간 계산 (KST 기준)
        if month:
            try:
                y, m = map(int, month.split("-"))
            except Exception:
                return _json({"error": "month는 YYYY-MM 형식이어야 합니다."}, 400)
            
            start_dt = KST.localize(datetime(y, m, 1))
            next_dt  = KST.localize(datetime(y+1, 1, 1)) if m == 12 else KST.localize(datetime(y, m+1, 1))
            start, end = start_dt.strftime("%Y-%m-%d"), (next_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        elif not (start and end):
            return _json({"error": "month 또는 start/end를 지정하세요."}, 400)

        # 형식 검증 & 순서 검증
        try:
            dt_start = datetime.strptime(start, "%Y-%m-%d")
            dt_end   = datetime.strptime(end,   "%Y-%m-%d")
        except ValueError:
            return _json({"error": "start/end는 YYYY-MM-DD 형식이어야 합니다."}, 400)
        if dt_start > dt_end:
            return _json({"error": "start가 end보다 클 수 없습니다."}, 400)
        
        uid = ObjectId(getattr(request, "user_id"))

        # 유저 출석 원본
        doc = db.attendance.find_one({"user_id": uid}, {"days": 1, "_id": 0}) or {}
        days_obj: dict = doc.get("days") or {}

        # 범위 내 '출석 true'만 선별 (날짜 키 문자열 비교 대신 datetime으로 안전 비교)
        attended = []
        detail = {}
        for d_str, blk in days_obj.items():
            try:
                d_dt = datetime.strptime(d_str, "%Y-%m-%d")
            except ValueError:
                continue  # 예상치 못한 키는 무시
            if dt_start <= d_dt <= dt_end and blk and blk.get("attended"):
                attended.append(d_str)
                detail[d_str] = {
                    "actions": blk.get("actions", []),
                    "first_action_at": blk.get("first_action_at"),
                    "last_action_at": blk.get("last_action_at"),
                }

        # 날짜 정렬(보장하고 싶다면)
        attended.sort()

        return _json({"attended": attended, "detail": detail}, 200)
    except Exception as e:
        current_app.logger.exception(e)
        return _json({"error": f"[attendance/calendar] {e}"}, 500)