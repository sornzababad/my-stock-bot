"""
webhook.py  —  LINE Messaging API webhook
Features:
  • Ask bot anything: 'วิเคราะห์ AAPL', 'ราคา TSLA', 'พอร์ต', 'p/l' ...
  • Buy / Sell portfolio tracking (THB & USD)
  • Google Sheets sync
  • TP/SL price alert background thread
"""
from flask import Flask, request
import requests, anthropic, yfinance as yf, pandas as pd
import os, json, re, time, threading
from datetime import datetime, timezone, timedelta
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
TZ_THAI            = timezone(timedelta(hours=7))
LINE_TOKEN         = os.getenv('LINE_ACCESS_TOKEN')
ANTHROPIC_API_KEY  = os.getenv('ANTHROPIC_API_KEY')
SPREADSHEET_ID     = os.getenv('SPREADSHEET_ID')
GOOGLE_CREDENTIALS = os.getenv('GOOGLE_CREDENTIALS')

# ── helpers (Google Sheets, price, LINE reply) ────────────────────
# (Keep all your existing helpers exactly as-is — unchanged below)

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
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return float(df['Close'].iloc[-1])
    except: return None

def get_fx_rate(from_currency):
    try:
        if from_currency == 'THB':
            df = yf.download('THBUSD=X', period='2d', interval='1d', progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            return float(df['Close'].iloc[-1])
        return 1.0
    except: return 0.03

def log_transaction_to_sheet(tx_type, ticker, qty, price, total_orig, currency, pnl=None):
    try:
        sh = get_gsheet()
        if not sh: return
        ws  = sh.worksheet('Transactions')
        now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
        ws.append_row([now, tx_type, ticker, round(qty,6), round(price,4),
                       f"{total_orig:.2f} {currency}", pnl if pnl else ''])
    except Exception as e: print(f"[SHEET LOG] {e}")

def update_portfolio_sheet(portfolio):
    try:
        sh = get_gsheet()
        if not sh: return
        ws = sh.worksheet('Portfolio'); ws.clear()
        ws.append_row(['Ticker','จำนวน','ราคาเฉลี่ย','ราคาปัจจุบัน','มูลค่า (USD)','P/L (USD)','P/L %','อัปเดต'])
        now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
        for ticker, h in portfolio['holdings'].items():
            qty, avg = h['qty'], h['avg_price']
            curr = get_current_price(ticker)
            if curr:
                pnl  = (curr-avg)*qty
                pct  = ((curr-avg)/avg)*100
                ws.append_row([ticker,round(qty,6),round(avg,4),round(curr,4),
                               round(curr*qty,2),round(pnl,2),round(pct,2),now])
            else:
                ws.append_row([ticker,round(qty,6),round(avg,4),'N/A','N/A','N/A','N/A',now])
    except Exception as e: print(f"[SHEET PORT] {e}")

PORTFOLIO_FILE = 'portfolio.json'
def load_portfolio():
    try:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE,'r',encoding='utf-8') as f: return json.load(f)
    except: pass
    return {"holdings":{},"transactions":[],"alerts":{}}

def save_portfolio(data):
    try:
        with open(PORTFOLIO_FILE,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
    except Exception as e: print(f"[SAVE] {e}")

def reply_line(reply_token, message):
    requests.post('https://api.line.me/v2/bot/message/reply',
                  headers={'Content-Type':'application/json','Authorization':f'Bearer {LINE_TOKEN}'},
                  json={'replyToken':reply_token,'messages':[{'type':'text','text':message}]},
                  timeout=10)

def push_line(message):
    uid = os.getenv('USER_ID') or os.getenv('LINE_USER_ID')
    if not uid: return
    requests.post('https://api.line.me/v2/bot/message/push',
                  headers={'Content-Type':'application/json','Authorization':f'Bearer {LINE_TOKEN}'},
                  json={'to':uid,'messages':[{'type':'text','text':message}]},
                  timeout=10)

def push_flex(flex_obj):
    uid = os.getenv('USER_ID') or os.getenv('LINE_USER_ID')
    if not uid: return
    alt = flex_obj.get('altText', '')
    msgs = [{'type': 'text', 'text': alt}, flex_obj] if alt else [flex_obj]
    requests.post('https://api.line.me/v2/bot/message/push',
                  headers={'Content-Type':'application/json','Authorization':f'Bearer {LINE_TOKEN}'},
                  json={'to':uid,'messages':msgs},
                  timeout=10)

# ── NEW: AI stock analysis ────────────────────────────────────────

def ask_claude_stock(user_message):
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=500,
            system="""คุณเป็นผู้ช่วยวิเคราะห์หุ้นส่วนตัว ตอบภาษาไทยสั้นกระชับ
เชี่ยวชาญด้านเทคนิคอลและปัจจัยพื้นฐาน ตอบไม่เกิน 5 บรรทัด
ถ้าถามนอกเรื่องหุ้นให้บอกว่าตอบได้เฉพาะเรื่องการลงทุน""",
            messages=[{"role":"user","content":user_message}])
        return msg.content[0].text
    except Exception as e: return f"ขออภัย เกิดข้อผิดพลาด: {e}"

def quick_analysis(ticker: str) -> str:
    """Fetch live data + ask Claude for quick analysis."""
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df.empty: return f"ไม่พบข้อมูล {ticker} ครับ"
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        price = float(df['Close'].iloc[-1])
        d     = df['Close'].diff()
        rsi   = float((100-(100/(1+d.where(d>0,0).rolling(14).mean()/
                              (-d.where(d<0,0)).rolling(14).mean()))).iloc[-1])
        ema20 = float(df['Close'].ewm(span=20,adjust=False).mean().iloc[-1])
        ema50 = float(df['Close'].ewm(span=50,adjust=False).mean().iloc[-1])
        trend = "Uptrend ✅" if ema20 > ema50 else "Downtrend ⚠️"
        prompt = (f"วิเคราะห์ {ticker} ราคา {price:.2f}  RSI {rsi:.1f}  "
                  f"EMA20 {'>' if ema20>ema50 else '<'} EMA50 ({trend})\n"
                  f"บอกสั้นๆ 3 บรรทัด: แนวโน้ม / สิ่งที่น่าสังเกต / ข้อควรระวัง")
        ai = ask_claude_stock(prompt)
        tv = f"https://www.tradingview.com/chart/?symbol={'SET:'+ticker if ticker.endswith('.BK') else ticker}&interval=D"
        return (f"📌 {ticker}  ราคา {price:.2f}\n"
                f"RSI {rsi:.1f}  |  {trend}\n"
                f"──────────────────\n"
                f"{ai}\n"
                f"──────────────────\n"
                f"📊 Chart: {tv}")
    except Exception as e:
        return f"เกิดข้อผิดพลาด: {e}"

# ── NEW: TP/SL alert system ───────────────────────────────────────

def set_alert(text, portfolio):
    """
    Format:  ตั้ง alert AAPL TP 220 SL 200
             ตั้ง alert KKP.BK TP 95 SL 82
    """
    m = re.search(r'alert\s+([\w.\-]+)\s+TP\s+([\d.]+)\s+SL\s+([\d.]+)', text, re.IGNORECASE)
    if not m:
        return ("รูปแบบไม่ถูกต้องครับ\n"
                "ตัวอย่าง: ตั้ง alert AAPL TP 220 SL 200\n"
                "หรือ: ตั้ง alert KKP.BK TP 95 SL 82")
    ticker, tp, sl = m.group(1).upper(), float(m.group(2)), float(m.group(3))
    if 'alerts' not in portfolio: portfolio['alerts'] = {}
    portfolio['alerts'][ticker] = {'tp': tp, 'sl': sl, 'triggered': False}
    save_portfolio(portfolio)
    return (f"🔔 ตั้ง Alert แล้วครับ\n"
            f"หุ้น : {ticker}\n"
            f"🎯 TP : {tp:.2f}\n"
            f"🛡 SL : {sl:.2f}\n"
            f"จะแจ้งเตือนทันทีที่ราคาถึง")

def check_alerts():
    """Background thread — checks TP/SL every 5 minutes during market hours."""
    while True:
        try:
            now_h = datetime.now(TZ_THAI).hour
            # Only check during Thai market (9-18) or US market (20-05 ICT)
            if (9 <= now_h <= 18) or (now_h >= 20) or (now_h <= 4):
                portfolio = load_portfolio()
                alerts    = portfolio.get('alerts', {})
                changed   = False
                for ticker, a in list(alerts.items()):
                    if a.get('triggered'): continue
                    price = get_current_price(ticker)
                    if not price: continue
                    if price >= a['tp']:
                        push_line(f"🎯 TP HIT!\n{ticker}  ราคา {price:.2f}\n🟢 ถึง Target {a['tp']:.2f} แล้วครับ!")
                        alerts[ticker]['triggered'] = True; changed = True
                    elif price <= a['sl']:
                        push_line(f"🛡 SL HIT!\n{ticker}  ราคา {price:.2f}\n🔴 ถึง Stop Loss {a['sl']:.2f} แล้วครับ!")
                        alerts[ticker]['triggered'] = True; changed = True
                if changed: save_portfolio(portfolio)
        except Exception as e:
            print(f"[ALERT THREAD] {e}")
        time.sleep(300)  # check every 5 min

# ── portfolio handlers (your original code, unchanged) ────────────

def parse_currency(raw):
    if not raw: return 'USD'
    raw = raw.upper().strip()
    if raw in ['THB','บาท','฿']: return 'THB'
    return 'USD'

def handle_buy(text, portfolio):
    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
    mA  = re.search(r'ซื้อ\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*@\s*([\d.]+)',text,re.IGNORECASE)
    mB  = re.search(r'ซื้อ\s+([\w.\-]+)\s+([\d.]+)\s*@\s*([\d.]+)',text,re.IGNORECASE)
    mC  = re.search(r'ซื้อ\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*$',text,re.IGNORECASE)
    if mA:
        ticker=mA.group(1).upper(); amount=float(mA.group(2))
        currency=parse_currency(mA.group(3)); price_local=float(mA.group(4))
        qty=amount/price_local
        if currency=='THB':
            fx=get_fx_rate('THB'); price_usd=price_local*fx; total_usd=amount*fx
        else:
            price_usd=price_local; total_usd=amount
        total_orig=amount
    elif mB:
        ticker=mB.group(1).upper(); qty=float(mB.group(2)); price_usd=float(mB.group(3))
        total_usd=qty*price_usd; total_orig=total_usd; currency='USD'
    elif mC:
        ticker=mC.group(1).upper(); amount=float(mC.group(2)); currency=parse_currency(mC.group(3))
        curr_price=get_current_price(ticker)
        if not curr_price: return f"ดึงราคา {ticker} ไม่ได้ครับ"
        if currency=='THB':
            fx=get_fx_rate('THB'); total_usd=amount*fx; qty=total_usd/curr_price
        else:
            total_usd=amount; qty=amount/curr_price
        price_usd=curr_price; total_orig=amount
    else:
        return "รูปแบบไม่ถูกต้องครับ\nตัวอย่าง: ซื้อ AAPL 1000 THB"
    if ticker in portfolio['holdings']:
        old=portfolio['holdings'][ticker]
        tq=(old['qty']+qty); ap=((old['qty']*old['avg_price'])+(qty*price_usd))/tq
        portfolio['holdings'][ticker]={'qty':round(tq,6),'avg_price':round(ap,4)}
    else:
        portfolio['holdings'][ticker]={'qty':round(qty,6),'avg_price':round(price_usd,4)}
    portfolio['transactions'].append({'type':'BUY','ticker':ticker,'qty':round(qty,6),
        'price':round(price_usd,4),'total_usd':round(total_usd,2),'date':now})
    save_portfolio(portfolio); log_transaction_to_sheet('BUY',ticker,qty,price_usd,total_orig,currency)
    update_portfolio_sheet(portfolio)
    cur_txt=f"{total_orig:,.2f} {currency}"+( f" ({total_usd:.2f} USD)" if currency=='THB' else "")
    return (f"✅ บันทึกการซื้อแล้ว\nหุ้น: {ticker}\nราคา: {price_usd:.4f} USD\n"
            f"จำนวน: {qty:.4f} หน่วย\nเงินที่ใช้: {cur_txt}\n"
            f"ราคาเฉลี่ย: {portfolio['holdings'][ticker]['avg_price']:.4f} USD\n📊 บันทึกลง Sheets แล้ว")

def handle_sell(text, portfolio):
    now = datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
    mA  = re.search(r'ขาย\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*@\s*([\d.]+)',text,re.IGNORECASE)
    mB  = re.search(r'ขาย\s+([\w.\-]+)\s+([\d.]+)\s*@\s*([\d.]+)',text,re.IGNORECASE)
    mC  = re.search(r'ขาย\s+([\w.\-]+)\s+([\d.]+)\s*(THB|USD|บาท|฿|\$)\s*$',text,re.IGNORECASE)
    if mA:
        ticker=mA.group(1).upper(); amount=float(mA.group(2))
        currency=parse_currency(mA.group(3)); price_local=float(mA.group(4))
        qty=amount/price_local
        price_usd=price_local*get_fx_rate('THB') if currency=='THB' else price_local
    elif mB:
        ticker=mB.group(1).upper(); qty=float(mB.group(2)); price_usd=float(mB.group(3)); currency='USD'
    elif mC:
        ticker=mC.group(1).upper(); amount=float(mC.group(2)); currency=parse_currency(mC.group(3))
        curr_price=get_current_price(ticker)
        if not curr_price: return f"ดึงราคา {ticker} ไม่ได้ครับ"
        fx=get_fx_rate('THB') if currency=='THB' else 1.0
        qty=(amount*fx)/curr_price; price_usd=curr_price
    else:
        return "รูปแบบไม่ถูกต้องครับ\nตัวอย่าง: ขาย AAPL 500 USD"
    if ticker not in portfolio['holdings']: return f"ไม่พบ {ticker} ในพอร์ตครับ"
    h=portfolio['holdings'][ticker]
    if qty>h['qty']+0.000001: return f"มีแค่ {h['qty']:.4f} หน่วยครับ"
    pnl=(price_usd-h['avg_price'])*qty; pct=((price_usd-h['avg_price'])/h['avg_price'])*100
    h['qty']=round(h['qty']-qty,6)
    if h['qty']<=0.000001: del portfolio['holdings'][ticker]
    else: portfolio['holdings'][ticker]=h
    portfolio['transactions'].append({'type':'SELL','ticker':ticker,'qty':round(qty,6),
        'price':round(price_usd,4),'pnl':round(pnl,2),'date':now})
    save_portfolio(portfolio); log_transaction_to_sheet('SELL',ticker,qty,price_usd,qty*price_usd,'USD',round(pnl,2))
    update_portfolio_sheet(portfolio)
    fx=get_fx_rate('THB'); pnl_thb=pnl/fx if fx>0 else 0
    icon="✅" if pnl>=0 else "❌"
    return (f"{icon} บันทึกการขายแล้ว\nหุ้น: {ticker}\n"
            f"จำนวน: {qty:.4f} หน่วย @ {price_usd:.4f} USD\n"
            f"P/L: {pnl:+.2f} USD ({pct:+.1f}%)\n"
            f"P/L (THB): {pnl_thb:+,.2f} บาท\n📊 บันทึกลง Sheets แล้ว")

def handle_portfolio(portfolio):
    if not portfolio['holdings']: return "ยังไม่มีหุ้นในพอร์ตครับ"
    now=datetime.now(TZ_THAI).strftime('%d/%m/%Y %H:%M')
    fx=get_fx_rate('THB'); lines=[f"📊 พอร์ตของคุณ\n🕐 {now}\n{'─'*22}"]
    tc,tv=0,0
    for ticker,h in portfolio['holdings'].items():
        qty,avg=h['qty'],h['avg_price']; curr=get_current_price(ticker)
        if curr:
            pnl=(curr-avg)*qty; pct=((curr-avg)/avg)*100; val=curr*qty
            pnl_thb=pnl/fx if fx>0 else 0; icon="📈" if pnl>=0 else "📉"
            lines.append(f"{icon} {ticker}\n   {qty:.4f} หน่วย | ต้นทุน: {avg:.4f}\n"
                         f"   ราคา: {curr:.4f}  P/L: {pnl:+.2f} USD ({pct:+.1f}%)\n"
                         f"   P/L (THB): {pnl_thb:+,.2f} บาท")
            tc+=avg*qty; tv+=val
        else:
            lines.append(f"• {ticker}: {qty:.4f} หน่วย @ {avg:.4f}"); tc+=avg*qty
    tot_pnl=tv-tc; tot_pct=(tot_pnl/tc*100) if tc>0 else 0
    tot_thb=tot_pnl/fx if fx>0 else 0; ti="✅" if tot_pnl>=0 else "❌"
    lines.append(f"{'─'*22}\n{ti} รวมพอร์ต\n   มูลค่า: {tv:,.2f} USD\n"
                 f"   P/L: {tot_pnl:+,.2f} USD ({tot_pct:+.1f}%)\n"
                 f"   P/L (THB): {tot_thb:+,.2f} บาท")
    return "\n".join(lines)

def handle_history(portfolio):
    txs=portfolio.get('transactions',[])
    if not txs: return "ยังไม่มีประวัติครับ"
    lines=[f"📋 ประวัติล่าสุด 10 รายการ\n{'─'*22}"]
    for tx in txs[-10:][::-1]:
        icon="🔵" if tx['type']=='BUY' else "🔴"
        pnl_txt=f" | P/L: {tx['pnl']:+,.2f} USD" if 'pnl' in tx else ""
        lines.append(f"{icon} {tx['type']} {tx['ticker']}\n   {tx['qty']:.4f} @ {tx['price']:.4f}{pnl_txt}\n   {tx['date']}")
    return "\n".join(lines)

def handle_pnl(portfolio):
    txs=[t for t in portfolio.get('transactions',[]) if t['type']=='SELL' and 'pnl' in t]
    if not txs: return "ยังไม่มีการขายครับ"
    tp=sum(t['pnl'] for t in txs); win=[t for t in txs if t['pnl']>0]; lose=[t for t in txs if t['pnl']<=0]
    wr=(len(win)/len(txs)*100) if txs else 0; fx=get_fx_rate('THB'); tp_thb=tp/fx if fx>0 else 0
    icon="✅" if tp>=0 else "❌"
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

# ── message router ────────────────────────────────────────────────

def process_message(text, portfolio):
    text = text.strip()

    # วิเคราะห์ / ราคา / chart
    m_analyze = re.search(r'^(วิเคราะห์|analyze|chart|ราคา|price)\s+([\w.\-]+)', text, re.IGNORECASE)
    if m_analyze:
        return quick_analysis(m_analyze.group(2).upper())

    # ตั้ง alert
    if re.search(r'^ตั้ง\s*alert', text, re.IGNORECASE):
        return set_alert(text, portfolio)

    # ดู alerts
    if text.lower() in ['alerts','alert','การแจ้งเตือน','ดู alert']:
        return handle_alerts_list(portfolio)

    # buy / sell / portfolio (existing)
    if re.search(r'^ซื้อ\s+', text):      return handle_buy(text, portfolio)
    if re.search(r'^ขาย\s+', text):       return handle_sell(text, portfolio)
    if text in ['พอร์ต','port','portfolio','ดูพอร์ต']: return handle_portfolio(portfolio)
    if text in ['ประวัติ','history','รายการ']:          return handle_history(portfolio)
    if text.lower() in ['p/l','pl','กำไร','pnl']:      return handle_pnl(portfolio)

    if text in ['ช่วยเหลือ','help','?','คำสั่ง']:
        return (
            "📖 คำสั่งที่ใช้ได้\n"
            "─────────────────────\n"
            "🔍 วิเคราะห์ AAPL\n"
            "🔍 ราคา TSLA\n"
            "─────────────────────\n"
            "ซื้อ AAPL 1000 THB\n"
            "ซื้อ AAPL 500 USD\n"
            "ซื้อ AAPL 5 @ 200\n"
            "ขาย AAPL 5 @ 210\n"
            "พอร์ต  |  p/l  |  ประวัติ\n"
            "─────────────────────\n"
            "🔔 ตั้ง alert AAPL TP 220 SL 200\n"
            "🔔 alerts — ดูรายการแจ้งเตือน\n"
            "─────────────────────\n"
            "หรือถามเรื่องหุ้นได้เลยครับ 💬"
        )

    # Fallback → Claude general Q&A
    return ask_claude_stock(text)

# ── Flask routes ──────────────────────────────────────────────────

@app.route('/', methods=['GET','POST','HEAD','OPTIONS'])
@app.route('/webhook', methods=['GET','POST','HEAD','OPTIONS'])
def webhook():
    if request.method == 'POST':
        try:
            body = request.get_json(force=True, silent=True)
            if body and 'events' in body:
                portfolio = load_portfolio()
                for event in body['events']:
                    if event.get('type')=='message' and event['message'].get('type')=='text':
                        rt   = event['replyToken']
                        text = event['message']['text']
                        print(f"[USER] {text}")
                        resp = process_message(text, portfolio)
                        reply_line(rt, resp)
        except Exception as e:
            print(f"[ERROR] {e}")
    return 'OK', 200

# ── start alert background thread ────────────────────────────────

alert_thread = threading.Thread(target=check_alerts, daemon=True)
alert_thread.start()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
