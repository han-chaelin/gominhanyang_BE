from flask import Blueprint, request
from utils.db import db
from utils.auth import token_required
from utils.response import json_kor
from datetime import datetime, timedelta
from routes.ai_test import ask_gpt, get_all_letter_contents
import os
from collections import Counter
from bson.objectid import ObjectId

report_routes = Blueprint("report_routes", __name__)

@report_routes.route("/report/monthly", methods=["GET"])
@token_required
def monthly_report():
    try:
        # 쿼리 파라미터에서 year, month 받기 (없으면 현재 시점 기본값)
        year = request.args.get("year", type=int, default=datetime.utcnow().year)
        month = request.args.get("month", type=int, default=datetime.utcnow().month)
        now = datetime.utcnow()
        start_of_month = datetime(now.year, now.month, 1)
        end_of_month = datetime(now.year, now.month+1, 1) if now.month < 12 else datetime(now.year+1, 1, 1)

         # 🔑 user 조회
        user = db.user.find_one({"_id": ObjectId(request.user_id)})
        if not user:
            return json_kor({"error": "유저를 찾을 수 없습니다."}, 404)

        # 이번 달 편지 / 답장 조회
        letters = list(db.letter.find({"from": user["_id"], "created_at": {"$gte": start_of_month, "$lt": end_of_month}}))
        replies = list(db.comment.find({"from": user["_id"], "created_at": {"$gte": start_of_month, "$lt": end_of_month}}))

        # 이번 달 답장 받은 횟수
        replied_letters = db.letter.count_documents({
            "from": user["_id"],
            "status": "replied",
            "created_at": {"$gte": start_of_month, "$lt": end_of_month}
        })

        # 지난달 작성 횟수
        prev_month = now.month - 1 if now.month > 1 else 12
        prev_year = now.year if now.month > 1 else now.year - 1
        prev_start = datetime(prev_year, prev_month, 1)
        prev_end = datetime(now.year, now.month, 1)
        prev_letters_count = db.letter.count_documents({
            "from": user["_id"],
            "created_at": {"$gte": prev_start, "$lt": prev_end}
        })

        # 편지 내용
        contents = [l["content"] for l in letters]
        
        # 편지 주제 분석 (GPT)
        topics = []
        if contents:
            topic_prompt = "다음 편지 목록을 보고 각 편지의 핵심 주제를 1-2 단어로 뽑아주세요. 출력은 JSON 배열 형식으로: [{\"content\": \"...\", \"topic\": \"...\"}, ...]\n\n"
            + "\n---\n".join(contents)
            try:
                topics = json.loads(ask_gpt(topic_prompt))
            except:
                topics = []

        # 선택 감정 빈도 (letter.emotion)
        selected_emotions = [l.get("emotion") for l in letters if l.get("emotion")]
        selected_emotion_count = Counter(selected_emotions)


        # 편지 감정 분석 (GPT)
        ai_emotions = []
        if contents:
            emotion_prompt = "다음 편지들을 [기쁨, 슬픔, 분노, 불안, 지침, 기대, 혼란] 중 하나 이상으로 분류하세요. 출력은 JSON 배열 형식으로: [{\"content\": \"...\", \"emotions\": [\"...\"]}, ...]\n\n"
            + "\n---\n".join(contents)
            try:
                ai_emotions = json.loads(ask_gpt(emotion_prompt))
            except:
                ai_emotions = []

        # AI 코멘트 생성
        summary_prompt = (
            f"이번 달 활동 요약:\n"
            f"- 편지 {len(letters)}개\n"
            f"- 답장 {len(replies)}개\n"
            f"- 답장 받은 횟수 {replied_letters}개\n"
            f"- 선택 감정 분포: {dict(selected_emotion_count)}\n"
            f"- 지난달 작성 {prev_letters_count}개\n"
            f"위 데이터를 보고 유저의 정서 활동을 따뜻하게 요약하는 한 줄 코멘트를 작성해주세요."
        )
        ai_comment = ask_gpt(summary_prompt, temperature=0.7)

        # 리포트 조회 직전 추가
        report_doc = db.report.find_one({
            "user_id": ObjectId(request.user_id),
            "year": year,
            "month": month
        })
        user_comment = report_doc.get("user_comment") if report_doc else None


        return json_kor({
            "nickname": user["nickname"],
            "letters_count": len(letters),
            "replies_count": len(replies),
            "replied_count": replied_letters,
            "last_month_letters": prev_letters_count, 
            "topics": topics,
            "selected_emotion_count": dict(selected_emotion_count),
            "ai_emotions": ai_emotions,
            "ai_comment": ai_comment,
            "user_comment": user_comment
        }, 200)

    except Exception as e:
        return json_kor({"error": str(e)}, 500)

# 전체 월별 리포트 조회
@report_routes.route("/report/monthly/all", methods=["GET"])
@token_required
def monthly_report_all():
    user = db.user.find_one({"_id": ObjectId(request.user_id)})
    if not user:
        return json_kor({"error": "유저를 찾을 수 없습니다."}, 404)

    pipeline = [
        {"$match": {"from": user["_id"]}},
        {"$group": {
            "_id": {"year": {"$year": "$created_at"}, "month": {"$month": "$created_at"}},
            "letters_count": {"$sum": 1}
        }},
        {"$sort": {"_id.year": 1, "_id.month": 1}}
    ]
    stats = list(db.letter.aggregate(pipeline))
    return json_kor({"monthly_stats": stats}, 200)

# 돌아보는 한마디 작성
@report_routes.route("/report/comment", methods=["POST"])
@token_required
def add_report_comment():
    data = request.get_json()
    now = datetime.utcnow()
    year = request.args.get("year", type=int, default=now.year)
    month = request.args.get("month", type=int, default=now.month)

    db.report.update_one(
        {"user_id": ObjectId(request.user_id), "year": year, "month": month},
        {"$set": {"user_comment": data.get("comment")}},
        upsert=True
    )
    return json_kor({
        "message": "돌아보는 한마디가 저장되었습니다.",
        "year": year,
        "month": month,
        "comment": data.get("comment")
    }, 200)