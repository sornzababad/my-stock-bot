"""
intraday_scanner.py  —  Intraday scanner (1h interval)
Runs during market hours and alerts on RSI extremes + BB breakouts
"""
import yfinance as yf
import pandas as pd
import requests
import anthropic
import os, re, time, json
from datetime import datetime, timezone, timedelta

TZ_THAI    = timezone(timedelta(hours=7))
LINE_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
LINE_UID   = os.getenv('USER_ID')

# Focused list for intraday (smaller = faster)
INTRADAY_STOCKS = [
    # US high-volume
    'AAPL','MSFT','NVDA','TSLA','META','AMZN','AMD','SPY','QQQ',
    'PLTR','COIN','MSTR','CRWD','NET',
    # Thai
    'PTT.BK','KBANK.BK','AOT.BK','CPALL.BK','ADVANC.BK',
    'DELTA.BK','SCB.BK','GULF.BK','BDMS.BK','BBL.BK',
]

def push_flex(obj):
    requests.post('https://api.line.me/v2/bot/message/push',
                  headers={'Content-Type':'application/json','Authorization':f'Bearer {LINE_TOKEN}'},
                  json={'to':LINE_UID,'messages':[obj]}, timeout=10)

def _sep():   return {"type":"separator","color":"#37474F","margin":"sm"}
def _kv(l,v): return {"type":"box","layout":"horizontal","margin":"xs","contents":[
    {"type":"text","text":l,"color":"#78909C","size":"xs","flex":2},
    {"type":"text","text":v,"color":"#ECEFF1","size":"xs","flex":4,"wrap":True}]}

def tv_url(ticker):
    sym = ("SET:"+ticker.replace(".BK","")) if ticker.endswith(".BK") else ticker
    return f"https://www.tradingview.com/chart/?symbol={sym}&interval=60&studies=STD%3BEMA%4020%2C%2050%2C%20200"

def flex_intraday_card(ticker, sig, price, rsi, reason, currency):
    is_buy = sig == "BUY"
    bc     = "#00C851" if is_buy else "#FF4444"
    bt     = "🟢 INTRADAY BUY" if is_buy else "🔴 INTRADAY SELL"
    hbg    = "#0D3321" if is_buy else "#3E0A0A"
    now    = datetime.now(TZ_THAI).strftime("%H:%M")
    rsi_bar = "█"*int(rsi/10) + "░"*(10-int(rsi/10))
    return {
        "type":"flex","altText":f"{bt} {ticker} @ {currency}{price:.2f}",
        "contents":{"type":"bubble","size":"kilo",
            "header":{"type":"box","layout":"vertical","backgroundColor":hbg,"paddingAll":"12px","contents":[
                {"type":"text","text":bt,"weight":"bold","size":"sm","color":bc},
                {"type":"text","text":f"⏰ Intraday  {now}","size":"xs","color":"#90CAF9","margin":"xs"},
            ]},
            "body":{"type":"box","layout":"vertical","backgroundColor":"#1E2A3A","paddingAll":"14px","spacing":"xs","contents":[
                {"type":"box","layout":"horizontal","contents":[
                    {"type":"text","text":ticker.replace(".BK",""),"weight":"bold","size":"xl","color":"#FFFFFF","flex":1},
                    {"type":"text","text":f"{currency}{price:,.2f}","weight":"bold","size":"lg","color":bc,"align":"end"},
                ]},
                {"type":"text","text":reason,"color":"#90CAF9","size":"sm","margin":"xs"},
                _sep(),
                _kv("📊 RSI", f"[{rsi_bar}]  {rsi:.1f}"),
            ]},
            "footer":{"type":"box","layout":"vertical","backgroundColor":"#263238","paddingAll":"10px","contents":[
                {"type":"button","action":{"type":"uri","label":"📊 ดูกราฟ 1H + EMA","uri":tv_url(ticker)},
                 "style":"primary","color":bc,"height":"sm"}
            ]}
        }
    }

def check_intraday(ticker):
    try:
        df = yf.download(ticker, period="5d", interval="1h", progress=False, auto_adjust=True)
        if df.empty or len(df) < 20: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        d = df['Close'].diff()
        df['RSI'] = 100-(100/(1+d.where(d>0,0).rolling(14).mean()/(-d.where(d<0,0)).rolling(14).mean()))
        bm = df['Close'].rolling(20).mean()
        bs = df['Close'].rolling(20).std()
        df['BB_U'] = bm + 2*bs
        df['BB_L'] = bm - 2*bs

        last  = df.iloc[-1]
        price = float(last['Close'])
        rsi   = float(last['RSI']) if not pd.isna(last['RSI']) else 50

        # RSI extreme
        if rsi <= 25:
            return ("BUY", price, rsi, f"RSI ต่ำมาก {rsi:.1f} — Oversold รุนแรง 🔻")
        if rsi >= 75:
            return ("SELL", price, rsi, f"RSI สูงมาก {rsi:.1f} — Overbought รุนแรง 🔺")

        # Bollinger breakout
        if price > float(last['BB_U'])*1.005:
            return ("SELL", price, rsi, f"ราคาทะลุ Upper BB — Breakout 🔺")
        if price < float(last['BB_L'])*0.995:
            return ("BUY",  price, rsi, f"ราคาหลุด Lower BB — Oversold Squeeze 🔻")
        return None
    except Exception as e:
        print(f"[INTRADAY] {ticker}: {e}"); return None

def main():
    now = datetime.now(TZ_THAI)
    print(f"[INTRADAY] {now.strftime('%Y-%m-%d %H:%M')}")

    signals = []
    for ticker in INTRADAY_STOCKS:
        res = check_intraday(ticker)
        if not res: continue
        sig, price, rsi, reason = res
        is_thai  = ticker.endswith(".BK")
        currency = "฿" if is_thai else "$"
        display  = ticker.replace(".BK","") if is_thai else ticker
        card     = flex_intraday_card(display, sig, price, rsi, reason, currency)
        signals.append(card)
        print(f"[SIGNAL] {ticker} {sig} RSI:{rsi:.1f}")
        time.sleep(0.1)

    if signals:
        for card in signals:
            push_flex(card)
            time.sleep(0.3)
        print(f"[DONE] ส่ง {len(signals)} สัญญาณ")
    else:
        print("[DONE] ไม่พบสัญญาณ intraday")

if __name__ == "__main__":
    main()
