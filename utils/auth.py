import jwt
import json
from functools import wraps
from flask import request, Response
from datetime import datetime, timedelta
from utils.config import JWT_SECRET_KEY, JWT_ALGORITHM, APP_BASE_URL

# 한글 JSON 응답 헬퍼
def json_kor(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False),
        content_type="application/json",
        status=status
    )

# JWT 인증 데코레이터
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header:
            return json_kor({'error': '토큰이 필요합니다.'}, 401)

        parts = auth_header.split()
        if parts[0].lower() != 'bearer' or len(parts) != 2:
            return json_kor({'error': '잘못된 토큰 형식입니다.'}, 401)

        token = parts[1]
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            request.user_id = payload.get('user_id')
            # payload에 nickname이 포함되어 있다면 설정
            request.nickname = payload.get('nickname')
        except jwt.ExpiredSignatureError:
            return json_kor({'error': '토큰이 만료되었습니다.'}, 401)
        except jwt.InvalidTokenError:
            return json_kor({'error': '유효하지 않은 토큰입니다.'}, 401)

        return f(*args, **kwargs)
    return decorated

# 이메일 인증용 토큰 생성
def generate_email_verify_token(user_id: str) -> str:
    """이메일 인증용 JWT 토큰 생성"""
    payload = {
        "sub": user_id,          # 누구를 인증하는지
        "type": "email_verify",  # 토큰 용도 구분
        "exp": datetime.utcnow() + timedelta(hours=24)  # 24시간 유효
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
