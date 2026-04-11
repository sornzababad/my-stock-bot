from flask import Flask, request
import requests
import anthropic
import yfinance as yf
import pandas as pd
import os
import json
import re
from datetime import datetime, timezone, timedelta
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

TZ_THAI = timezone(timedelta(hours=7))
LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
GOOGLE_CREDENTIALS = os.getenv('GOOGLE_CREDENTIALS')

def get_gsheet():
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        print(f"[GSHEET ERROR] {e}")
        return None

def log_transaction_to_sheet(tx_type, ticker, qty, price, pnl=None):
    try:
        sh = get_gsheet()
        if not sh:
            return
        ws = sh.worksheet('Transactions')
        now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
        row = [now, tx_type, ticker, qty, price, qty * price, pnl if pnl else '']
        ws.append_row(row)
        print(f"[SHEET] บันทึก {tx_type} {ticker} สำเร็จ")
    except Exception as e:
        print(f"[SHEET LOG ERROR] {e}")

def update_portfolio_sheet(portfolio):
    try:
        sh = get_gsheet()
        if not sh:
            return
        ws = sh.worksheet('Portfolio')
        ws.clear()
        ws.append_row(['Ticker', 'จำนวน', 'ราคาเฉลี่ย', 'ราคาปัจจุบัน', 'มูลค่า', 'P/L', 'P/L %', 'อัปเดต'])
        now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
        for ticker, h in portfolio['holdings'].items():
            qty = h['qty']
            avg = h['avg_price']
            curr = get_current_price(ticker)
            if curr:
                pnl = (curr - avg) * qty
                pnl_pct = ((curr - avg) / avg) * 100
                value = curr * qty
                ws.append_row([ticker, qty, avg, curr, round(value, 2), round(pnl, 2), round(pnl_pct, 2), now])
            else:
                ws.append_row([ticker, qty, avg, 'N/A', 'N/A', 'N/A', 'N/A', now])
        print(f"[SHEET] อัปเดต Portfolio sheet สำเร็จ")
    except Exception as e:
        print(f"[SHEET PORTFOLIO ERROR] {e}")

def log_signal_to_sheet(ticker, signal_type, price, rsi, conviction):
    try:
        sh = get_gsheet()
        if not sh:
            return
        ws = sh.worksheet('Signals')
        now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
        ws.append_row([now, signal_type, ticker, price, rsi, conviction])
        print(f"[SHEET] บันทึก Signal {ticker} สำเร็จ")
    except Exception as e:
        print(f"[SHEET SIGNAL ERROR] {e}")

PORTFOLIO_FILE = 'portfolio.json'

def load_portfolio():
    try:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {"holdings": {}, "transactions": []}

def save_portfolio(data):
    try:
        with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[SAVE ERROR] {e}")

def get_current_price(ticker):
    try:
        df = yf.download(ticker, period='2d', interval='1d', progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return float(df['Close'].iloc[-1])
    except:
        return None

def reply_to_line(reply_token, message):
    url = 'https://api.line.me/v2/bot/message/reply'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {LINE_ACCESS_TOKEN}'}
    data = {'replyToken': reply_token, 'messages': [{'type': 'text', 'text': message}]}
    try:
        requests.post(url, headers=headers, json=data, timeout=10)
    except Exception as e:
        print(f"[REPLY ERROR] {e}")

def ask_claude(user_message):
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system="""คุณเป็นผู้ช่วยวิเคราะห์หุ้นส่วนตัว ตอบภาษาไทยสั้นกระชับ
เชี่ยวชาญด้านการลงทุนระยะกลาง-ยาว เทคนิคอล และปัจจัยพื้นฐาน
ตอบไม่เกิน 5 บรรทัด ถ้าถามนอกเรื่องหุ้นให้บอกว่าตอบได้เฉพาะเรื่องการลงทุน""",
            messages=[{"role": "user", "content": user_message}]
        )
        return msg.content[0].text
    except Exception as e:
        return f"ขออภัย เกิดข้อผิดพลาด: {str(e)}"

def handle_buy(text, portfolio):
    m = re.search(r'ซื้อ\s+(\S+)\s+([\d.]+)\s*@\s*([\d.]+)', text, re.IGNORECASE)
    if not m:
        return "รูปแบบไม่ถูกต้องครับ\nตัวอย่าง: ซื้อ NVDA 10 @ 875"

    ticker = m.group(1).upper()
    qty = float(m.group(2))
    price = float(m.group(3))
    total = qty * price
    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')

    if ticker in portfolio['holdings']:
        old = portfolio['holdings'][ticker]
        total_qty = old['qty'] + qty
        avg_price = ((old['qty'] * old['avg_price']) + (qty * price)) / total_qty
        portfolio['holdings'][ticker] = {'qty': total_qty, 'avg_price': round(avg_price, 4)}
    else:
        portfolio['holdings'][ticker] = {'qty': qty, 'avg_price': price}

    portfolio['transactions'].append({
        'type': 'BUY', 'ticker': ticker,
        'qty': qty, 'price': price,
        'total': total, 'date': now
    })
    save_portfolio(portfolio)
    log_transaction_to_sheet('BUY', ticker, qty, price)
    update_portfolio_sheet(portfolio)

    return (
        f"✅ บันทึกการซื้อแล้ว\n"
        f"หุ้น: {ticker}\n"
        f"จำนวน: {qty} หุ้น @ {price:.2f}\n"
        f"มูลค่ารวม: {total:,.2f}\n"
        f"ราคาเฉลี่ย: {portfolio['holdings'][ticker]['avg_price']:.2f}\n"
        f"📊 บันทึกลง Google Sheets แล้ว"
    )

def handle_sell(text, portfolio):
    m = re.search(r'ขาย\s+(\S+)\s+([\d.]+)\s*@\s*([\d.]+)', text, re.IGNORECASE)
    if not m:
        return "รูปแบบไม่ถูกต้องครับ\nตัวอย่าง: ขาย NVDA 5 @ 920"

    ticker = m.group(1).upper()
    qty = float(m.group(2))
    price = float(m.group(3))
    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')

    if ticker not in portfolio['holdings']:
        return f"ไม่พบ {ticker} ในพอร์ตครับ"

    holding = portfolio['holdings'][ticker]
    if qty > holding['qty']:
        return f"มีแค่ {holding['qty']} หุ้น ขายไม่ได้ {qty} หุ้นครับ"

    avg_price = holding['avg_price']
    pnl = (price - avg_price) * qty
    pnl_pct = ((price - avg_price) / avg_price) * 100
    pnl_icon = "✅" if pnl >= 0 else "❌"

    holding['qty'] -= qty
    if holding['qty'] <= 0:
        del portfolio['holdings'][ticker]
    else:
        portfolio['holdings'][ticker] = holding

    portfolio['transactions'].append({
        'type': 'SELL', 'ticker': ticker,
        'qty': qty, 'price': price,
        'pnl': round(pnl, 2), 'date': now
    })
    save_portfolio(portfolio)
    log_transaction_to_sheet('SELL', ticker, qty, price, round(pnl, 2))
    update_portfolio_sheet(portfolio)

    return (
        f"{pnl_icon} บันทึกการขายแล้ว\n"
        f"หุ้น: {ticker}\n"
        f"จำนวน: {qty} หุ้น @ {price:.2f}\n"
        f"ต้นทุนเฉลี่ย: {avg_price:.2f}\n"
        f"กำไร/ขาดทุน: {pnl:+,.2f} ({pnl_pct:+.1f}%)\n"
        f"📊 บันทึกลง Google Sheets แล้ว"
    )

def handle_portfolio(portfolio):
    if not portfolio['holdings']:
        return "ยังไม่มีหุ้นในพอร์ตครับ\nพิมพ์ เช่น: ซื้อ NVDA 10 @ 875"

    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
    lines = [f"📊 พอร์ตของคุณ\n🕐 {now}\n{'─'*22}"]

    total_cost = 0
    total_value = 0

    for ticker, h in portfolio['holdings'].items():
        qty = h['qty']
        avg = h['avg_price']
        curr = get_current_price(ticker)

        if curr:
            pnl = (curr - avg) * qty
            pnl_pct = ((curr - avg) / avg) * 100
            value = curr * qty
            icon = "📈" if pnl >= 0 else "📉"
            lines.append(
                f"{icon} {ticker}\n"
                f"   {qty} หุ้น | ต้นทุน: {avg:.2f}\n"
                f"   ราคาปัจจุบัน: {curr:.2f}\n"
                f"   P/L: {pnl:+,.2f} ({pnl_pct:+.1f}%)"
            )
            total_cost += avg * qty
            total_value += value
        else:
            lines.append(f"• {ticker}: {qty} หุ้น @ {avg:.2f}")
            total_cost += avg * qty

    total_pnl = total_value - total_cost
    total_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    total_icon = "✅" if total_pnl >= 0 else "❌"

    lines.append(f"{'─'*22}")
    lines.append(
        f"{total_icon} รวมพอร์ต\n"
        f"   มูลค่า: {total_value:,.2f}\n"
        f"   P/L รวม: {total_pnl:+,.2f} ({total_pct:+.1f}%)"
    )
    return "\n".join(lines)

def handle_history(portfolio):
    txs = portfolio.get('transactions', [])
    if not txs:
        return "ยังไม่มีประวัติการซื้อขายครับ"

    last10 = txs[-10:][::-1]
    lines = [f"📋 ประวัติล่าสุด 10 รายการ\n{'─'*22}"]
    for tx in last10:
        icon = "🔵" if tx['type'] == 'BUY' else "🔴"
        pnl_text = f" | P/L: {tx['pnl']:+,.2f}" if 'pnl' in tx else ""
        lines.append(
            f"{icon} {tx['type']} {tx['ticker']}\n"
            f"   {tx['qty']} หุ้น @ {tx['price']:.2f}{pnl_text}\n"
            f"   {tx['date']}"
        )
    return "\n".join(lines)

def handle_pnl(portfolio):
    txs = [t for t in portfolio.get('transactions', []) if t['type'] == 'SELL' and 'pnl' in t]
    if not txs:
        return "ยังไม่มีการขายหุ้นครับ"

    total_pnl = sum(t['pnl'] for t in txs)
    win = [t for t in txs if t['pnl'] > 0]
    lose = [t for t in txs if t['pnl'] <= 0]
    win_rate = (len(win) / len(txs) * 100) if txs else 0
    icon = "✅" if total_pnl >= 0 else "❌"

    return (
        f"{icon} สรุป P/L ทั้งหมด\n"
        f"{'─'*22}\n"
        f"กำไร/ขาดทุนรวม: {total_pnl:+,.2f}\n"
        f"จำนวนครั้งที่ขาย: {len(txs)} ครั้ง\n"
        f"ชนะ: {len(win)} | แพ้: {len(lose)}\n"
        f"Win Rate: {win_rate:.1f}%"
    )

def process_message(text, portfolio):
    text = text.strip()
    if re.search(r'^ซื้อ\s+', text):
        return handle_buy(text, portfolio)
    elif re.search(r'^ขาย\s+', text):
        return handle_sell(text, portfolio)
    elif text in ['พอร์ต', 'port', 'portfolio', 'ดูพอร์ต']:
        return handle_portfolio(portfolio)
    elif text in ['ประวัติ', 'history', 'รายการ']:
        return handle_history(portfolio)
    elif text in ['p/l', 'pl', 'กำไร', 'กำไรขาดทุน', 'pnl']:
        return handle_pnl(portfolio)
    elif text in ['ช่วยเหลือ', 'help', '?', 'คำสั่ง']:
        return (
            "📖 คำสั่งที่ใช้ได้\n"
            "─────────────────\n"
            "ซื้อ NVDA 10 @ 875\n"
            "ขาย NVDA 5 @ 920\n"
            "พอร์ต — ดูหุ้นที่ถืออยู่\n"
            "p/l — สรุปกำไรขาดทุน\n"
            "ประวัติ — รายการซื้อขาย\n"
            "─────────────────\n"
            "หรือถามเรื่องหุ้นได้เลย\n"
            "เช่น: NVDA น่าซื้อไหม"
        )
    else:
        return ask_claude(text)

@app.route('/', methods=['GET', 'POST', 'HEAD', 'OPTIONS'])
def index():
    if request.method == 'POST':
        try:
            body = request.get_json(force=True, silent=True)
            if body and 'events' in body:
                portfolio = load_portfolio()
                for event in body['events']:
                    if event.get('type') == 'message' and event['message'].get('type') == 'text':
                        reply_token = event['replyToken']
                        user_text = event['message']['text']
                        print(f"[USER] {user_text}")
                        response = process_message(user_text, portfolio)
                        reply_to_line(reply_token, response)
        except Exception as e:
            print(f"[ERROR] {e}")
    return 'OK', 200

@app.route('/webhook', methods=['GET', 'POST', 'HEAD', 'OPTIONS'])
def webhook():
    if request.method == 'POST':
        try:
            body = request.get_json(force=True, silent=True)
            if body and 'events' in body:
                portfolio = load_portfolio()
                for event in body['events']:
                    if event.get('type') == 'message' and event['message'].get('type') == 'text':
                        reply_token = event['replyToken']
                        user_text = event['message']['text']
                        print(f"[USER] {user_text}")
                        response = process_message(user_text, portfolio)
                        reply_to_line(reply_token, response)
        except Exception as e:
            print(f"[ERROR] {e}")
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
