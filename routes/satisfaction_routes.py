from flask import Blueprint, request
from flasgger import swag_from
from utils.db import db
from utils.response import json_kor
from utils.auth import token_required
from bson import ObjectId
from datetime import datetime
satisfaction_bp = Blueprint(
    'satisfaction',
    __name__,
    url_prefix='/satisfaction',      
    strict_slashes=False              
)


@satisfaction_bp.route('/', methods=['POST'])
@token_required
@swag_from({
    'tags': ['Satisfaction'],
    'description': '답장에 대한 만족도를 평가하고 저장합니다.',
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
        404: {'description': '답장 댓글이 존재하지 않음'}
    }
})
def save_satisfaction():
    """
    답장에 대한 만족도 저장
    """
    data = request.get_json()
    letter_id = data.get("letter_id")
    rating = data.get("rating")
    reason = data.get("reason")

    if not letter_id or not rating or not reason:
        return json_kor({"error": "필수 항목이 누락되었습니다."}, 400)

    try:
        comment = db.comment.find_one({"_id": ObjectId(letter_id)})
    except Exception:
        return json_kor({"error": "letter_id 형식이 잘못되었습니다."}, 400)

    if not comment:
        return json_kor({"error": "해당 답장을 찾을 수 없습니다."}, 404)

    # 답장 작성자가 유저인지 AI인지 판단
    from_id = comment.get("from")
    user_exists = db.user.find_one({"_id": from_id}) if isinstance(from_id, ObjectId) else None
    responder_type = "user" if user_exists else "AI"
    
    # 만족도 평가 저장
    evaluation = {
        "letter_id": str(letter_id),
        "creater_type": responder_type,
        "rating": rating,
        "reason": reason,
        "created_by": str(comment["to"]),
        "created_at": datetime.utcnow().isoformat()
    }

    insert_result = db.satisfactions.insert_one(evaluation)
    
    # ✅ MongoDB가 자동 생성한 _id 필드 추가 (ObjectId → str)
    evaluation["_id"] = str(insert_result.inserted_id)
    
    return json_kor({
        "message": "만족도 저장 완료",
        "data": evaluation
    }, 200)


