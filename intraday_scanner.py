"""
intraday_scanner.py  —  Intraday scanner (1h interval)
Runs during market hours and alerts on RSI extremes + BB breakouts
"""
import yfinance as yf
import pandas as pd
import requests
import anthropic
import os, re, time, json
from users import load_users
from datetime import datetime, timezone, timedelta

TZ_THAI    = timezone(timedelta(hours=7))
LINE_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
LINE_UID   = os.getenv('USER_ID')

INTRADAY_STOCKS = list(dict.fromkeys([
    # ── US Tech ──────────────────────────────────────────────────
    'AAPL','MSFT','NVDA','AMD','META','GOOGL','AMZN','TSLA',
    'INTC','QCOM','AVGO','CRM','ORCL','NFLX','ADBE',
    'PLTR','CRWD','NET','SNOW','DDOG','COIN','MSTR',

    # ── US Banking / Finance ─────────────────────────────────────
    'JPM','BAC','GS','MS','WFC','C','V','MA','AXP','PYPL',

    # ── US Energy ────────────────────────────────────────────────
    'XOM','CVX','COP','SLB','EOG',

    # ── US Health ────────────────────────────────────────────────
    'UNH','JNJ','PFE','ABBV','LLY','MRK','AMGN',

    # ── US ETF / Index ───────────────────────────────────────────
    'SPY','QQQ','IWM','GLD',

    # ── TH Banking ───────────────────────────────────────────────
    'KBANK.BK','SCB.BK','BBL.BK','KTB.BK','TTB.BK','BAY.BK','TISCO.BK',

    # ── TH Energy ────────────────────────────────────────────────
    'PTT.BK','PTTEP.BK','TOP.BK','OR.BK','BCP.BK','GULF.BK','GPSC.BK',

    # ── TH Tech / Telecom ────────────────────────────────────────
    'DELTA.BK','ADVANC.BK','TRUE.BK','INTUCH.BK','HANA.BK','KCE.BK',

    # ── TH Health ────────────────────────────────────────────────
    'BDMS.BK','BH.BK','BCH.BK','CHG.BK',

    # ── TH Retail / Consumer ─────────────────────────────────────
    'CPALL.BK','CRC.BK','HMPRO.BK','BJC.BK','MAKRO.BK','CBG.BK',

    # ── TH Transport / Property ──────────────────────────────────
    'AOT.BK','BEM.BK','BTS.BK','LH.BK','AP.BK','CPN.BK',
]))

def push_flex(obj):
    uids = load_users()
    if not uids: return
    requests.post('https://api.line.me/v2/bot/message/multicast',
                  headers={'Content-Type':'application/json','Authorization':f'Bearer {LINE_TOKEN}'},
                  json={'to':uids,'messages':[obj]}, timeout=10)

def _sep():   return {"type":"separator","color":"#37474F","margin":"sm"}
def _kv(l,v): return {"type":"box","layout":"horizontal","margin":"xs","contents":[
    {"type":"text","text":l,"color":"#78909C","size":"xs","flex":2},
    {"type":"text","text":v,"color":"#ECEFF1","size":"xs","flex":4,"wrap":True}]}

def tv_url(ticker):
    sym = ("SET:"+ticker.replace(".BK","")) if ticker.endswith(".BK") else ticker
    return f"https://www.tradingview.com/chart/?symbol={sym}&interval=60&studies=STD%3BEMA%4020%2C%2050%2C%20200"

def flex_intraday_card(ticker, sig, price, rsi, atr, reason, currency):
    is_buy  = sig == "BUY"
    bc      = "#00C851" if is_buy else "#FF4444"
    bt      = "🟢 INTRADAY BUY" if is_buy else "🔴 INTRADAY SELL"
    hbg     = "#0D3321" if is_buy else "#3E0A0A"
    now     = datetime.now(TZ_THAI).strftime("%H:%M")
    rsi_bar = "█"*int(rsi/10) + "░"*(10-int(rsi/10))

    tp = price + 2*atr if is_buy else price - 2*atr
    sl = price - 1*atr if is_buy else price + 1*atr
    rr = abs(tp - price) / abs(price - sl) if abs(price - sl) > 0 else 0

    body = [
        {"type":"box","layout":"horizontal","contents":[
            {"type":"text","text":ticker.replace(".BK",""),"weight":"bold","size":"xl","color":"#FFFFFF","flex":1},
            {"type":"text","text":f"{currency}{price:,.2f}","weight":"bold","size":"lg","color":bc,"align":"end"},
        ]},
        {"type":"text","text":reason,"color":"#90CAF9","size":"sm","margin":"xs"},
        _sep(),
        _kv("📊 RSI", f"[{rsi_bar}]  {rsi:.1f}"),
        _sep(),
        _kv("🎯 TP", f"{currency}{tp:,.2f}"),
        _kv("🛡 SL", f"{currency}{sl:,.2f}"),
        _kv("📏 R:R", f"1 : {rr:.1f}"),
    ]

    return {
        "type":"flex","altText":f"{bt} {ticker} @ {currency}{price:.2f}",
        "contents":{"type":"bubble","size":"kilo",
            "header":{"type":"box","layout":"vertical","backgroundColor":hbg,"paddingAll":"12px","contents":[
                {"type":"text","text":bt,"weight":"bold","size":"sm","color":bc},
                {"type":"text","text":f"⏰ Intraday  {now}","size":"xs","color":"#90CAF9","margin":"xs"},
            ]},
            "body":{"type":"box","layout":"vertical","backgroundColor":"#1E2A3A","paddingAll":"14px","spacing":"xs","contents":body},
            "footer":{"type":"box","layout":"vertical","backgroundColor":"#263238","paddingAll":"10px","contents":[
                {"type":"button","action":{"type":"uri","label":"📊 ดูกราฟ 1H + EMA","uri":tv_url(ticker)},
                 "style":"primary","color":bc,"height":"sm"}
            ]}
        }
    }

def check_intraday(ticker):
    df = yf.download(ticker, period="5d", interval="1h", progress=False, auto_adjust=True)
    if df.empty or len(df) < 20: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    d = df['Close'].diff()
    df['RSI'] = 100-(100/(1+d.where(d>0,0).rolling(14).mean()/(-d.where(d<0,0)).rolling(14).mean()))
    bm = df['Close'].rolling(20).mean()
    bs = df['Close'].rolling(20).std()
    df['BB_U'] = bm + 2*bs
    df['BB_L'] = bm - 2*bs

    hl  = df['High'] - df['Low']
    atr = float(pd.concat([hl, abs(df['High']-df['Close'].shift()),
                            abs(df['Low']-df['Close'].shift())], axis=1)
                .max(axis=1).rolling(14).mean().iloc[-1])

    last  = df.iloc[-1]
    price = float(last['Close'])
    rsi   = float(last['RSI']) if not pd.isna(last['RSI']) else 50

    if rsi <= 25:
        return ("BUY",  price, rsi, atr, f"RSI ต่ำมาก {rsi:.1f} — Oversold รุนแรง 🔻")
    if rsi >= 75:
        return ("SELL", price, rsi, atr, f"RSI สูงมาก {rsi:.1f} — Overbought รุนแรง 🔺")
    if price > float(last['BB_U'])*1.005:
        return ("SELL", price, rsi, atr, f"ราคาทะลุ Upper BB — Breakout 🔺")
    if price < float(last['BB_L'])*0.995:
        return ("BUY",  price, rsi, atr, f"ราคาหลุด Lower BB — Oversold Squeeze 🔻")
    return None

def main():
    now = datetime.now(TZ_THAI)
    print(f"[INTRADAY] {now.strftime('%Y-%m-%d %H:%M')}")

    signals = []
    errors  = 0
    for ticker in INTRADAY_STOCKS:
        try:
            res = check_intraday(ticker)
        except Exception as e:
            print(f"[ERROR] {ticker}: {e}")
            errors += 1
            continue
        if not res: continue
        sig, price, rsi, atr, reason = res
        is_thai  = ticker.endswith(".BK")
        currency = "฿" if is_thai else "$"
        display  = ticker.replace(".BK","") if is_thai else ticker
        card     = flex_intraday_card(display, sig, price, rsi, atr, reason, currency)
        signals.append(card)
        print(f"[SIGNAL] {ticker} {sig} RSI:{rsi:.1f} TP:{price+2*atr:.2f} SL:{price-atr:.2f}")
        time.sleep(0.1)

    total = len(INTRADAY_STOCKS)
    print(f"[DONE] สแกน {total} | สัญญาณ {len(signals)} | error {errors}")

    if errors > total // 2:
        push_flex({
            "type": "flex", "altText": "⚠️ Intraday Scanner — ดึงข้อมูลไม่ได้",
            "contents": {"type": "bubble", "size": "kilo",
                "body": {"type": "box", "layout": "vertical", "backgroundColor": "#1E2A3A",
                    "paddingAll": "16px", "contents": [
                        {"type": "text", "text": "⚠️ Intraday Scanner Error", "weight": "bold",
                         "color": "#FF4444", "size": "md"},
                        {"type": "text", "text": f"ดึงข้อมูลไม่ได้ {errors}/{total} ตัว",
                         "color": "#CFD8DC", "size": "sm", "margin": "sm"},
                        {"type": "text", "text": "อาจเป็นปัญหา yfinance หรือ network",
                         "color": "#90CAF9", "size": "xs", "wrap": True, "margin": "xs"},
                    ]}}
        })
        return

    if signals:
        bubbles = [card['contents'] for card in signals]
        now_str = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")
        carousel = {
            "type": "flex",
            "altText": f"⏰ Intraday Alert — {len(signals)} สัญญาณ  {now_str}",
            "contents": {"type": "carousel", "contents": bubbles[:12]}
        }
        push_flex(carousel)

if __name__ == "__main__":
    main()
