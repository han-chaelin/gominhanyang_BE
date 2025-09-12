"""from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# Mongo URI는 .env에서 불러옴
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise Exception("MONGO_URI가 .env에 설정되지 않았습니다.")

# MongoDB 클라이언트 생성
client = MongoClient(MONGO_URI)
db = client.get_default_database()  # 기본 데이터베이스 사용"""

from pymongo import MongoClient
import os

# 로컬 개발 환경에서만 dotenv 사용
if os.environ.get("FLASK_ENV") != "production":
    from dotenv import load_dotenv
    load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
#<<<<<<< HEAD
db = client['dev']  # 기본 데이터베이스 사용
#=======
#db = client.get_default_database()  # 기본 데이터베이스 사용


#>>>>>>> 4ba4669844dec7656428f4c111a015e05fe41362
