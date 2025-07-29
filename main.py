import os
import time
import json
import uuid
import random
from datetime import datetime, timedelta
from openai import OpenAI
from pymongo import MongoClient
from dotenv import load_dotenv
from utils.db import db
from bson import ObjectId

# 환경변수 로드
#load_dotenv()

# OpenAI 클라이언트 설정
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))



# Fallback 메시지
AI_REPLY_POOL = [
    "지금도 충분히 잘하고 있어요.",
    "당신의 감정을 이해해요. 같이 이겨내봐요.",
    "조금만 쉬어가도 괜찮아요.",
    "당신은 혼자가 아니에요.",
    "그 마음, 충분히 소중해요."
]

def generate_ai_reply(content):
    prompt = f"""
아래는 사용자가 쓴 편지입니다:
"{content}"

공감 위주로 3-4문장의 답장을 생성해주세요.
존댓말로 작성해주세요.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "당신은 따뜻한 답장을 잘 쓰는 AI입니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85
        )
        reply_text = response.choices[0].message.content.strip()
        return reply_text
    except Exception as e:
        print("AI 응답 실패:", e)
        return random.choice(AI_REPLY_POOL)

def auto_reply_to_old_letters():
    threshold = datetime.utcnow() - timedelta(hours=24)

    query = {
        "status": "sent",
        "created_at": {"$lte": threshold},
        "to": {"$ne": "volunteer_user"},
        "$expr": {"$ne": ["$to", "$from"]}
    }

    letters = list(db.letter.find(query))
    print(f"{len(letters)}건의 자동 답장 대상 편지를 찾았습니다.")

    for mail in letters:
        reply = generate_ai_reply(mail.get('content', ''))
        comment = {
            "_id": ObjectId(),
            "from": "온달",
            "to": mail["from"],
            "content": reply,
            "read": False,
            "created_at": datetime.utcnow(),
            "original_letter_id": mail["_id"]
        }
        db.comment.insert_one(comment)
        db.letter.update_one(
            {"_id": mail["_id"]},
            {"$set": {"status": "auto_replied", "replied_at": datetime.utcnow()}}
        )
        print(f"자동 답장 완료: 편지 ID {mail['_id']}")

if __name__ == "__main__":
    interval_hours = int(os.getenv("REPLY_INTERVAL_HOURS", "6"))
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 자동 답장 워커 시작! {interval_hours}시간 간격으로 실행")

    while True:
        auto_reply_to_old_letters()
        time.sleep(3600)

