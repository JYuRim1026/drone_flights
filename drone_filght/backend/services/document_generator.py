import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

def generate_flight_approval_text(profile, flight_info, ai_result):
    """
    Generates a structured text document pre-filled for Drone One-Stop Flight Approval Application.
    """
    text = f"""[드론원스톱 민원 서식] 초경량비행장치 비행 승인 신청서 (자동 작성본)

1. 신청인 정보 (User Profile)
 - 성 명: {profile.get('applicant_name')}
 - 생년월일: {profile.get('birth_date')}
 - 연 락 처: {profile.get('phone')}
 - 이 메 일: {profile.get('email')}
 - 주 소: {profile.get('address')}
 - 소속/회사: {profile.get('organization')}

2. 비행 장치(드론) 정보
 - 기종 및 모델명: {profile.get('drone_model')}
 - 기체 자중(무게): {flight_info.get('weight_g')} g
 - 기체 등록번호: {profile.get('drone_reg_num')}
 - 기체 시리얼번호: {profile.get('drone_serial')}
 - 조종자 자격증: {profile.get('license_num')}

3. 비행 계획 및 장소
 - 비행 목적: {flight_info.get('purpose', '경관 촬영 및 취미 비행')}
 - 비행 예정 일시: {flight_info.get('date_str')} {flight_info.get('time_str')}
 - 비행 위치(위경도): 위도 {flight_info.get('lat')}, 경도 {flight_info.get('lon')}
 - 비행 장소(주소/지역): {flight_info.get('location_name', '지정 좌표 지역')}
 - 비행 반경 및 고도: 반경 500m 이내 / 최고 고도 {flight_info.get('max_altitude', 120)}m 이하

4. AI 분석 및 신청 사유
 - 비행구역 진단: {flight_info.get('airspace_name')}
 - 비행 승인 신청 사유: {ai_result.get('summary')}
 - 관련 기상 상태: 풍속 {flight_info.get('wind_speed')}m/s, 날씨 {flight_info.get('weather_desc')}

본 신청서는 드론원스톱 민원서비스 (drone.onestop.go.kr) 제출용 자동 생성 문서입니다.
"""
    return text

def generate_photo_permit_text(profile, flight_info, ai_result):
    """
    Generates a structured text document pre-filled for Aerial Photography Permit Application.
    """
    text = f"""[드론원스톱 민원 서식] 항공촬영 허가 신청서 (자동 작성본)

1. 신청인 정보 (User Profile)
 - 성 명: {profile.get('applicant_name')}
 - 연 락 처: {profile.get('phone')} (비상연락처: {profile.get('emergency_contact')})
 - 이 메 일: {profile.get('email')}
 - 소속 및 직위: {profile.get('organization')}

2. 촬영 장비 및 드론 스펙
 - 드론 기종: {profile.get('drone_model')} (무게: {flight_info.get('weight_g')}g)
 - 카메라 명칭 및 스펙: 일체형 고화질 4K 광학 카메라 (보안시설 비촬영 조건)
 - 촬영 목적: {flight_info.get('purpose', '자연 경관 및 대중매체 촬영')}

3. 촬영 일시 및 구역
 - 촬영 예정일: {flight_info.get('date_str')} {flight_info.get('time_str')}
 - 촬영 장소: {flight_info.get('location_name', '지정 좌표 지역')} (Lat: {flight_info.get('lat')}, Lon: {flight_info.get('lon')})

4. 보안 및 준수사항 서약
 - 국가 보안시설 및 군사시설 촬영 절대 금지 준수
 - 촬영된 영상물 유출 방지 및 보안 조치 이행 서약

본 신청서는 국방부 / 드론원스톱 서비스 신청 항목에 자동 반영된 서식입니다.
"""
    return text

def create_pdf_document(filename, title, content_text):
    """
    Creates a downloadable PDF document using ReportLab.
    """
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    # Title Header
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor("#1E3A8A")) # Navy Blue
    c.drawString(40, height - 50, title)
    
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1)
    c.line(40, height - 60, width - 40, height - 60)
    
    # Body Content
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#1E293B"))
    
    y = height - 90
    lines = content_text.split('\n')
    for line in lines:
        if y < 50:
            c.showPage()
            y = height - 50
        
        if line.startswith('[') or line.startswith('1.') or line.startswith('2.') or line.startswith('3.') or line.startswith('4.'):
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(colors.HexColor("#0F172A"))
        else:
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.HexColor("#334155"))
            
        c.drawString(40, y, line)
        y -= 16
        
    c.save()
    return filename
