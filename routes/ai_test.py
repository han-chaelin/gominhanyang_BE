import os
import sys
import json
from openai import OpenAI
from utils.db import db

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_all_letter_contents(limit: int | None = 300) -> list[str]:
    cursor = db.letter.find({}, {"_id": 0, "content": 1}).sort("created_at", -1)
    contents = [d["content"] for d in cursor]
    return contents if limit is None else contents[:limit]

def ask_gpt(prompt: str, model: str = "gpt-4o", temperature: float = 0.7) -> str:
    """OpenAI 호출 래퍼"""
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()

if __name__ == "__main__":
    custom_query = " ".join(sys.argv[1:]).strip()
    contents = get_all_letter_contents(limit=100)          
    base_prompt = (
        "다음 편지 목록을 보고 각 편지의 핵심 주제(1~2 단어)를 뽑아주세요.\n"
        "출력: 줄마다 <편지 내용>. <주제>\n\n"
        + "\n---\n".join(contents)
    )

    prompt = custom_query if custom_query else base_prompt
    print("\n===== GPT-4o 응답 =====\n")
    try:
        answer = ask_gpt(prompt)
        print(answer)
    except Exception as e:
        print("❌ OpenAI 호출 오류:", e)