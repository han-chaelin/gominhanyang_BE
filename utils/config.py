# utils/config.py
import os
from dotenv import load_dotenv

# 1) .env 파일 로드
load_dotenv()

# 2) 환경 구분
ENV = os.getenv("FLASK_ENV", "development")
DEBUG = ENV == "development"

# 3) 데이터베이스 설정
MONGODB_URI = os.getenv("MONGO_URI")
DB_NAME      = os.getenv("DB_NAME", "user_test")

# 4) 인증 · 보안 설정 
JWT_ALGORITHM              = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret")

POINT_RULES = {
    "write_letter": 10,
    "reply_letter": 10,
    "long_letter_bonus": 5  # 200자 초과 시 추가 포인트
}
LEVEL_UP_THRESHOLD = {
    100: "level_up"
}

# 6) 서버 · 배포 설정
#CORS_ORIGINS       = os.getenv("CORS_ORIGINS", "*").split(",")
#MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))

# 7) 로깅 설정
#LOG_LEVEL     = os.getenv("LOG_LEVEL", "INFO")
#LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "./logs/app.log")

# 8) 기타 공통 상수
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
PAGE_SIZE       = int(os.getenv("PAGE_SIZE", 20))

# 9) ✉️ 이메일 / 알림 관련 설정 추가
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER or "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"

# 이메일 템플릿 내 링크 기본 주소
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://gominhanyang.vercel.app")


MAIL_DEBUG = os.getenv("MAIL_DEBUG", "false").lower() == "true"
def masked_env_snapshot():
    def hide(v):
      if not v: return v
      if len(v) <= 4: return "***"
      return v[:2] + "***" + v[-2:]
    return {
      "SMTP_HOST": os.getenv("SMTP_HOST"),
      "SMTP_PORT": os.getenv("SMTP_PORT"),
      "SMTP_USER": hide(os.getenv("SMTP_USER")),
      "SMTP_PASSWORD(len)": len(os.getenv("SMTP_PASSWORD","")),
      "EMAIL_FROM": os.getenv("EMAIL_FROM"),
      "EMAIL_USE_TLS": os.getenv("EMAIL_USE_TLS"),
    }
