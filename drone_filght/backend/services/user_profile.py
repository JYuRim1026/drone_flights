import json
import os

PROFILE_FILE = "user_profile.json"

DEFAULT_PROFILE = {
    "applicant_name": "홍길동",
    "phone": "010-1234-5678",
    "email": "user@example.com",
    "address": "서울특별시 강남구 테헤란로 123",
    "birth_date": "1990-01-01",
    "organization": "개인 / 비행 동호회",
    "drone_model": "DJI Mini 4 Pro",
    "drone_weight_g": 249,
    "drone_serial": "1582F4X12345678",
    "drone_reg_num": "2024-DRONE-00123",
    "license_num": "4종 초경량비행장치 조종자",
    "emergency_contact": "010-9876-5432"
}

def load_profile():
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # merge with default for any missing keys
                profile = DEFAULT_PROFILE.copy()
                profile.update(data)
                return profile
        except Exception:
            return DEFAULT_PROFILE.copy()
    return DEFAULT_PROFILE.copy()

def save_profile(profile_data):
    try:
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving profile: {e}")
        return False
