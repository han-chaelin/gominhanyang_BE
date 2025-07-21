import os
import sys
import json
from openai import OpenAI
from utils.db import db

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_all_letter_contents(limit: int | None = 300) -> list[str]:
    cursor = db.letter.find({}, {"_id": 0, "content": 1}).sort("created_at", -1)

    contents = []
    seen = set()

    for d in cursor:
        content = d["content"]
        if content not in seen:
            seen.add(content)
            contents.append(content)

    return contents if limit is None else contents[:limit]

def ask_gpt(prompt: str, model: str = "gpt-4o", temperature: float = 0.3) -> str:
    """OpenAI 호출 래퍼"""
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()

if __name__ == "__main__":
    contents = get_all_letter_contents(limit=100)          
    prompt = (
        "다음 편지 목록을 보고 각 편지의 핵심 주제를 1-2 단어로 뽑되 같은 의미의 표현은 같은 단어로 통일해 주세요"
        "출력은 노션용 마크다운 형식으로 편지 내용과 주제를 열로 해주세요"
        + "\n---\n".join(contents)
    )
    print("\n===== GPT-4o 응답 =====\n")
    try:
        answer = ask_gpt(prompt)
        print(answer)
    except Exception as e:
        print("❌ OpenAI 호출 오류:", e)