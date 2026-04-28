"""
portfolio_routes.py  —  Flask Blueprint for portfolio management
Exposes REST endpoints and exports handler functions used by webhook.py.
"""
from flask import Blueprint, jsonify
import yfinance as yf, pandas as pd
import os, json, re
from datetime import datetime, timezone, timedelta
import gspread
from google.oauth2.service_account import Credentials

portfolio_bp = Blueprint('portfolio', __name__, url_prefix='/portfolio')

TZ_THAI            = timezone(timedelta(hours=7))
PORTFOLIO_FILE     = 'portfolio.json'
SPREADSHEET_ID     = os.getenv('SPREADSHEET_ID')
GOOGLE_CREDENTIALS = os.getenv('GOOGLE_CREDENTIALS')
LINE_TOKEN         = os.getenv('LINE_ACCESS_TOKEN')


# ── shared helpers ────────────────────────────────────────────────

def get_gsheet():
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        scopes = ['https://www.googleapis.com/auth/spreadsheets',
                  'https://www.googleapis.com/auth/drive']
        creds  = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        print(f"[GSHEET] {e}"); return None


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
        if not sh: return
        ws  = sh.worksheet('Transactions')
        now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
        ws.append_row([now, tx_type, ticker, round(qty, 6), round(price, 4),
                       f"{total_orig:.2f} {currency}", pnl if pnl else ''])
    except Exception as e:
        print(f"[SHEET LOG] {e}")


def update_portfolio_sheet(portfolio):
    try:
        sh = get_gsheet()
        if not sh: return
        ws = sh.worksheet('Portfolio')
        ws.clear()
        ws.append_row(['Ticker', 'จำนวน', 'ราคาเฉลี่ย', 'ราคาปัจจุบัน',
                       'มูลค่า (USD)', 'P/L (USD)', 'P/L %', 'อัปเดต'])
        now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
        for ticker, h in portfolio['holdings'].items():
            qty, avg = h['qty'], h['avg_price']
            curr = get_current_price(ticker)
            if curr:
                pnl = (curr - avg) * qty
                pct = ((curr - avg) / avg) * 100
                ws.append_row([ticker, round(qty, 6), round(avg, 4), round(curr, 4),
                               round(curr * qty, 2), round(pnl, 2), round(pct, 2), now])
            else:
                ws.append_row([ticker, round(qty, 6), round(avg, 4),
                               'N/A', 'N/A', 'N/A', 'N/A', now])
    except Exception as e:
        print(f"[SHEET PORT] {e}")


# ── portfolio data I/O ────────────────────────────────────────────

def load_portfolio():
    try:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {"holdings": {}, "transactions": [], "alerts": {}}


def save_portfolio(data):
    try:
        with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[SAVE] {e}")


# ── portfolio command handlers ────────────────────────────────────

def parse_currency(raw):
    if not raw: return 'USD'
    raw = raw.upper().strip()
    if raw in ['THB', 'บาท', '฿']: return 'THB'
    return 'USD'


def handle_buy(text, portfolio):
    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
    mA  = re.search(r'ซื้อ\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*@\s*([\d.]+)', text, re.IGNORECASE)
    mB  = re.search(r'ซื้อ\s+([\w.\-]+)\s+([\d.]+)\s*@\s*([\d.]+)', text, re.IGNORECASE)
    mC  = re.search(r'ซื้อ\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*$', text, re.IGNORECASE)
    if mA:
        ticker = mA.group(1).upper(); amount = float(mA.group(2))
        currency = parse_currency(mA.group(3)); price_local = float(mA.group(4))
        qty = amount / price_local
        if currency == 'THB':
            fx = get_fx_rate('THB'); price_usd = price_local * fx; total_usd = amount * fx
        else:
            price_usd = price_local; total_usd = amount
        total_orig = amount
    elif mB:
        ticker = mB.group(1).upper(); qty = float(mB.group(2)); price_usd = float(mB.group(3))
        total_usd = qty * price_usd; total_orig = total_usd; currency = 'USD'
    elif mC:
        ticker = mC.group(1).upper(); amount = float(mC.group(2)); currency = parse_currency(mC.group(3))
        curr_price = get_current_price(ticker)
        if not curr_price: return f"ดึงราคา {ticker} ไม่ได้ครับ"
        if currency == 'THB':
            fx = get_fx_rate('THB'); total_usd = amount * fx; qty = total_usd / curr_price
        else:
            total_usd = amount; qty = amount / curr_price
        price_usd = curr_price; total_orig = amount
    else:
        return "รูปแบบไม่ถูกต้องครับ\nตัวอย่าง: ซื้อ AAPL 1000 THB"
    if ticker in portfolio['holdings']:
        old = portfolio['holdings'][ticker]
        tq  = old['qty'] + qty
        ap  = ((old['qty'] * old['avg_price']) + (qty * price_usd)) / tq
        portfolio['holdings'][ticker] = {'qty': round(tq, 6), 'avg_price': round(ap, 4)}
    else:
        portfolio['holdings'][ticker] = {'qty': round(qty, 6), 'avg_price': round(price_usd, 4)}
    portfolio['transactions'].append({'type': 'BUY', 'ticker': ticker, 'qty': round(qty, 6),
        'price': round(price_usd, 4), 'total_usd': round(total_usd, 2), 'date': now})
    save_portfolio(portfolio)
    log_transaction_to_sheet('BUY', ticker, qty, price_usd, total_orig, currency)
    update_portfolio_sheet(portfolio)
    cur_txt = f"{total_orig:,.2f} {currency}" + (f" ({total_usd:.2f} USD)" if currency == 'THB' else "")
    return (f"✅ บันทึกการซื้อแล้ว\nหุ้น: {ticker}\nราคา: {price_usd:.4f} USD\n"
            f"จำนวน: {qty:.4f} หน่วย\nเงินที่ใช้: {cur_txt}\n"
            f"ราคาเฉลี่ย: {portfolio['holdings'][ticker]['avg_price']:.4f} USD\n📊 บันทึกลง Sheets แล้ว")


def handle_sell(text, portfolio):
    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
    mA  = re.search(r'ขาย\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*@\s*([\d.]+)', text, re.IGNORECASE)
    mB  = re.search(r'ขาย\s+([\w.\-]+)\s+([\d.]+)\s*@\s*([\d.]+)', text, re.IGNORECASE)
    mC  = re.search(r'ขาย\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*$', text, re.IGNORECASE)
    if mA:
        ticker = mA.group(1).upper(); amount = float(mA.group(2))
        currency = parse_currency(mA.group(3)); price_local = float(mA.group(4))
        qty = amount / price_local
        price_usd = price_local * get_fx_rate('THB') if currency == 'THB' else price_local
    elif mB:
        ticker = mB.group(1).upper(); qty = float(mB.group(2)); price_usd = float(mB.group(3)); currency = 'USD'
    elif mC:
        ticker = mC.group(1).upper(); amount = float(mC.group(2)); currency = parse_currency(mC.group(3))
        curr_price = get_current_price(ticker)
        if not curr_price: return f"ดึงราคา {ticker} ไม่ได้ครับ"
        fx = get_fx_rate('THB') if currency == 'THB' else 1.0
        qty = (amount * fx) / curr_price; price_usd = curr_price
    else:
        return "รูปแบบไม่ถูกต้องครับ\nตัวอย่าง: ขาย AAPL 500 USD"
    if ticker not in portfolio['holdings']: return f"ไม่พบ {ticker} ในพอร์ตครับ"
    h = portfolio['holdings'][ticker]
    if qty > h['qty'] + 0.000001: return f"มีแค่ {h['qty']:.4f} หน่วยครับ"
    pnl = (price_usd - h['avg_price']) * qty
    pct = ((price_usd - h['avg_price']) / h['avg_price']) * 100
    h['qty'] = round(h['qty'] - qty, 6)
    if h['qty'] <= 0.000001:
        del portfolio['holdings'][ticker]
    else:
        portfolio['holdings'][ticker] = h
    portfolio['transactions'].append({'type': 'SELL', 'ticker': ticker, 'qty': round(qty, 6),
        'price': round(price_usd, 4), 'pnl': round(pnl, 2), 'date': now})
    save_portfolio(portfolio)
    log_transaction_to_sheet('SELL', ticker, qty, price_usd, qty * price_usd, 'USD', round(pnl, 2))
    update_portfolio_sheet(portfolio)
    fx = get_fx_rate('THB'); pnl_thb = pnl / fx if fx > 0 else 0
    icon = "✅" if pnl >= 0 else "❌"
    return (f"{icon} บันทึกการขายแล้ว\nหุ้น: {ticker}\n"
            f"จำนวน: {qty:.4f} หน่วย @ {price_usd:.4f} USD\n"
            f"P/L: {pnl:+.2f} USD ({pct:+.1f}%)\n"
            f"P/L (THB): {pnl_thb:+,.2f} บาท\n📊 บันทึกลง Sheets แล้ว")


def handle_portfolio(portfolio):
    if not portfolio['holdings']: return "ยังไม่มีหุ้นในพอร์ตครับ"
    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
    fx  = get_fx_rate('THB')
    lines = [f"📊 พอร์ตของคุณ\n🕐 {now}\n{'─'*22}"]
    tc, tv = 0, 0
    for ticker, h in portfolio['holdings'].items():
        qty, avg = h['qty'], h['avg_price']
        curr = get_current_price(ticker)
        if curr:
            pnl = (curr - avg) * qty; pct = ((curr - avg) / avg) * 100; val = curr * qty
            pnl_thb = pnl / fx if fx > 0 else 0; icon = "📈" if pnl >= 0 else "📉"
            lines.append(f"{icon} {ticker}\n   {qty:.4f} หน่วย | ต้นทุน: {avg:.4f}\n"
                         f"   ราคา: {curr:.4f}  P/L: {pnl:+.2f} USD ({pct:+.1f}%)\n"
                         f"   P/L (THB): {pnl_thb:+,.2f} บาท")
            tc += avg * qty; tv += val
        else:
            lines.append(f"• {ticker}: {qty:.4f} หน่วย @ {avg:.4f}"); tc += avg * qty
    tot_pnl = tv - tc; tot_pct = (tot_pnl / tc * 100) if tc > 0 else 0
    tot_thb = tot_pnl / fx if fx > 0 else 0; ti = "✅" if tot_pnl >= 0 else "❌"
    lines.append(f"{'─'*22}\n{ti} รวมพอร์ต\n   มูลค่า: {tv:,.2f} USD\n"
                 f"   P/L: {tot_pnl:+,.2f} USD ({tot_pct:+.1f}%)\n"
                 f"   P/L (THB): {tot_thb:+,.2f} บาท")
    return "\n".join(lines)


def handle_history(portfolio):
    txs = portfolio.get('transactions', [])
    if not txs: return "ยังไม่มีประวัติครับ"
    lines = [f"📋 ประวัติล่าสุด 10 รายการ\n{'─'*22}"]
    for tx in txs[-10:][::-1]:
        icon = "🔵" if tx['type'] == 'BUY' else "🔴"
        pnl_txt = f" | P/L: {tx['pnl']:+,.2f} USD" if 'pnl' in tx else ""
        lines.append(f"{icon} {tx['type']} {tx['ticker']}\n"
                     f"   {tx['qty']:.4f} @ {tx['price']:.4f}{pnl_txt}\n   {tx['date']}")
    return "\n".join(lines)


def handle_pnl(portfolio):
    txs = [t for t in portfolio.get('transactions', []) if t['type'] == 'SELL' and 'pnl' in t]
    if not txs: return "ยังไม่มีการขายครับ"
    tp   = sum(t['pnl'] for t in txs)
    win  = [t for t in txs if t['pnl'] > 0]
    lose = [t for t in txs if t['pnl'] <= 0]
    wr   = (len(win) / len(txs) * 100) if txs else 0
    fx   = get_fx_rate('THB'); tp_thb = tp / fx if fx > 0 else 0
    icon = "✅" if tp >= 0 else "❌"
    return (f"{icon} สรุป P/L ทั้งหมด\n{'─'*22}\nกำไร/ขาดทุนรวม: {tp:+,.2f} USD\n"
            f"P/L (THB): {tp_thb:+,.2f} บาท\nจำนวนครั้งขาย: {len(txs)}\n"
            f"ชนะ: {len(win)} | แพ้: {len(lose)}\nWin Rate: {wr:.1f}%")


def handle_alerts_list(portfolio):
    alerts = portfolio.get('alerts', {})
    if not alerts: return "ยังไม่มี Alert ที่ตั้งไว้ครับ"
    lines = ["🔔 Alerts ที่ตั้งไว้\n" + "─"*22]
    for ticker, a in alerts.items():
        status = "✅ Triggered" if a.get('triggered') else "⏳ รอ"
        lines.append(f"{ticker}  TP:{a['tp']:.2f}  SL:{a['sl']:.2f}  {status}")
    return "\n".join(lines)


# ── REST endpoints ────────────────────────────────────────────────

@portfolio_bp.route('/', methods=['GET'])
def api_portfolio():
    portfolio = load_portfolio()
    holdings  = []
    for ticker, h in portfolio['holdings'].items():
        qty, avg = h['qty'], h['avg_price']
        curr = get_current_price(ticker)
        entry = {'ticker': ticker, 'qty': qty, 'avg_price': avg, 'current_price': curr}
        if curr:
            entry['pnl_usd']  = round((curr - avg) * qty, 2)
            entry['pnl_pct']  = round(((curr - avg) / avg) * 100, 2)
            entry['value_usd'] = round(curr * qty, 2)
        holdings.append(entry)
    return jsonify({'holdings': holdings})


@portfolio_bp.route('/history', methods=['GET'])
def api_history():
    portfolio = load_portfolio()
    return jsonify({'transactions': portfolio.get('transactions', [])})


@portfolio_bp.route('/pnl', methods=['GET'])
def api_pnl():
    portfolio = load_portfolio()
    txs  = [t for t in portfolio.get('transactions', []) if t['type'] == 'SELL' and 'pnl' in t]
    tp   = sum(t['pnl'] for t in txs)
    win  = len([t for t in txs if t['pnl'] > 0])
    lose = len([t for t in txs if t['pnl'] <= 0])
    fx   = get_fx_rate('THB')
    return jsonify({
        'total_pnl_usd':  round(tp, 2),
        'total_pnl_thb':  round(tp / fx, 2) if fx > 0 else 0,
        'total_trades':   len(txs),
        'wins':           win,
        'losses':         lose,
        'win_rate_pct':   round(win / len(txs) * 100, 1) if txs else 0,
    })


@portfolio_bp.route('/alerts', methods=['GET'])
def api_alerts():
    portfolio = load_portfolio()
    return jsonify({'alerts': portfolio.get('alerts', {})})
