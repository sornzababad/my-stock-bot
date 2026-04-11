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

def get_current_price(ticker):
    try:
        df = yf.download(ticker, period='2d', interval='1d', progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return float(df['Close'].iloc[-1])
    except:
        return None

def get_fx_rate(from_currency):
    try:
        if from_currency == 'THB':
            df = yf.download('THBUSD=X', period='2d', interval='1d', progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return float(df['Close'].iloc[-1])
        return 1.0
    except:
        return 0.03

def log_transaction_to_sheet(tx_type, ticker, qty, price, total_orig, currency, pnl=None):
    try:
        sh = get_gsheet()
        if not sh:
            return
        ws = sh.worksheet('Transactions')
        now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
        row = [now, tx_type, ticker, round(qty, 6), round(price, 4),
               f"{total_orig:.2f} {currency}", pnl if pnl else '']
        ws.append_row(row)
    except Exception as e:
        print(f"[SHEET LOG ERROR] {e}")

def update_portfolio_sheet(portfolio):
    try:
        sh = get_gsheet()
        if not sh:
            return
        ws = sh.worksheet('Portfolio')
        ws.clear()
        ws.append_row(['Ticker', 'จำนวน', 'ราคาเฉลี่ย', 'ราคาปัจจุบัน', 'มูลค่า (USD)', 'P/L (USD)', 'P/L %', 'อัปเดต'])
        now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
        for ticker, h in portfolio['holdings'].items():
            qty = h['qty']
            avg = h['avg_price']
            curr = get_current_price(ticker)
            if curr:
                pnl = (curr - avg) * qty
                pnl_pct = ((curr - avg) / avg) * 100
                value = curr * qty
                ws.append_row([ticker, round(qty, 6), round(avg, 4), round(curr, 4),
                               round(value, 2), round(pnl, 2), round(pnl_pct, 2), now])
            else:
                ws.append_row([ticker, round(qty, 6), round(avg, 4), 'N/A', 'N/A', 'N/A', 'N/A', now])
    except Exception as e:
        print(f"[SHEET PORTFOLIO ERROR] {e}")

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

def parse_currency(raw):
    if not raw:
        return 'USD'
    raw = raw.upper().strip()
    if raw in ['THB', 'บาท', '฿']:
        return 'THB'
    if raw in ['USD', '$']:
        return 'USD'
    return 'USD'

def handle_buy(text, portfolio):
    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')

    # รูปแบบ A: ซื้อ US500-UH-E 1000 THB @ 15.23 (เงิน + สกุล + ราคา)
    mA = re.search(r'ซื้อ\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*@\s*([\d.]+)', text, re.IGNORECASE)
    # รูปแบบ B: ซื้อ AAPL 5 @ 200 (จำนวนหุ้น @ ราคา ไม่มีสกุลเงิน)
    mB = re.search(r'ซื้อ\s+([\w.\-]+)\s+([\d.]+)\s*@\s*([\d.]+)', text, re.IGNORECASE)
    # รูปแบบ C: ซื้อ AAPL 1000 THB (เงิน + สกุล ดึงราคาเอง)
    mC = re.search(r'ซื้อ\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*$', text, re.IGNORECASE)

    if mA:
        ticker = mA.group(1).upper()
        amount = float(mA.group(2))
        currency = parse_currency(mA.group(3))
        price_local = float(mA.group(4))
        qty = amount / price_local

        if currency == 'THB':
            fx = get_fx_rate('THB')
            price_usd = price_local * fx
            total_usd = amount * fx
        else:
            price_usd = price_local
            total_usd = amount

        total_orig = amount

    elif mB:
        ticker = mB.group(1).upper()
        qty = float(mB.group(2))
        price_usd = float(mB.group(3))
        total_usd = qty * price_usd
        total_orig = total_usd
        currency = 'USD'

    elif mC:
        ticker = mC.group(1).upper()
        amount = float(mC.group(2))
        currency = parse_currency(mC.group(3))

        curr_price = get_current_price(ticker)
        if not curr_price:
            return (
                f"ดึงราคา {ticker} ไม่ได้ครับ\n"
                f"ลองใส่ราคาเองได้เลย เช่น:\n"
                f"ซื้อ {ticker} {amount} {currency} @ 15.23"
            )

        if currency == 'THB':
            fx = get_fx_rate('THB')
            total_usd = amount * fx
            qty = total_usd / curr_price
        else:
            total_usd = amount
            qty = amount / curr_price

        price_usd = curr_price
        total_orig = amount

    else:
        return (
            "รูปแบบไม่ถูกต้องครับ ตัวอย่าง:\n"
            "ซื้อ AAPL 1000 THB\n"
            "ซื้อ AAPL 500 USD\n"
            "ซื้อ AAPL 5 @ 200\n"
            "ซื้อ US500-UH-E 1000 THB @ 15.23"
        )

    if ticker in portfolio['holdings']:
        old = portfolio['holdings'][ticker]
        total_qty = old['qty'] + qty
        avg_price = ((old['qty'] * old['avg_price']) + (qty * price_usd)) / total_qty
        portfolio['holdings'][ticker] = {'qty': round(total_qty, 6), 'avg_price': round(avg_price, 4)}
    else:
        portfolio['holdings'][ticker] = {'qty': round(qty, 6), 'avg_price': round(price_usd, 4)}

    portfolio['transactions'].append({
        'type': 'BUY', 'ticker': ticker,
        'qty': round(qty, 6), 'price': round(price_usd, 4),
        'total_usd': round(total_usd, 2),
        'total_orig': round(total_orig, 2),
        'currency': currency, 'date': now
    })
    save_portfolio(portfolio)
    log_transaction_to_sheet('BUY', ticker, qty, price_usd, total_orig, currency)
    update_portfolio_sheet(portfolio)

    currency_text = f"{total_orig:,.2f} {currency}"
    if currency == 'THB':
        currency_text += f" ({total_usd:.2f} USD)"

    return (
        f"✅ บันทึกการซื้อแล้ว\n"
        f"หุ้น: {ticker}\n"
        f"ราคา: {price_usd:.4f} USD\n"
        f"จำนวน: {qty:.4f} หน่วย\n"
        f"เงินที่ใช้: {currency_text}\n"
        f"ราคาเฉลี่ย: {portfolio['holdings'][ticker]['avg_price']:.4f} USD\n"
        f"📊 บันทึกลง Google Sheets แล้ว"
    )

def handle_sell(text, portfolio):
    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')

    # รูปแบบ A: ขาย US500-UH-E 1000 THB @ 16.00
    mA = re.search(r'ขาย\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*@\s*([\d.]+)', text, re.IGNORECASE)
    # รูปแบบ B: ขาย AAPL 5 @ 210
    mB = re.search(r'ขาย\s+([\w.\-]+)\s+([\d.]+)\s*@\s*([\d.]+)', text, re.IGNORECASE)
    # รูปแบบ C: ขาย AAPL 500 USD
    mC = re.search(r'ขาย\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*$', text, re.IGNORECASE)

    if mA:
        ticker = mA.group(1).upper()
        amount = float(mA.group(2))
        currency = parse_currency(mA.group(3))
        price_local = float(mA.group(4))
        qty = amount / price_local
        if currency == 'THB':
            fx = get_fx_rate('THB')
            price_usd = price_local * fx
        else:
            price_usd = price_local

    elif mB:
        ticker = mB.group(1).upper()
        qty = float(mB.group(2))
        price_usd = float(mB.group(3))
        currency = 'USD'

    elif mC:
        ticker = mC.group(1).upper()
        amount = float(mC.group(2))
        currency = parse_currency(mC.group(3))
        curr_price = get_current_price(ticker)
        if not curr_price:
            return (
                f"ดึงราคา {ticker} ไม่ได้ครับ\n"
                f"ลองใส่ราคาเองได้เลย เช่น:\n"
                f"ขาย {ticker} {amount} {currency} @ 16.00"
            )
        if currency == 'THB':
            fx = get_fx_rate('THB')
            qty = (amount * fx) / curr_price
        else:
            qty = amount / curr_price
        price_usd = curr_price

    else:
        return (
            "รูปแบบไม่ถูกต้องครับ ตัวอย่าง:\n"
            "ขาย AAPL 500 USD\n"
            "ขาย AAPL 5 @ 210\n"
            "ขาย US500-UH-E 1000 THB @ 16.00"
        )

    if ticker not in portfolio['holdings']:
        return f"ไม่พบ {ticker} ในพอร์ตครับ"

    holding = portfolio['holdings'][ticker]
    if qty > holding['qty'] + 0.000001:
        return f"มีแค่ {holding['qty']:.4f} หน่วย ขายไม่ได้ {qty:.4f} หน่วยครับ"

    avg_price = holding['avg_price']
    pnl_usd = (price_usd - avg_price) * qty
    pnl_pct = ((price_usd - avg_price) / avg_price) * 100
    pnl_icon = "✅" if pnl_usd >= 0 else "❌"

    holding['qty'] = round(holding['qty'] - qty, 6)
    if holding['qty'] <= 0.000001:
        del portfolio['holdings'][ticker]
    else:
        portfolio['holdings'][ticker] = holding

    portfolio['transactions'].append({
        'type': 'SELL', 'ticker': ticker,
        'qty': round(qty, 6), 'price': round(price_usd, 4),
        'pnl': round(pnl_usd, 2), 'date': now
    })
    save_portfolio(portfolio)
    log_transaction_to_sheet('SELL', ticker, qty, price_usd, qty * price_usd, 'USD', round(pnl_usd, 2))
    update_portfolio_sheet(portfolio)

    fx = get_fx_rate('THB')
    pnl_thb = pnl_usd / fx if fx > 0 else 0

    return (
        f"{pnl_icon} บันทึกการขายแล้ว\n"
        f"หุ้น: {ticker}\n"
        f"จำนวน: {qty:.4f} หน่วย @ {price_usd:.4f} USD\n"
        f"ต้นทุนเฉลี่ย: {avg_price:.4f} USD\n"
        f"P/L: {pnl_usd:+.2f} USD ({pnl_pct:+.1f}%)\n"
        f"P/L (THB): {pnl_thb:+,.2f} บาท\n"
        f"📊 บันทึกลง Google Sheets แล้ว"
    )

def handle_portfolio(portfolio):
    if not portfolio['holdings']:
        return "ยังไม่มีหุ้นในพอร์ตครับ\nตัวอย่าง: ซื้อ AAPL 1000 THB"

    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
    fx = get_fx_rate('THB')
    lines = [f"📊 พอร์ตของคุณ\n🕐 {now}\n{'─'*22}"]

    total_cost_usd = 0
    total_value_usd = 0

    for ticker, h in portfolio['holdings'].items():
        qty = h['qty']
        avg = h['avg_price']
        curr = get_current_price(ticker)

        if curr:
            pnl_usd = (curr - avg) * qty
            pnl_pct = ((curr - avg) / avg) * 100
            value_usd = curr * qty
            pnl_thb = pnl_usd / fx if fx > 0 else 0
            icon = "📈" if pnl_usd >= 0 else "📉"
            lines.append(
                f"{icon} {ticker}\n"
                f"   {qty:.4f} หน่วย | ต้นทุน: {avg:.4f} USD\n"
                f"   ราคาปัจจุบัน: {curr:.4f} USD\n"
                f"   P/L: {pnl_usd:+.2f} USD ({pnl_pct:+.1f}%)\n"
                f"   P/L (THB): {pnl_thb:+,.2f} บาท"
            )
            total_cost_usd += avg * qty
            total_value_usd += value_usd
        else:
            lines.append(f"• {ticker}: {qty:.4f} หน่วย @ {avg:.4f} USD")
            total_cost_usd += avg * qty

    total_pnl_usd = total_value_usd - total_cost_usd
    total_pct = (total_pnl_usd / total_cost_usd * 100) if total_cost_usd > 0 else 0
    total_pnl_thb = total_pnl_usd / fx if fx > 0 else 0
    total_icon = "✅" if total_pnl_usd >= 0 else "❌"

    lines.append(f"{'─'*22}")
    lines.append(
        f"{total_icon} รวมพอร์ต\n"
        f"   มูลค่า: {total_value_usd:,.2f} USD\n"
        f"   P/L: {total_pnl_usd:+,.2f} USD ({total_pct:+.1f}%)\n"
        f"   P/L (THB): {total_pnl_thb:+,.2f} บาท"
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
        pnl_text = f" | P/L: {tx['pnl']:+,.2f} USD" if 'pnl' in tx else ""
        lines.append(
            f"{icon} {tx['type']} {tx['ticker']}\n"
            f"   {tx['qty']:.4f} หน่วย @ {tx['price']:.4f} USD{pnl_text}\n"
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
    fx = get_fx_rate('THB')
    total_pnl_thb = total_pnl / fx if fx > 0 else 0
    icon = "✅" if total_pnl >= 0 else "❌"

    return (
        f"{icon} สรุป P/L ทั้งหมด\n"
        f"{'─'*22}\n"
        f"กำไร/ขาดทุนรวม: {total_pnl:+,.2f} USD\n"
        f"กำไร/ขาดทุน (THB): {total_pnl_thb:+,.2f} บาท\n"
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
            "ซื้อ AAPL 1000 THB\n"
            "ซื้อ AAPL 500 USD\n"
            "ซื้อ AAPL 5 @ 200\n"
            "ซื้อ US500-UH-E 1000 THB @ 15.23\n"
            "ขาย AAPL 1000 THB\n"
            "ขาย AAPL 5 @ 210\n"
            "ขาย US500-UH-E 1000 THB @ 16.00\n"
            "พอร์ต — ดูหุ้นที่ถืออยู่\n"
            "p/l — สรุปกำไรขาดทุน\n"
            "ประวัติ — รายการซื้อขาย\n"
            "─────────────────\n"
            "หรือถามเรื่องหุ้นได้เลย"
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
