from flask import Blueprint, request, Response
from utils.db import db
from utils.auth import token_required
from utils.response import json_kor
from datetime import datetime, timedelta
from routes.ai_test import ask_gpt, get_all_letter_contents
import os
from collections import Counter
from bson.objectid import ObjectId
import traceback
import json
import re

def safe_json_parse(text):
    try:
        return json.loads(text)
    except:
        # 문자열 안에서 JSON 배열만 추출
        match = re.search(r"\[.*\]", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                return []
        return []


report_routes = Blueprint("report_routes", __name__)

@report_routes.route("/report/monthly", methods=["GET"])
@token_required
def monthly_report():
    try:
        # 쿼리 파라미터에서 year, month 받기 (없으면 현재 시점 기본값)
        # 쿼리 파라미터에서 year, month 받기
        year = request.args.get("year", type=int, default=datetime.utcnow().year)
        month = request.args.get("month", type=int, default=datetime.utcnow().month)

        # 조회할 달의 시작과 끝
        start_of_month = datetime(year, month, 1)
        if month < 12:
            end_of_month = datetime(year, month + 1, 1)
        else:
            end_of_month = datetime(year + 1, 1, 1)


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
        now = datetime.utcnow()
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
            topic_prompt = (
                "다음은 청소년들이 쓴 편지 모음이며, 이 편지들을 분류하기 위한 주제를 몇가지 선정하려고 합니다. 주제 선정을 위해서는 다음과 같은 조건을 충족해야 합니다. 첫째, 편지의 내용을 읽고, 내용에서 등장하는 주요 키워드와 상황을 기반으로 주제를 도출해야 합니다. 둘째, 너무 적거나 너무 많은 주제보다는 적정한 개수를 판단해서 주제를 선정해야 합니다. 셋째, 각 주제는 다른 주제와 명확히 구분되며, 포괄적이고 중복되지 않도록 합니다. 단, 유사한 의미의 단어는 하나의 주제로 통합해주세요. 넷째, '기타'나 '모르겠음'과 같이 불분명한 항목은 제외함으로써 주제가 모호해지지 않도록 해야 합니다. 다섯째, 각 주제는 한 단어로 간결하게 표현하되, 명확한 의미가 드러나야 합니다."
                "그런 다음에 각 편지를 선정된 주제 중 하나로 분류해서 출력해주세요. 출력은 아무 설명 없이 JSON 배열만 반환하세요. "
            )
            try:
                raw_topics = ask_gpt(topic_prompt + "\n---\n".join(contents))
                topics = safe_json_parse(raw_topics)
            except Exception as e:
                print("❌ GPT 주제 분석 오류:", e)
                topics = []

        # 선택 감정 빈도 (letter.emotion)
        selected_emotions = [l.get("emotion") for l in letters if l.get("emotion")]
        selected_emotion_count = Counter(selected_emotions)

        # 편지 감정 분석 (GPT)
        ai_emotions = []
        if contents:
            emotion_prompt = (
                "다음은 청소년들이 쓴 편지의 모음이며, 이 편지들을 [기쁨, 슬픔, 분노, 불안, 지침, 기대, 혼란] 이라는 감정 카테고리에 따라 분류하려고 합니다. 각 편지에 대해 작성자가 느낀 감정을 아래의 감정 카테고리 중에서 하나 이상 선택하세요. 감정 카테고리는 중복 선택이 가능합니다. 출력은 아무 설명 없이 JSON 배열만 반환하세요."
            )
            try:
                raw_emotions = ask_gpt(emotion_prompt + "\n---\n".join(contents))
                ai_emotions = safe_json_parse(raw_emotions)
            except Exception as e:
                print("❌ GPT 감정 분석 오류:", e)
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

        # ✅ JSON 문자열 변환
        response_body = {
            "nickname": user["nickname"],
            "letters_count": len(letters),
            "replies_count": len(replies),
            "replied_count": replied_letters,
            "last_month_letters": prev_letters_count,
            "topics": topics if isinstance(topics, list) else [],
            "selected_emotion_count": dict(selected_emotion_count),
            "ai_emotions": ai_emotions if isinstance(ai_emotions, list) else [],
            "ai_comment": ai_comment if isinstance(ai_comment, str) else "",
            "user_comment": user_comment if isinstance(user_comment, str) else None
        }

        return Response(json.dumps(response_body, ensure_ascii=False),
                        status=200, mimetype="application/json")

    except Exception as e:
        import traceback
        print("❌ 서버 오류 발생:", e)
        traceback.print_exc()
        return Response(json.dumps({"error": str(e)}, ensure_ascii=False),
                        status=500, mimetype="application/json")

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