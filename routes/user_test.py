from flask import request, Blueprint, current_app
from flasgger import swag_from
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from functools import wraps
import jwt, json, re, random
from utils.db import db
from utils.config import JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, APP_BASE_URL
from utils.attendance import mark_attendance_login, attended_today, record_attendance
from utils.auth import token_required
from utils.response import json_kor
from utils.mailer import send_email

# 이메일 인증코드
CODE_EXPIRE_MINUTES = 10          # 인증코드 유효시간 (10분)
EMAIL_CODE_RESEND_COOLDOWN = 60   # 재발송 쿨타임 (초)
EMAIL_CODE_MAX_ATTEMPTS = 5      # 최대 시도 횟수

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

def create_token(user_doc):
    expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "user_id": str(user_doc["_id"]),
        "nickname": user_doc["nickname"],
        "exp": expire
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

# 이메일 중복 체크
@user_test.route('/email/check', methods=['POST'])
def check_email():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()

    if not email:
        return json_kor({"error": "이메일을 입력해주세요."}, 400)

    if not is_valid_email(email):
        return json_kor({"error": "올바른 이메일 형식이 아닙니다."}, 400)

    existed = db.user.find_one({"email": email})
    if existed:
        return json_kor({
            "available": False,
            "reason": "이미 가입된 이메일입니다."
        }, 200)

    return json_kor({"available": True}, 200)

@user_test.route('/email/send-code', methods=['POST'])
def send_email_code():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()

    if not email:
        return json_kor({"error": "이메일을 입력해주세요."}, 400)

    if not is_valid_email(email):
        return json_kor({"error": "올바른 이메일 형식이 아닙니다."}, 400)

    now = datetime.utcnow()

    # 최근 인증코드 기록 가져오기
    record = db.email_verification.find_one({"email": email})

    # 재발송 쿨타임 체크
    if record and record.get("last_sent_at"):
        last = record["last_sent_at"]
        if isinstance(last, datetime):
            diff = (now - last).total_seconds()
            if diff < EMAIL_CODE_RESEND_COOLDOWN:
                remain = int(EMAIL_CODE_RESEND_COOLDOWN - diff)
                return json_kor({
                    "error": f"{remain}초 후에 다시 시도해주세요.",
                    "retry_after": remain
                }, 429)

    # 6자리 코드 생성
    code = f"{random.randint(0, 999999):06d}"
    code_hash = generate_password_hash(code)
    expires_at = now + timedelta(minutes=CODE_EXPIRE_MINUTES)

    # upsert (있으면 업데이트, 없으면 새 문서 생성)
    db.email_verification.update_one(
        {"email": email},
        {
            "$set": {
                "code_hash": code_hash,
                "expires_at": expires_at,
                "last_sent_at": now,
                "verified": False,
            },
            "$setOnInsert": {
                "attempts": 0
            }
        },
        upsert=True
    )

    # 이메일 발송
    subject = "[마음의 항해] 이메일 인증코드 안내"
    html = f"""
    <h3>이메일 인증코드 안내</h3>
    <p>아래 인증코드를 회원가입 화면에 입력해주세요.</p>
    <h2>{code}</h2>
    <p>인증코드 유효시간은 {CODE_EXPIRE_MINUTES}분입니다.</p>
    """

    ok, err = send_email(
        to_email=email,
        subject=subject,
        html=html
    )

    if not ok:
        current_app.logger.warning(f"[mail] send_email_code fail: {err}")
        return json_kor({"error": "인증 메일 발송 중 오류가 발생했습니다."}, 500)

    return json_kor({
        "message": "인증코드를 이메일로 전송했습니다.",
        "expire_minutes": CODE_EXPIRE_MINUTES,
        "cooldown_seconds": EMAIL_CODE_RESEND_COOLDOWN
    }, 200)

@user_test.route('/email/verify-code', methods=['POST'])
def verify_email_code():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    code = (data.get('code') or '').strip()

    if not email or not code:
        return json_kor({"error": "이메일과 인증코드를 모두 입력해주세요."}, 400)

    if not is_valid_email(email):
        return json_kor({"error": "올바른 이메일 형식이 아닙니다."}, 400)

    record = db.email_verification.find_one({"email": email})
    if not record:
        return json_kor({"error": "해당 이메일로 요청된 인증코드가 없습니다. 코드를 다시 요청해주세요."}, 400)

    now = datetime.utcnow()

    # 만료 체크
    expires_at = record.get("expires_at")
    if not expires_at or not isinstance(expires_at, datetime) or expires_at < now:
        return json_kor({"error": "인증코드가 만료되었습니다. 다시 요청해주세요."}, 400)

    # 시도 횟수 체크
    attempts = record.get("attempts", 0)
    if attempts >= EMAIL_CODE_MAX_ATTEMPTS:
        return json_kor({"error": "인증 시도 가능 횟수를 초과했습니다. 코드를 다시 요청해주세요."}, 400)

    # 코드 검증
    code_hash = record.get("code_hash")
    if not code_hash or not check_password_hash(code_hash, code):
        # 실패 시 시도 횟수 증가
        db.email_verification.update_one(
            {"email": email},
            {"$set": {"attempts": attempts + 1}}
        )
        return json_kor({"error": "인증코드가 일치하지 않습니다."}, 400)

    # 성공: verified 플래그, 시도 횟수 리셋
    db.email_verification.update_one(
        {"email": email},
        {"$set": {"verified": True, "attempts": 0}}
    )

    # 이메일 인증 토큰 발급 (회원가입 전용 토큰)
    expire = datetime.utcnow() + timedelta(minutes=30)  # 예: 30분 동안 유효
    payload = {
        "sub": email,
        "type": "email_signup",
        "exp": expire
    }
    email_verification_token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    return json_kor({
        "message": "이메일 인증이 완료되었습니다.",
        "email_verification_token": email_verification_token,
        "email": email,
    }, 200)

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
                        'email_verification_token': {'type': 'string'},
                        'email_notify_enabled': {'type': 'boolean'}
                    },
                    'required': ['nickname', 'password', 'age', 'gender', 'status', 'email', 'email_verification_token', 'email_notify_enabled']
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
        address  = data.get('address')
        phone    = data.get('phone')
        email    = (data.get('email') or '').strip().lower()
        email_verification_token = data.get('email_verification_token')
        raw_notify = data.get('email_notify_enabled', None)

        # 1) 필수값 체크
        if not nickname or age is None or not password or not gender or not status or not email:
            return json_kor({"error": "닉네임, 비밀번호, 나이, 성별, 신분, 이메일은 필수입니다."}, 400)

        # 이메일 형식 체크
        if not is_valid_email(email):
            return json_kor({"error": "올바른 이메일 형식이 아닙니다."}, 400)

        # 이메일 수신 동의는 필수 체크항목 (null/미전달 허용 X)
        if raw_notify is None:
            return json_kor({"error": "이메일 수신 동의 여부는 필수입니다."}, 400)
        
        # 2) 닉네임 중복
        if db.user.find_one({"nickname": nickname}):
            return json_kor({"error": "이미 존재하는 닉네임입니다."}, 400)
        
        # 3) 비밀번호/신분 규칙 체크
        if not is_strong_password(password):
            return json_kor({"error": f"비밀번호는 최소 {PASSWORD_MIN_LEN}자 이상이어야 합니다."}, 400)

        if not is_valid_status(status):
            return json_kor({"error": f"신분(status)은 {ALLOWED_STATUS} 중 하나여야 합니다."}, 400)

        # 4) 이메일 인증 토큰 필수
        if not email_verification_token:
            return json_kor({"error": "이메일 인증 토큰이 필요합니다. 이메일 인증을 먼저 진행해주세요."}, 400)
        
        # 이메일 인증 토큰 검증
        try:
            payload = jwt.decode(email_verification_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return json_kor({"error": "이메일 인증 토큰이 만료되었습니다. 이메일 인증을 다시 진행해주세요."}, 400)
        except jwt.InvalidTokenError:
            return json_kor({"error": "유효하지 않은 이메일 인증 토큰입니다."}, 400)

        if payload.get("type") != "email_signup":
            return json_kor({"error": "이메일 인증용 토큰이 아닙니다."}, 400)

        email_from_token = payload.get("sub")

        # 토큰 안 이메일 검증
        if not email or not is_valid_email(email_from_token):
            return json_kor({"error": "토큰에 포함된 이메일 정보가 올바르지 않습니다."}, 400)

        # 요청 바디의 이메일과 토큰의 이메일이 일치하는지 확인
        if email_from_token.lower() != email:
            return json_kor({"error": "이메일 인증을 완료한 주소와 현재 입력한 이메일이 일치하지 않습니다."}, 400)
        
        # 6) 이메일 중복 최종 체크
        if db.user.find_one({"email": email}):
            return json_kor({"error": "이미 등록된 이메일입니다. 다른 이메일로 시도해주세요."}, 400)

        # 7) 이메일 수신 동의값 파싱 (필수지만 true/false 형태로 변환)
        email_notify_enabled = None
        if isinstance(raw_notify, bool):
            email_notify_enabled = raw_notify
        elif isinstance(raw_notify, str):
            v = raw_notify.strip().lower()
            if v in ["true", "1", "yes", "y", "on"]:
                email_notify_enabled = True
            elif v in ["false", "0", "no", "n", "off"]:
                email_notify_enabled = False
            else:
                return json_kor({"error": "email_notify_enabled 값은 true/false 여야 합니다."}, 400)
        else:
            return json_kor({"error": "email_notify_enabled 값은 boolean 이거나 이에 준하는 문자열이어야 합니다."}, 400)

        # 8) limited_access는 phone 유무로 판단
        limited_access = not (phone)

        # 9) 유저 생성 (이메일은 이미 인증된 상태로 가입)
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
            "email_verified": True,
            "email_verified_at": datetime.utcnow(),
            "email_notify_enabled": email_notify_enabled,
            "created_at": datetime.utcnow(),
        }

        result = db.user.insert_one(new_user)

        # 온보딩 더미 편지 생성
        try:
            onboarding_letter = {
                "_id": ObjectId(),
                "from": ObjectId('68260f67f02ef2dccfdeffca'),  # 시스템/온달 계정 같은 고정 발신자
                "to": result.inserted_id,                      # 방금 가입한 유저에게
                "title": "익명의 사용자에게서 온 편지",
                "emotion": "슬픔",
                "content": """요즘은 하루하루가 조금 벅차게 느껴져요.
주어진 일들을 해내고는 있지만, 마음 한구석이 계속 무거운 느낌이 들어요.

누군가에게 털어놓고 싶다가도,
괜히 부담만 줄까 봐 말을 아끼게 되더라고요.

다들 잘 지내는 것 같아 보여도,
어쩌면 우리 모두 각자의 자리에서
묵묵히 버티며 하루를 살아내고 있는 건 아닐까—
그런 생각도 들어요.

혹시 당신도 비슷한 시간을 지나고 있다면
내 마음은 당신에게 닿고 있어요.
말하지 못했던 마음들을
여기에서는 조금씩 꺼내도 괜찮아요.""",
                "status": "sent",
                "saved": False,
                "created_at": datetime.utcnow()
            }
            db.letter.insert_one(onboarding_letter)
        except Exception as e:
            current_app.logger.warning(f"[onboarding_letter] failed: {e}")

        # 여기서는 바로 로그인 JWT를 발급하지 않고, 회원가입 성공만 알려줌
        return json_kor({
            "message": "회원가입이 완료되었습니다. 이제 로그인할 수 있어요.",
            "limited_access": limited_access
        }, 201)
    except Exception as e:
        current_app.logger.error(f"[signup] {e}")
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
            }, 403)
        
        token = create_token(user_doc)

        # 로그인 기반 출석 체크
        today_done = record_attendance(user_doc["_id"])


        ##### 더미용 데이터 - 실제 배포 시에는 삭제 ####
        """letter = {"_id": ObjectId(), "from": ObjectId('68260f67f02ef2dccfdeffca'), "to": user_id, "title": '익명의 사용자에게서 온 편지',"emotion": '슬픔', "content": '정말 친하다고 생각했던 친구와 크게 싸웠어요. 좋은 친구라고 생각했는데 아니였던 것 같아요 우정이 영원할 수는 없는 걸까요?', "status": 'sent',
              "saved": False, "created_at": datetime.now()}
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
        allowed_fields = ['nickname', 'status', 'email', 'address', 'phone', 'email_notify_enabled']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}

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

        # 이메일 알림 동의: boolean 값 검증
        if "email_notify_enabled" in update_fields:
            raw_val = update_fields["email_notify_enabled"]

            # true/false로 들어온 경우
            if isinstance(raw_val, bool):
                parsed = raw_val
            # 혹시 프론트에서 문자열로 보낼 수도 있으니 안전하게 처리
            elif isinstance(raw_val, str):
                v = raw_val.strip().lower()
                if v in ["true", "1", "yes", "y", "on"]:
                    parsed = True
                elif v in ["false", "0", "no", "n", "off"]:
                    parsed = False
                else:
                    return json_kor(
                        {"error": "email_notify_enabled 값은 true/false 여야 합니다."}, 
                        400
                    )
            else:
                return json_kor(
                    {"error": "email_notify_enabled 값은 boolean 이거나 이에 준하는 문자열이어야 합니다."}, 
                    400
                )

            update_fields["email_notify_enabled"] = parsed

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
            "limited_access": user.get("limited_access", True),
            "email_notify_enabled": user.get("email_notify_enabled"),
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
        updated_at = datetime.utcnow()
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
    
@user_test.route('/email/consent', methods=['PATCH'])
@token_required
@swag_from({
    'tags': ['User'],
    'summary': '이메일 수신 동의/거부',
    'description': '서비스 알림/편지 도착 알림 등 이메일 수신에 대한 동의 여부를 설정합니다.',
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
                        'email_notify_enabled': {
                            'type': 'boolean',
                            'description': '이메일 수신 동의 여부 (true: 동의, false: 거부)'
                        }
                    },
                    'required': ['email_notify_enabled']
                }
            }
        }
    },
    'responses': {
        200: {'description': '동의 상태 변경 성공'},
        400: {'description': '잘못된 입력 값'},
        401: {'description': '인증 실패'},
        500: {'description': '서버 에러'}
    }
})
def update_email_consent():
    try:
        user = request.user
        data = request.get_json(force=True) or {}

        raw_val = data.get("email_notify_enabled", None)
        if raw_val is None:
            return json_kor({"error": "email_notify_enabled 값은 필수입니다."}, 400)

        # true/false로 들어온 경우
        if isinstance(raw_val, bool):
            parsed = raw_val
        # 문자열로 들어올 수도 있으니 처리
        elif isinstance(raw_val, str):
            v = raw_val.strip().lower()
            if v in ["true", "1", "yes", "y", "on"]:
                parsed = True
            elif v in ["false", "0", "no", "n", "off"]:
                parsed = False
            else:
                return json_kor({"error": "email_notify_enabled 값은 true/false 여야 합니다."}, 400)
        else:
            return json_kor(
                {"error": "email_notify_enabled 값은 boolean 이거나 이에 준하는 문자열이어야 합니다."},
                400
            )

        db.user.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "email_notify_enabled": parsed,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        return json_kor({
            "message": "이메일 수신 동의 상태가 변경되었습니다.",
            "email_notify_enabled": parsed
        }, 200)

    except Exception as e:
        current_app.logger.error(f"[update_email_consent] {e}")
        return json_kor({"error": "서버 오류가 발생했습니다."}, 500)