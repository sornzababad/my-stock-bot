"""
premarket_news.py — Pre-market news analysis
Runs before market opens, fetches news via yfinance,
Claude analyzes sentiment, sends bullish/bearish signals to LINE.
"""
import yfinance as yf
import anthropic
import requests
import os, re, time, sys
from users import load_users
from datetime import datetime, timezone, timedelta

TZ_THAI           = timezone(timedelta(hours=7))
LINE_TOKEN        = os.getenv('CHANNEL_ACCESS_TOKEN')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Stocks to scan for news (most liquid / high-impact)
NEWS_STOCKS = {
    'SET': [
        'PTT.BK','KBANK.BK','SCB.BK','AOT.BK','CPALL.BK',
        'DELTA.BK','ADVANC.BK','GULF.BK','BDMS.BK','BBL.BK',
        'TRUE.BK','KTB.BK','OR.BK','BEM.BK','MINT.BK',
    ],
    'US': [
        'AAPL','MSFT','NVDA','META','GOOGL','AMZN','TSLA',
        'JPM','BAC','GS','XOM','UNH','LLY','V','MA',
        'AMD','AVGO','PLTR','COIN','SPY','QQQ',
    ],
}

def push_flex(obj):
    uids = load_users()
    print(f"[PUSH] token={'OK' if LINE_TOKEN else 'MISSING'} | users={uids}")
    if not LINE_TOKEN:
        print("[PUSH] ERROR: CHANNEL_ACCESS_TOKEN not set"); return
    if not uids:
        print("[PUSH] ERROR: no users — set USER_ID or USER_IDS secret"); return
    r = requests.post('https://api.line.me/v2/bot/message/multicast',
                      headers={'Content-Type':'application/json','Authorization':f'Bearer {LINE_TOKEN}'},
                      json={'to':uids,'messages':[obj]}, timeout=10)
    print(f"[PUSH] {r.status_code} {r.text[:200]}")

def _sep():   return {"type":"separator","color":"#37474F","margin":"sm"}
def _kv(l,v): return {"type":"box","layout":"horizontal","margin":"xs","contents":[
    {"type":"text","text":l,"color":"#78909C","size":"xs","flex":2},
    {"type":"text","text":v,"color":"#ECEFF1","size":"xs","flex":4,"wrap":True}]}

def fetch_news(ticker, max_items=4):
    try:
        t     = yf.Ticker(ticker)
        news  = t.news or []
        return [(n.get('title',''), n.get('link','')) for n in news[:max_items] if n.get('title')]
    except:
        return []

def analyze_news(ticker, headlines):
    if not headlines: return None, "neutral"
    text = "\n".join(f"- {h}" for h, _ in headlines)
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=250,
            messages=[{"role":"user","content":
                f"ข่าวล่าสุดหุ้น {ticker}:\n{text}\n\n"
                f"วิเคราะห์ภาษาไทยตามรูปแบบ:\n"
                f"[sentiment] bullish / bearish / neutral\n"
                f"[สรุป] สรุปสั้นๆ 1-2 ประโยคว่าข่าวนี้ส่งผลต่อหุ้นอย่างไร\n"
                f"[ผลต่อราคา] คาดว่าราคาจะ ขึ้น / ลง / ทรงตัว เพราะอะไร"}])
        txt = msg.content[0].text
        sm  = re.search(r'\[sentiment\]\s*(\w+)', txt, re.IGNORECASE)
        sentiment = sm.group(1).lower() if sm else "neutral"
        return txt, sentiment
    except Exception as e:
        print(f"[NEWS CLAUDE] {ticker}: {e}")
        return None, "neutral"

def news_bubble(ticker, headlines, analysis, sentiment):
    is_bull = sentiment == "bullish"
    is_bear = sentiment == "bearish"
    bc  = "#00C851" if is_bull else ("#FF4444" if is_bear else "#78909C")
    ico = "🟢" if is_bull else ("🔴" if is_bear else "⬛")
    lbl = "BULLISH" if is_bull else ("BEARISH" if is_bear else "NEUTRAL")
    hbg = "#0D3321" if is_bull else ("#3E0A0A" if is_bear else "#1A237E")

    def extract(tag):
        m = re.search(rf'\[{tag}\]\s*(.+?)(?=\[|$)', analysis or "", re.DOTALL)
        return m.group(1).strip() if m else ""

    summary    = extract("สรุป")
    price_view = extract("ผลต่อราคา")

    body_contents = [
        {"type":"box","layout":"horizontal","contents":[
            {"type":"text","text":ticker.replace(".BK",""),"weight":"bold","size":"xl","color":"#FFFFFF","flex":1},
            {"type":"text","text":f"{ico} {lbl}","weight":"bold","size":"sm","color":bc,"align":"end"},
        ]},
        _sep(),
    ]
    if summary:
        body_contents.append({"type":"text","text":summary,"color":"#CFD8DC","size":"xs","wrap":True})
    if price_view:
        body_contents += [
            {"type":"text","text":"📈 ผลต่อราคา","color":"#90CAF9","size":"xs","weight":"bold","margin":"sm"},
            {"type":"text","text":price_view,"color":"#CFD8DC","size":"xs","wrap":True,"margin":"xs"},
        ]
    if headlines:
        body_contents += [_sep(),
            {"type":"text","text":"📰 พาดหัวข่าว","color":"#90CAF9","size":"xs","weight":"bold"}]
        for title, _ in headlines[:2]:
            body_contents.append({"type":"text","text":f"• {title[:80]}","color":"#B0BEC5",
                                  "size":"xxs","wrap":True,"margin":"xs"})

    return {"type":"bubble","size":"kilo",
        "header":{"type":"box","layout":"vertical","backgroundColor":hbg,"paddingAll":"12px","contents":[
            {"type":"text","text":ticker.replace(".BK","")+" — Pre-Market","weight":"bold","size":"sm","color":bc},
        ]},
        "body":{"type":"box","layout":"vertical","backgroundColor":"#1E2A3A",
                "paddingAll":"14px","spacing":"xs","contents":body_contents},
    }

def run(market="both"):
    now_str = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")
    markets = []
    if market in ("both","thai"): markets.append(("SET", NEWS_STOCKS["SET"]))
    if market in ("both","us"):   markets.append(("US",  NEWS_STOCKS["US"]))

    for mkt_name, stocks in markets:
        print(f"[NEWS] {mkt_name} pre-market scan {now_str}")
        bubbles = []

        for ticker in stocks:
            headlines = fetch_news(ticker)
            if not headlines:
                print(f"[NEWS] {ticker}: no news")
                continue

            analysis, sentiment = analyze_news(ticker, headlines)
            print(f"[NEWS] {ticker}: {sentiment}")

            if sentiment == "neutral":
                continue

            bubble = news_bubble(ticker, headlines, analysis, sentiment)
            bubbles.append(bubble)
            time.sleep(0.3)

        if not bubbles:
            print(f"[NEWS] {mkt_name}: ไม่มีข่าว bullish/bearish ชัดเจน")
            continue

        flag    = "🏦" if mkt_name == "SET" else "🗽"
        carousel = {
            "type": "flex",
            "altText": f"📰 {flag} {mkt_name} Pre-Market News — {now_str}",
            "contents": {"type": "carousel", "contents": bubbles[:12]}
        }
        push_flex(carousel)
        print(f"[NEWS] ส่ง {mkt_name} {len(bubbles)} ข่าว")

if __name__ == "__main__":
    market = sys.argv[1] if len(sys.argv) > 1 else "both"
    run(market)
