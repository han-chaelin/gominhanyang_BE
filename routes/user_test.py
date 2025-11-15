from datetime import datetime, timedelta
from flask import request, Blueprint, Response, current_app, make_response, jsonify, redirect
from flasgger import swag_from
import jwt
from bson.objectid import ObjectId
from functools import wraps
import json
from utils.db import db
from utils.config import JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, APP_BASE_URL
from utils.attendance import mark_attendance_login, attended_today, record_attendance
import re
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.security import check_password_hash, generate_password_hash
from utils.response import json_kor
from utils.auth import token_required
from utils.mailer import send_email_verification

# 비밀번호
PASSWORD_MIN_LEN = 8

def is_strong_password(pw: str) -> bool:
    if not isinstance(pw, str) or len(pw) < PASSWORD_MIN_LEN:
        return False
    return True  # 필요시: 숫자/특수문자 규칙 추가


# 신분/이메일
ALLOWED_STATUS = ["무직","중/고등학생","대학생","유학생","주부","직장인","군인","기타"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def is_valid_email(v: str) -> bool:
    return EMAIL_RE.match(v or "") is not None

def is_valid_status(v: str) -> bool:
    return v in ALLOWED_STATUS

user_test = Blueprint('user', __name__, url_prefix='/api/users')

# 한글 JSON 응답 헬퍼
def json_kor(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        content_type="application/json; charset=utf-8",
        status=status
    )

def create_token(user_doc):
    expire = datetime.utcnow() + datetime.timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "user_id": str(user_doc["_id"]),
        "nickname": user_doc["nickname"],
        "exp": expire
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

@user_test.route('/signup', methods=['POST'])
@swag_from({
    'tags': ['User'],
    'summary': '회원가입',
    'description': '사용자를 등록합니다. 닉네임, 비밀번호, 나이, 성별, 이메일, 신분은 필수이며, 주소/전화번호는 선택 항목입니다.',
    'requestBody': {
        'required': True,
        'content': {
            'application/json': {
                'schema': {
                    'type': 'object',
                    'properties': {
                        'nickname': {'type': 'string'},
                        'password': {'type': 'string', 'minLength': PASSWORD_MIN_LEN},
                        'age': {'type': 'integer'},
                        'gender': {'type': 'string'},
                        'address': {'type': 'string'},
                        'phone': {'type': 'string'},
                        'status': {'type': 'string', 'enum': ALLOWED_STATUS},
                        'email': {'type': 'string', 'format': 'email'},
                    },
                    'required': ['nickname', 'password', 'age', 'gender', 'status', 'email']
                }
            }
        }
    },
    'responses': {
        201: {'description': '회원가입 성공'},
        400: {'description': '중복 닉네임 또는 필수 항목 누락/형식 오류'},
        500: {'description': '서버 에러'}
    }
})
def signup():
    try:
        data = request.get_json(force=True)
        
        nickname = data.get('nickname')
        password = data.get('password')
        age      = data.get('age')
        gender   = data.get('gender')
        status   = (data.get('status') or '').strip()
        email    = (data.get('email') or '').strip()
        address  = data.get('address')
        phone    = data.get('phone')

        if not nickname or age is None or not password or not gender or not status or not email:
            return json_kor({"error": "닉네임, 비밀번호, 나이, 성별, 신분, 이메일은 필수입니다."}, 400)

        if db.user.find_one({"nickname": nickname}):
            return json_kor({"error": "이미 존재하는 닉네임입니다."}, 400)
        
        if not is_strong_password(password):
            return json_kor({"error": f"비밀번호는 최소 {PASSWORD_MIN_LEN}자 이상이어야 합니다."}, 400)

        if not is_valid_status(status):
            return json_kor({"error": f"신분(status)은 {ALLOWED_STATUS} 중 하나여야 합니다."}, 400)

        if not is_valid_email(email):
            return json_kor({"error": "올바른 이메일 형식이 아닙니다."}, 400)

        if db.user.find_one({"email": email}):
            return json_kor({"error": "이미 등록된 이메일입니다."}, 400)

        # limited_access는 phone 유무로 판단
        limited_access = not (phone)

        # ✅ 아직 "완료된 회원"이 아니므로 email_verified=False 로 저장
        new_user = {
            "nickname": nickname,
            "password_hash": generate_password_hash(password),
            "age": age,
            "gender": gender,
            "status": status,  
            "email": email, 
            "address": address or "",
            "phone": phone or "",
            "point": 0,
            "level": 1,
            "limited_access": limited_access,
            "email_verified": False,
            "email_verified_at": None,
            "created_at": datetime.utcnow(),
        }

        result = db.user.insert_one(new_user)
        user_doc = db.user.find_one({"_id": result.inserted_id})
        token = create_token(user_doc)
        
        # ✅ 여기서는 이메일 인증 메일만 보냄 (토큰 발급/온보딩 편지 X)
        try:
            send_email_verification(user_doc)
        except Exception as e:
            current_app.logger.warning(f"[mail] email verification failed: {e}")

        return json_kor({
            "message": "회원가입 신청이 완료되었습니다. 이메일을 인증하면 가입이 완료됩니다.",
            "limited_access": limited_access
        }, 201)
    except Exception as e:
        return json_kor({"error": str(e)}, 500)
    
        # 온보딩 더미 편지(기존 로직 유지)
        letter = {
            "_id": ObjectId(),
            "from": ObjectId('68260f67f02ef2dccfdeffca'),
            "to": result.inserted_id,
            "title": '익명의 사용자에게서 온 편지',
            "emotion": '슬픔',
            "content": '정말 친하다고 생각했던 친구와 크게 싸웠어요. 좋은 친구라고 생각했는데 아니였던 것 같아요 우정이 영원할 수는 없는 걸까요?',
            "status": 'sent',
            "saved": False,
            "created_at": datetime.datetime.now()
        }
        db.letter.insert_one(letter)

        try:
            send_email_verification(user_doc)
        except Exception as e:
            current_app.logger.warning(f"[mail] email verification failed: {e}")

        return json_kor({
            "message": "회원가입 성공!",
            "nickname": user_doc["nickname"],
            "age": user_doc["age"],
            "gender": user_doc["gender"],
            "status": user_doc["status"],
            "email": user_doc["email"],
            "limited_access": limited_access,
            "token": token
        }, 201)
    except Exception as e:
        return json_kor({"error": str(e)}, 500)

@user_test.route('/login', methods=['POST'])
@swag_from({
    'tags': ['User'],
    'summary': '로그인',
    'description': '닉네임과 비밀번호를 입력하면 토큰이 반환됩니다.',
    'requestBody': {
        'required': True,
        'content': {
            'application/json': {
                'schema': {
                    'type': 'object',
                    'properties': {
                        'nickname': {'type': 'string'},
                        'password': {'type': 'string'}
                    },
                    'required': ['nickname']
                }
            }
        }
    },
    'responses': {
        200: {'description': '로그인 성공'},
        400: {'description': '닉네임 누락'},
        401: {'description': '비밀번호 불일치/미설정'},
        404: {'description': '사용자 없음'},
        500: {'description': '서버 에러'}
    }
})
def login():
    try:
        data = (request.get_json() or {})
        nickname = data.get('nickname')
        password = data.get('password')

        if not nickname:
            return json_kor({"error": "닉네임을 입력해주세요."}, 400)

        user_doc = db.user.find_one({"nickname": nickname})
        
        if not user_doc:
            return json_kor({"error": "해당 닉네임의 사용자가 존재하지 않습니다."}, 404)

        if not check_password_hash(user_doc["password_hash"], password):
            return json_kor({"error": "비밀번호가 올바르지 않습니다."}, 401)

        # ✅ 이메일 인증 여부 체크
        if not user_doc.get("email_verified"):
            return json_kor({
                "error": "이메일 인증이 완료되지 않은 계정입니다. 이메일을 먼저 인증해주세요."
            }, 401)
        
        token = create_token(user_doc)

        # 로그인 기반 출석 체크
        today_done = record_attendance(user_doc["_id"])


        ##### 더미용 데이터 - 실제 배포 시에는 삭제 ####
        """letter = {"_id": ObjectId(), "from": ObjectId('68260f67f02ef2dccfdeffca'), "to": user_id, "title": '익명의 사용자에게서 온 편지',"emotion": '슬픔', "content": '정말 친하다고 생각했던 친구와 크게 싸웠어요. 좋은 친구라고 생각했는데 아니였던 것 같아요 우정이 영원할 수는 없는 걸까요?', "status": 'sent',
              "saved": False, "created_at": datetime.datetime.now()}
        db.letter.insert_one(letter)"""

        return json_kor({
            "message": "로그인 성공!",
            "nickname": user_doc["nickname"],
            "limited_access": user_doc.get("limited_access", False),
            "token": token,
            "attended_today": today_done
        })
        
    except Exception as e:
        return json_kor({"error": str(e)}, 500)


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            return json_kor({"error": "Authorization 헤더가 필요합니다."}, 401)
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id = payload["user_id"]
            user = db.user.find_one({"_id": ObjectId(user_id)})
            if not user:
                return json_kor({"error": "사용자를 찾을 수 없습니다."}, 404)
            request.user = user
            request.user_id = str(user["_id"])
        except jwt.ExpiredSignatureError:
            return json_kor({"error": "토큰이 만료되었습니다."}, 401)
        except jwt.InvalidTokenError:
            return json_kor({"error": "유효하지 않은 토큰입니다."}, 401)
        return f(*args, **kwargs)
    return decorated

@user_test.route('/update', methods=['PATCH'])
@token_required
@swag_from({
    'tags': ['User'],
    'summary': '회원 정보 수정',
    'description': '회원의 닉네임, 신분, 이메일, 주소, 전화번호를 수정합니다. (신분/이메일은 필수 필드이므로 공백으로 변경할 수 없습니다)',
    'parameters': [
        {
            'name': 'Authorization',
            'in': 'header',
            'type': 'string',
            'required': True,
            'description': 'Bearer 액세스 토큰'
        }
    ],
    'requestBody': {
        'required': True,
        'content': {
            'application/json': {
                'schema': {
                    'type': 'object',
                    'properties': {
                        'nickname': {'type': 'string'},
                        'status': {'type': 'string', 'enum': ALLOWED_STATUS},
                        'email': {'type': 'string', 'format': 'email'},
                        'address': {'type': 'string'},
                        'phone': {'type': 'string'}
                    }
                }
            }
        }
    },
    'responses': {
        200: {'description': '수정 성공'},
        400: {'description': '중복 닉네임/이메일 또는 형식 오류/필수 필드 공백'},
        401: {'description': '인증 실패'},
        500: {'description': '서버 에러'}
    }
})
def update_user():
    try:
        user_id = request.user["_id"]
        data = request.get_json()

        # 나이와 성별은 수정에서 제외
        update_fields = {k: v for k, v in data.items() if k in ['nickname', 'status', 'email', 'address', 'phone']}
        # 아무 필드도 제공되지 않았을 경우 예외 처리
        if not update_fields:
            return json_kor({"error": "수정할 항목이 제공되지 않았습니다."}, 400)
        
        # 닉네임 중복
        if "nickname" in update_fields:
            if db.user.find_one({"nickname": update_fields["nickname"], "_id": {"$ne": user_id}}):
                return json_kor({"error": "이미 존재하는 닉네임입니다."}, 400)

        # 신분: 공백 금지 + 허용값
        if "status" in update_fields:
            status = (update_fields.get("status") or "").strip()
            if not status:
                return json_kor({"error": "신분(status)은 비울 수 없습니다."}, 400)
            if not is_valid_status(status):
                return json_kor({"error": f"신분(status)은 {ALLOWED_STATUS} 중 하나여야 합니다."}, 400)
            update_fields["status"] = status  

        # 이메일: 공백 금지 + 형식 + 중복
        if "email" in update_fields:
            email = (update_fields.get("email") or "").strip()
            if not email:
                return json_kor({"error": "이메일은 비울 수 없습니다."}, 400)
            if not is_valid_email(email):
                return json_kor({"error": "올바른 이메일 형식이 아닙니다."}, 400)
            if db.user.find_one({"email": email, "_id": {"$ne": user_id}}):
                return json_kor({"error": "이미 등록된 이메일입니다."}, 400)
            update_fields["email"] = email  

        db.user.update_one({"_id": user_id}, {"$set": update_fields})

        updated_user = db.user.find_one({"_id": user_id})
        updated_user["_id"] = str(updated_user["_id"])
        return json_kor({
            "message": "회원 정보가 성공적으로 수정되었습니다.",
            "updated_user": updated_user
        })
    except Exception as e:
        return json_kor({"error": str(e)}, 500)

@user_test.route('/me', methods=['GET'])
@token_required
@swag_from({
    'tags': ['User'],
    'summary': '내 정보 조회',
    'description': '로그인한 사용자의 정보를 반환합니다.',
    'parameters': [
        {
            'name': 'Authorization',
            'in': 'header',
            'type': 'string',
            'required': True,
            'description': 'Bearer 액세스 토큰'
        }
    ],
    'responses': {
        200: {
            'description': '사용자 정보 반환',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'user': {
                                'type': 'object',
                                'properties': {
                                    'nickname': {'type': 'string'},
                                    'age': {'type': 'integer'},
                                    'gender': {'type': 'string'},
                                    'status': {'type': 'string', 'enum': ALLOWED_STATUS},
                                    'email': {'type': 'string', 'format': 'email'},
                                    'address': {'type': 'string'},
                                    'phone': {'type': 'string'},
                                    'point': {'type': 'integer'},
                                    'level': {'type': 'integer'},
                                    'limited_access': {'type': 'boolean'}
                                }
                            }
                        }
                    }
                }
            }
        },
        401: {'description': '인증 실패'},
        404: {'description': '사용자 없음'}
    }
})
def get_my_info():
    try:
        user = request.user
        user_info = {
            "nickname": user.get("nickname"),
            "age": user.get("age"),
            "gender": user.get("gender"),
            "status": user.get("status", ""),
            "email": user.get("email", ""),
            "address": user.get("address", ""),
            "phone": user.get("phone", ""),
            "point": user.get("point", 0),
            "level": user.get("level", 1),
            "limited_access": user.get("limited_access", True)
        }
        return json_kor({"user": user_info}, 200)
    except Exception as e:
        return json_kor({"error": str(e)}, 500)


@user_test.route('/password/change', methods=['POST'])
@token_required
@swag_from({
    'tags': ['User'],
    'summary': '비밀번호 변경',
    'description': '로그인된 사용자가 현재 비밀번호를 검증한 뒤 새 비밀번호로 변경합니다.',
    'parameters': [
        {
            'name': 'Authorization',
            'in': 'header',
            'type': 'string',
            'required': True,
            'description': 'Bearer 액세스 토큰'
        }
    ],
    'requestBody': {
        'required': True,
        'content': {
            'application/json': {
                'schema': {
                    'type': 'object',
                    'properties': {
                        'current_password': {'type': 'string'},
                        'new_password': {'type': 'string', 'minLength': PASSWORD_MIN_LEN}
                    },
                    'required': ['current_password', 'new_password']
                }
            }
        }
    },
    'responses': {
        200: {'description': '변경 성공'},
        400: {'description': '입력값/규칙 오류 또는 기존 비밀번호와 동일'},
        401: {'description': '인증 실패/현재 비밀번호 불일치'},
        409: {'description': '아직 비밀번호가 설정되지 않은 계정'},
        500: {'description': '서버 에러'}
    }
})
def change_password():
    try:
        user = request.user
        body = request.get_json(force=True) or {}
        cur = body.get('current_password')
        new = body.get('new_password')

        if not cur or not new:
            return json_kor({"error": "current_password와 new_password는 필수입니다."}, 400)

        # 현재 비밀번호 검증
        if not check_password_hash(user['password_hash'], cur):
            return json_kor({"error": "현재 비밀번호가 올바르지 않습니다."}, 401)

        # 새 비밀번호 규칙 확인
        if not is_strong_password(new):
            return json_kor({"error": f"새 비밀번호는 최소 {PASSWORD_MIN_LEN}자 이상이어야 합니다."}, 400)

        # 기존 비밀번호와 동일 금지
        if check_password_hash(user['password_hash'], new):
            return json_kor({"error": "기존 비밀번호와 동일한 비밀번호는 사용할 수 없습니다."}, 400)

        # 업데이트
        updated_at = datetime.datetime.utcnow()
        db.user.update_one(
            {"_id": user["_id"]},
            {"$set": {
                "password_hash": generate_password_hash(new),
                "password_updated_at": updated_at
            }}
        )

        return json_kor({
            "message": "비밀번호가 변경되었습니다.",
            "password_updated_at": updated_at.isoformat() + "Z"
        }, 200)

    except Exception as e:
        return json_kor({"error": str(e)}, 500)

@user_test.route("/verify-email", methods=["GET"])
def verify_email():
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "토큰이 필요합니다."}), 400

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "토큰이 만료되었습니다. 다시 인증 메일을 요청해주세요."}), 400
    except jwt.InvalidTokenError:
        return jsonify({"error": "유효하지 않은 토큰입니다."}), 400

    if payload.get("type") != "email_verify":
        return jsonify({"error": "이메일 인증 토큰이 아닙니다."}), 400

    user_id = payload.get("sub")
    user = db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"error": "사용자를 찾을 수 없습니다."}), 404

    # 이미 인증된 경우 → 온보딩 편지도 이미 만들어졌다고 가정하고 바로 리다이렉트
    if user.get("email_verified"):
        # 프론트 페이지로 리다이렉트해도 되고, JSON으로 응답해도 됨
        return redirect(f"{APP_BASE_URL}/email-verified?status=already")
    
    # ✅ 이메일 인증 완료 처리
    db.user.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "email_verified": True,
                "email_verified_at": datetime.utcnow()
            }
        }
    )

    # ✅ 여기서 온보딩 더미 편지 생성 (가입 최종 완료 시점)
    letter = {
        "_id": ObjectId(),
        "from": ObjectId('68260f67f02ef2dccfdeffca'),
        "to": user["_id"],
        "title": '익명의 사용자에게서 온 편지',
        "emotion": '슬픔',
        "content": '정말 친하다고 생각했던 친구와 크게 싸웠어요. 좋은 친구라고 생각했는데 아니였던 것 같아요 우정이 영원할 수는 없는 걸까요?',
        "status": 'sent',
        "saved": False,
        "created_at": datetime.utcnow()
    }
    db.letter.insert_one(letter)

    # 프론트 가입완료 페이지로 리다이렉트
    return redirect(f"{APP_BASE_URL}/email-verified?status=success")

# 인증 메일 재발송
@user_test.route('/resend-email-verification', methods=['POST'])
def resend_email_verification():
    try:
        data = request.get_json(force=True)
        email = (data.get("email") or "").strip()

        if not email:
            return json_kor({"error": "이메일을 입력해주세요."}, 400)

        # 1) 계정 찾기
        user = db.user.find_one({"email": email})
        if not user:
            return json_kor({"error": "해당 이메일로 가입된 계정이 없습니다."}, 404)

        # 2) 이미 인증된 계정이면 재전송 불가
        if user.get("email_verified"):
            return json_kor({"error": "이미 이메일 인증이 완료된 계정입니다."}, 400)

        if not user.get("email"):
            return json_kor({"error": "등록된 이메일이 없습니다."}, 400)

        # 3) 너무 자주 누르는 것 방지 → 1분 제한
        now = datetime.utcnow()
        last_sent = user.get("last_verification_sent_at")  # datetime or None
        limit = timedelta(minutes=1)

        if last_sent is not None:
            elapsed = now - last_sent
            if elapsed < limit:
                retry_after = int((limit - elapsed).total_seconds())
                return json_kor({
                    "error": "인증 메일은 1분에 한 번만 재전송할 수 있어요.",
                    "retry_after": retry_after
                }, 429)
            
        # 4) 인증 메일 재전송
        try:
            send_email_verification(user)
        except Exception as e:
            current_app.logger.warning(f"[mail] resend verification failed: {e}")
            return json_kor({"error": "인증 메일 전송 중 오류가 발생했어요."}, 500)

        # 4) 마지막 발송 시간 업데이트
        db.user.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_verification_sent_at": now}}
        )

        return json_kor({"message": "인증 메일을 다시 보냈습니다. 메일함을 확인해주세요!"}, 200)

    except Exception as e:
        current_app.logger.error(f"[resend_email_verification] {e}")
        return json_kor({"error": "서버 오류가 발생했습니다."}, 500)