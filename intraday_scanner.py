"""
intraday_scanner.py  —  Intraday scanner (1h interval)
Runs during market hours and alerts on RSI extremes + BB breakouts
Signals are filtered by Claude AI (conviction ≥ 3/5)
"""
import yfinance as yf
import pandas as pd
import requests
import anthropic
import logging
import os, re, time, json

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
from users import load_users
from datetime import datetime, timezone, timedelta
from compact_cards import build_compact_carousels
from ticker_info import get_name
from ai_ticker_selector import get_ai_tickers

TZ_THAI    = timezone(timedelta(hours=7))
LINE_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

INTRADAY_STOCKS = list(dict.fromkeys([
    # ── US Mega-cap Tech ─────────────────────────────────────────
    'AAPL','MSFT','NVDA','AMD','META','GOOGL','AMZN','TSLA',
    'AVGO','ORCL','NFLX','ADBE','CRM','INTC','QCOM',

    # ── US Semiconductor ─────────────────────────────────────────
    'MU','LRCX','AMAT','TXN','MRVL','ON','KLAC','ASML',

    # ── US Software / Cloud ──────────────────────────────────────
    'NOW','WDAY','INTU','TEAM','DDOG','SNOW','NET','CRWD',

    # ── US High-volatility / Crypto-adjacent ─────────────────────
    'PLTR','COIN','MSTR','HOOD','SQ','RIOT','MARA',

    # ── US Banking / Finance ─────────────────────────────────────
    'JPM','BAC','GS','MS','WFC','C','BLK','SCHW',
    'V','MA','AXP','PYPL','COF',

    # ── US Energy ────────────────────────────────────────────────
    'XOM','CVX','COP','SLB','EOG','OXY','MPC','HAL',

    # ── US Health / Biotech ──────────────────────────────────────
    'UNH','JNJ','PFE','ABBV','LLY','MRK','AMGN',
    'GILD','REGN','VRTX','MRNA','TMO','ISRG',

    # ── US Consumer ──────────────────────────────────────────────
    'WMT','COST','TGT','HD','NKE','SBUX','MCD','KO','PEP',
    'BABA','MELI','SHOP',

    # ── US EV / Auto ─────────────────────────────────────────────
    'F','GM','RIVN',

    # ── US ETF ───────────────────────────────────────────────────
    'SPY','QQQ','QQQM','VOO','IWM','SCHD','GLD','TLT','SOXX','XLK','XLF','XLE','XLV',

]))

def push_flex(obj):
    uids = load_users()
    kind = obj.get("type", "?")
    alt  = obj.get("altText", "")[:60]
    print(f"[PUSH] {kind} alt={alt!r} token={'OK' if LINE_TOKEN else 'MISSING'} | users={uids}")
    if not LINE_TOKEN:
        print("[PUSH] ERROR: CHANNEL_ACCESS_TOKEN not set"); return
    if not uids:
        print("[PUSH] ERROR: no users — set USER_ID or USER_IDS secret"); return
    payload = {'to': uids, 'messages': [obj]}
    body    = json.dumps(payload, ensure_ascii=False)
    print(f"[PUSH] payload size: {len(body.encode('utf-8'))} bytes")
    r = requests.post('https://api.line.me/v2/bot/message/multicast',
                      headers={'Content-Type':'application/json','Authorization':f'Bearer {LINE_TOKEN}'},
                      data=body.encode('utf-8'), timeout=10)
    if r.status_code != 200:
        print(f"[PUSH] ❌ {r.status_code} {r.text[:600]}")
    else:
        print(f"[PUSH] ✅ {r.status_code}")

def _sep():   return {"type":"separator","color":"#37474F","margin":"sm"}
def _kv(l,v): return {"type":"box","layout":"horizontal","margin":"xs","contents":[
    {"type":"text","text":l,"color":"#78909C","size":"xs","flex":2},
    {"type":"text","text":v,"color":"#ECEFF1","size":"xs","flex":4,"wrap":True}]}

def tv_url(ticker):
    sym = ("SET:"+ticker.replace(".BK","")) if ticker.endswith(".BK") else ticker
    return f"https://www.tradingview.com/chart/?symbol={sym}&interval=60&studies=STD%3BEMA%4020%2C%2050%2C%20200"

def fetch_top_news(ticker):
    try:
        news = yf.Ticker(ticker).news or []
        headlines = [n.get('title','') for n in news[:3] if n.get('title')]
        return headlines
    except:
        return []

def analyze_with_claude(ticker, sig, price, rsi, tp, sl, headlines):
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        news_txt = "\n".join(f"- {h}" for h in headlines) if headlines else "ไม่มีข่าว"
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=350,
            messages=[{"role":"user","content":
                f"หุ้น {ticker} สัญญาณ {sig} ราคา {price:.2f} RSI:{rsi:.1f} TP:{tp:.2f} SL:{sl:.2f}\n"
                f"ข่าวล่าสุด:\n{news_txt}\n\n"
                f"ตอบภาษาไทยตามรูปแบบ:\n"
                f"[ชื่อ] ชื่อเต็มบริษัท\n"
                f"[ธุรกิจ] ทำอะไร 6-8 คำ\n"
                f"[เหตุผล] วิเคราะห์สัญญาณ+ข่าว 2 ประโยค\n"
                f"[ข่าว] สรุปข่าวที่กระทบราคาสั้นๆ 1 ประโยค\n"
                f"[Conviction] X/5"}])
        return msg.content[0].text
    except Exception as e:
        print(f"[CLAUDE] {ticker}: {e}"); return None

def parse_analysis(txt):
    if not txt:
        return {"name":"","business":"","reason":"","news":""}, 3
    def extract(tag):
        m = re.search(rf'\[{tag}\]\s*(.+?)(?=\[|$)', txt, re.DOTALL)
        raw = m.group(1).strip() if m else ""
        return re.sub(r'\*+', '', raw).strip()
    conv_m = re.search(r'\[Conviction\]\s*(\d)', txt)
    conv   = int(conv_m.group(1)) if conv_m else 3
    return {
        "name":     extract("ชื่อ"),
        "business": extract("ธุรกิจ"),
        "reason":   extract("เหตุผล"),
        "news":     extract("ข่าว"),
    }, conv

def flex_intraday_card(ticker, sig, price, rsi, tp, sl, tp_src, reason, currency, conviction, info):
    is_buy    = sig == "BUY"
    bc        = "#00E676" if is_buy else "#FF5252"
    hbg       = "#071912" if is_buy else "#180707"
    badge     = "▲ BUY" if is_buy else "▼ SELL"
    rr        = abs(tp - price) / abs(price - sl) if abs(price - sl) > 0 else 0
    pct_tp    = (tp - price) / price * 100
    pct_sl    = (sl - price) / price * 100
    now       = datetime.now(TZ_THAI).strftime("%H:%M")
    sym       = ticker.replace(".BK", "")
    rsi_color = "#FF5252" if rsi >= 70 else ("#00E676" if rsi <= 30 else "#90CAF9")
    conv_bar  = "▰" * conviction + "▱" * (5 - conviction)

    name_line = get_name(ticker) or info.get("name") or sym
    biz_line  = info.get("business") or ""
    reason_ai = info.get("reason") or ""
    news_line = info.get("news") or ""

    return {
        "type": "flex",
        "altText": f"{'🟢' if is_buy else '🔴'} {badge} {sym} {currency}{price:.2f}  R:R 1:{rr:.1f}",
        "contents": {
            "type": "bubble", "size": "kilo",
            "header": {
                "type": "box", "layout": "vertical",
                "backgroundColor": hbg, "paddingAll": "12px", "spacing": "none",
                "contents": [
                    # Ticker + badge pill
                    {"type": "box", "layout": "horizontal", "alignItems": "center", "contents": [
                        {"type": "text", "text": sym, "weight": "bold",
                         "size": "xl", "color": "#FFFFFF", "flex": 1},
                        {"type": "box", "layout": "vertical", "backgroundColor": bc,
                         "cornerRadius": "5px", "paddingStart": "8px", "paddingEnd": "8px",
                         "paddingTop": "2px", "paddingBottom": "2px", "justifyContent": "center",
                         "contents": [{"type": "text", "text": badge,
                                       "weight": "bold", "size": "xs", "color": "#000000"}]},
                    ]},
                    # Full company name — always shown
                    {"type": "text", "text": name_line, "size": "xs",
                     "color": "#90A4AE", "margin": "xs", "wrap": True},
                    # Price + RSI pill + time
                    {"type": "box", "layout": "horizontal", "margin": "sm",
                     "alignItems": "center", "contents": [
                        {"type": "text", "text": f"{currency}{price:,.2f}",
                         "weight": "bold", "size": "sm", "color": bc, "flex": 1},
                        {"type": "box", "layout": "vertical", "flex": 0,
                         "backgroundColor": "#1A2332", "cornerRadius": "8px",
                         "paddingStart": "6px", "paddingEnd": "6px",
                         "paddingTop": "2px", "paddingBottom": "2px",
                         "contents": [{"type": "text", "text": f"RSI {rsi:.0f}",
                                       "size": "xxs", "color": rsi_color, "weight": "bold"}]},
                        {"type": "text", "text": f"  ⏰{now}", "size": "xxs",
                         "color": "#37474F", "flex": 0},
                    ]},
                    *([{"type": "text", "text": f"🏢  {biz_line}", "size": "xxs",
                        "color": "#546E7A", "wrap": True, "margin": "xs"}] if biz_line else []),
                ]
            },
            "body": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#0E1621", "paddingAll": "10px", "spacing": "xs",
                "contents": [
                    {"type": "text", "text": reason,
                     "color": "#CFD8DC", "size": "xxs", "wrap": True},
                    *([{"type": "text", "text": f"🤖  {reason_ai}",
                        "color": "#FFD54F", "size": "xxs", "wrap": True}] if reason_ai else []),
                    *([{"type": "box", "layout": "horizontal", "margin": "xs",
                        "backgroundColor": "#111B2A", "cornerRadius": "5px",
                        "paddingAll": "5px", "contents": [
                            {"type": "text", "text": "📰  " + news_line,
                             "color": "#90CAF9", "size": "xxs", "wrap": True},
                        ]}] if news_line else []),

                    {"type": "separator", "color": "#1E2D3D", "margin": "xs"},

                    # TP | SL side by side
                    {"type": "box", "layout": "horizontal", "spacing": "sm", "margin": "xs", "contents": [
                        {"type": "box", "layout": "vertical",
                         "backgroundColor": "#0A1F10", "cornerRadius": "8px",
                         "paddingAll": "8px", "flex": 1,
                         "contents": [
                             {"type": "text", "text": "🎯 TARGET", "size": "xxs",
                              "color": "#2E7D52", "weight": "bold"},
                             {"type": "text", "text": f"{currency}{tp:,.2f}",
                              "size": "sm", "color": "#69F0AE", "weight": "bold"},
                             {"type": "text", "text": f"{pct_tp:+.1f}%",
                              "size": "xxs", "color": "#2E7D52"},
                         ]},
                        {"type": "box", "layout": "vertical",
                         "backgroundColor": "#1F0A0A", "cornerRadius": "8px",
                         "paddingAll": "8px", "flex": 1,
                         "contents": [
                             {"type": "text", "text": "🛡 STOP", "size": "xxs",
                              "color": "#7D2E2E", "weight": "bold"},
                             {"type": "text", "text": f"{currency}{sl:,.2f}",
                              "size": "sm", "color": "#FF8A80", "weight": "bold"},
                             {"type": "text", "text": f"{pct_sl:+.1f}%",
                              "size": "xxs", "color": "#7D2E2E"},
                         ]},
                    ]},

                    # R:R + conviction bar pill
                    {"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
                        {"type": "text", "text": f"📏 R:R  1:{rr:.1f}",
                         "color": "#90CAF9", "size": "xxs", "flex": 1},
                        {"type": "box", "layout": "vertical", "flex": 0,
                         "backgroundColor": "#1A2332", "cornerRadius": "8px",
                         "paddingStart": "7px", "paddingEnd": "7px",
                         "paddingTop": "2px", "paddingBottom": "2px",
                         "contents": [{"type": "text", "text": conv_bar,
                                       "size": "xxs", "color": bc}]},
                    ]},
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#070F18", "paddingAll": "8px",
                "contents": [
                    {"type": "button",
                     "action": {"type": "uri", "label": "📊 ดูกราฟ 1H", "uri": tv_url(ticker)},
                     "style": "primary", "color": bc, "height": "sm"},
                ]
            }
        }
    }

def find_swing_tp_sl(sig, price, atr, df, window=5):
    highs = df['High'].values
    lows  = df['Low'].values
    n     = len(highs)

    swing_highs, swing_lows = [], []
    for i in range(window, n - window):
        if all(highs[i] >= highs[i-j] for j in range(1, window+1)) and \
           all(highs[i] >= highs[i+j] for j in range(1, window+1)):
            swing_highs.append(highs[i])
        if all(lows[i] <= lows[i-j] for j in range(1, window+1)) and \
           all(lows[i] <= lows[i+j] for j in range(1, window+1)):
            swing_lows.append(lows[i])

    if sig == "BUY":
        sl_cands = [l for l in swing_lows  if l < price * 0.999]
        tp_cands = [h for h in swing_highs if h > price * 1.001]
        sl = max(sl_cands) if sl_cands else price - atr
        tp = min(tp_cands) if tp_cands else price + 2*atr
    else:
        sl_cands = [h for h in swing_highs if h > price * 1.001]
        tp_cands = [l for l in swing_lows  if l < price * 0.999]
        sl = min(sl_cands) if sl_cands else price + atr
        tp = max(tp_cands) if tp_cands else price - 2*atr

    used_swing = bool(sl_cands and tp_cands)
    rr = abs(tp - price) / abs(price - sl) if abs(price - sl) > 0 else 0
    if rr < 1 or (sig == "BUY"  and (tp <= price or sl >= price)) or \
                 (sig == "SELL" and (tp >= price or sl <= price)):
        sl = price - atr if sig == "BUY" else price + atr
        tp = price + 2*atr if sig == "BUY" else price - 2*atr
        used_swing = False

    return tp, sl, "swing" if used_swing else "atr"

def check_intraday(ticker):
    df = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
    if df.empty or len(df) < 30: return None
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

    sig = None
    if rsi <= 30:
        sig, reason = "BUY",  f"RSI ต่ำ {rsi:.1f} — Oversold 🔻"
    elif rsi >= 70:
        sig, reason = "SELL", f"RSI สูง {rsi:.1f} — Overbought 🔺"
    elif price > float(last['BB_U']):
        sig, reason = "SELL", f"ราคาทะลุ Upper BB — Breakout 🔺"
    elif price < float(last['BB_L']):
        sig, reason = "BUY",  f"ราคาหลุด Lower BB — Oversold Squeeze 🔻"

    if sig is None:
        return None

    tp, sl, tp_src = find_swing_tp_sl(sig, price, atr, df)
    return (sig, price, rsi, tp, sl, tp_src, reason)

def main():
    now = datetime.now(TZ_THAI)
    print(f"[INTRADAY] {now.strftime('%Y-%m-%d %H:%M')}")

    compact_signals = []
    errors          = 0
    filtered        = 0

    global INTRADAY_STOCKS
    ai_picks = get_ai_tickers()
    if ai_picks:
        existing = set(INTRADAY_STOCKS)
        new_us   = [t for t in ai_picks if t not in existing and not t.endswith(".BK")]
        INTRADAY_STOCKS = INTRADAY_STOCKS + new_us
        print(f"[AI_SELECT] Added {len(new_us)} dynamic tickers → total {len(INTRADAY_STOCKS)}")

    for ticker in INTRADAY_STOCKS:
        try:
            res = check_intraday(ticker)
        except Exception as e:
            print(f"[ERROR] {ticker}: {e}")
            errors += 1
            continue
        if not res: continue

        sig, price, rsi, tp, sl, tp_src, reason = res

        headlines  = fetch_top_news(ticker)
        ai_text    = analyze_with_claude(ticker, sig, price, rsi, tp, sl, headlines)
        _, conv    = parse_analysis(ai_text)
        if conv < 3:
            print(f"[SKIP] {ticker} {sig} RSI:{rsi:.1f} conv:{conv}/5")
            filtered += 1
            continue

        is_thai  = ticker.endswith(".BK")
        currency = "฿" if is_thai else "$"
        rr       = abs(tp - price) / abs(price - sl) if abs(price - sl) > 0 else 0
        print(f"[SIGNAL] {ticker} {sig} RSI:{rsi:.1f} conv:{conv}/5")
        compact_signals.append({
            "ticker":    ticker,
            "sig":       sig,
            "price":     price,
            "rsi":       rsi,
            "rr":        rr,
            "tp":        tp,
            "sl":        sl,
            "currency":  currency,
            "chart_url": tv_url(ticker),
        })
        time.sleep(0.2)

    total = len(INTRADAY_STOCKS)
    print(f"[DONE] สแกน {total} | สัญญาณ {len(compact_signals)} | กรอง {filtered} | error {errors}")

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

    now_str = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")
    if compact_signals:
        build_compact_carousels(
            compact_signals,
            push_fn=lambda msgs: push_flex(msgs[0]),
            alt_prefix="⏰ Intraday Alert",
        )
    else:
        push_flex({
            "type": "flex", "altText": f"😴 Intraday — ไม่พบสัญญาณ  {now_str}",
            "contents": {"type": "bubble", "size": "kilo",
                "body": {"type": "box", "layout": "vertical", "backgroundColor": "#0E1621",
                    "paddingAll": "20px", "spacing": "sm", "contents": [
                        {"type": "text", "text": "😴 ไม่พบสัญญาณ", "weight": "bold",
                         "color": "#90CAF9", "size": "lg"},
                        {"type": "text", "text": now_str, "color": "#546E7A", "size": "xs"},
                        {"type": "separator", "color": "#1E2D3D", "margin": "sm"},
                        {"type": "text",
                         "text": f"สแกน {total} หุ้น ไม่มีตัวไหนผ่าน RSI/BB filter ในชั่วโมงนี้",
                         "color": "#CFD8DC", "size": "xs", "wrap": True},
                    ]}}
        })

if __name__ == "__main__":
    main()
