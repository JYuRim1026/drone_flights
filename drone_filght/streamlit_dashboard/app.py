import streamlit as st
import streamlit.components.v1 as components
import folium
from streamlit_folium import st_folium
from datetime import datetime, date, time
import os
from dotenv import load_dotenv

_BACKEND_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", ".env")
if os.path.exists(_BACKEND_ENV_PATH):
    load_dotenv(_BACKEND_ENV_PATH)
load_dotenv()

import urllib.parse
import json
import re
import textwrap

import sys
from pathlib import Path
_SERVICES_DIR = Path(__file__).resolve().parent.parent / "backend" / "services"
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from user_profile import load_profile, save_profile
from geocoding_service import geocode_address
from airspace_service import check_airspace, OFFICIAL_LEGENDS
from weather_service import get_weather
from ai_evaluator import evaluate_flight_suitability
from ai_assistant import get_ai_response, process_flight_approval_request
from document_generator import (
    generate_flight_approval_text,
    generate_photo_permit_text,
    create_pdf_document
)
from onestop_automation import run_onestop_auto_fill
import cinematography_service as cs

# Page Setup
st.set_page_config(
    page_title="스카이 커맨드 | AI 드론 비행 안전 & 드론원스톱 승인 도우미",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# Modern Navy & Blue HTML/CSS Design System (Matching User Provided Template)
# ---------------------------------------------------------
st.markdown("""
<style>
:root {
    --navy: #10233f;
    --navy2: #18365b;
    --blue: #3978f6;
    --sky: #eaf2ff;
    --bg: #f4f7fb;
    --text: #18263b;
    --muted: #77849a;
    --line: #e5ebf3;
    --white: #ffffff;
    --green: #159b75;
    --shadow: 0 14px 40px rgba(21, 44, 78, 0.08);
    --radius-lg: 20px;
    --radius-md: 14px;
    --radius-sm: 10px;
}

/* Modern Dark Navy Sidebar Styling */
[data-testid="stSidebar"] {
    background-color: #10233f !important;
    color: #ffffff !important;
    border-right: 1px solid #1f3b61 !important;
    min-width: 270px !important;
    max-width: 300px !important;
}
[data-testid="stSidebar"] > div:first-child,
[data-testid="stSidebarContent"] {
    padding-top: 1.5rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    padding-bottom: 1.2rem !important;
    display: flex !important;
    flex-direction: column !important;
    min-height: 100vh !important;
    box-sizing: border-box !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]:first-of-type,
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"]:first-of-type {
    display: flex !important;
    flex-direction: column !important;
    flex: 1 1 auto !important;
    min-height: calc(100vh - 3.5rem) !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: #cbd8e8;
}
[data-testid="stSidebar"] hr {
    border-color: #234166 !important;
    margin: 12px 0 !important;
}

/* Sidebar Brand Header (Strict Horizontal Alignment) */
.sidebar-brand {
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    gap: 12px !important;
    padding: 0 4px 18px 4px !important;
    width: 100% !important;
}
.sidebar-brand-icon {
    width: 42px !important;
    height: 42px !important;
    border-radius: 12px !important;
    background: #3978f6 !important;
    color: white !important;
    display: grid !important;
    place-items: center !important;
    font-size: 22px !important;
    font-weight: 800 !important;
    box-shadow: 0 8px 20px rgba(57, 120, 246, 0.35) !important;
    flex-shrink: 0 !important;
}
.sidebar-brand-text {
    display: flex !important;
    flex-direction: column !important;
    white-space: nowrap !important;
    overflow: hidden !important;
}
.sidebar-brand-title {
    font-size: 17px !important;
    font-weight: 800 !important;
    color: #ffffff !important;
    letter-spacing: -0.4px !important;
    line-height: 1.25 !important;
    white-space: nowrap !important;
}
.sidebar-brand-sub {
    font-size: 11px !important;
    color: #8da6c8 !important;
    letter-spacing: 0.5px !important;
    margin-top: 2px !important;
    white-space: nowrap !important;
}
.sidebar-menu-label {
    font-size: 11px;
    color: #7b94b5;
    font-weight: 700;
    letter-spacing: 1.2px;
    padding: 0 8px;
    margin-bottom: 8px;
}

/* Vertical Radio Navigation as Pill Tabs */
[data-testid="stSidebar"] div[role="radiogroup"] {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 8px;
}
[data-testid="stSidebar"] div[role="radiogroup"] label {
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 12px !important;
    padding: 11px 14px !important;
    margin: 0 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    width: 100% !important;
    display: flex !important;
    align-items: center !important;
}
[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
    background: #19365c !important;
}
[data-testid="stSidebar"] div[role="radiogroup"] label p {
    color: #b9c8dc !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    margin: 0 !important;
}
[data-testid="stSidebar"] div[role="radiogroup"] label:hover p {
    color: #ffffff !important;
}
/* Hide the default radio circle completely */
[data-testid="stSidebar"] div[role="radiogroup"] input[type="radio"],
[data-testid="stSidebar"] div[role="radiogroup"] label div:first-child {
    display: none !important;
}
/* Selected active menu item */
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background: #244675 !important;
    border-color: #3b689e !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25) !important;
}
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {
    color: #ffffff !important;
    font-weight: 700 !important;
}

/* Sidebar Action Link Button (신청서 미리보기) */
[data-testid="stSidebar"] [data-testid="stLinkButton"] a {
    background: #18375e !important;
    color: #ffffff !important;
    border: 1.5px solid #33598d !important;
    border-radius: 12px !important;
    padding: 11px 14px !important;
    font-size: 13.5px !important;
    font-weight: 700 !important;
    box-shadow: 0 3px 10px rgba(0,0,0,0.15) !important;
    text-align: left !important;
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
    margin-bottom: 6px !important;
    text-decoration: none !important;
}
[data-testid="stSidebar"] [data-testid="stLinkButton"] a:hover {
    background: #234878 !important;
    border-color: #4a77b3 !important;
}

/* Sidebar Regular Buttons */
[data-testid="stSidebar"] button {
    background: transparent !important;
    color: #b9c8dc !important;
    border: 1px solid #234166 !important;
    border-radius: 12px !important;
    padding: 10px 14px !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    text-align: left !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    transition: all 0.2s ease !important;
    width: 100% !important;
}
[data-testid="stSidebar"] button:hover {
    background: #19365c !important;
    color: #ffffff !important;
    border-color: #3b689e !important;
}
[data-testid="stSidebar"] button p {
    color: inherit !important;
}

/* History Box in Sidebar */
.sidebar-hist-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    color: #7b94b5;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 0 4px 6px;
}
[data-testid="stSidebar"] div:has(> .sidebar-note),
[data-testid="stSidebar"] div:has(> div > .sidebar-note),
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.sidebar-note),
[data-testid="stSidebar"] [data-testid="element-container"]:has(.sidebar-note) {
    margin-top: auto !important;
    margin-bottom: 0.5rem !important;
}
.sidebar-note {
    border: 1px solid #2d4c70;
    background: #143050;
    border-radius: 12px;
    padding: 12px;
    font-size: 11px;
    color: #a7bdd8;
    line-height: 1.55;
    margin-top: auto !important;
}
.sidebar-note strong {
    display: block;
    color: #ffffff;
    font-size: 12px;
    margin-bottom: 4px;
}

/* Base Streamlit Overrides */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* Keep Header functional so sidebar reopen control stays fully accessible */
header[data-testid="stHeader"] {
    background: transparent !important;
    visibility: visible !important;
    height: 0px !important;
    min-height: 0px !important;
    z-index: 999990 !important;
}

/* Visually hide redundant native collapse & expand buttons so user only sees the topbar toggle */
[data-testid="stSidebarCollapseButton"] {
    position: fixed !important;
    top: -9999px !important;
    left: -9999px !important;
    opacity: 0 !important;
    pointer-events: none !important;
    width: 0px !important;
    height: 0px !important;
    overflow: hidden !important;
}

[data-testid="collapsedControl"] {
    position: fixed !important;
    top: -9999px !important;
    left: -9999px !important;
    opacity: 0 !important;
    pointer-events: none !important;
    width: 0px !important;
    height: 0px !important;
    overflow: hidden !important;
}

/* Topbar Toggle Button (The ONLY toggle for folding & unfolding sidebar) */
.topbar-toggle-btn {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: #edf2f9;
    border: 1.5px solid #cbd5e1;
    border-radius: 10px;
    padding: 7px 14px;
    color: var(--navy);
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.topbar-toggle-btn:hover {
    background: #e2e8f0;
    border-color: #94a3b8;
    color: var(--blue);
}

.stApp {
    background-color: var(--bg);
    font-family: ui-sans-serif, system-ui, -apple-system, 'Malgun Gothic', '맑은 고딕', sans-serif;
    color: var(--text);
}
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 3rem;
    max-width: 1440px;
}

/* Modern Top Navigation Bar */
.topbar {
    background: var(--white);
    border: 1px solid var(--line);
    border-radius: var(--radius-md);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
    box-shadow: 0 4px 16px rgba(16, 35, 63, 0.04);
    margin-bottom: 20px;
}
.brand-wrap {
    display: flex;
    align-items: center;
    gap: 12px;
}
.brand-icon {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    background: var(--blue);
    color: white;
    display: grid;
    place-items: center;
    font-size: 20px;
    font-weight: 800;
    box-shadow: 0 6px 16px rgba(57, 120, 246, 0.35);
}
.brand-copy strong {
    display: block;
    font-size: 17px;
    letter-spacing: -0.4px;
    color: var(--navy);
}
.brand-copy small {
    display: block;
    color: var(--muted);
    font-size: 11px;
    letter-spacing: 0.5px;
}
.topbar-status {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #2b6a55;
    background: #eaf8f2;
    border: 1px solid #d4f0e4;
    padding: 7px 13px;
    border-radius: 99px;
    font-weight: 600;
}
.status-dot {
    width: 8px;
    height: 8px;
    background: var(--green);
    border-radius: 50%;
    box-shadow: 0 0 0 3px rgba(21, 155, 117, 0.2);
}

/* Hero Section */
.hero-box {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 20px;
    margin-bottom: 22px;
    padding: 0 6px;
}
.eyebrow {
    font-size: 11px;
    color: var(--blue);
    font-weight: 800;
    letter-spacing: 1.2px;
    margin-bottom: 6px;
}
.hero-title {
    margin: 0 0 6px;
    font-size: 24px;
    font-weight: 800;
    letter-spacing: -0.8px;
    color: var(--navy);
}
.hero-desc {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.6;
}
.step-chip {
    white-space: nowrap;
    background: var(--white);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 9px 15px;
    font-size: 12px;
    color: var(--muted);
    font-weight: 500;
    box-shadow: 0 2px 8px rgba(0,0,0,0.02);
}
.step-chip b {
    color: var(--blue);
    font-weight: 700;
}

/* Streamlit Tabs Customization */
[data-testid="stTabs"] {
    margin-bottom: 18px;
}
[data-testid="stTabs"] [role="tablist"] {
    gap: 10px;
    border-bottom: 1px solid var(--line);
    padding-bottom: 8px;
}
[data-testid="stTabs"] [role="tab"] {
    background-color: var(--white) !important;
    border: 1px solid var(--line) !important;
    border-radius: 12px !important;
    color: var(--muted) !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    padding: 10px 20px !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02) !important;
    transition: all 0.2s ease !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    background-color: var(--navy) !important;
    color: white !important;
    border-color: var(--navy) !important;
    box-shadow: 0 6px 18px rgba(16, 35, 63, 0.18) !important;
}

/* Card & Analysis Panel Styles */
.analysis-panel {
    background: var(--white);
    border: 1px solid var(--line);
    border-radius: var(--radius-md);
    padding: 18px 20px;
    margin-bottom: 14px;
    box-shadow: 0 4px 16px rgba(21, 44, 78, 0.04);
}
.analysis-section-title {
    font-size: 14px;
    font-weight: 800;
    margin-bottom: 10px;
    color: var(--navy);
    display: flex;
    align-items: center;
    gap: 8px;
}
.score-badge-card {
    background: var(--white);
    border: 1px solid var(--line);
    border-radius: var(--radius-md);
    padding: 16px 20px;
    box-shadow: 0 4px 16px rgba(21, 44, 78, 0.04);
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.score-number {
    font-size: 36px;
    font-weight: 850;
    color: var(--blue);
    line-height: 1.1;
    margin: 4px 0;
}

/* Stat Grid Cards */
.stat-box {
    background: #f8fafc;
    border: 1px solid #eef2f7;
    border-radius: 12px;
    padding: 14px 16px;
    transition: transform 0.15s ease;
}
.stat-box:hover {
    transform: translateY(-2px);
    background: #ffffff;
    border-color: var(--line);
    box-shadow: 0 6px 16px rgba(0,0,0,0.03);
}
.stat-label {
    font-size: 11px;
    color: var(--muted);
    font-weight: 600;
    margin-bottom: 4px;
}
.stat-value {
    font-size: 15px;
    font-weight: 750;
    color: var(--navy);
}

/* Pill Badges */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background-color: #EFF6FF;
    color: #1E40AF;
    padding: 6px 13px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.85rem;
    border: 1px solid #BFDBFE;
}
.badge-ready { background-color: #EFF6FF; color: #1E40AF; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 1.05rem; border: 1px solid #BFDBFE; }
.badge-flyable { background-color: #DEF7EC; color: #03543F; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 1.05rem; }
.badge-caution { background-color: #FEF08A; color: #713F12; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 1.05rem; }
.badge-prohibited { background-color: #FDE8E8; color: #9B1C1C; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 1.05rem; }

/* Table Styling */
.onestop-table {
    background-color: var(--white);
    border: 1px solid var(--line);
    border-radius: 10px;
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
    margin-bottom: 16px;
    overflow: hidden;
}
.onestop-table th {
    background-color: #F8FAFC;
    color: var(--navy);
    font-size: 0.88rem;
    font-weight: 700;
    padding: 10px 14px;
    border: 1px solid var(--line);
    text-align: left;
}
.onestop-table td {
    font-size: 0.86rem;
    padding: 10px 14px;
    border: 1px solid var(--line);
    color: #334155;
}

/* Summary Card Style for Tab 2 */
.summary-card {
    background: var(--white);
    border: 1px solid var(--line);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow);
    overflow: hidden;
}
.summary-head {
    padding: 18px 20px;
    border-bottom: 1px solid var(--line);
}
.summary-head h3 {
    margin: 0 0 4px;
    font-size: 15px;
    font-weight: 800;
    color: var(--navy);
}
.summary-head p {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
}
.sum-row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 11px 0;
    border-bottom: 1px solid #f0f3f8;
    font-size: 12px;
}
.sum-row:last-child { border-bottom: 0; }
.sum-row span { color: var(--muted); flex-shrink: 0; }
.sum-row strong { font-weight: 650; text-align: right; overflow-wrap: anywhere; color: var(--navy); }
.empty-val { color: #b2bdcc !important; font-weight: 400 !important; }

/* Floating AI Chat Popover */
div[data-testid="stPopover"] {
    position: fixed !important;
    bottom: 25px !important;
    right: 25px !important;
    width: 420px !important;
    max-width: 85vw !important;
    z-index: 999999 !important;
}
div[data-testid="stPopover"] > button {
    width: 100% !important;
    background-color: var(--navy) !important;
    color: white !important;
    font-weight: bold !important;
    font-size: 1.02rem !important;
    border-radius: 30px !important;
    padding: 12px 24px !important;
    box-shadow: 0 6px 20px rgba(16, 35, 63, 0.3) !important;
    border: none !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stPopover"] > button:hover {
    background-color: var(--navy2) !important;
    transform: translateY(-2px);
}
/* =========================================================
   Unified Chat Card & View 2 Polish (Matching media_1791941586639.png)
   ========================================================= */

/* Unified Single-Box Container for Chat */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.chat-card-marker),
div[class*="st-key-chat_main_card"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 20px !important;
    box-shadow: 0 4px 20px rgba(16, 35, 63, 0.05) !important;
    padding: 20px 22px 18px !important;
    overflow: hidden !important;
}

/* Remove internal borders from any nested containers inside the chat card */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.chat-card-marker) [data-testid="stVerticalBlockBorderWrapper"],
div[class*="st-key-chat_main_card"] [data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    background: transparent !important;
}

/* Header inside chat card */
.chat-card-header {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    padding-bottom: 14px !important;
    border-bottom: 1px solid #f1f5f9 !important;
    margin-bottom: 12px !important;
}
.chat-header-icon {
    width: 38px !important;
    height: 38px !important;
    background: #eff6ff !important;
    border-radius: 12px !important;
    display: grid !important;
    place-items: center !important;
    font-size: 20px !important;
}
.chat-header-title {
    font-size: 15.5px !important;
    font-weight: 800 !important;
    color: #10233F !important;
    line-height: 1.2 !important;
}
.chat-header-sub {
    font-size: 11.5px !important;
    color: #77849A !important;
    margin-top: 2px !important;
}
.chat-header-badge {
    font-size: 11.5px !important;
    font-weight: 700 !important;
    color: #2563EB !important;
    background: #eff6ff !important;
    padding: 5px 12px !important;
    border-radius: 20px !important;
}

/* Chat Input Form inside Chat Card */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.chat-card-marker) [data-testid="stForm"],
div[class*="st-key-chat_main_card"] [data-testid="stForm"] {
    margin-top: 10px !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.chat-card-marker) [data-testid="stForm"] div[data-testid="stTextInput"] input,
div[class*="st-key-chat_main_card"] [data-testid="stForm"] div[data-testid="stTextInput"] input {
    border: 1.5px solid #cbd5e1 !important;
    border-radius: 14px !important;
    padding: 11px 16px !important;
    font-size: 14px !important;
    height: 48px !important;
    background: #ffffff !important;
    color: #10233F !important;
    box-shadow: inset 0 1px 2px rgba(0,0,0,0.03) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.chat-card-marker) [data-testid="stForm"] div[data-testid="stTextInput"] input:focus,
div[class*="st-key-chat_main_card"] [data-testid="stForm"] div[data-testid="stTextInput"] input:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.chat-card-marker) [data-testid="stForm"] button[kind="primaryFormSubmit"],
div[class*="st-key-chat_main_card"] [data-testid="stForm"] button[kind="primaryFormSubmit"] {
    background: #2563EB !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 14px !important;
    height: 48px !important;
    font-size: 14px !important;
    font-weight: 750 !important;
    box-shadow: 0 3px 10px rgba(37, 99, 235, 0.25) !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.chat-card-marker) [data-testid="stForm"] button[kind="primaryFormSubmit"]:hover,
div[class*="st-key-chat_main_card"] [data-testid="stForm"] button[kind="primaryFormSubmit"]:hover {
    background: #1d4ed8 !important;
    transform: translateY(-1px) !important;
}

.chat-card-footer {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #94a3b8;
    margin-top: 6px;
    line-height: 1.4;
}

/* Chat Messages Bubble Polish */
[data-testid="stChatMessage"] {
    border-radius: 14px !important;
    padding: 12px 18px !important;
    margin-bottom: 10px !important;
    border: 1px solid #f1f5f9 !important;
    font-size: 13.5px !important;
    line-height: 1.65 !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    background: #f8fafc !important;
    border-color: #f1f5f9 !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #eff6ff !important;
    border-color: #dbeafe !important;
}

/* Summary Action Button 1: Dark Navy Button (신청서 미리보기) */
div[class*="st-key-v2_preview_link"] a {
    background: #10233F !important;
    color: #ffffff !important;
    border: 1px solid #10233F !important;
    border-radius: 12px !important;
    padding: 12px 16px !important;
    font-size: 14px !important;
    font-weight: 750 !important;
    text-align: center !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    text-decoration: none !important;
    box-shadow: 0 4px 14px rgba(16, 35, 63, 0.2) !important;
    transition: all 0.2s ease !important;
    margin-bottom: 4px !important;
}
div[class*="st-key-v2_preview_link"] a:hover {
    background: #18365b !important;
    border-color: #18365b !important;
    color: #ffffff !important;
    transform: translateY(-1px) !important;
}

/* Summary Action Button 2: White Download Button (신청서 텍스트 내려받기) */
div[class*="st-key-v2_download_btn"] button {
    background: #ffffff !important;
    color: #10233F !important;
    border: 1.5px solid #cbd5e1 !important;
    border-radius: 12px !important;
    padding: 11px 16px !important;
    font-size: 13.5px !important;
    font-weight: 700 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
    transition: all 0.2s ease !important;
    margin-bottom: 4px !important;
}
div[class*="st-key-v2_download_btn"] button:hover {
    background: #f8fafc !important;
    border-color: #94a3b8 !important;
    color: #0f172a !important;
}

/* Summary Action Button 3: White Save Button (💾 현재 대화 저장소에 보관) */
div[class*="st-key-v2_save_chat_btn"] button {
    background: #ffffff !important;
    color: #10233F !important;
    border: 1.5px solid #cbd5e1 !important;
    border-radius: 12px !important;
    padding: 11px 16px !important;
    font-size: 13.5px !important;
    font-weight: 700 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
    transition: all 0.2s ease !important;
}
div[class*="st-key-v2_save_chat_btn"] button:hover {
    background: #f8fafc !important;
    border-color: #94a3b8 !important;
    color: #0f172a !important;
}

/* History Clear Button (비우기) */
div[class*="st-key-v2_clear_hist_btn"] button {
    background: transparent !important;
    border: none !important;
    color: #ef4444 !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    padding: 2px 6px !important;
    min-height: auto !important;
    height: auto !important;
    text-align: right !important;
    justify-content: flex-end !important;
    box-shadow: none !important;
}
div[class*="st-key-v2_clear_hist_btn"] button:hover {
    color: #dc2626 !important;
    background: #fef2f2 !important;
    border-radius: 6px !important;
}

/* Individual History Delete Button (선택적 개별 삭제) */
div[class*="st-key-v2_del_hist_"] button {
    background: #fff1f2 !important;
    color: #e11d48 !important;
    border: 1px solid #fecdd3 !important;
    border-radius: 10px !important;
    padding: 8px 12px !important;
    font-size: 12.5px !important;
    font-weight: 700 !important;
    transition: all 0.2s ease !important;
}
div[class*="st-key-v2_del_hist_"] button:hover {
    background: #ffe4e6 !important;
    border-color: #fda4af !important;
    color: #be123c !important;
    transform: translateY(-1px) !important;
}

/* Quick Recommendation Pills in Chat Card */
div[class*="st-key-quick_pill_"] button {
    background: #f1f5f9 !important;
    color: #1e3a5f !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 20px !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    padding: 3px 6px !important;
    min-height: 28px !important;
    height: 28px !important;
    transition: all 0.2s ease !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}
div[class*="st-key-quick_pill_"] button:hover {
    background: #e2e8f0 !important;
    border-color: #3b82f6 !important;
    color: #1d4ed8 !important;
}

/* History Batch Delete Button (선택 항목 일괄 삭제) */
div[class*="st-key-v2_del_multi_btn"] button {
    background: #e11d48 !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    font-size: 12.5px !important;
    font-weight: 700 !important;
    padding: 8px 14px !important;
    box-shadow: 0 2px 6px rgba(225, 29, 72, 0.2) !important;
    transition: all 0.2s ease !important;
}
div[class*="st-key-v2_del_multi_btn"] button:hover {
    background: #be123c !important;
}

/* =========================================================
   ChatGPT / Gemini Style Conversation Drawer & Hover Delete
   ========================================================= */

/* History Panel Outer Box (ChatGPT / Gemini style left sidebar) */
div[class*="st-key-chat_hist_panel"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 18px !important;
    box-shadow: 0 4px 20px rgba(16, 35, 63, 0.05) !important;
    padding: 16px 14px 14px !important;
    overflow: hidden !important;
}
div[class*="st-key-chat_hist_panel"] [data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    background: transparent !important;
}

/* History Panel Header */
.hist-panel-header {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    padding-bottom: 10px !important;
    border-bottom: 1px solid #f1f5f9 !important;
    margin-bottom: 12px !important;
}

/* + 새 채팅 버튼 (ChatGPT / Gemini Style Primary Button) */
div[class*="st-key-v2_new_chat_btn"] button {
    background: #10233F !important;
    color: #ffffff !important;
    border: 1px solid #10233F !important;
    border-radius: 12px !important;
    padding: 10px 14px !important;
    font-size: 13.5px !important;
    font-weight: 750 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    box-shadow: 0 3px 10px rgba(16, 35, 63, 0.15) !important;
    transition: all 0.2s ease !important;
    margin-bottom: 10px !important;
}
div[class*="st-key-v2_new_chat_btn"] button:hover {
    background: #1d4ed8 !important;
    border-color: #1d4ed8 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 5px 14px rgba(29, 78, 216, 0.25) !important;
}

/* History Item Row Container */
div[class*="st-key-hist_row_"] {
    position: relative !important;
    border-radius: 10px !important;
    margin-bottom: 4px !important;
    transition: background 0.18s ease !important;
    padding: 2px 4px !important;
    border: 1px solid transparent !important;
}
div[class*="st-key-hist_row_"]:hover {
    background: #f1f5f9 !important;
    border-color: #e2e8f0 !important;
}

/* History Item Title Button */
div[class*="st-key-hist_load_"] button {
    background: transparent !important;
    border: none !important;
    color: #1e293b !important;
    font-size: 12.5px !important;
    font-weight: 600 !important;
    text-align: left !important;
    justify-content: flex-start !important;
    padding: 8px 6px !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    box-shadow: none !important;
    transition: color 0.15s ease !important;
}
div[class*="st-key-hist_load_"] button:hover {
    color: #2563eb !important;
    background: transparent !important;
}

/* Hover Delete Button on Right: Hidden normally, visible on hover! */
div[class*="st-key-hist_del_"] button {
    opacity: 0 !important;
    pointer-events: none !important;
    background: transparent !important;
    border: none !important;
    color: #94a3b8 !important;
    font-size: 13px !important;
    padding: 6px 4px !important;
    min-height: auto !important;
    height: auto !important;
    box-shadow: none !important;
    transition: all 0.2s ease !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
/* When hovering over the row, reveal the delete button! */
div[class*="st-key-hist_row_"]:hover div[class*="st-key-hist_del_"] button,
div[class*="st-key-hist_del_"] button:focus {
    opacity: 1 !important;
    pointer-events: auto !important;
}
div[class*="st-key-hist_del_"] button:hover {
    color: #ef4444 !important;
    background: #fee2e2 !important;
    border-radius: 6px !important;
    transform: scale(1.1) !important;
}

/* Clear all button at bottom of history panel */
div[class*="st-key-v2_clear_all_hist_btn"] button {
    background: transparent !important;
    border: none !important;
    color: #94a3b8 !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    padding: 4px 6px !important;
    box-shadow: none !important;
    text-align: center !important;
    justify-content: center !important;
    transition: color 0.2s ease !important;
}
div[class*="st-key-v2_clear_all_hist_btn"] button:hover {
    color: #ef4444 !important;
    background: #fef2f2 !important;
    border-radius: 6px !important;
}

/* Dark Navy Empty State Card for History */
.hist-empty-card {
    background: #10233F;
    color: #94a3b8;
    border-radius: 12px;
    padding: 16px 18px;
    font-size: 12px;
    line-height: 1.5;
    margin-top: 8px;
    border: 1px solid #1e3a5f;
}

/* =========================================================
   Cinematography Shooting Assistant Styles (View 3)
   ========================================================= */
.cinema-card {
    background: #ffffff;
    border: 1px solid var(--line);
    border-radius: var(--radius-md);
    padding: 18px 20px;
    box-shadow: 0 4px 16px rgba(16, 35, 63, 0.04);
    margin-bottom: 16px;
}
.solar-timeline-wrap {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: linear-gradient(90deg, #14243b 0%, #294368 25%, #e07a3f 65%, #c2410c 85%, #0f172a 100%);
    border-radius: 12px;
    padding: 14px 18px;
    margin: 12px 0 16px;
    color: white;
    box-shadow: 0 4px 14px rgba(0,0,0,0.12);
}
.solar-node {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
}
.solar-node-time {
    font-size: 13.5px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.2px;
}
.solar-node-label {
    font-size: 10.5px;
    color: #e2e8f0;
    margin-top: 3px;
    font-weight: 600;
}
.solar-highlight {
    background: rgba(255, 255, 255, 0.22);
    border: 1.5px solid #fbbf24;
    border-radius: 8px;
    padding: 5px 10px;
    box-shadow: 0 2px 8px rgba(251, 191, 36, 0.3);
}
div[class*="st-key-cinema_pill_"] button {
    background: #f8fafc !important;
    color: #1e3a5f !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 20px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    padding: 6px 14px !important;
    transition: all 0.2s ease !important;
    white-space: nowrap !important;
}
div[class*="st-key-cinema_pill_"] button:hover {
    background: #eff6ff !important;
    border-color: #3b82f6 !important;
    color: #1d4ed8 !important;
    transform: translateY(-1px) !important;
}
div[class*="st-key-cinema_sync_btn"] button {
    background: linear-gradient(135deg, #10233F 0%, #1D4ED8 100%) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 14px !important;
    padding: 16px 24px !important;
    font-size: 16px !important;
    font-weight: 800 !important;
    box-shadow: 0 6px 20px rgba(29, 78, 216, 0.35) !important;
    width: 100% !important;
    transition: all 0.2s ease !important;
}
div[class*="st-key-cinema_sync_btn"] button:hover {
    background: linear-gradient(135deg, #0b172a 0%, #1e40af 100%) !important;
    box-shadow: 0 8px 24px rgba(29, 78, 216, 0.5) !important;
    transform: translateY(-2px) !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------
if "user_profile" not in st.session_state:
    st.session_state.user_profile = load_profile()

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {
            "role": "assistant",
            "content": "안녕하세요! 저는 스카이 커맨드 비행 도우미에요!\n궁금한 점이나 비행 계획 신청서 초안을 만드실 때 등의 목적으로 입력해주세요!"
        }
    ]

if "current_address" not in st.session_state:
    st.session_state.current_address = ""

if "flight_form_data" not in st.session_state:
    st.session_state.flight_form_data = {
        "location": "",
        "date": "",
        "time": "",
        "weight": "",
        "camera": "",
        "purpose": "",
        "altitude": ""
    }

if "chat_history_archive" not in st.session_state:
    st.session_state.chat_history_archive = []

if "cinema_query" not in st.session_state:
    st.session_state.cinema_query = ""

if "cinema_analysis" not in st.session_state:
    st.session_state.cinema_analysis = None

if "nav_radio" not in st.session_state:
    st.session_state.nav_radio = "◈ 1. 비행 적합성 분석"

# ---------------------------------------------------------
# Common Helper Functions (Chrome Extension Trigger & Chat Processor)
# ---------------------------------------------------------
def render_clean_html(html_str):
    clean = re.sub(r'^[ \t]+', '', html_str.strip(), flags=re.MULTILINE)
    st.markdown(clean, unsafe_allow_html=True)

def render_extension_trigger(flight_data):
    json_str = json.dumps(flight_data, ensure_ascii=False)
    encoded_data = urllib.parse.quote(json_str)
    html_code = f"""
    <div style="font-family: system-ui, -apple-system, sans-serif; margin-top: 10px;">
        <button id="ext-trigger-btn" onclick="triggerExtension()" style="
            background: linear-gradient(135deg, #10233F, #1D4ED8);
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 10px;
            font-size: 0.95rem;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(16, 35, 63, 0.25);
            width: 100%;
            transition: all 0.2s;
        ">
            🛸 드론원스톱 신청서 자동 입력 (Chrome Extension)
        </button>
        <div id="status-msg" style="margin-top: 8px; font-size: 0.85rem; color: #475569; font-weight: 500;"></div>
    </div>
    <script>
        function triggerExtension() {{
            const rawData = decodeURIComponent('{encoded_data}');
            const payload = JSON.parse(rawData);
            window.parent.postMessage({{
                type: 'SKY_COMMAND_FLIGHT_APPROVAL',
                payload: payload
            }}, '*');
            
            const btn = document.getElementById('ext-trigger-btn');
            const msg = document.getElementById('status-msg');
            btn.style.background = '#159B75';
            btn.innerText = '✅ Chrome Extension으로 데이터 전송 완료!';
            msg.innerHTML = '✨ Extension 팝업 또는 드론원스톱 신청 페이지를 열어 자동 입력을 진행하세요.';
        }}
    </script>
    """
    components.html(html_code, height=95)

def parse_korean_date(text, base=None):
    from datetime import date, timedelta
    if not base:
        base = date.today()
    t = text.strip()
    
    # 1. Direct standard date: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD
    m = re.search(r'(\d{4})[-./](\d{1,2})[-./](\d{1,2})', t)
    if m:
        y, mon, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            target = date(y, mon, d)
            return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
        except Exception:
            pass
            
    # 2. M월 D일
    m2 = re.search(r'(\d{1,2})월\s*(\d{1,2})일', t)
    if m2:
        mon, d = int(m2.group(1)), int(m2.group(2))
        try:
            target = date(base.year, mon, d)
            if target < base and (base - target).days > 60:
                target = date(base.year + 1, mon, d)
            return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
        except Exception:
            pass

    # 3. M.D format (e.g. 10.28, 11.15)
    m2_dot = re.search(r'\b(\d{1,2})[./](\d{1,2})\b', t)
    if m2_dot and not any(k in t for k in ["시", "분"]):
        mon, d = int(m2_dot.group(1)), int(m2_dot.group(2))
        if 1 <= mon <= 12 and 1 <= d <= 31:
            try:
                target = date(base.year, mon, d)
                return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
            except Exception:
                pass

    num_map = {'한': 1, '두': 2, '세': 3, '네': 4, '다섯': 5, '여섯': 6, '일곱': 7, '여덟': 8, '아홉': 9, '열': 10, '이': 2, '삼': 3, '사': 4}

    # 4. Weeks: N주 뒤, N주일 뒤, N주 후, 다음 주, 다다음 주
    m_week = re.search(r'(\d+|[한두세네])\s*주(?:일)?\s*(?:뒤|후)', t)
    if m_week:
        val = m_week.group(1)
        w = int(val) if val.isdigit() else num_map.get(val, 1)
        target = base + timedelta(days=w * 7)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    
    if "다다음주" in t or "다다음 주" in t:
        target = base + timedelta(days=14)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    elif "다음주" in t or "다음 주" in t:
        if "토요일" in t or "토" in t:
            days_ahead = 5 - base.weekday()
            if days_ahead <= 0: days_ahead += 7
            days_ahead += 7
            target = base + timedelta(days=days_ahead)
            return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
        elif "일요일" in t or ("일" in t and "주일" not in t):
            days_ahead = 6 - base.weekday()
            if days_ahead <= 0: days_ahead += 7
            days_ahead += 7
            target = base + timedelta(days=days_ahead)
            return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
        else:
            target = base + timedelta(days=7)
            return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"

    # 5. Months: N달 뒤, N달 후, N개월 뒤, N개월 후, 다음 달
    m_mon = re.search(r'(\d+|[한두세네])\s*(?:달|개월)\s*(?:뒤|후)', t)
    if m_mon:
        val = m_mon.group(1)
        m_cnt = int(val) if val.isdigit() else num_map.get(val, 1)
        target = base + timedelta(days=m_cnt * 30)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    if "다음달" in t or "다음 달" in t:
        target = base + timedelta(days=30)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"

    # 6. Days: N일 뒤, N일 후, 하루 뒤, 이틀 뒤, 사흘 뒤, 나흘 뒤
    m_day = re.search(r'(\d+)\s*일\s*(?:뒤|후)', t)
    if m_day:
        d_cnt = int(m_day.group(1))
        target = base + timedelta(days=d_cnt)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    
    if "하루 뒤" in t or "하루 후" in t or "하루뒤" in t:
        target = base + timedelta(days=1)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    if "이틀 뒤" in t or "이틀 후" in t or "이틀뒤" in t:
        target = base + timedelta(days=2)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    if "사흘 뒤" in t or "사흘 후" in t or "사흘뒤" in t:
        target = base + timedelta(days=3)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    if "나흘 뒤" in t or "나흘 후" in t or "나흘뒤" in t:
        target = base + timedelta(days=4)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"

    # 7. Named relative days: 오늘, 내일, 모레, 글피, 이번 주말
    if "글피" in t:
        target = base + timedelta(days=3)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    if "모레" in t:
        target = base + timedelta(days=2)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    if "내일" in t:
        target = base + timedelta(days=1)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    if "오늘" in t:
        target = base
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"
    if "주말" in t:
        days_to_sat = 5 - base.weekday()
        if days_to_sat <= 0:
            days_to_sat += 7
        target = base + timedelta(days=days_to_sat)
        return f"{target.strftime('%Y-%m-%d')} ({target.month}월 {target.day}일)"

    return None

def round_to_nearest_10_minutes(dt):
    from datetime import timedelta
    m = dt.minute
    rounded_m = int(round(m / 10.0) * 10)
    if rounded_m == 60:
        return (dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    return dt.replace(minute=rounded_m, second=0, microsecond=0)

def parse_korean_time(text, base=None):
    from datetime import datetime, timedelta
    if not base:
        base = datetime.now()
    t = text.strip()

    num_map = {'한': 1, '두': 2, '세': 3, '네': 4, '다섯': 5, '이': 2, '삼': 3, '사': 4}

    # 1. Relative hours: "1시간 뒤", "약 1시간 뒤", "한 시간 반 뒤", "2시간 후"
    m_hour = re.search(r'(?:약|대략|한)?\s*(\d+|[한두세네])\s*시간(?:\s*(반|30분))?\s*(?:뒤|후|뒤에|후에)?', t)
    if m_hour and any(k in t for k in ["뒤", "후", "대략", "약"]):
        val = m_hour.group(1)
        h = int(val) if val.isdigit() else num_map.get(val, 1)
        extra_min = 30 if m_hour.group(2) else 0
        target = base + timedelta(hours=h, minutes=extra_min)
        target = round_to_nearest_10_minutes(target)
        return target.strftime('%H:%M')

    # 2. Relative minutes: "30분 뒤", "40분 후", "약 20분 뒤"
    m_min = re.search(r'(?:약|대략)?\s*(\d+)\s*분\s*(?:뒤|후|뒤에|후에)', t)
    if m_min:
        m_val = int(m_min.group(1))
        target = base + timedelta(minutes=m_val)
        target = round_to_nearest_10_minutes(target)
        return target.strftime('%H:%M')

    # 3. "지금", "곧", "바로"
    if any(k in t for k in ["지금", "곧", "바로"]):
        target = round_to_nearest_10_minutes(base)
        return target.strftime('%H:%M')

    # 4. Range: "14:00 ~ 16:00" or "오후 2시 ~ 오후 4시" or "오후 2시~4시" or "10시~12시"
    range_m = re.search(r'(?:(오전|오후)\s*)?(\d{1,2})(?::(\d{2})|시)?\s*(?:~|-|부터)\s*(?:(오전|오후)\s*)?(\d{1,2})(?::(\d{2})|시)?', t)
    if range_m and any(k in t for k in ["~", "-", "부터"]):
        ampm1, h1, m1, ampm2, h2, m2 = range_m.groups()
        h1 = int(h1)
        m1 = int(m1) if m1 else 0
        h2 = int(h2)
        m2 = int(m2) if m2 else 0

        if ampm1 == "오후" and h1 < 12:
            h1 += 12
        elif ampm1 == "오전" and h1 == 12:
            h1 = 0

        if ampm2 == "오후" and h2 < 12:
            h2 += 12
        elif ampm2 == "오전" and h2 == 12:
            h2 = 0
        elif not ampm2 and ampm1 == "오후" and h2 <= 12:
            h2 += 12

        return f"{h1:02d}:{m1:02d} ~ {h2:02d}:{m2:02d}"

    # 5. Direct single HH:MM
    direct_m = re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\b', t)
    if direct_m:
        return f"{int(direct_m.group(1)):02d}:{int(direct_m.group(2)):02d}"

    # 6. Single Korean time: "오후 2시", "오전 10시 30분", "오후 10시", "14시"
    single_m = re.search(r'(?:(오전|오후)\s*)?(\d{1,2})시(?:\s*(\d{1,2})분)?', t)
    if single_m:
        ampm, h, mn = single_m.groups()
        h = int(h)
        mn = int(mn) if mn else 0
        if ampm == "오후" and h < 12:
            h += 12
        elif ampm == "오전" and h == 12:
            h = 0
        return f"{h:02d}:{mn:02d}"

    # 7. Common keywords
    if "일몰" in t or "골든아워" in t:
        return "17:30 ~ 18:30"
    if "점심" in t:
        return "12:00 ~ 13:00"

    return None

def process_chat_message(prompt, address_query, zone_name):
    import re
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    context_data = {
        "loc_name": address_query,
        "airspace_status": zone_name
    }
    
    # 1. Emergency, Safety, Repairs or Legal questions
    is_emergency_or_info = any(k in prompt for k in ["사고", "추락", "인명", "과태료", "벌금", "처벌", "고장", "수리", "비행 중지", "멈추는", "rth"])
    if is_emergency_or_info:
        bot_reply = get_ai_response(
            prompt, 
            context_info=context_data, 
            conversation_history=st.session_state.chat_messages
        )
        st.session_state.chat_messages.append({"role": "assistant", "content": bot_reply})
        return

    # 2. Flight Application Form Data Processing
    if "flight_form_data" not in st.session_state:
        st.session_state.flight_form_data = {
            "location": "", "date": "", "time": "", "weight": "", "camera": "", "purpose": "", "altitude": ""
        }
    form_data = st.session_state.flight_form_data
    matched_fields = set()

    last_diag = st.session_state.get("last_diagnosed_location") or address_query or ""
    last_diag = last_diag.strip()
    if last_diag in ["-------", "------"]:
        last_diag = ""

    # Check if user is confirming a previously queried location
    if st.session_state.get("awaiting_location_confirmation"):
        target_loc = st.session_state.pop("awaiting_location_confirmation")
        if any(k in prompt for k in ["네", "응", "어", "맞아", "맞아요", "그래", "그렇습니다", "좋아", "맞는", target_loc[:3]]):
            form_data["location"] = target_loc
            st.session_state.current_address = target_loc
            bot_reply = (
                f"네, 비행 장소를 **'{target_loc}'**(으)로 등록했습니다! 📍 (정보 수집 14% 완료)\n\n"
                f"다음으로, **드론을 언제 날리실 예정인가요?**\n"
                f"비행 일자를 알려주세요. (예: 2026-10-25 또는 이번 주말)"
            )
            st.session_state.chat_messages.append({"role": "assistant", "content": bot_reply})
            return
        elif any(k in prompt for k in ["아니", "다른", "틀려"]):
            bot_reply = (
                f"알겠습니다! 그렇다면 드론을 날리실 **희망 장소나 주소**를 구체적으로 말씀해 주세요. 😊"
            )
            st.session_state.chat_messages.append({"role": "assistant", "content": bot_reply})
            return

    # Check if user asks about application procedure, laws, regulations or general flight inquiry when location is not yet set
    is_asking_procedure = any(k in prompt for k in ["신청서", "신청", "작성", "어떻게", "법률", "규정", "승인", "절차", "방법", "허가", "자격증", "가능해", "날려도", "준비", "궁금"])
    if is_asking_procedure and (not form_data.get("location") or form_data.get("location") in ["------", "-------"]):
        if last_diag:
            st.session_state.awaiting_location_confirmation = last_diag
            bot_reply = (
                f"드론 비행 승인 신청은 국토교통부 **드론원스톱(drone.onestop.go.kr)** 시스템을 통해 사전에 비행 승인을 받는 공적 절차입니다. 비행 장소, 일시, 고도, 기체 제원 등 7가지 필수 정보를 등록하여 승인을 받으실 수 있어요.\n\n"
                f"제가 대화형으로 신청서 초안 작성을 처음부터 끝까지 도와드릴게요! 😊\n\n"
                f"**혹시 조금 전 비행 적합성 분석에서 확인하신 '{last_diag}'에서 날리고 싶으신가요?**\n\n"
                f"(맞으시다면 **'네'** 또는 **'응'**이라고 말씀해 주시면 바로 '{last_diag}'(으)로 등록하고 다음 단계로 진행해 드릴게요!)"
            )
            st.session_state.chat_messages.append({"role": "assistant", "content": bot_reply})
            return
        else:
            bot_reply = (
                f"드론 비행 승인 신청은 국토교통부 **드론원스톱(drone.onestop.go.kr)** 시스템을 통해 사전에 비행 승인을 받는 공적 절차입니다. 제가 대화형으로 신청서 작성을 도와드릴 수 있어요! 😊\n\n"
                f"먼저, **드론을 어디에서 날리실 예정인가요?** 비행 희망 장소나 주소를 알려주세요."
            )
            st.session_state.chat_messages.append({"role": "assistant", "content": bot_reply})
            return

    # Altitude
    alt_m = re.search(r'(\d+)\s*(?:m|미터)|고도\s*(\d+)', prompt, re.I)
    if alt_m and any(k in prompt for k in ["m", "고도", "미터", "높이"]):
        val = f"{alt_m.group(1) or alt_m.group(2)}m"
        form_data["altitude"] = val
        matched_fields.add("altitude")

    # Date (정밀 날짜 파싱 및 상대 날짜 '2주 뒤', '13일 뒤', '한 달 뒤' 자동 계산)
    parsed_date = parse_korean_date(prompt)
    if parsed_date:
        form_data["date"] = parsed_date
        matched_fields.add("date")

    # Time (정밀 시간 파싱 및 상대 시간 '1시간 뒤', '30분 뒤' 자동 계산)
    parsed_time = parse_korean_time(prompt)
    if parsed_time:
        form_data["time"] = parsed_time
        matched_fields.add("time")
    else:
        time_m = re.search(r'(\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2})|(\d{1,2}:\d{2})|(\d{1,2}시\s*~\s*\d{1,2}시)|(\d{1,2}시)', prompt)
        if time_m or any(k in prompt for k in ["오전", "오후", "골든아워", "일몰", "점심", "낮"]):
            form_data["time"] = prompt
            matched_fields.add("time")

    # Drone Weight
    weight_m = re.search(r'(\d+)\s*(?:g|kg)|250g\s*미만|초경량|mini|air|mavic|매빅', prompt, re.I)
    if weight_m and any(k in prompt for k in ["g", "kg", "중량", "무게", "드론", "초경량", "mini", "air", "mavic"]):
        form_data["weight"] = prompt
        matched_fields.add("weight")

    # Camera
    if any(k in prompt for k in ["카메라", "촬영", "영상"]):
        if any(k in prompt for k in ["없음", "안 함", "안함", "아니오", "미탑재"]):
            form_data["camera"] = "카메라 없음 (촬영 안 함)"
        else:
            form_data["camera"] = "카메라 있음 (촬영 예정)"
        matched_fields.add("camera")

    # Purpose
    if any(k in prompt for k in ["목적", "레저", "취미", "풍경", "경관", "프로젝트", "캡스톤", "점검", "방제", "연습", "교육", "수업"]):
        form_data["purpose"] = prompt
        matched_fields.add("purpose")

    # Location (비행 장소)
    if not matched_fields or any(k in prompt for k in ["공원", "학교", "중학교", "초등학교", "고등학교", "대학교", "역", "시", "구", "동", "리", "로", "길", "타워", "해수욕장", "경기장", "센터", "여의도", "김천", "율곡", "부산", "해운대", "서울"]):
        if not form_data.get("location"):
            form_data["location"] = prompt
            st.session_state.current_address = prompt
            matched_fields.add("location")

    # Sequential fallback for single answers
    field_order = ["location", "date", "time", "weight", "camera", "purpose", "altitude"]
    if not matched_fields:
        for f_key in field_order:
            if not form_data.get(f_key):
                if f_key == "date":
                    p_date = parse_korean_date(prompt)
                    form_data[f_key] = p_date if p_date else prompt
                elif f_key == "time":
                    p_time = parse_korean_time(prompt)
                    form_data[f_key] = p_time if p_time else prompt
                elif f_key == "location":
                    form_data[f_key] = prompt
                    st.session_state.current_address = prompt
                else:
                    form_data[f_key] = prompt
                matched_fields.add(f_key)
                break

    unfilled = [k for k in field_order if not form_data.get(k)]
    if not unfilled:
        # All 7 completed!
        bot_reply = (
            f"🎉 **비행 신청에 필요한 7가지 정보 수집이 모두 완료되었습니다!**\n\n"
            f"• **비행 장소**: `{form_data['location']}`\n"
            f"• **비행 날짜**: `{form_data['date']}`\n"
            f"• **비행 시간**: `{form_data['time']}`\n"
            f"• **드론 중량**: `{form_data['weight']}`\n"
            f"• **카메라 탑재**: `{form_data['camera']}`\n"
            f"• **비행 목적**: `{form_data['purpose']}`\n"
            f"• **예정 고도**: `{form_data['altitude']}`\n\n"
            f"👉 우측의 **'신청서 미리보기 (새 탭) ↗'** 버튼 또는 아래의 Chrome Extension 자동 입력을 진행하세요!"
        )
        alt_int = 120
        try:
            alt_int = int(re.sub(r'[^0-9]', '', form_data['altitude']))
        except Exception:
            pass

        st.session_state["latest_flight_approval"] = {
            "type": "flight_approval",
            "status": "ready",
            "period": {
                "startDate": form_data['date'].split(' ')[0],
                "endDate": form_data['date'].split(' ')[0]
            },
            "purpose": form_data['purpose'],
            "flightMethod": "시계비행",
            "area": {
                "address": form_data['location'],
                "latitude": 37.5284,
                "longitude": 126.9328,
                "radius": 1000,
                "altitude": alt_int
            },
            "drone": {
                "model": "초경량 드론",
                "weight": form_data['weight'],
                "hasCamera": "없음" not in form_data['camera']
            },
            "time": form_data['time'],
            "notice": "주민 및 주변 안전 확보 후 비행 진행"
        }
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": bot_reply,
            "approval_data": st.session_state["latest_flight_approval"]
        })
    else:
        next_f = unfilled[0]
        last_k = list(matched_fields)[0] if matched_fields else None
        confirm_text = ""
        labels = {"location": "비행 장소", "date": "비행 날짜", "time": "비행 시간", "weight": "드론 중량", "camera": "카메라 탑재", "purpose": "비행 목적", "altitude": "예정 고도"}
        if last_k:
            confirm_text = f"**{labels.get(last_k, '정보')}** 확인했어요: `{form_data[last_k]}` ✨\n\n"

        questions = {
            "location": "드론을 어디에서 날릴 예정인가요? 구체적인 비행 장소나 주소를 알려주세요. (예: 서울 여의도 한강공원)",
            "date": "비행할 날짜를 알려주세요. (예: 2026-10-20 또는 이번 주말)",
            "time": "비행할 시간대를 알려주세요. (예: 14:00~16:00 또는 오후 2시)",
            "weight": "드론 기체 중량 또는 모델명을 알려주세요. (예: DJI Mini 4 Pro, 249g)",
            "camera": "드론에 카메라가 탑재되어 항공촬영을 진행하시나요? (예: 카메라 있음 · 촬영 예정 / 카메라 없음)",
            "purpose": "이번 비행의 주요 목적은 무엇인가요? (예: 풍경 촬영, 캡스톤 프로젝트, 조종 연습)",
            "altitude": "마지막으로 지면으로부터의 예정 비행 고도(m)를 알려주세요. (예: 120m 또는 150m)"
        }
        bot_reply = f"{confirm_text}{questions[next_f]}"
        st.session_state.chat_messages.append({"role": "assistant", "content": bot_reply})

# ---------------------------------------------------------
# ---------------------------------------------------------
# Left Vertical Sidebar Navigation (Matching media_1791917834377.png)
# ---------------------------------------------------------
st.sidebar.markdown("""
<div class="sidebar-brand">
    <div class="sidebar-brand-icon">✦</div>
    <div class="sidebar-brand-text">
        <div class="sidebar-brand-title">스카이 커맨드</div>
        <div class="sidebar-brand-sub">드론 비행 안전 도우미</div>
    </div>
</div>
<div class="sidebar-menu-label">메뉴</div>
""", unsafe_allow_html=True)

def reset_chat_messages():
    st.session_state.chat_messages = [
        {
            "role": "assistant",
            "content": "안녕하세요! 저는 스카이 커맨드 비행 도우미에요!\n궁금한 점이나 비행 계획 신청서 초안을 만드실 때 등의 목적으로 입력해주세요!"
        }
    ]
    st.session_state.flight_form_data = {
        "location": "",
        "date": "",
        "time": "",
        "weight": "",
        "camera": "",
        "purpose": "",
        "altitude": ""
    }
    st.session_state.latest_flight_approval = None

def start_new_chat():
    user_msgs = [m for m in st.session_state.chat_messages if m.get("role") == "user"]
    if user_msgs:
        cur_loc = st.session_state.current_address if st.session_state.current_address and st.session_state.current_address not in ["-------", "------"] else user_msgs[0]["content"][:16]
        new_hist = {
            "title": f"{cur_loc} ({date.today().strftime('%m/%d')})",
            "date": str(date.today()),
            "location": cur_loc,
            "messages": list(st.session_state.chat_messages),
            "form_data": dict(st.session_state.get("flight_form_data", {}))
        }
        if not (st.session_state.chat_history_archive and st.session_state.chat_history_archive[0].get("messages") == st.session_state.chat_messages):
            st.session_state.chat_history_archive.insert(0, new_hist)

    reset_chat_messages()
    st.session_state.current_address = ""
    st.session_state.latest_flight_approval = None

if st.session_state.get("nav_target"):
    st.session_state["nav_radio"] = st.session_state.pop("nav_target")

menu_options = [
    "◈ 1. 비행 적합성 분석",
    "◉ 2. 대화로 신청하기",
    "📷 3. 촬영 도우미",
    "⚙️ 사용자 프로필 설정"
]

selected_menu = st.sidebar.radio(
    "메뉴 선택",
    options=menu_options,
    label_visibility="collapsed",
    key="nav_radio"
)

# 신청서 미리보기 (새 탭 생성)
st.sidebar.link_button(
    "▤ 신청서 미리보기 (새 탭) ↗",
    "https://drone.onestop.go.kr/civilappeal/flight/register",
    use_container_width=True
)

st.sidebar.markdown("""
<div class="sidebar-note">
    <strong>✈ 실시간 관제 연동</strong>
    국토교통부 공역 데이터와 실시간 기상을 바탕으로 비행 적합성을 종합 분석하고 신청서 작성을 보조합니다.
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Main Topbar (Dynamic Breadcrumb based on Selected Menu)
# ---------------------------------------------------------
if selected_menu == "◈ 1. 비행 적합성 분석":
    crumb_text = "비행 적합성 분석"
    top_badge_text = "실시간 공역 관제 가동 중"
elif selected_menu == "◉ 2. 대화로 신청하기":
    crumb_text = "대화로 신청하기"
    top_badge_text = "대화형 신청 도우미"
elif selected_menu == "📷 3. 촬영 도우미":
    crumb_text = "촬영 도우미"
    top_badge_text = "AI 시네마틱 비행 플래너"
else:
    crumb_text = "사용자 프로필 설정"
    top_badge_text = "프로필 & 기체 관리"

st.markdown(f"""
<div class="topbar">
    <div style="display:flex; align-items:center; gap:14px;">
        <button class="topbar-toggle-btn" title="사이드바 메뉴 탭 열기/접기">
            ☰ <span style="font-size:12px; font-weight:700;">메뉴 탭 토글</span>
        </button>
        <div class="crumb" style="font-size:13.5px; color:var(--muted);">
            드론 비행 도우미　/　<strong style="color:var(--text); font-weight:700;">{crumb_text}</strong>
        </div>
    </div>
    <div class="topbar-status">
        <span class="status-dot"></span>{top_badge_text}
    </div>
</div>
""", unsafe_allow_html=True)

components.html("""
<script>
(function() {
    var doc = window.parent.document;
    if (!doc) return;
    if (window.parent.__skyToggleInit) return;
    window.parent.__skyToggleInit = true;
    
    doc.addEventListener('click', function(e) {
        var btn = e.target.closest('.topbar-toggle-btn');
        if (btn) {
            e.preventDefault();
            e.stopPropagation();
            var collapseBtn = doc.querySelector('[data-testid="stSidebarCollapseButton"] button');
            var expandBtn = doc.querySelector('[data-testid="collapsedControl"] button');
            var sidebar = doc.querySelector('[data-testid="stSidebar"]');
            var isCollapsed = !sidebar || sidebar.getAttribute('aria-expanded') === 'false';
            if (isCollapsed && expandBtn) {
                expandBtn.click();
            } else if (!isCollapsed && collapseBtn) {
                collapseBtn.click();
            } else if (collapseBtn) {
                collapseBtn.click();
            } else if (expandBtn) {
                expandBtn.click();
            }
        }
    }, true);
})();
</script>
""", height=0)

# =========================================================
# Shared Flight Context & Suitability Pre-computation
# =========================================================
address_query = st.session_state.current_address.strip()
is_empty_address = not address_query or address_query == "-------"

if is_empty_address:
    display_address_text = "-------"
    display_loc_name = "-------"
    lat_val, lon_val = 36.5, 127.8  # Korea National Center Overview
    map_zoom = 7
else:
    display_address_text = address_query
    lat_val, lon_val, display_loc_name = geocode_address(address_query)
    map_zoom = 14

# Standard Flight Defaults
flight_date = date.today()
flight_time = time(14, 0)
drone_weight = st.session_state.user_profile.get("drone_weight_g", 249)
has_camera = True
purpose = "경관 촬영 및 취미 비행"
max_altitude = 120

if not is_empty_address:
    airspace_res = check_airspace(lat_val, lon_val, address_query)
    weather_res = get_weather(lat_val, lon_val)
    
    drone_info = {
        "weight_g": drone_weight,
        "has_camera": has_camera,
        "purpose": purpose,
        "max_altitude": max_altitude
    }
    ai_eval = evaluate_flight_suitability(drone_info, airspace_res, weather_res, address_query)
else:
    airspace_res = {
        "zone_name": "-------",
        "approval_required": False,
        "official_contacts": {"flight_contact": "-------", "special_contact": "-------", "photo_contact": "-------"}
    }
    weather_res = {
        "weather_desc": "-------",
        "wind_speed": "-------",
        "wind_gust": "-------",
        "visibility_km": "-------",
        "rain": "-------"
    }
    ai_eval = {
        "score": "--",
        "status_code": "READY",
        "status_label": "비행 희망 장소를 검색해 주세요",
        "detailed_explanation": "상단 검색창에 드론 비행을 희망하는 장소를 입력해 주시면 실시간 공역, 기상 및 드론원스톱 신청 민원 서류 진단 결과가 즉시 표시됩니다.",
        "reasons": ["비행 희망 장소를 검색창에 입력해 주세요."],
        "required_documents": [],
        "legal_penalties": [
            {
                "regulation": "항공안전법 제161조 / 제166조 (미승인 비행)",
                "violation": "비행금지구역 / 관제권 내 사전 비행 승인 없이 드론을 비행한 경우",
                "fine_details": "1차 150만원 / 2차 225만원 / 3차 300만원 과태료 부과",
                "severity": "HIGH"
            },
            {
                "regulation": "군사기지 및 군사시설 보호법 제19조 (미승인 촬영)",
                "violation": "국방부 사전 촬영 허가 없이 군사시설, 보안 구역을 항공 촬영한 경우",
                "fine_details": "3년 이하의 징역 또는 3,000만원 이하의 벌금 (형사 처벌)",
                "severity": "CRITICAL"
            }
        ]
    }

flight_context = {
    "date_str": str(flight_date),
    "time_str": str(flight_time),
    "lat": lat_val,
    "lon": lon_val,
    "location_name": address_query,
    "weight_g": drone_weight,
    "purpose": purpose,
    "max_altitude": max_altitude,
    "airspace_name": airspace_res["zone_name"],
    "wind_speed": weather_res["wind_speed"],
    "weather_desc": weather_res["weather_desc"]
}

flight_app_text = generate_flight_approval_text(st.session_state.user_profile, flight_context, ai_eval)
photo_permit_text = generate_photo_permit_text(st.session_state.user_profile, flight_context, ai_eval)

# =========================================================
# VIEW 1: 대시보드 (비행 적합성 진단)
# =========================================================
if selected_menu == "◈ 1. 비행 적합성 분석":
    # Hero Sub-banner
    st.markdown("""
    <div class="hero-box">
        <div>
            <div class="eyebrow">FLIGHT READINESS DASHBOARD</div>
            <h1 class="hero-title">실시간 비행 안전 관제 및 공역 진단</h1>
            <p class="hero-desc">비행 희망 장소를 검색하면 국토교통부 공역과 실시간 기상 데이터를 결합하여 비행 적합성을 1초 만에 종합 판정합니다.</p>
        </div>
        <div class="step-chip">관제 상태 <b>정상 연동</b></div>
    </div>
    """, unsafe_allow_html=True)

    # SKY COMMAND DASHBOARD GRID (Left Map ~55%, Right Diagnosis Box ~45%)
    col_left, col_right = st.columns([1.1, 0.9])

    # LEFT COLUMN: Address Search Bar + Interactive Map
    with col_left:
        top_search = st.text_input(
            "🔍 비행 희망 장소 주소 검색 (엔터를 누르시면 실시간 진단됩니다)", 
            value=st.session_state.current_address,
            placeholder="드론 비행을 희망하는 장소를 입력하세요 (예: 여의도 한강공원, 김천 율곡중학교)",
            key="top_address_input"
        )
        if top_search != st.session_state.current_address:
            st.session_state.current_address = top_search
            st.session_state.last_diagnosed_location = top_search
            st.rerun()
        elif top_search and "last_diagnosed_location" not in st.session_state:
            st.session_state.last_diagnosed_location = top_search

        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <strong style="color:var(--navy); font-size:14px;">🗺️ 비행구역 지도 관제화면 (<span style="color:var(--blue);">{display_address_text}</span>)</strong>
        </div>
        """, unsafe_allow_html=True)
        st.link_button("🌐 드론원스톱 공식 비행구역 지도 새 창에서 열기 (drone.onestop.go.kr)", "https://drone.onestop.go.kr/common/flightArea")

        m = folium.Map(location=[lat_val, lon_val], zoom_start=map_zoom)
        
        if not is_empty_address:
            folium.Marker(
                [lat_val, lon_val],
                popup=f"비행 희망 장소: {address_query}",
                tooltip=f"선택 지점 ({address_query})",
                icon=folium.Icon(color="blue", icon="plane", prefix="fa")
            ).add_to(m)
            
            # 1km radius safety diagnosis circle around selected address
            folium.Circle(
                location=[lat_val, lon_val],
                radius=1000,
                color="#2563EB",
                weight=2,
                fill=True,
                fill_color="#3B82F6",
                fill_opacity=0.15,
                popup=f"📍 {address_query} (반경 1km 비행 진단 구역)",
                tooltip="📍 반경 1km 비행 진단 구역"
            ).add_to(m)
            
            if airspace_res.get("matched_zones"):
                for z in airspace_res.get("matched_zones"):
                    zone_color = z.get("color", "#D97706")
                    folium.Circle(
                        location=[lat_val, lon_val],
                        radius=1000,
                        color=zone_color,
                        weight=3,
                        fill=True,
                        fill_color=zone_color,
                        fill_opacity=0.25,
                        popup=f"{z['name']} ({z['category']}) - 반경 1km 감지",
                        tooltip=f"{z['name']} (반경 1km)"
                    ).add_to(m)

        legend_box_html = """
        <div style="
            position: fixed; 
            bottom: 25px; left: 25px; width: 220px; 
            z-index:9999; font-size:11px; font-family: sans-serif;
            background-color: rgba(255, 255, 255, 0.95); 
            border:2px solid #94A3B8; border-radius: 8px;
            padding: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.15);
            ">
            <b style="font-size:12px; color:#0F172A;">🌐 드론원스톱 공식 범례</b><br>
            <div style="margin-top:5px; line-height: 1.6;">
              <span style="background:#DC2626; width:10px; height:10px; display:inline-block; border-radius:50%;"></span> <b>🔴 P: 비행금지구역</b><br>
              <span style="background:#EA580C; width:10px; height:10px; display:inline-block; border-radius:50%;"></span> <b>🟠 R: 비행제한구역</b><br>
              <span style="background:#D97706; width:10px; height:10px; display:inline-block; border-radius:50%;"></span> <b>🟡 CTR: 공항 관제권</b><br>
              <span style="background:#9333EA; width:10px; height:10px; display:inline-block; border-radius:50%;"></span> <b>🟣 MOA: 군작전구역</b><br>
              <span style="background:#059669; width:10px; height:10px; display:inline-block; border-radius:50%;"></span> <b>🟢 UA: 드론전용공역</b><br>
              <span style="background:#0284C7; width:10px; height:10px; display:inline-block; border-radius:50%;"></span> <b>🔵 G: 비관제공역</b>
            </div>
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_box_html))
            
        st_folium(m, width="100%", height=550)

        st.markdown(f"""
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; margin-bottom:8px;">
            <span class="status-pill">✔ 기상 상태: {weather_res['weather_desc']}</span>
            <span class="status-pill">✔ 관제 공역: {airspace_res['zone_name'].split('(')[0]}</span>
            <span class="status-pill">✔ 등록 기체: {drone_weight}g</span>
        </div>
        """, unsafe_allow_html=True)

    # RIGHT COLUMN: AI Flight Diagnosis Announcement + Rationale + Documents
    with col_right:
        status_code = ai_eval["status_code"]
        score_val = ai_eval["score"]

        badge_class = (
            "badge-ready" if status_code == "READY" else
            "badge-flyable" if status_code == "FLYABLE" else
            "badge-caution" if status_code == "CAUTION" else "badge-prohibited"
        )

        st.markdown(f"""
        <div class="analysis-panel" style="margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-size:12px; color:var(--muted); font-weight:700;">종합 안전 진단 상태</span>
                <span class="{badge_class}">{ai_eval['status_label']}</span>
            </div>
            <div style="display:flex; align-items:baseline; gap:8px;">
                <span style="font-size:38px; font-weight:850; color:var(--blue);">{score_val}</span>
                <span style="font-size:16px; color:var(--muted); font-weight:600;">/ 100점</span>
            </div>
            <div style="font-size:11px; color:var(--muted); margin-top:4px;">
                기본 100점 만점 기준 · 공역 규제 및 실시간 기상 감점 반영
            </div>
        </div>
        """, unsafe_allow_html=True)

        # AI Detailed Callout Box
        detailed_box_html = f"""
        <div class="analysis-panel" style="border-left: 5px solid var(--blue); background: #fbfdff;">
            <div class="analysis-section-title">
                💬 AI 상세 진단 소견 & 안전 가이드
            </div>
            <div style="font-size: 13px; line-height: 1.7; color: #25354d;">
                {ai_eval['detailed_explanation'].replace('\n', '<br>')}
            </div>
        </div>
        """
        st.markdown(detailed_box_html, unsafe_allow_html=True)

        # AI Rationale Box
        reasons_list_html = "".join([f"<li style='margin-bottom:4px;'>{r}</li>" for r in ai_eval["reasons"]])
        st.markdown(
            f'<div class="analysis-panel">'
            f'<div class="analysis-section-title">🔍 AI 세부 판단 사유</div>'
            f'<ul style="margin:0; padding-left:20px; font-size:13px; color:#334155; line-height:1.7;">{reasons_list_html}</ul>'
            f'</div>',
            unsafe_allow_html=True
        )
            
        if ai_eval["required_documents"]:
            docs_list_html = "".join([f"<li style='margin-bottom:6px;'><b>{d['name']}</b> ({d['authority']}) — <span style='color:var(--muted);'>{d['desc']}</span></li>" for d in ai_eval["required_documents"]])
            st.markdown(
                f'<div class="analysis-panel" style="background:#fffaf0; border-color:#f2dfb6;">'
                f'<div class="analysis-section-title" style="color:#b45309;">📋 작성 필요 민원 서류</div>'
                f'<ul style="margin:0; padding-left:20px; font-size:12px; color:#451a03; line-height:1.7;">{docs_list_html}</ul>'
                f'</div>',
                unsafe_allow_html=True
            )

    # 4-COLUMN DASHBOARD ROW (Upgraded to Modern Stat Grid Cards)
    st.divider()
    st.markdown("<h3 style='font-size:17px; font-weight:800; color:var(--navy); margin-bottom:14px;'>📊 비행 환경 종합 진단 대시보드</h3>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-label">🛡️ 안전 등급</div>
            <div class="stat-value">{ai_eval['score']} <small style="font-size:11px; font-weight:normal; color:var(--muted);">/ 100</small></div>
            <div style="font-size:12px; color:var(--muted); margin-top:4px;">공역: <b>{airspace_res['zone_name'].split('(')[0]}</b></div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-label">📋 진단 요약</div>
            <div class="stat-value" style="font-size:13px; font-weight:600; line-height:1.6;">
                • 날씨: <b>{weather_res['weather_desc']}</b><br>
                • 공역: <b>{airspace_res['zone_name'].split('(')[0]}</b><br>
                • 기체: <b>{drone_weight}g</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-label">🌤️ 실시간 기상</div>
            <div class="stat-value">{weather_res['weather_desc']}</div>
            <div style="font-size:12px; color:var(--muted); margin-top:4px;">
                풍속 <b>{weather_res['wind_speed']} m/s</b> · 강수 <b>{weather_res['rain']} mm/h</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        approval_text = '⚠️ 사전 승인 필요' if airspace_res['approval_required'] else '🟢 비행승인 면제'
        st.markdown(f"""
        <div class="stat-box">
            <div class="stat-label">🛡️ 공역 규제 분석</div>
            <div class="stat-value" style="font-size:13px;">{approval_text}</div>
            <div style="font-size:12px; color:var(--muted); margin-top:4px;">
                촬영허가: <b>{'사전 확인 필요' if has_camera else '해당 없음'}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # FLOATING AI CHATBOT WIDGET (Bottom-Right Corner Floating Pill Button)
    with st.popover("💬 AI 컨설턴트 챗봇"):
        st.markdown("<h4 style='margin:0 0 4px; font-size:16px; color:var(--navy); font-weight:800;'>🤖 AI 드론 전문가 컨설턴트</h4>", unsafe_allow_html=True)
        st.caption("비행 안전, 승인 절차, 긴급 조치, 고장 수리 등 자유롭게 질문하세요!")
        
        float_chat_box = st.container(height=280)
        with float_chat_box:
            for msg in st.session_state.chat_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    if msg.get("approval_data"):
                        render_extension_trigger(msg["approval_data"])

        if float_prompt := st.chat_input("AI 컨설턴트에게 질문하기...", key="floating_chat_input"):
            process_chat_message(float_prompt, address_query, airspace_res["zone_name"])
            st.rerun()

    # BOTTOM 2-SPLIT SECTION: Official Department Table (Left) & Legal Fines (Right)
    st.divider()
    bot_col1, bot_col2 = st.columns(2)

    with bot_col1:
        contacts = airspace_res.get("official_contacts", {})
        table_html = (
            f'<table class="onestop-table">'
            f'<tr><th width="35%">검색 주소</th><td><b>{address_query}</b> ({display_loc_name})</td></tr>'
            f'<tr><th>비행구역 담당자</th><td><b>{contacts.get("flight_contact")}</b></td></tr>'
            f'<tr><th>특별비행 담당자</th><td><b>{contacts.get("special_contact")}</b></td></tr>'
            f'<tr><th>항공촬영 담당자</th><td><b>{contacts.get("photo_contact")}</b></td></tr>'
            f'</table>'
        )
        st.markdown(
            f'<div class="analysis-panel">'
            f'<div class="analysis-section-title">🌐 드론원스톱 공식 민원 담당 부서</div>'
            f'{table_html}'
            f'<div style="font-size:11px; color:var(--muted);">'
            f'공식 민원 접수 및 승인은 <a href="https://drone.onestop.go.kr/" target="_blank" style="color:var(--blue); text-decoration:underline;">드론원스톱 민원포털</a>에서 진행됩니다.'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with bot_col2:
        penalty_items = []
        for p in ai_eval["legal_penalties"]:
            severity_badge = "<span style='color:#b91c1c; font-weight:700;'>[형사처벌]</span>" if p["severity"] == "CRITICAL" else "<span style='color:#b45309; font-weight:700;'>[과태료]</span>"
            penalty_items.append(
                f"<li style='margin-bottom:8px;'>"
                f"<b>{p['regulation']}</b> {severity_badge}<br>"
                f"<span style='color:var(--muted);'>위반: {p['violation']}</span> ➔ <strong style='color:var(--navy);'>{p['fine_details']}</strong>"
                f"</li>"
            )
        penalties_html = "".join(penalty_items)
        st.markdown(
            f'<div class="analysis-panel" style="background:#fff8f8; border-color:#fed7d7;">'
            f'<div class="analysis-section-title" style="color:#9b1c1c;">⚖️ 관련 법규 위반 시 과태료 및 벌금</div>'
            f'<ul style="margin:0; padding-left:18px; font-size:12px; line-height:1.7;">{penalties_html}</ul>'
            f'</div>',
            unsafe_allow_html=True
        )

    # ---------------------------------------------------------
    # VERY BOTTOM OF TAB 1: Drone One-Stop 1:1 Form Field Matching Copy Tool
    # ---------------------------------------------------------
    st.divider()
    st.markdown("<h3 style='font-size:16px; font-weight:800; color:var(--navy); margin-bottom:10px;'>📄 드론원스톱 공식 민원 신청 안내</h3>", unsafe_allow_html=True)
    st.link_button(
        "🚀 대한민국 드론원스톱 공식 비행 승인 신청 페이지 바로가기 (drone.onestop.go.kr)",
        "https://drone.onestop.go.kr/civilappeal/flight/register",
        type="primary"
    )

    flight_context = {
        "date_str": str(flight_date),
        "time_str": str(flight_time),
        "lat": lat_val,
        "lon": lon_val,
        "location_name": address_query,
        "weight_g": drone_weight,
        "purpose": purpose,
        "max_altitude": max_altitude,
        "airspace_name": airspace_res["zone_name"],
        "wind_speed": weather_res["wind_speed"],
        "weather_desc": weather_res["weather_desc"]
    }
    
    flight_app_text = generate_flight_approval_text(st.session_state.user_profile, flight_context, ai_eval)
    photo_permit_text = generate_photo_permit_text(st.session_state.user_profile, flight_context, ai_eval)
    
    with st.expander("📄 신청서 전체 텍스트 서식 전문 보기 (복사 및 PDF 준비)"):
        doc_tab1, doc_tab2 = st.tabs(["📋 초경량비행장치 비행 승인 신청서 전문", "📷 항공촬영 허가 신청서 전문"])
        with doc_tab1:
            st.text_area("비행 승인 신청서 서식 전문", flight_app_text, height=300)
        with doc_tab2:
            st.text_area("항공촬영 허가 신청서 서식 전문", photo_permit_text, height=300)

# =========================================================
# VIEW 2: AI 컨설턴트 챗봇 (Matching media_1791917834377.png)
# =========================================================
elif selected_menu == "◉ 2. 대화로 신청하기":
    form_data = st.session_state.get("flight_form_data", {})
    loc_val = form_data.get("location") or "------"
    date_val = form_data.get("date") or "------"
    time_val = form_data.get("time") or "------"
    weight_val = form_data.get("weight") or "------"
    cam_val = form_data.get("camera") or "------"
    purpose_val = form_data.get("purpose") or "------"
    alt_val = form_data.get("altitude") or "------"

    filled_count = sum(1 for val in [loc_val, date_val, time_val, weight_val, cam_val, purpose_val, alt_val] if val != "------")
    progress_pct = round((filled_count / 7) * 100)

    st.markdown(f"""
    <div class="hero-box" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
        <h1 class="hero-title" style="margin:0; font-size:24px; font-weight:850; letter-spacing:-0.6px; color:var(--navy);">AI 드론 비행 도우미</h1>
        <div class="step-chip" style="background:white; border:1px solid var(--line); border-radius:12px; padding:9px 16px; font-size:13px; color:#65758b; font-weight:600; box-shadow:0 2px 6px rgba(0,0,0,0.02);">
            작성 진행 <b style="color:var(--blue);">{filled_count} / 7</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    hist_col, chat_col, summary_col = st.columns([0.65, 1.45, 0.9])

    # 1) Left Column: ChatGPT / Gemini Style Conversation Drawer
    with hist_col:
        with st.container(key="chat_hist_panel", border=True):
            st.markdown("""
            <div class="hist-panel-header">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:15px;">💬</span>
                    <strong style="font-size:14px; color:#10233F; font-weight:800;">대화 보관함</strong>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # + 새 채팅 시작 버튼 (Promptly resets & archives current conversation)
            if st.button("➕ 새 채팅 시작", key="v2_new_chat_btn", use_container_width=True):
                start_new_chat()
                st.toast("새로운 대화를 시작합니다. (이전 대화 자동 보관)")
                st.rerun()

            if st.session_state.chat_history_archive:
                st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
                for idx, hist in enumerate(st.session_state.chat_history_archive):
                    h_title = hist.get("title", f"대화 #{idx+1}")
                    h_date = hist.get("date", "")
                    with st.container(key=f"hist_row_{idx}"):
                        c_load, c_del = st.columns([4.2, 0.9])
                        with c_load:
                            if st.button(f"💬 {h_title}", key=f"hist_load_{idx}", use_container_width=True, help=f"{h_date} 대화 복원"):
                                st.session_state.chat_messages = list(hist.get("messages", []))
                                if hist.get("location"):
                                    st.session_state.current_address = hist.get("location")
                                if hist.get("form_data"):
                                    st.session_state.flight_form_data = dict(hist.get("form_data"))
                                st.toast(f"'{h_title}' 대화를 불러왔습니다.")
                                st.rerun()
                        with c_del:
                            if st.button("🗑️", key=f"hist_del_{idx}", help="이 대화 삭제"):
                                del_title = hist.get("title", "대화")
                                st.session_state.chat_history_archive.pop(idx)
                                st.toast(f"'{del_title}' 대화가 삭제되었습니다.")
                                st.rerun()

                st.markdown("<div style='margin-top:12px; border-top:1px solid #f1f5f9; padding-top:8px;'></div>", unsafe_allow_html=True)
                if st.button("전체 기록 비우기", key="v2_clear_all_hist_btn", use_container_width=True):
                    st.session_state.chat_history_archive = []
                    st.rerun()
            else:
                st.markdown("""
                <div class="hist-empty-card" style="padding:14px 12px; font-size:11.5px; text-align:center; line-height:1.6;">
                    아직 저장된 지난 대화가 없어요.<br><strong>'+ 새 채팅 시작'</strong>을 누르면<br>현재 대화가 자동 보관됩니다.
                </div>
                """, unsafe_allow_html=True)

    # 2) Center Column: Conversation Chat Window (Enclosed in a single unified card matching media_1791941586639.png)
    with chat_col:
        with st.container(key="chat_main_card", border=True):
            st.markdown('<div class="chat-card-marker"></div>', unsafe_allow_html=True)

            # Card Header matching media_1791941586639.png
            st.markdown("""
            <div class="chat-card-header">
                <div style="display:flex; align-items:center; gap:12px;">
                    <div class="chat-header-icon">🤖</div>
                    <div>
                        <div class="chat-header-title">스카이 비행 도우미</div>
                        <div class="chat-header-sub">비행 계획을 함께 정리해요</div>
                    </div>
                </div>
                <span class="chat-header-badge">대화형 작성</span>
            </div>
            """, unsafe_allow_html=True)

            # Scrollable Message Area (No internal borders)
            chat_container = st.container(height=480, border=False)
            with chat_container:
                for msg in st.session_state.chat_messages:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"], unsafe_allow_html=True)
                        if msg.get("approval_data"):
                            render_extension_trigger(msg["approval_data"])

            # Dynamic Placeholder & Quick Suggestions for Current Question
            field_keys = ["location", "date", "time", "weight", "camera", "purpose", "altitude"]
            unfilled_keys = [k for k in field_keys if not form_data.get(k)]
            next_f = unfilled_keys[0] if unfilled_keys else None
            
            placeholders = {
                "location": "예: 서울 여의도 한강공원",
                "date": "예: 2026-10-20 또는 이번 주말",
                "time": "예: 14:00~16:00 또는 오후 2시",
                "weight": "예: DJI Mini 4 Pro, 249g",
                "camera": "예: 카메라 있음 (촬영 예정)",
                "purpose": "예: 풍경 촬영, 캡스톤 프로젝트",
                "altitude": "예: 120m 또는 150m"
            }
            active_placeholder = placeholders.get(next_f, "메시지를 입력하세요...")

            if next_f:
                quick_options = {
                    "location": [("📍 여의도 한강공원", "서울 여의도 한강공원"), ("📍 김천 율곡중학교", "김천 율곡중학교"), ("📍 해운대", "부산 해운대")],
                    "date": [("📅 오늘 비행", str(date.today())), ("📅 이번 주말", "이번 주말"), ("📅 2026-10-25", "2026-10-25")],
                    "time": [("⏰ 14:00~16:00", "14:00~16:00"), ("⏰ 10:00~12:00", "10:00~12:00"), ("⏰ 일몰 골든아워", "일몰 골든아워")],
                    "weight": [("🛸 249g (초경량)", "249g"), ("🛸 250g~2kg", "250g~2kg"), ("🛸 2kg 초과", "2kg 초과")],
                    "camera": [("📷 카메라 있음 (촬영)", "카메라 있음 (촬영 예정)"), ("📷 미촬영", "카메라 있음 (촬영 안 함)"), ("🚫 카메라 없음", "카메라 없음")],
                    "purpose": [("🎯 풍경·경관 촬영", "풍경 촬영"), ("🎯 캡스톤 프로젝트", "캡스톤 프로젝트"), ("🎯 조종 연습", "조종 연습")],
                    "altitude": [("📐 50m", "50m"), ("📐 80m", "80m"), ("📐 120m", "120m"), ("📐 150m", "150m")]
                }
                opts = quick_options.get(next_f, [])
                if opts:
                    qp_cols = st.columns(len(opts))
                    for q_idx, (q_label, q_val) in enumerate(opts):
                        with qp_cols[q_idx]:
                            if st.button(q_label, key=f"quick_pill_{q_idx}", use_container_width=True):
                                process_chat_message(q_val, address_query, airspace_res["zone_name"])
                                st.rerun()

            # Prompt Input Form (Cleanly enclosed inside the bottom of the card)
            with st.form("chat_input_form", clear_on_submit=True, border=False):
                f_col1, f_col2 = st.columns([5.2, 1.2])
                with f_col1:
                    user_prompt = st.text_input(
                        "프롬프트 입력",
                        placeholder=active_placeholder,
                        label_visibility="collapsed",
                        key="chat_prompt_text"
                    )
                with f_col2:
                    send_submitted = st.form_submit_button("보내기 ➤", type="primary", use_container_width=True)

                if send_submitted and user_prompt and user_prompt.strip():
                    process_chat_message(user_prompt.strip(), address_query, airspace_res["zone_name"])
                    st.rerun()

            # Security / Privacy hint inside the card
            st.markdown("""
            <div class="chat-card-footer">
                <span>🔒</span>
                <span>개인정보나 민감한 정보는 입력하지 않아도 돼요. 모르는 항목은 '모르겠어요'라고 답해 주세요.</span>
            </div>
            """, unsafe_allow_html=True)

    # 3) Right Column: Live Flight Approval Summary Card (Matching media_1791941586639.png)
    with summary_col:
        form_data = st.session_state.get("flight_form_data", {})
        
        # 7 items default to "------" (6 hyphens) unless entered by user
        loc_val = form_data.get("location") or "------"
        date_val = form_data.get("date") or "------"
        time_val = form_data.get("time") or "------"
        weight_val = form_data.get("weight") or "------"
        cam_val = form_data.get("camera") or "------"
        purpose_val = form_data.get("purpose") or "------"
        alt_val = form_data.get("altitude") or "------"

        filled_count = sum(1 for val in [loc_val, date_val, time_val, weight_val, cam_val, purpose_val, alt_val] if val != "------")
        progress_pct = round((filled_count / 7) * 100)

        st.markdown(f"""
        <div class="summary-card" style="background:white; border:1px solid var(--line); border-radius:18px; box-shadow:0 4px 20px rgba(16,35,63,0.05); overflow:hidden;">
            <div style="padding:18px 20px; border-bottom:1px solid var(--line);">
                <h3 style="font-size:16px; margin:0 0 4px; color:var(--navy); font-weight:800;">비행 신청 정보</h3>
                <p style="font-size:11.5px; color:var(--muted); margin:0;">대화에서 받은 답변이 여기에 자동으로 정리돼요.</p>
            </div>
            <div style="padding:16px 20px 6px;">
                <div style="display:flex; justify-content:space-between; font-size:11.5px; color:var(--muted); margin-bottom:8px;">
                    <span>정보 수집 진행률</span>
                    <b style="color:#2563EB; font-size:12px;">{progress_pct}%</b>
                </div>
                <div style="height:6px; background:#edf1f7; border-radius:10px; overflow:hidden;">
                    <div style="height:100%; width:{progress_pct}%; background:#2563EB; border-radius:10px; transition:width .3s;"></div>
                </div>
            </div>
            <div style="padding:6px 20px 16px;">
                <div class="sum-row">
                    <span>비행 장소</span>
                    <strong class="{'' if loc_val != '------' else 'empty-val'}">{loc_val}</strong>
                </div>
                <div class="sum-row">
                    <span>비행 날짜</span>
                    <strong class="{'' if date_val != '------' else 'empty-val'}">{date_val}</strong>
                </div>
                <div class="sum-row">
                    <span>비행 시간</span>
                    <strong class="{'' if time_val != '------' else 'empty-val'}">{time_val}</strong>
                </div>
                <div class="sum-row">
                    <span>드론 기체 중량</span>
                    <strong class="{'' if weight_val != '------' else 'empty-val'}">{weight_val}</strong>
                </div>
                <div class="sum-row">
                    <span>카메라 탑재</span>
                    <strong class="{'' if cam_val != '------' else 'empty-val'}">{cam_val}</strong>
                </div>
                <div class="sum-row">
                    <span>비행 목적</span>
                    <strong class="{'' if purpose_val != '------' else 'empty-val'}">{purpose_val}</strong>
                </div>
                <div class="sum-row">
                    <span>예정 고도</span>
                    <strong class="{'' if alt_val != '------' else 'empty-val'}">{alt_val}</strong>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

        # Button 1: Dark Navy Button -> 신청서 미리보기 (새 탭) ↗
        st.link_button(
            "신청서 미리보기 (새 탭) ↗",
            "https://drone.onestop.go.kr/civilappeal/flight/register",
            key="v2_preview_link",
            use_container_width=True
        )

        # Prepare text for download button
        v2_context = {
            "date_str": date_val if date_val != "------" else str(date.today()),
            "time_str": time_val if time_val != "------" else "14:00",
            "lat": lat_val,
            "lon": lon_val,
            "location_name": loc_val if loc_val != "------" else "미입력",
            "weight_g": weight_val if weight_val != "------" else "249g",
            "purpose": purpose_val if purpose_val != "------" else "경관 촬영",
            "max_altitude": alt_val if alt_val != "------" else "120m",
            "airspace_name": airspace_res.get("zone_name", "일반공역"),
            "wind_speed": weather_res.get("wind_speed", 2.0),
            "weather_desc": weather_res.get("weather_desc", "맑음")
        }
        v2_flight_text = generate_flight_approval_text(st.session_state.user_profile, v2_context, ai_eval)

        # Button 2: White Secondary Button -> 신청서 텍스트 내려받기
        st.download_button(
            "신청서 텍스트 내려받기",
            data=v2_flight_text,
            file_name=f"drone_flight_app_{date.today()}.txt",
            mime="text/plain",
            key="v2_download_btn",
            disabled=(filled_count == 0),
            use_container_width=True
        )

        # Button 3: White Secondary Button -> 💾 현재 대화 저장소에 보관
        if st.button("💾 현재 대화 저장소에 보관", key="v2_save_chat_btn", use_container_width=True):
            cur_loc = loc_val if loc_val and loc_val not in ["-------", "------"] else "드론 비행 대화"
            new_hist = {
                "title": f"{cur_loc} ({date.today().strftime('%m/%d')})",
                "date": str(date.today()),
                "location": cur_loc,
                "messages": list(st.session_state.chat_messages),
                "form_data": dict(st.session_state.get("flight_form_data", {}))
            }
            st.session_state.chat_history_archive.insert(0, new_hist)
            st.success("현재 대화가 저장소에 보관되었습니다!")
            st.rerun()

        app_data = st.session_state.get("latest_flight_approval")
        if app_data and app_data.get("status") == "ready":
            st.markdown("<div style='margin-top:10px;'>", unsafe_allow_html=True)
            render_extension_trigger(app_data)
            st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# VIEW 3: 📷 3. 촬영 도우미 (AI 시네마틱 드론 비행 & 앵글 플래너)
# =========================================================
elif selected_menu == "📷 3. 촬영 도우미":
    render_clean_html("""
    <div class="hero-box" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
        <div>
            <div class="eyebrow">AI CINEMATOGRAPHY & FLIGHT PLANNER</div>
            <h1 class="hero-title" style="margin:0; font-size:24px; font-weight:850; letter-spacing:-0.6px; color:var(--navy);">📷 AI 시네마틱 드론 촬영 도우미</h1>
            <p class="hero-desc" style="margin:4px 0 0; font-size:13px; color:var(--muted);">촬영 장소와 목적을 자연어로 말씀해 주시면, 태양 위치(일출·일몰·골든아워)와 실시간 기상·공역을 종합 분석하여 최적의 촬영 시간대와 카메라/비행 구도를 추천해 드립니다.</p>
        </div>
        <div class="step-chip" style="background:white; border:1px solid var(--line); border-radius:12px; padding:9px 16px; font-size:13px; color:#1e40af; font-weight:700; box-shadow:0 2px 6px rgba(0,0,0,0.02);">
            ✨ 골든아워 &amp; 앵글 분석기
        </div>
    </div>
    """)

    # Example Prompt Guide Box for Users
    example_prompt_text = "이번 주 금요일 오후 6시~8시 사이에 서울 여의도 한강공원 인근에서 국회의사당과 주변 야경을 공중에서 담으려고 해. DJI Air 3 기체(듀얼 렌즈: 광원/망원)로 사용하고 있고, 건물 조명이 켜지는 매직아워(블루아워) 진입 시점과 도심 야경을 압축감 있게 담을 수 있는 망원 구도 팁을 분석하고 추천해줘."
    
    render_clean_html(f"""
    <div style="background: linear-gradient(135deg, #f0f7ff 0%, #f8fafc 100%); border: 1px solid #bfdbfe; border-left: 4px solid #2563eb; border-radius: 12px; padding: 13px 18px; margin-bottom: 8px; box-shadow: 0 2px 6px rgba(37,99,235,0.03);">
        <div style="font-size: 13px; font-weight: 800; color: #1e40af; margin-bottom: 5px; display: flex; align-items: center; gap: 6px;">
            💡 <span>작성 예시</span>
        </div>
        <div style="font-size: 13px; color: #334155; line-height: 1.6; word-break: keep-all;">
            "{example_prompt_text}"
        </div>
    </div>
    """)

    # Search Bar
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    with st.container():
        sc1, sc2 = st.columns([4.2, 1.0])
        with sc1:
            cinema_input = st.text_input(
                "촬영 의도 자연어 입력",
                value=st.session_state.get("cinema_query", ""),
                placeholder="원하는 촬영 장소, 목적 및 조건 등을 자유롭게 입력하세요 (예: 서울 여의도 한강공원 일몰 촬영)",
                label_visibility="collapsed"
            )
        with sc2:
            search_submitted = st.button("🔍 촬영 의도 분석", type="primary", use_container_width=True, key="cinema_search_btn")

    if search_submitted:
        st.session_state.cinema_query = cinema_input.strip()
        if cinema_input.strip():
            st.session_state.cinema_analysis = cs.analyze_cinematography_intent(cinema_input.strip())
        else:
            st.session_state.cinema_analysis = None
    elif st.session_state.cinema_analysis is None and st.session_state.get("cinema_query", "").strip():
        st.session_state.cinema_analysis = cs.analyze_cinematography_intent(st.session_state.cinema_query.strip())

    if st.session_state.cinema_analysis is not None:
        analysis = st.session_state.cinema_analysis
    else:
        # Default baseline (e.g. Yeouido Hangang baseline for solar timeline & weather)
        analysis = cs.analyze_cinematography_intent("서울 여의도 한강공원 일몰")

    sun = analysis["sun_times"]

    # Dynamic Notices & Announcements Box right beneath the prompt
    # Only shown when user has entered a prompt and searched!
    if st.session_state.get("cinema_query", "").strip():
        notices = analysis.get("notices", [])
        if notices:
            notices_html = "".join([f"""
            <div style="background:{n.get('badge_bg', '#f8fafc')}; border:1px solid #e2e8f0; border-radius:10px; padding:12px 14px; margin-bottom:8px; display:flex; align-items:flex-start; gap:12px;">
                <span style="font-size:18px; flex-shrink:0; line-height:1.2;">{n['icon']}</span>
                <div style="flex-grow:1;">
                    <div style="display:flex; align-items:center; gap:8px; margin-bottom:3px;">
                        <span style="font-size:11px; font-weight:800; color:{n.get('badge_color', '#1e40af')}; background:white; border:1px solid {n.get('badge_color', '#1e40af')}33; padding:1px 7px; border-radius:4px;">{n['badge']}</span>
                        <strong style="font-size:13px; color:#0f172a;">{n['title']}</strong>
                    </div>
                    <div style="font-size:12px; color:#475569; line-height:1.55;">{n['desc']}</div>
                </div>
            </div>
            """ for n in notices])
            
            render_clean_html(f"""
            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:14px; padding:16px 18px; margin-top:10px; margin-bottom:18px; box-shadow:0 2px 8px rgba(0,0,0,0.03);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-size:15px;">📢</span>
                        <strong style="font-size:14px; color:#0f172a; font-weight:800;">촬영 의도 기반 참고 및 필수 공지사항</strong>
                    </div>
                    <span style="font-size:11px; color:#2563eb; background:#eff6ff; font-weight:700; padding:2px 8px; border-radius:6px; border:1px solid #bfdbfe;">입력 내용 실시간 연동</span>
                </div>
                {notices_html}
            </div>
            """)

    # Compute Real-time Weather & Airspace for this location
    loc_weather = get_weather(analysis["lat"], analysis["lon"])
    loc_airspace = check_airspace(analysis["lat"], analysis["lon"], analysis["location"])

    # 1. Solar Timeline & Real-time Weather/Airspace Evaluation
    row1_c1, row1_c2 = st.columns([1.1, 0.9])

    with row1_c1:
        render_clean_html(f"""
<div class="cinema-card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <div style="font-size:15px; font-weight:800; color:var(--navy);">☀️ 태양 천문 위치 & 골든아워 타임라인</div>
        <div style="font-size:12px; color:var(--muted); font-weight:600;">📍 {analysis['location']} · {analysis['date']}</div>
    </div>
    <div class="solar-timeline-wrap">
        <div class="solar-node">
            <span style="font-size:16px;">🌅</span>
            <span class="solar-node-time">{sun['sunrise']}</span>
            <span class="solar-node-label">일출</span>
        </div>
        <div style="color:rgba(255,255,255,0.4); font-size:14px;">➔</div>
        <div class="solar-node">
            <span style="font-size:16px;">☀️</span>
            <span class="solar-node-time">{sun['solar_noon']}</span>
            <span class="solar-node-label">정오</span>
        </div>
        <div style="color:rgba(255,255,255,0.4); font-size:14px;">➔</div>
        <div class="solar-node solar-highlight">
            <span style="font-size:16px;">⭐</span>
            <span class="solar-node-time">{analysis['recommended_time']}</span>
            <span class="solar-node-label" style="color:#fef08a; font-weight:800;">최적 추천</span>
        </div>
        <div style="color:rgba(255,255,255,0.4); font-size:14px;">➔</div>
        <div class="solar-node">
            <span style="font-size:16px;">🛑</span>
            <span class="solar-node-time">{sun['sunset']}</span>
            <span class="solar-node-label" style="color:#fca5a5;">법정 일몰</span>
        </div>
        <div style="color:rgba(255,255,255,0.4); font-size:14px;">➔</div>
        <div class="solar-node">
            <span style="font-size:16px;">🌌</span>
            <span class="solar-node-time">{sun['evening_blue_hour'].split(' ~ ')[1]}</span>
            <span class="solar-node-label">야간 시작</span>
        </div>
    </div>
    <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:12px 14px; margin-top:10px;">
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
            <span class="status-pill" style="background:#eff6ff; color:#1d4ed8; font-weight:750; font-size:12px; padding:3px 10px;">🎯 {analysis['scene_title']}</span>
            <span style="font-size:13px; font-weight:800; color:var(--navy);">추천 시간: {analysis['recommended_time']}</span>
        </div>
        <div style="font-size:12.5px; color:#334155; line-height:1.6; margin-top:6px;">
            {analysis['time_reason']}
        </div>
    </div>
</div>
""")

        if analysis.get("night_flight_warning"):
            st.warning(analysis["night_flight_warning"])

    with row1_c2:
        wind_spd = loc_weather['wind_speed']
        gust = loc_weather['wind_gust']
        if wind_spd < 5.0:
            fly_badge = "<span style='background:#def7ec; color:#03543f; padding:4px 10px; border-radius:12px; font-weight:750; font-size:12px;'>🟢 최적 비행 (미풍)</span>"
            wind_eval = "풍속이 5m/s 미만으로 짐벌 영상 떨림이 없으며 호버링 안전성이 매우 우수합니다."
        elif wind_spd < 8.0:
            fly_badge = "<span style='background:#fef08a; color:#713f12; padding:4px 10px; border-radius:12px; font-weight:750; font-size:12px;'>🟡 주의 비행 (돌풍 주의)</span>"
            wind_eval = "풍속이 약간 있으므로 수동 자세 제어 및 배터리 잔량 관리에 주의하세요."
        else:
            fly_badge = "<span style='background:#fde8e8; color:#9b1c1c; padding:4px 10px; border-radius:12px; font-weight:750; font-size:12px;'>🔴 비행 위험 (강풍)</span>"
            wind_eval = "강풍으로 인해 기체 유실 위험이 있으므로 비행 일정 조정을 권고합니다."

        render_clean_html(f"""
<div class="cinema-card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="font-size:15px; font-weight:800; color:var(--navy);">🌤️ 실시간 기상 & 공역 적합도 평가</div>
        <div>{fly_badge}</div>
    </div>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px;">
        <div class="stat-box" style="padding:10px 12px;">
            <div class="stat-label">실시간 날씨</div>
            <div class="stat-value" style="font-size:14px;">{loc_weather['weather_desc']}</div>
            <div style="font-size:11px; color:var(--muted); margin-top:2px;">기온 {loc_weather['temp']}°C · 강수 {loc_weather['rain']}mm</div>
        </div>
        <div class="stat-box" style="padding:10px 12px;">
            <div class="stat-label">바람 & 돌풍</div>
            <div class="stat-value" style="font-size:14px;">풍속 {wind_spd} m/s</div>
            <div style="font-size:11px; color:var(--muted); margin-top:2px;">최대 돌풍 {gust} m/s</div>
        </div>
    </div>
    <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:12px 14px;">
        <div style="font-size:12px; color:var(--muted); font-weight:700;">🌐 공역 규제 상태</div>
        <div style="font-size:13px; font-weight:750; color:var(--navy); margin:2px 0 4px;">{loc_airspace['zone_name'].split('(')[0]}</div>
        <div style="font-size:11.5px; color:#475569; line-height:1.5;">
            • {wind_eval}<br>
            • 법정 기준: <b>{analysis['legal_clearance']}</b>
        </div>
    </div>
</div>
""")

    # 2. Visual Flight Path & Camera Angle Diagram
    st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:16px; font-weight:800; color:var(--navy); margin-bottom:8px;'>📐 3D 시네마틱 비행 궤적 & 카메라 화각 다이어그램</div>", unsafe_allow_html=True)
    components.html(analysis["svg_diagram"], height=270)
    st.caption("위 다이어그램은 이륙(WP1) ➔ 핵심 촬영 구간(WP2) ➔ 상승 이탈(WP3) 및 카메라 조준 타겟(POI), 150m 법정 고도 한계선을 시각화한 비행 계획도입니다.")

    # 3. Cinematic Flight Mode & Camera Setting Recipes
    row3_c1, row3_c2 = st.columns(2)

    with row3_c1:
        render_clean_html(f"""
<div class="cinema-card" style="margin-top:14px;">
    <div style="font-size:15px; font-weight:800; color:var(--navy); margin-bottom:6px;">🎬 추천 비행 무빙 & 조종기 스틱 콤보</div>
    <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
        <span class="status-pill" style="background:#ecfdf5; color:#065f46; font-size:12.5px; font-weight:800;">{analysis['mode_name']}</span>
        <span style="font-size:12px; color:var(--muted); font-weight:600;">순항속도 {analysis['speed']} · 고도 {analysis['altitude_m']}m</span>
    </div>
    <div style="font-size:12.5px; color:#334155; line-height:1.6; margin-bottom:12px;">
        {analysis['mode_desc']}
    </div>
    <div style="background:#f1f5f9; border-radius:10px; padding:12px 14px; border:1px solid #e2e8f0;">
        <div style="font-size:12px; font-weight:800; color:var(--navy); margin-bottom:6px;">🎮 조종기 양손 스틱 조작 안내:</div>
        <div style="font-size:12px; color:#1e293b; line-height:1.7;">
            • <b>좌측 스틱 (Throttle / Yaw)</b>: {analysis['stick_left']}<br>
            • <b>우측 스틱 (Pitch / Roll)</b>: {analysis['stick_right']}<br>
            • <b>카메라 짐벌 피치</b>: {analysis['gimbal_pitch']} (피사체 중심 락온)
        </div>
    </div>
</div>
""")

    with row3_c2:
        cam = analysis["camera_settings"]
        render_clean_html(f"""
<div class="cinema-card" style="margin-top:14px;">
    <div style="font-size:15px; font-weight:800; color:var(--navy); margin-bottom:6px;">📷 카메라 & 노출 세팅 레시피 (180° Rule)</div>
    <div style="font-size:12px; color:var(--muted); margin-bottom:10px;">자연스러운 모션 블러와 최적의 다이내믹 레인지를 얻기 위한 드론 카메라 프로페셔널 세팅입니다.</div>
    <table class="onestop-table" style="margin-top:0;">
        <tr><th width="35%">해상도 & 프레임</th><td><b>{cam['resolution']}</b></td></tr>
        <tr><th>셔터스피드</th><td><b>{cam['shutter']}</b> <span style="font-size:11px; color:#0284c7;">(180° 셔터 앵글)</span></td></tr>
        <tr><th>추천 ND 필터</th><td><b style="color:#d97706; font-size:14px;">⭐ {cam['nd_filter']}</b></td></tr>
        <tr><th>ISO 감도 & 색온도</th><td><b>{cam['iso']}</b> · WB: <b>{cam['white_balance']}</b></td></tr>
        <tr><th>컬러 프로파일</th><td><b>{cam['color_profile']}</b></td></tr>
    </table>
</div>
""")



# =========================================================
# VIEW 4: 사용자 프로필 설정 (Clean Modern Forms)
# =========================================================
elif selected_menu == "⚙️ 사용자 프로필 설정":
    st.markdown("""
    <div class="hero-box">
        <div>
            <div class="eyebrow">USER & FLEET SETTINGS</div>
            <h1 class="hero-title">신청인 기본 정보 및 드론 기체 프로필</h1>
            <p class="hero-desc">여기에 등록된 신청인 정보와 기체 스펙은 드론원스톱 비행승인 및 항공촬영 신청서에 100% 자동 반영됩니다.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    profile = st.session_state.user_profile
    
    with st.form("profile_form"):
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            st.markdown("<div class='analysis-section-title'>👤 신청인 개인 정보</div>", unsafe_allow_html=True)
            app_name = st.text_input("성명 (신청인 대표)", value=profile.get("applicant_name", ""))
            phone = st.text_input("연락처 (휴대전화)", value=profile.get("phone", ""))
            email = st.text_input("이메일 주소", value=profile.get("email", ""))
            address = st.text_input("거주지 주소", value=profile.get("address", ""))
            birth_date = st.text_input("생년월일 (YYYY-MM-DD)", value=profile.get("birth_date", ""))
            organization = st.text_input("소속 / 회사명 (선택)", value=profile.get("organization", ""))
            emergency_contact = st.text_input("비상 연락처", value=profile.get("emergency_contact", ""))

        with p_col2:
            st.markdown("<div class='analysis-section-title'>🛸 기본 보유 드론 기체 정보</div>", unsafe_allow_html=True)
            drone_model = st.text_input("드론 기종 / 모델명 (예: DJI Mini 4 Pro)", value=profile.get("drone_model", ""))
            drone_weight_g = st.number_input("드론 자중 (g 단위, 250g 미만 면제 기준)", value=profile.get("drone_weight_g", 249))
            drone_serial = st.text_input("기체 시리얼 번호 (S/N)", value=profile.get("drone_serial", ""))
            drone_reg_num = st.text_input("드론원스톱 기체 등록번호 (신고 기체인 경우)", value=profile.get("drone_reg_num", ""))
            license_num = st.text_input("조종자 자격증 명칭 / 자격 번호", value=profile.get("license_num", ""))
            
        st.markdown("<div style='margin-top:14px;'>", unsafe_allow_html=True)
        submitted = st.form_submit_button("💾 프로필 저장하기", type="primary", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if submitted:
            new_profile = {
                "applicant_name": app_name,
                "phone": phone,
                "email": email,
                "address": address,
                "birth_date": birth_date,
                "organization": organization,
                "emergency_contact": emergency_contact,
                "drone_model": drone_model,
                "drone_weight_g": drone_weight_g,
                "drone_serial": drone_serial,
                "drone_reg_num": drone_reg_num,
                "license_num": license_num
            }
            if save_profile(new_profile):
                st.session_state.user_profile = new_profile
                st.success("✅ 사용자 기본 정보 및 드론 프로필이 성공적으로 저장되었습니다! 모든 서식에 자동 반영됩니다.")
