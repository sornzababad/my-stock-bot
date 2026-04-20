import yfinance as yf
import pandas as pd
import requests
import anthropic
import os
import re
import time
import json
from datetime import datetime, timezone, timedelta

TZ_THAI = timezone(timedelta(hours=7))
LINE_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
LINE_USER_ID      = os.getenv('USER_ID')

# ─────────────────────────────────────────────────────────────────
#  LINE PUSH  — supports both text and Flex Message
# ─────────────────────────────────────────────────────────────────

def push_messages(messages: list) -> bool:
    """Push a list of LINE message objects (text or flex) in one call."""
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        print(f"[ERROR] TOKEN={'SET' if LINE_ACCESS_TOKEN else 'MISSING'}")
        return False
    # LINE allows max 5 messages per push call
    for i in range(0, len(messages), 5):
        batch = messages[i:i+5]
        r = requests.post(
            'https://api.line.me/v2/bot/message/push',
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {LINE_ACCESS_TOKEN}'},
            json={'to': LINE_USER_ID, 'messages': batch},
            timeout=10
        )
        print(f"[LINE] {r.status_code} | {r.text[:120]}")
        if r.status_code != 200:
            return False
        time.sleep(0.3)
    return True

def text_msg(text: str) -> dict:
    return {"type": "text", "text": text}

# ─────────────────────────────────────────────────────────────────
#  FLEX MESSAGE BUILDERS
# ─────────────────────────────────────────────────────────────────

def flex_header_card(flag, market_label, index_name, index_price,
                     index_chg, scan_count, scan_secs,
                     buy_n, watch_n, exit_n, ai_filtered, summary) -> dict:
    now       = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")
    is_up     = index_chg >= 0
    chg_color = "#00C851" if is_up else "#FF4444"
    chg_arrow = "↑" if is_up else "↓"
    chg_text  = f"{chg_arrow}{'+' if is_up else ''}{index_chg:.2f}%"
    bg_color  = "#1A237E"   # dark navy — same as screenshot

    return {
        "type": "flex",
        "altText": f"{flag} {market_label} Alert — Market Close",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box", "layout": "vertical",
                "backgroundColor": bg_color,
                "paddingAll": "16px",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": f"{flag} {market_label} Alert — Market Close 📊",
                             "weight": "bold", "size": "sm", "color": "#FFFFFF", "flex": 1,
                             "wrap": True},
                        ]
                    },
                    {"type": "text", "text": now, "size": "xs", "color": "#90CAF9", "margin": "sm"},
                ]
            },
            "body": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#1E2A3A",
                "paddingAll": "14px", "spacing": "sm",
                "contents": [
                    # Index row
                    {
                        "type": "box", "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": index_name, "color": "#FFFFFF",
                             "size": "sm", "weight": "bold", "flex": 1},
                            {"type": "text", "text": f"{index_price:,.2f}", "color": "#FFFFFF",
                             "size": "sm", "weight": "bold", "align": "end"},
                            {"type": "text", "text": f"  {chg_text}", "color": chg_color,
                             "size": "sm", "weight": "bold"},
                        ]
                    },
                    {"type": "separator", "color": "#37474F"},
                    # Scan stats
                    {"type": "text",
                     "text": f"สแกน {scan_count} หุ้น  •  {scan_secs:.1f}s",
                     "color": "#B0BEC5", "size": "xs"},
                    # BUY / WATCH / EXIT
                    {
                        "type": "box", "layout": "horizontal", "spacing": "md",
                        "contents": [
                            _pill(f"🟢 BUY {buy_n}",   "#00C851", "#FFFFFF"),
                            _pill(f"🟡 WATCH {watch_n}", "#FFB300", "#000000"),
                            _pill(f"🔴 EXIT {exit_n}",  "#FF4444", "#FFFFFF"),
                        ]
                    },
                    {"type": "text",
                     "text": f"🤖 AI กรองออก {ai_filtered} สัญญาณ",
                     "color": "#90CAF9", "size": "xs"},
                    {"type": "separator", "color": "#37474F"},
                    {"type": "text", "text": summary, "color": "#CFD8DC",
                     "size": "xs", "wrap": True},
                ]
            }
        }
    }


def flex_stock_card(ticker, signal_type, price, rsi, atr,
                    ema_cross, bb_pos, reasons, ai_text,
                    conviction, tp=None, sl=None, currency="$") -> dict:

    is_buy   = signal_type == "BUY"
    is_exit  = not is_buy and conviction >= 4

    if is_buy:
        badge_color  = "#00C851"
        badge_text   = "🟢  BUY / ซื้อ"
        header_bg    = "#0D3321"
    elif is_exit:
        badge_color  = "#FF4444"
        badge_text   = "🔴  EXIT / ขาย"
        header_bg    = "#3E0A0A"
    else:
        badge_color  = "#FFB300"
        badge_text   = "🟡  WATCH / เฝ้าดู"
        header_bg    = "#3E2E00"

    # RSI visual
    rsi_filled = int(rsi / 10)
    rsi_bar    = "█" * rsi_filled + "░" * (10 - rsi_filled)
    if rsi <= 30:   rsi_zone = "Oversold 🔻"
    elif rsi >= 70: rsi_zone = "Overbought 🔺"
    else:           rsi_zone = "Normal ✅"

    ma_text = "Golden Cross ✨" if ema_cross == "golden" else "Death Cross ☠️"
    bb_text = {"above": "Breakout 🔺", "below": "Squeeze 🔻", "inside": "Normal ➡️"}.get(bb_pos, "")

    stars    = "⭐" * conviction + "☆" * (5 - conviction)
    strength = "STRONG 💪" if conviction >= 4 else ("MODERATE 👍" if conviction == 3 else "WEAK 👀")

    body_contents = [
        # Ticker + Price
        {
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text", "text": ticker, "weight": "bold",
                 "size": "xl", "color": "#FFFFFF", "flex": 1},
                {"type": "text", "text": f"{currency}{price:,.2f}",
                 "weight": "bold", "size": "lg",
                 "color": badge_color, "align": "end"},
            ]
        },
        {"type": "text", "text": reasons[0] if reasons else "", "color": "#90CAF9",
         "size": "sm", "margin": "xs"},
        {"type": "separator", "color": "#37474F", "margin": "sm"},
        # Indicators
        _kv_row("📊 RSI",   f"[{rsi_bar}]  {rsi:.1f}  {rsi_zone}"),
        _kv_row("📈 MA",    ma_text),
        _kv_row("📉 BB",    bb_text),
        _kv_row("📐 ATR",   f"{atr:.4f}"),
    ]

    if tp and sl and price > sl:
        rr = (tp - price) / (price - sl)
        body_contents += [
            {"type": "separator", "color": "#37474F", "margin": "sm"},
            _kv_row("🎯 TP",  f"{currency}{tp:.2f}"),
            _kv_row("🛡 SL",  f"{currency}{sl:.2f}"),
            _kv_row("📏 R:R", f"1 : {rr:.1f}"),
        ]

    # AI section
    body_contents += [
        {"type": "separator", "color": "#37474F", "margin": "sm"},
        {
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text", "text": "🤖 AI", "color": "#B0BEC5", "size": "xs", "flex": 0},
                {"type": "text", "text": f"  {stars}  {strength}",
                 "color": "#FFD54F", "size": "xs", "flex": 1, "wrap": True},
            ]
        },
    ]

    if ai_text:
        ai_lines = [l.strip() for l in ai_text.strip().split("\n") if l.strip()][:3]
        body_contents.append({
            "type": "text",
            "text": "\n".join(ai_lines),
            "color": "#CFD8DC", "size": "xs", "wrap": True, "margin": "xs"
        })

    # "ดูกราฟ TradingView" button
    tv_symbol = ticker.replace(".BK", "") + (":SET" if currency == "฿" else "")
    tv_url    = f"https://www.tradingview.com/chart/?symbol={tv_symbol}"

    return {
        "type": "flex",
        "altText": f"{badge_text}  {ticker}  {currency}{price:,.2f}",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box", "layout": "vertical",
                "backgroundColor": header_bg,
                "paddingAll": "12px",
                "contents": [
                    {"type": "text", "text": badge_text, "weight": "bold",
                     "size": "sm", "color": badge_color}
                ]
            },
            "body": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#1E2A3A",
                "paddingAll": "14px", "spacing": "xs",
                "contents": body_contents
            },
            "footer": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#263238",
                "paddingAll": "10px",
                "contents": [
                    {
                        "type": "button",
                        "action": {"type": "uri", "label": "📊 ดูกราฟ TradingView",
                                   "uri": tv_url},
                        "style": "primary",
                        "color": badge_color,
                        "height": "sm"
                    }
                ]
            }
        }
    }


def flex_no_signal(flag, market_label, index_name, index_price,
                   index_chg, scan_count, scan_secs) -> dict:
    now      = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")
    is_up    = index_chg >= 0
    chg_col  = "#00C851" if is_up else "#FF4444"
    chg_text = f"{'↑+' if is_up else '↓'}{index_chg:.2f}%"
    return {
        "type": "flex",
        "altText": f"{flag} {market_label} — ไม่พบสัญญาณวันนี้",
        "contents": {
            "type": "bubble", "size": "kilo",
            "header": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#1A237E", "paddingAll": "16px",
                "contents": [
                    {"type": "text", "text": f"{flag} {market_label} Alert — Market Close 📊",
                     "weight": "bold", "size": "sm", "color": "#FFFFFF", "wrap": True},
                    {"type": "text", "text": now, "size": "xs", "color": "#90CAF9", "margin": "sm"},
                ]
            },
            "body": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#1E2A3A", "paddingAll": "14px", "spacing": "sm",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": index_name, "color": "#FFFFFF",
                             "size": "sm", "weight": "bold", "flex": 1},
                            {"type": "text", "text": f"{index_price:,.2f}  ", "color": "#FFFFFF",
                             "size": "sm", "weight": "bold"},
                            {"type": "text", "text": chg_text, "color": chg_col,
                             "size": "sm", "weight": "bold"},
                        ]
                    },
                    {"type": "separator", "color": "#37474F"},
                    {"type": "text",
                     "text": f"สแกน {scan_count} หุ้น  •  {scan_secs:.1f}s",
                     "color": "#B0BEC5", "size": "xs"},
                    {"type": "text", "text": "🟢 BUY 0   🟡 WATCH 0   🔴 EXIT 0",
                     "color": "#B0BEC5", "size": "xs"},
                    {"type": "separator", "color": "#37474F"},
                    {"type": "text", "text": "😴 ไม่พบสัญญาณที่ผ่าน AI filter",
                     "color": "#90CAF9", "size": "sm", "weight": "bold"},
                    {"type": "text", "text": "ตลาดยังไม่มี setup ที่ชัดเจนพอในวันนี้",
                     "color": "#CFD8DC", "size": "xs", "wrap": True},
                ]
            }
        }
    }


# ── helpers ───────────────────────────────────────────────────────

def _pill(text, bg, fg) -> dict:
    return {
        "type": "box", "layout": "vertical",
        "backgroundColor": bg, "cornerRadius": "20px",
        "paddingStart": "8px", "paddingEnd": "8px",
        "paddingTop": "4px", "paddingBottom": "4px",
        "contents": [
            {"type": "text", "text": text, "color": fg,
             "size": "xs", "weight": "bold", "align": "center"}
        ]
    }

def _kv_row(label, value) -> dict:
    return {
        "type": "box", "layout": "horizontal", "margin": "xs",
        "contents": [
            {"type": "text", "text": label, "color": "#78909C",
             "size": "xs", "flex": 2},
            {"type": "text", "text": value, "color": "#ECEFF1",
             "size": "xs", "flex": 5, "wrap": True},
        ]
    }

def market_summary(index_chg, market):
    if abs(index_chg) < 0.1:   return "⬛ ทรงตัว ไม่มีทิศทางชัดเจน"
    elif index_chg > 1.0:      return "🚀 ปรับขึ้นแรง มีแรงซื้อเข้ามาหนุน"
    elif index_chg > 0:        return "🟢 ปรับขึ้นเล็กน้อย แนวโน้มเป็นบวก"
    elif index_chg < -1.0:     return "💥 ปรับลงแรง แรงขายครอบงำตลาด"
    else:                       return "🔴 ปรับลงเล็กน้อย ควรระวังความเสี่ยง"

# ─────────────────────────────────────────────────────────────────
#  INDEX / CLAUDE / SIGNAL  (unchanged logic)
# ─────────────────────────────────────────────────────────────────

def get_index(ticker):
    try:
        df = yf.download(ticker, period="5d", interval="1d", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if len(df) >= 2:
            prev, close = float(df['Close'].iloc[-2]), float(df['Close'].iloc[-1])
            return round(close, 2), round((close - prev) / prev * 100, 2)
    except Exception as e:
        print(f"[INDEX ERROR] {ticker}: {e}")
    return 0.0, 0.0

def analyze_with_claude(ticker, signal_type, price, rsi, atr, tp=None, sl=None):
    try:
        client = anthropic.Anthropic()
        tp_sl  = f"TP: {tp:.2f} | SL: {sl:.2f}" if tp and sl else ""
        prompt = f"""คุณเป็นนักวิเคราะห์หุ้นสำหรับนักลงทุนระยะกลาง-ยาว
หุ้น {ticker} เกิดสัญญาณ {signal_type}
ราคา: {price:.2f}  RSI: {rsi:.1f}  ATR: {atr:.2f}  {tp_sl}
วิเคราะห์ภาษาไทย ไม่เกิน 3 บรรทัด แล้วให้คะแนน Conviction: X/5"""
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=250,
            messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text
    except Exception as e:
        print(f"[CLAUDE ERROR] {ticker}: {e}")
        return None

def get_conviction(ai_text):
    try:
        m = re.search(r'Conviction:\s*(\d)', ai_text or "")
        return int(m.group(1)) if m else 3
    except:
        return 3

def check_trade_signal(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df['EMA20']  = df['Close'].ewm(span=20,  adjust=False).mean()
        df['EMA50']  = df['Close'].ewm(span=50,  adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        delta = df['Close'].diff()
        df['RSI'] = 100 - (100 / (1 + delta.where(delta>0,0).rolling(14).mean() /
                                      (-delta.where(delta<0,0)).rolling(14).mean()))
        hl = df['High']-df['Low']
        df['ATR'] = pd.concat([hl, abs(df['High']-df['Close'].shift()),
                                abs(df['Low']-df['Close'].shift())],
                               axis=1).max(axis=1).rolling(14).mean()
        df['VOL_SURGE'] = df['Volume'] > df['Volume'].rolling(20).mean() * 1.3

        last, prev = df.iloc[-1], df.iloc[-2]
        price = float(last['Close'])
        atr   = float(last['ATR'])  if not pd.isna(last['ATR'])  else 0
        rsi   = float(last['RSI'])  if not pd.isna(last['RSI'])  else 0
        vol   = bool(last['VOL_SURGE'])

        ema_up = float(prev['EMA20']) < float(prev['EMA200']) and float(last['EMA20']) > float(last['EMA200'])
        ema_dn = float(prev['EMA20']) > float(prev['EMA200']) and float(last['EMA20']) < float(last['EMA200'])
        aligned = float(last['EMA20']) > float(last['EMA50']) > float(last['EMA200'])
        ema_cross = "golden" if float(last['EMA20']) > float(last['EMA200']) else "death"

        bb_mid = float(df['Close'].rolling(20).mean().iloc[-1])
        bb_std = float(df['Close'].rolling(20).std().iloc[-1])
        bb_pos = "above" if price > bb_mid+2*bb_std else ("below" if price < bb_mid-2*bb_std else "inside")

        if ema_up and (45 < rsi < 75) and aligned:
            vol_txt = "Volume Surge ✅" if vol else "Volume ปกติ"
            return ("BUY",  price, rsi, atr, ema_cross, bb_pos,
                    [f"EMA Golden Cross  {vol_txt}", f"RSI {rsi:.1f}"],
                    price+4*atr, price-2*atr)
        elif ema_dn:
            return ("SELL", price, rsi, atr, ema_cross, bb_pos,
                    ["EMA Death Cross ☠️", f"RSI {rsi:.1f}"], None, None)
        return None
    except Exception as e:
        print(f"[ERROR] {ticker}: {e}")
        return None

# ─────────────────────────────────────────────────────────────────
#  WATCHLIST
# ─────────────────────────────────────────────────────────────────

stocks = [
    'AAPL','MSFT','GOOGL','AMZN','META','TSLA','NVDA','AVGO','ORCL','ADBE',
    'NFLX','AMD','CRM','INTC','QCOM','TXN','AMAT','MU','LRCX','PANW',
    'V','MA','JPM','BAC','WFC','GS','MS','BLK','AXP','PYPL',
    'SCHW','C','USB','PNC','TFC','COF','SQ','HOOD',
    'WMT','COST','TGT','HD','LOW','NKE','SBUX','MCD','KO','PEP',
    'BABA','JD','PDD','MELI','SE',
    'PFE','JNJ','UNH','ABBV','MRK','LLY','TMO','DHR','ISRG','AMGN',
    'GILD','REGN','VRTX','MRNA','BMY','CVS','CI',
    'XOM','CVX','COP','SLB','EOG','BA','CAT','DE','GE','MMM',
    'HON','RTX','LMT','NOC','UPS','FDX',
    'PLTR','ARM','SMCI','CRWD','SNOW','DDOG','NET','COIN',
    'UBER','LYFT','ABNB','DASH','RBLX','ZM','DOCU','TWLO','OKTA',
    'MDB','SHOP','ETSY','PINS','SNAP','SPOT','MSTR','RIOT','MARA',
    'SPY','VOO','QQQ','DIA','VTI','SCHD','XLK','XLF','XLE','XLV',
    'SOXX','ARKK','GLD','SLV','TLT',
    'PTT.BK','PTTEP.BK','TOP.BK','OR.BK','BCP.BK','PTTGC.BK','IVL.BK',
    'CPALL.BK','CPAXT.BK','BJC.BK','HMPRO.BK','CRC.BK','CPN.BK',
    'AOT.BK','BA.BK','BEM.BK','BTS.BK','WHA.BK','AMATA.BK',
    'ADVANC.BK','TRUE.BK','INTUCH.BK','DELTA.BK','HANA.BK','KCE.BK',
    'KBANK.BK','SCB.BK','BBL.BK','KTB.BK','TTB.BK','TISCO.BK','KKP.BK',
    'BDMS.BK','BH.BK','BCH.BK','CHG.BK','GULF.BK','GPSC.BK','BGRIM.BK',
    'EA.BK','EGCO.BK','RATCH.BK','BANPU.BK','SCC.BK','SCGP.BK','CBG.BK',
    'OSP.BK','TU.BK','MINT.BK','LH.BK','AP.BK','SIRI.BK',
    'AWC.BK','CENTEL.BK','MTC.BK','TIDLOR.BK','SAWAD.BK','AEONTS.BK',
    'ORI.BK','SPALI.BK','STEC.BK','CK.BK','MAKRO.BK','COM7.BK',
    'GFPT.BK','TFG.BK','TPIPP.BK','SUPER.BK','SPCG.BK',
]
stocks = list(dict.fromkeys(stocks))

# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def _build_and_send(signals, flag, market_label, index_name,
                    index_price, index_chg, scan_count, scan_secs, ai_filtered):
    buy_n   = sum(1 for t,_,_ in signals if t=="BUY")
    watch_n = sum(1 for t,c,_ in signals if t=="SELL" and c<4)
    exit_n  = sum(1 for t,c,_ in signals if t=="SELL" and c>=4)
    summary = market_summary(index_chg, market_label)

    msgs = []
    if not signals:
        msgs.append(flex_no_signal(flag, market_label, index_name,
                                   index_price, index_chg, scan_count, scan_secs))
    else:
        msgs.append(flex_header_card(flag, market_label, index_name, index_price,
                                     index_chg, scan_count, scan_secs,
                                     buy_n, watch_n, exit_n, ai_filtered, summary))
        for _, _, card_flex in signals:
            msgs.append(card_flex)

    push_messages(msgs)


def main():
    t0 = time.time()
    print(f"[START] {datetime.now(TZ_THAI).strftime('%Y-%m-%d %H:%M:%S')} | {len(stocks)} หุ้น")

    set_price,   set_chg   = get_index("^SET.BK")
    sp500_price, sp500_chg = get_index("^GSPC")

    thai_sigs, us_sigs, filtered = [], [], 0

    for ticker in stocks:
        res = check_trade_signal(ticker)
        if not res: continue
        sig, price, rsi, atr, ema_cross, bb_pos, reasons, tp, sl = res
        print(f"[SIGNAL] {ticker} {sig}")

        ai_text    = analyze_with_claude(ticker, sig, price, rsi, atr, tp, sl)
        conviction = get_conviction(ai_text)
        print(f"[CONVICTION] {ticker}: {conviction}/5")

        if conviction < 3:
            filtered += 1
            continue

        is_thai  = ticker.endswith(".BK")
        currency = "฿" if is_thai else "$"
        display  = ticker.replace(".BK","") if is_thai else ticker

        card = flex_stock_card(display, sig, price, rsi, atr,
                               ema_cross, bb_pos, reasons, ai_text,
                               conviction, tp, sl, currency)
        bucket = thai_sigs if is_thai else us_sigs
        bucket.append((sig, conviction, card))

    scan_secs  = round(time.time()-t0, 1)
    thai_count = sum(1 for s in stocks if s.endswith(".BK"))
    us_count   = len(stocks) - thai_count
    print(f"[DONE] Thai={len(thai_sigs)} US={len(us_sigs)} filtered={filtered} time={scan_secs}s")

    _build_and_send(thai_sigs, "🏦", "SET", "SET Index",
                    set_price, set_chg, thai_count, scan_secs, filtered)
    time.sleep(1)
    _build_and_send(us_sigs, "🗽", "US", "S&P 500",
                    sp500_price, sp500_chg, us_count, scan_secs, filtered)

if __name__ == "__main__":
    main()
