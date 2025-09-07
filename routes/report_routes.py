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
        now = datetime.utcnow()
        start_of_month = datetime(now.year, now.month, 1)
        end_of_month = datetime(now.year, now.month+1, 1) if now.month < 12 else datetime(now.year+1, 1, 1)

         # 🔑 request.user_id 활용해서 user 조회
        user = db.user.find_one({"_id": ObjectId(request.user_id)})
        if not user:
            return json_kor({"error": "유저를 찾을 수 없습니다."}, 404)

        # 이번 달 편지 조회
        letters = list(db.letter.find({
            "from": user["_id"],
            "created_at": {"$gte": start_of_month, "$lt": end_of_month}
        }))

        # 이번 달 답장 조회
        replies = list(db.comment.find({
            "from": user["_id"],
            "created_at": {"$gte": start_of_month, "$lt": end_of_month}
        }))

        contents = [l["content"] for l in letters]
        
        # 편지 주제 분석 (GPT)
        topic_prompt = (
            "다음 편지 목록을 보고 각 편지의 핵심 주제를 1-2 단어로 뽑아주세요. "
            "출력은 JSON 배열 형식으로: [{\"content\": \"...\", \"topic\": \"...\"}, ...]\n\n"
            + "\n---\n".join(contents)
        )
        topics = ask_gpt(topic_prompt)

        # 선택 감정 빈도 (letter.emotion)
        selected_emotions = [l.get("emotion") for l in letters if l.get("emotion")]
        selected_emotion_count = Counter(selected_emotions)


        # AI 감정 분석
        emotion_prompt = (
            "다음 편지들을 [기쁨, 슬픔, 분노, 불안, 지침, 기대, 혼란] 중 하나 이상으로 분류하세요. "
            "출력은 JSON 배열 형식으로: [{\"content\": \"...\", \"emotions\": [\"...\"]}, ...]\n\n"
            + "\n---\n".join(contents)
        )
        ai_emotions = ask_gpt(emotion_prompt)

        # AI 코멘트 생성
        summary_prompt = (
            f"이번 달 활동 요약:\n"
            f"- 편지 {len(letters)}개\n"
            f"- 답장 {len(replies)}개\n"
            f"- 선택 감정 분포: {dict(selected_emotion_count)}\n"
            f"위 데이터를 보고 유저의 정서 활동을 따뜻하게 요약하는 한 줄 코멘트를 작성해주세요."
        )
        ai_comment = ask_gpt(summary_prompt, temperature=0.7)

        return json_kor({
            "nickname": user["nickname"],
            "letters_count": len(letters),
            "replies_count": len(replies),
            "topics": topics,
            "selected_emotion_count": dict(selected_emotion_count),
            "ai_emotions": ai_emotions,
            "ai_comment": ai_comment
        }, 200)

    except Exception as e:
        return json_kor({"error": str(e)}, 500)
