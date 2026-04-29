"""
portfolio_routes.py  —  Portfolio Dashboard API
เพิ่ม endpoints สำหรับ Dashboard ที่ทำงานคู่กับ webhook.py
ใช้ระบบ Google Sheets เดิมทุกอย่าง
"""
from flask import Blueprint, request, jsonify
import json, os
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime, timezone, timedelta

portfolio_bp = Blueprint('portfolio', __name__)

TZ_THAI        = timezone(timedelta(hours=7))
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
GOOGLE_CREDS   = os.getenv('GOOGLE_CREDENTIALS')


# ── ใช้ get_gsheet เดิมของ webhook.py ──────────────────────────
def get_gsheet():
    try:
        creds_dict = json.loads(GOOGLE_CREDS)
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds  = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        print(f"[PORTFOLIO API] gsheet error: {e}")
        return None


def ensure_tab(sh, tab_name, headers):
    """สร้าง tab ใหม่ถ้ายังไม่มี พร้อม header"""
    try:
        return sh.worksheet(tab_name)
    except:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
        ws.append_row(headers)
        return ws


def cors(response):
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,DELETE,OPTIONS'
    return response


# ── Health check ────────────────────────────────────────────────
@portfolio_bp.route('/api/health', methods=['GET'])
def health():
    return cors(jsonify({'ok': True, 'status': 'Portfolio API running ✅'}))


# ── Log transaction จาก Dashboard ──────────────────────────────
@portfolio_bp.route('/api/transaction', methods=['POST', 'OPTIONS'])
def log_transaction():
    if request.method == 'OPTIONS':
        return cors(jsonify({'ok': True}))
    try:
        d  = request.json or {}
        sh = get_gsheet()
        if not sh:
            return cors(jsonify({'ok': False, 'error': 'Google Sheets ไม่ได้เชื่อมต่อ'})), 500

        ws = ensure_tab(sh, 'DashboardTransactions', [
            'Date', 'Type', 'Ticker', 'Shares', 'Price', 'Total', 'Fees', 'Notes', 'Source'
        ])

        shares = float(d.get('shares', 0))
        price  = float(d.get('price',  0))
        now    = datetime.now(TZ_THAI).strftime('%Y-%m-%d %H:%M')

        ws.append_row([
            d.get('date', now),
            d.get('type', ''),
            d.get('ticker', '').upper(),
            shares,
            price,
            round(shares * price, 4),
            float(d.get('fees', 0)),
            d.get('notes', ''),
            'Dashboard'
        ])
        return cors(jsonify({'ok': True, 'message': f"บันทึก {d.get('type')} {d.get('ticker')} แล้ว"}))
    except Exception as e:
        return cors(jsonify({'ok': False, 'error': str(e)})), 500


# ── ดึง transactions ทั้งหมด ────────────────────────────────────
@portfolio_bp.route('/api/transactions', methods=['GET', 'OPTIONS'])
def get_transactions():
    if request.method == 'OPTIONS':
        return cors(jsonify({'ok': True}))
    try:
        sh = get_gsheet()
        if not sh:
            return cors(jsonify({'ok': False, 'error': 'Google Sheets ไม่ได้เชื่อมต่อ'})), 500

        ws   = ensure_tab(sh, 'DashboardTransactions', [
            'Date', 'Type', 'Ticker', 'Shares', 'Price', 'Total', 'Fees', 'Notes', 'Source'
        ])
        rows = ws.get_all_records()
        return cors(jsonify({'ok': True, 'data': rows, 'count': len(rows)}))
    except Exception as e:
        return cors(jsonify({'ok': False, 'error': str(e)})), 500


# ── ดึงพอร์ตจาก LINE bot (Portfolio sheet เดิม) ─────────────────
@portfolio_bp.route('/api/portfolio', methods=['GET', 'OPTIONS'])
def get_portfolio():
    if request.method == 'OPTIONS':
        return cors(jsonify({'ok': True}))
    try:
        sh = get_gsheet()
        if not sh:
            return cors(jsonify({'ok': False, 'error': 'Google Sheets ไม่ได้เชื่อมต่อ'})), 500

        ws   = sh.worksheet('Portfolio')   # tab เดิมที่ webhook.py เขียนอยู่
        rows = ws.get_all_records()
        return cors(jsonify({'ok': True, 'data': rows}))
    except Exception as e:
        return cors(jsonify({'ok': False, 'error': str(e)})), 500
