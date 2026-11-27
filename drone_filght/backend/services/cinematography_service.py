"""
cinematography_service.py
AI 시네마틱 드론 촬영 도우미 모듈
- 천문 태양 위치 계산 (일출, 일몰, 골든아워, 블루아워)
"""

import math
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# 1. Pure Python NOAA Solar Position Algorithm
# ---------------------------------------------------------------------------
def calculate_sun_times(lat: float, lon: float, target_date: date = None) -> dict:
    """
    Computes exact astronomical solar times (Sunrise, Sunset, Morning/Evening Golden Hour, Blue Hour)
    for a given latitude, longitude, and date in Korea Standard Time (UTC+9).
    """
    if target_date is None:
        target_date = date.today()
        
    year = target_date.year
    month = target_date.month
    day = target_date.day
    
    # Day of the year
    n = (datetime(year, month, day) - datetime(year, 1, 1)).days + 1
    
    # Fractional year in radians
    gamma = 2.0 * math.pi / 365.0 * (n - 1)
    
    # Equation of time in minutes
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    
    # Solar declination angle in radians
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.0148 * math.sin(3 * gamma))
    
    lat_rad = math.radians(lat)
    
    # Zenith for standard sunrise/sunset: 90.833 degrees (atmospheric refraction)
    zenith_official = math.radians(90.833)
    
    # Hour angle for sunrise/sunset
    cos_ha_official = (math.cos(zenith_official) / (math.cos(lat_rad) * math.cos(decl)) 
                       - math.tan(lat_rad) * math.tan(decl))
    
    # Clamp for polar regions
    cos_ha_official = max(-1.0, min(1.0, cos_ha_official))
    ha_official = math.degrees(math.acos(cos_ha_official))
    
    # Zenith for Golden hour (+6 degrees elevation = 84 degrees zenith)
    zenith_golden = math.radians(84.0)
    cos_ha_golden = (math.cos(zenith_golden) / (math.cos(lat_rad) * math.cos(decl)) 
                     - math.tan(lat_rad) * math.tan(decl))
    cos_ha_golden = max(-1.0, min(1.0, cos_ha_golden))
    ha_golden = math.degrees(math.acos(cos_ha_golden))
    
    # Zenith for Blue hour (civil twilight: -6 degrees elevation = 96 degrees zenith)
    zenith_blue = math.radians(96.0)
    cos_ha_blue = (math.cos(zenith_blue) / (math.cos(lat_rad) * math.cos(decl)) 
                   - math.tan(lat_rad) * math.tan(decl))
    cos_ha_blue = max(-1.0, min(1.0, cos_ha_blue))
    ha_blue = math.degrees(math.acos(cos_ha_blue))
    
    # Solar noon in minutes from midnight UTC
    tz_offset = 9.0  # Korea Standard Time (UTC+9)
    solar_noon_min = 720.0 - 4.0 * lon - eqtime + (tz_offset * 60.0)
    
    sunrise_min = solar_noon_min - (ha_official * 4.0)
    sunset_min = solar_noon_min + (ha_official * 4.0)
    
    m_golden_end_min = solar_noon_min - (ha_golden * 4.0)
    e_golden_start_min = solar_noon_min + (ha_golden * 4.0)
    
    m_blue_start_min = solar_noon_min - (ha_blue * 4.0)
    e_blue_end_min = solar_noon_min + (ha_blue * 4.0)
    
    def min_to_hhmm(m: float) -> str:
        m = (m + 1440.0) % 1440.0
        hrs = int(m // 60)
        mins = int(round(m % 60))
        if mins >= 60:
            hrs = (hrs + 1) % 24
            mins = 0
        return f"{hrs:02d}:{mins:02d}"
    
    sunrise_str = min_to_hhmm(sunrise_min)
    sunset_str = min_to_hhmm(sunset_min)
    m_golden_start = sunrise_str
    m_golden_end = min_to_hhmm(m_golden_end_min)
    
    e_golden_start = min_to_hhmm(e_golden_start_min)
    e_golden_end = min_to_hhmm(sunset_min - 5)  # Safe landing 5 min before legal sunset
    
    m_blue_start = min_to_hhmm(m_blue_start_min)
    m_blue_end = sunrise_str
    
    e_blue_start = sunset_str
    e_blue_end = min_to_hhmm(e_blue_end_min)
    
    solar_noon_str = min_to_hhmm(solar_noon_min)
    
    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "sunrise": sunrise_str,
        "sunset": sunset_str,
        "solar_noon": solar_noon_str,
        "morning_golden_hour": f"{m_golden_start} ~ {m_golden_end}",
        "evening_golden_hour": f"{e_golden_start} ~ {e_golden_end}",
        "morning_blue_hour": f"{m_blue_start} ~ {m_blue_end}",
        "evening_blue_hour": f"{e_blue_start} ~ {e_blue_end}",
        "safe_sunset_flight_window": f"{min_to_hhmm(sunset_min - 45)} ~ {min_to_hhmm(sunset_min - 5)}",
        "raw_sunset_min": sunset_min,
        "raw_sunrise_min": sunrise_min
    }
