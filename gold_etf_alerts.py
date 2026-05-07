"""
gold_etf_alerts.py — Gold & ETF Daily Alert
Dedicated scanner for gold, commodities, and ETF sectors.
Called from trading_bot.py main()
"""
import yfinance as yf
import pandas as pd
import anthropic
import os, re, time
from datetime import datetime, timezone, timedelta

TZ_THAI    = timezone(timedelta(hours=7))
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# ── ETF watchlists by category ────────────────────────────────────

GOLD_TICKERS = [
    'GLD',   # SPDR Gold Shares — ราคาทองคำ
    'IAU',   # iShares Gold Trust
    'GDX',   # VanEck Gold Miners
    'GDXJ',  # VanEck Junior Gold Miners
    'SLV',   # iShares Silver Trust
]

ETF_CATEGORIES = {
    "📊 Broad Market": ['SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'SCHD', 'VIG'],
    "🏭 Sectors":      ['XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLY', 'XLP', 'XLB', 'XLRE'],
    "🔬 Thematic":     ['SOXX', 'ARKK', 'BOTZ', 'CIBR', 'ICLN'],
    "🏦 Bonds":        ['TLT', 'IEF', 'HYG', 'LQD', 'SHY'],
    "🌏 International":['EWJ', 'EEM', 'FXI', 'VEA', 'EWZ'],
    "🛢️ Commodities":  ['USO', 'UNG', 'DBA', 'DBB', 'PDBC'],
}

ALL_ETF_TICKERS = GOLD_TICKERS + [t for tickers in ETF_CATEGORIES.values() for t in tickers]

# ── ETF display names ─────────────────────────────────────────────

ETF_NAMES = {
    'GLD':  'SPDR Gold',    'IAU':  'iShares Gold', 'GDX':  'Gold Miners',
    'GDXJ': 'Jr Miners',    'SLV':  'Silver',
    'SPY':  'S&P 500',      'QQQ':  'Nasdaq 100',   'IWM':  'Russell 2000',
    'DIA':  'Dow Jones',    'VTI':  'Total Market', 'SCHD': 'Dividend',
    'VIG':  'Div Growth',   'XLK':  'Tech',         'XLF':  'Finance',
    'XLE':  'Energy',       'XLV':  'Healthcare',   'XLI':  'Industrial',
    'XLY':  'Cons Disc',    'XLP':  'Cons Staples', 'XLB':  'Materials',
    'XLRE': 'Real Estate',  'SOXX': 'Semicon',      'ARKK': 'ARK Innov',
    'BOTZ': 'Robotics',     'CIBR': 'Cybersecurity','ICLN': 'Clean Energy',
    'TLT':  '20Y Treasury', 'IEF':  '7-10Y Bond',   'HYG':  'High Yield',
    'LQD':  'Corp Bond',    'SHY':  '1-3Y Treasury','EWJ':  'Japan',
    'EEM':  'Emerg Mkt',    'FXI':  'China',        'VEA':  'Dev Mkt',
    'EWZ':  'Brazil',       'USO':  'Oil',          'UNG':  'Nat Gas',
    'DBA':  'Agriculture',  'DBB':  'Base Metals',  'PDBC': 'Commodities',
}

# ── helpers (re-use from trading_bot style) ───────────────────────

def _sep():
    return {"type": "separator", "color": "#37474F", "margin": "sm"}

def _kv(label, value, vcolor="#ECEFF1"):
    return {"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
        {"type": "text", "text": label, "color": "#78909C", "size": "xs", "flex": 3},
        {"type": "text", "text": value, "color": vcolor,   "size": "xs", "flex": 4, "wrap": True},
    ]}

def _pill(text, bg, fg):
    return {"type": "box", "layout": "vertical", "backgroundColor": bg,
            "cornerRadius": "16px", "paddingStart": "8px", "paddingEnd": "8px",
            "paddingTop": "3px", "paddingBottom": "3px",
            "contents": [{"type": "text", "text": text, "color": fg,
                          "size": "xxs", "weight": "bold", "align": "center"}]}

def tv_symbol(ticker):
    return "AMEX:" + ticker   # all ETFs listed on AMEX / NYSE Arca

def tv_chart_url(ticker):
    sym = tv_symbol(ticker)
    return (f"https://www.tradingview.com/chart/?symbol={sym}&interval=D"
            f"&studies=STD%3BEMA%4020%2C%2050%2C%20200")

# ── price & signal ────────────────────────────────────────────────

def get_etf_quote(ticker):
    """Return (price, pct_change_1d, above_ema20, above_ema50, above_ema200, rsi, trend_str)."""
    try:
        df = yf.download(ticker, period="1y", interval="1d",
                         auto_adjust=True, progress=False)
        if df.empty or len(df) < 5:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        for span, col in [(20, 'EMA20'), (50, 'EMA50'), (200, 'EMA200')]:
            df[col] = df['Close'].ewm(span=span, adjust=False).mean()
        d      = df['Close'].diff()
        gain   = d.where(d > 0, 0).rolling(14).mean()
        loss   = (-d.where(d < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain / loss))

        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        price = float(last['Close'])
        chg   = (price - float(prev['Close'])) / float(prev['Close']) * 100
        rsi   = float(last['RSI']) if not pd.isna(last['RSI']) else 50

        a20  = price > float(last['EMA20'])
        a50  = price > float(last['EMA50'])
        a200 = price > float(last['EMA200'])

        if a20 and a50 and a200:
            trend = "Uptrend ▲"
        elif not a20 and not a50 and not a200:
            trend = "Downtrend ▼"
        else:
            trend = "Mixed ↔"

        return price, chg, a20, a50, a200, rsi, trend
    except Exception as e:
        print(f"[ETF QUOTE] {ticker}: {e}")
        return None

def check_etf_signal(ticker):
    """
    Returns (sig, price, rsi, atr, ema_cross, bb_pos, tp, sl) or None.
    Reuses the same EMA-crossover logic as trading_bot.check_signal.
    """
    try:
        df = yf.download(ticker, period="1y", interval="1d",
                         auto_adjust=True, progress=False)
        if df.empty or len(df) < 200:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        for span, col in [(20, 'EMA20'), (50, 'EMA50'), (200, 'EMA200')]:
            df[col] = df['Close'].ewm(span=span, adjust=False).mean()

        d      = df['Close'].diff()
        gain   = d.where(d > 0, 0).rolling(14).mean()
        loss   = (-d.where(d < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain / loss))

        hl  = df['High'] - df['Low']
        df['ATR'] = pd.concat(
            [hl, abs(df['High'] - df['Close'].shift()), abs(df['Low'] - df['Close'].shift())],
            axis=1).max(axis=1).rolling(14).mean()

        last, prev = df.iloc[-1], df.iloc[-2]
        price = float(last['Close'])
        atr   = float(last['ATR']) if not pd.isna(last['ATR']) else 0
        rsi   = float(last['RSI']) if not pd.isna(last['RSI']) else 50

        e20, e200     = float(last['EMA20']), float(last['EMA200'])
        e20p, e200p   = float(prev['EMA20']), float(prev['EMA200'])
        e50           = float(last['EMA50'])
        golden_cross  = e20p < e200p and e20 > e200
        death_cross   = e20p > e200p and e20 < e200
        aligned_up    = e20 > e50 > e200

        bm = float(df['Close'].rolling(20).mean().iloc[-1])
        bs = float(df['Close'].rolling(20).std().iloc[-1])
        bb_pos = "above" if price > bm + 2*bs else ("below" if price < bm - 2*bs else "inside")
        ec     = "golden" if e20 > e200 else "death"

        if golden_cross and 45 < rsi < 75 and aligned_up:
            return ("BUY",  price, rsi, atr, ec, bb_pos, price + 4*atr, price - 2*atr)
        elif death_cross:
            return ("SELL", price, rsi, atr, ec, bb_pos, None, None)
        return None
    except Exception as e:
        print(f"[ETF SIGNAL] {ticker}: {e}")
        return None

def analyze_etf_with_claude(ticker, sig, price, rsi, atr, tp, sl):
    try:
        client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        tp_sl   = f"TP:{tp:.2f} SL:{sl:.2f}" if tp and sl else ""
        name    = ETF_NAMES.get(ticker, ticker)
        msg     = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=200,
            messages=[{"role": "user", "content":
                f"วิเคราะห์ ETF {ticker} ({name}) สัญญาณ {sig} ราคา {price:.2f} RSI {rsi:.1f} ATR {atr:.4f} {tp_sl}\n"
                f"ภาษาไทย ไม่เกิน 2 บรรทัด แล้วให้คะแนน Conviction: X/5"}])
        return msg.content[0].text
    except Exception as e:
        print(f"[CLAUDE ETF] {ticker}: {e}")
        return None

def get_conviction(txt):
    try:
        m = re.search(r'Conviction:\s*(\d)', txt or "")
        return int(m.group(1)) if m else 3
    except:
        return 3

# ── Flex card builders ────────────────────────────────────────────

def flex_gold_summary(gold_data):
    """
    gold_data: list of (ticker, price, chg, rsi, trend) for GLD/IAU/GDX/GDXJ/SLV
    """
    now = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")

    # Primary: GLD price
    gld = next((d for d in gold_data if d[0] == 'GLD'), None)
    if not gld:
        gld = gold_data[0] if gold_data else None

    if gld:
        _, gld_price, gld_chg, _, gld_trend = gld
        up      = gld_chg >= 0
        chg_clr = "#FFD54F" if up else "#FF8A65"
        chg_txt = f"{'↑+' if up else '↓'}{gld_chg:.2f}%"
    else:
        gld_price, chg_txt, chg_clr, gld_trend = 0, "N/A", "#90CAF9", "N/A"

    rows = []
    for ticker, price, chg, rsi, trend in gold_data:
        name    = ETF_NAMES.get(ticker, ticker)
        up_t    = chg >= 0
        cc      = "#FFD54F" if up_t else "#FF8A65"
        chg_t   = f"{'▲' if up_t else '▼'}{abs(chg):.2f}%"
        tr_clr  = "#69F0AE" if "▲" in trend else ("#FF5252" if "▼" in trend else "#90CAF9")
        rows.append({"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
            {"type": "text", "text": ticker, "color": "#FFFFFF", "size": "xs",
             "weight": "bold", "flex": 2},
            {"type": "text", "text": name,   "color": "#78909C", "size": "xs", "flex": 3},
            {"type": "text", "text": f"${price:,.2f}", "color": "#ECEFF1",
             "size": "xs", "flex": 3, "align": "end"},
            {"type": "text", "text": chg_t, "color": cc, "size": "xs",
             "flex": 2, "align": "end"},
            {"type": "text", "text": trend.split()[0], "color": tr_clr,
             "size": "xs", "flex": 2, "align": "end"},
        ]})

    return {
        "type": "flex",
        "altText": f"🥇 Gold & Precious Metals — GLD ${gld_price:,.2f}  {chg_txt}",
        "contents": {
            "type": "bubble", "size": "kilo",
            "header": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#1A1200", "paddingAll": "14px",
                "contents": [
                    {"type": "text", "text": "🥇 Gold & Precious Metals",
                     "weight": "bold", "size": "sm", "color": "#F9A825"},
                    {"type": "text", "text": now, "size": "xs",
                     "color": "#795548", "margin": "xs"},
                ]
            },
            "body": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#120F00", "paddingAll": "14px", "spacing": "sm",
                "contents": [
                    # GLD big price
                    {"type": "box", "layout": "horizontal", "contents": [
                        {"type": "text", "text": "GLD", "weight": "bold",
                         "size": "xxl", "color": "#FFD54F", "flex": 1},
                        {"type": "text", "text": f"${gld_price:,.2f}",
                         "weight": "bold", "size": "xl", "color": "#FFFFFF", "align": "end"},
                        {"type": "text", "text": f"  {chg_txt}", "weight": "bold",
                         "size": "md", "color": chg_clr, "align": "end"},
                    ]},
                    {"type": "text", "text": f"Trend: {gld_trend}",
                     "color": "#A1887F", "size": "xs", "margin": "xs"},
                    _sep(),
                    # Column header
                    {"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
                        {"type": "text", "text": "Ticker", "color": "#546E7A",
                         "size": "xxs", "flex": 2},
                        {"type": "text", "text": "Name", "color": "#546E7A",
                         "size": "xxs", "flex": 3},
                        {"type": "text", "text": "Price", "color": "#546E7A",
                         "size": "xxs", "flex": 3, "align": "end"},
                        {"type": "text", "text": "Chg%", "color": "#546E7A",
                         "size": "xxs", "flex": 2, "align": "end"},
                        {"type": "text", "text": "Trend", "color": "#546E7A",
                         "size": "xxs", "flex": 2, "align": "end"},
                    ]},
                    *rows,
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#0A0900", "paddingAll": "10px",
                "contents": [
                    {"type": "button",
                     "action": {"type": "uri", "label": "📊 ดูกราฟ GLD",
                                "uri": tv_chart_url("GLD")},
                     "style": "primary", "color": "#F9A825", "height": "sm"},
                ]
            }
        }
    }

def flex_etf_category_summary(category_name, etf_rows):
    """
    etf_rows: list of (ticker, price, chg, rsi, trend)
    Returns a bubble card for one ETF category.
    """
    now      = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")
    up_count = sum(1 for _, _, chg, _, _ in etf_rows if chg >= 0)
    dn_count = len(etf_rows) - up_count

    rows = []
    for ticker, price, chg, rsi, trend in etf_rows:
        name   = ETF_NAMES.get(ticker, ticker)
        up_t   = chg >= 0
        cc     = "#69F0AE" if up_t else "#FF5252"
        chg_t  = f"{'▲' if up_t else '▼'}{abs(chg):.2f}%"
        tr_clr = "#69F0AE" if "▲" in trend else ("#FF5252" if "▼" in trend else "#90CAF9")
        rows.append({"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
            {"type": "text", "text": ticker, "color": "#FFFFFF", "size": "xs",
             "weight": "bold", "flex": 2},
            {"type": "text", "text": name,   "color": "#78909C", "size": "xs", "flex": 3},
            {"type": "text", "text": f"${price:,.2f}", "color": "#ECEFF1",
             "size": "xs", "flex": 3, "align": "end"},
            {"type": "text", "text": chg_t, "color": cc, "size": "xs",
             "flex": 2, "align": "end"},
            {"type": "text", "text": trend.split()[0], "color": tr_clr,
             "size": "xs", "flex": 2, "align": "end"},
        ]})

    sentiment_txt = f"▲ {up_count} ตัวบวก  ▼ {dn_count} ตัวลบ"
    sentiment_clr = "#69F0AE" if up_count >= dn_count else "#FF5252"

    return {
        "type": "bubble", "size": "kilo",
        "header": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#0D1B2A", "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": category_name,
                 "weight": "bold", "size": "sm", "color": "#64B5F6"},
                {"type": "text", "text": now, "size": "xs",
                 "color": "#546E7A", "margin": "xs"},
            ]
        },
        "body": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#0E1621", "paddingAll": "14px", "spacing": "xs",
            "contents": [
                {"type": "text", "text": sentiment_txt, "color": sentiment_clr,
                 "size": "xs", "weight": "bold"},
                _sep(),
                {"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
                    {"type": "text", "text": "Ticker", "color": "#546E7A", "size": "xxs", "flex": 2},
                    {"type": "text", "text": "Name",   "color": "#546E7A", "size": "xxs", "flex": 3},
                    {"type": "text", "text": "Price",  "color": "#546E7A", "size": "xxs",
                     "flex": 3, "align": "end"},
                    {"type": "text", "text": "Chg%",   "color": "#546E7A", "size": "xxs",
                     "flex": 2, "align": "end"},
                    {"type": "text", "text": "Trend",  "color": "#546E7A", "size": "xxs",
                     "flex": 2, "align": "end"},
                ]},
                *rows,
            ]
        }
    }

def flex_etf_signal_card(ticker, sig, price, rsi, atr, ec, bp, ai_text, conv, tp, sl):
    """Signal card for an ETF that triggered BUY/SELL."""
    is_buy = sig == "BUY"
    bc     = "#FFD54F" if is_buy else "#FF5252"
    hbg    = "#1A1400" if is_buy else "#1A0000"
    badge  = "🟡 BUY"  if is_buy else "🔴 SELL"
    name   = ETF_NAMES.get(ticker, ticker)
    stars  = "⭐" * conv + "☆" * (5 - conv)
    rr_txt = ""
    if tp and sl and abs(price - sl) > 0:
        rr = abs(tp - price) / abs(price - sl)
        rr_txt = f"1 : {rr:.1f}"

    body_items = [
        {"type": "box", "layout": "horizontal", "contents": [
            {"type": "text", "text": ticker, "weight": "bold", "size": "xl",
             "color": "#FFFFFF", "flex": 1},
            {"type": "text", "text": f"${price:,.2f}", "weight": "bold",
             "size": "lg", "color": bc, "align": "end"},
        ]},
        {"type": "text", "text": name, "color": "#78909C", "size": "xs", "margin": "xs"},
        _sep(),
        _kv("📊 RSI",     f"{rsi:.1f}  {'Oversold 🔻' if rsi<=30 else ('Overbought 🔺' if rsi>=70 else 'Normal ✅')}"),
        _kv("📈 MA Cross", "Golden Cross ✨" if ec == "golden" else "Death Cross ☠️"),
        _kv("📉 BB",       {"above": "Breakout 🔺", "below": "Squeeze 🔻", "inside": "Normal ➡️"}.get(bp, "")),
        _kv("📐 ATR",      f"{atr:.4f}"),
    ]
    if tp and sl:
        body_items += [
            _sep(),
            _kv("🎯 TP", f"${tp:.2f}"),
            _kv("🛡 SL", f"${sl:.2f}"),
            _kv("📏 R:R", rr_txt),
        ]
    body_items += [
        _sep(),
        {"type": "box", "layout": "horizontal", "contents": [
            {"type": "text", "text": "🤖 AI", "color": "#B0BEC5", "size": "xs", "flex": 0},
            {"type": "text", "text": f"  {stars}", "color": "#FFD54F", "size": "xs", "flex": 1},
        ]},
    ]
    if ai_text:
        lines = [l.strip() for l in ai_text.strip().split("\n") if l.strip()][:2]
        body_items.append({"type": "text", "text": "\n".join(lines),
                           "color": "#CFD8DC", "size": "xs", "wrap": True, "margin": "xs"})

    return {
        "type": "bubble", "size": "kilo",
        "header": {
            "type": "box", "layout": "vertical",
            "backgroundColor": hbg, "paddingAll": "12px",
            "contents": [
                {"type": "text", "text": f"{badge}  ETF Signal",
                 "weight": "bold", "size": "sm", "color": bc}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#1E2A3A", "paddingAll": "14px",
            "spacing": "xs", "contents": body_items,
        },
        "footer": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#263238", "paddingAll": "10px",
            "contents": [
                {"type": "button",
                 "action": {"type": "uri", "label": "📊 ดูกราฟ + EMA20/50/200",
                            "uri": tv_chart_url(ticker)},
                 "style": "primary", "color": bc, "height": "sm"}
            ]
        }
    }

# ── main scanner ─────────────────────────────────────────────────

def send_gold_etf_alerts(push_fn):
    """
    push_fn: callable(messages_list) — reuse push_messages from trading_bot
    """
    print(f"[GOLD/ETF] Starting scan — {len(ALL_ETF_TICKERS)} tickers")
    t0 = time.time()

    # 1. Collect quotes for all tickers
    quotes = {}
    for ticker in ALL_ETF_TICKERS:
        q = get_etf_quote(ticker)
        if q:
            quotes[ticker] = q   # (price, chg, a20, a50, a200, rsi, trend)
        time.sleep(0.05)

    # 2. Build gold summary card
    gold_data = []
    for t in GOLD_TICKERS:
        if t in quotes:
            price, chg, _, _, _, rsi, trend = quotes[t]
            gold_data.append((t, price, chg, rsi, trend))

    bubbles = []
    if gold_data:
        gold_card = flex_gold_summary(gold_data)
        bubbles.append(gold_card['contents'])

    # 3. Build ETF category summary cards
    for cat_name, tickers in ETF_CATEGORIES.items():
        rows = []
        for t in tickers:
            if t in quotes:
                price, chg, _, _, _, rsi, trend = quotes[t]
                rows.append((t, price, chg, rsi, trend))
        if rows:
            bubbles.append(flex_etf_category_summary(cat_name, rows))

    # 4. Scan for signals (EMA crossover)
    signal_bubbles = []
    filtered = 0
    for ticker in ALL_ETF_TICKERS:
        res = check_etf_signal(ticker)
        if not res:
            continue
        sig, price, rsi, atr, ec, bp, tp, sl = res
        print(f"[ETF SIGNAL] {ticker} {sig}")

        ai   = analyze_etf_with_claude(ticker, sig, price, rsi, atr, tp, sl)
        conv = get_conviction(ai)
        if conv < 3:
            filtered += 1
            continue

        card = flex_etf_signal_card(ticker, sig, price, rsi, atr, ec, bp, ai, conv, tp, sl)
        signal_bubbles.append(card)
        time.sleep(0.2)

    print(f"[GOLD/ETF] quotes={len(quotes)} signals={len(signal_bubbles)} "
          f"filtered={filtered}  {round(time.time()-t0,1)}s")

    # 5. Send overview carousel (gold + category summaries)
    if bubbles:
        total_pages = (len(bubbles) + 9) // 10
        for i in range(0, len(bubbles), 10):
            chunk    = bubbles[i:i + 10]
            page_num = i // 10 + 1
            suffix   = f" ({page_num}/{total_pages})" if total_pages > 1 else ""
            push_fn([{
                "type": "flex",
                "altText": f"🥇 Gold & ETF Overview{suffix}",
                "contents": {"type": "carousel", "contents": chunk},
            }])
            if i + 10 < len(bubbles):
                time.sleep(0.5)

    time.sleep(0.5)

    # 6. Send signal cards (if any)
    if signal_bubbles:
        total_pages = (len(signal_bubbles) + 9) // 10
        for i in range(0, len(signal_bubbles), 10):
            chunk    = signal_bubbles[i:i + 10]
            page_num = i // 10 + 1
            suffix   = f" ({page_num}/{total_pages})" if total_pages > 1 else ""
            push_fn([{
                "type": "flex",
                "altText": f"📡 ETF Signals — {len(signal_bubbles)} สัญญาณ{suffix}",
                "contents": {"type": "carousel", "contents": chunk},
            }])
            if i + 10 < len(signal_bubbles):
                time.sleep(0.5)
    else:
        print("[GOLD/ETF] No ETF signals today — skipping signal push")


if __name__ == "__main__":
    # Quick test without LINE push
    import json

    def print_push(msgs):
        print(json.dumps(msgs, ensure_ascii=False, indent=2)[:500])

    send_gold_etf_alerts(print_push)
