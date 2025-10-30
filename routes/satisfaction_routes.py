from flask import Blueprint, request
from flasgger import swag_from
from utils.db import db
from utils.response import json_kor
from utils.auth import token_required
from bson import ObjectId
from datetime import datetime

satisfaction_bp = Blueprint('satisfaction', __name__)

@satisfaction_bp.route('', methods=['POST']) 
@token_required
@swag_from({
    'tags': ['Satisfaction'],
    'description': '서비스에 대한 만족도를 평가하고 저장합니다.',
    'parameters': [
        {'name': 'Authorization', 'in': 'header', 'type': 'string', 'required': True, 'description': 'Bearer 토큰'},
        {'name': 'body', 'in': 'body', 'required': True,
         'schema': {
             'type': 'object',
             'properties': {
                 'letter_id': {'type': 'string', 'example': '665f1234abcde9876543210f'},
                 'rating': {'type': 'integer', 'example': 4},
                 'reason': {'type': 'string', 'example': '공감이 잘 느껴졌어요.'}
             },
             'required': ['letter_id', 'rating', 'reason']
         }}
    ],
    'responses': {
        200: {'description': '만족도 저장 성공',
              'schema': {'type': 'object', 'properties': {'message': {'type': 'string'}}}},
        400: {'description': '입력 값 오류'},
        404: {'description': '편지를 찾을 수 없음'},
        409: {'description': '이미 제출됨'}
    }
})
def save_satisfaction():
    data = request.get_json()
    letter_id = data.get("letter_id")
    rating = data.get("rating")
    reason = data.get("reason")

    if not letter_id or not rating or not reason:
        return json_kor({"error": "필수 항목이 누락되었습니다."}, 400)

    # letter_id 형식 검사 + 편지 조회
    try:
        oid = ObjectId(letter_id)
    except Exception:
        return json_kor({"error": "letter_id 형식이 잘못되었습니다."}, 400)

    letter = db.letter.find_one({"_id": oid})
    if not letter:
        return json_kor({"error": "해당 편지를 찾을 수 없습니다."}, 404)

    # 작성자 본인 편지인지 검증
    if letter.get("from") != user_id:
        return json_kor({"error": "본인이 작성한 편지에 대해서만 만족도를 제출할 수 있습니다."}, 403)

    # 중복 제출 방지(같은 사용자 + 같은 편지 + 같은 단계)
    exists = db.satisfactions.find_one({
        "letter_id": str(oid),
        "phase": "after_letter",
        "created_by": str(user_id)
    })
    if exists:
        return json_kor({"error": "이미 해당 편지에 대한 만족도를 제출하셨습니다."}, 409)
    
    # 만족도 평가 저장
    evaluation = {
        "letter_id": str(letter_id),
        "rating": rating,
        "reason": reason,
        "created_by": str(user_id),
        "created_at": datetime.utcnow().isoformat()
    }

    insert_result = db.satisfactions.insert_one(evaluation)
    
    # ✅ MongoDB가 자동 생성한 _id 필드 추가 (ObjectId → str)
    evaluation["_id"] = str(insert_result.inserted_id)
    
    return json_kor({
        "message": "만족도 저장 완료",
        "data": evaluation
    }, 200)


