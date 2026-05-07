"""
compact_cards.py — Compact multi-signal Flex Message cards grouped by sector.
Each bubble = one sector category, each row = one signal (tap to open chart).
"""
from datetime import datetime, timezone, timedelta
from ticker_info import get_name, get_sector

TZ_THAI = timezone(timedelta(hours=7))

SECTOR_HEADER_COLORS = {
    "Tech":          ("#0D1F3C", "#64B5F6"),
    "Semiconductor": ("#1A0D2E", "#CE93D8"),
    "Finance":       ("#0D2318", "#81C784"),
    "Health":        ("#1A2A0D", "#AED581"),
    "Energy":        ("#2A1A00", "#FFB74D"),
    "Consumer":      ("#1A1A2E", "#F48FB1"),
    "EV / Auto":     ("#002A1A", "#80CBC4"),
    "Crypto":        ("#1A0A00", "#FF8A65"),
    "Industrial":    ("#0D1A2E", "#90CAF9"),
    "Property":      ("#1A1200", "#FFF176"),
    "Transport":     ("#001A2A", "#80DEEA"),
    "International": ("#0A1A0A", "#A5D6A7"),
    "Broad ETF":     ("#1A1A0D", "#E6EE9C"),
    "Gold / Metal":  ("#1A1200", "#FFD54F"),
    "Bond ETF":      ("#0D0D2A", "#B0BEC5"),
    "Commodity ETF": ("#1A0A00", "#FFCC80"),
    "Small-Cap":     ("#001A1A", "#80CBC4"),
    "Thai":          ("#1A0D0D", "#EF9A9A"),
    "Other":         ("#111827", "#9CA3AF"),
}

def _sep():
    return {"type": "separator", "color": "#1E2D3D", "margin": "sm"}

def _signal_row(ticker, sig, price, rsi, rr, currency, chart_url):
    """One compact row for a single signal — tappable to open TradingView."""
    is_buy  = sig == "BUY"
    is_sell = sig == "SELL"
    bc      = "#00E676" if is_buy else "#FF5252"
    arrow   = "▲" if is_buy else "▼"
    name    = get_name(ticker)
    display = ticker.replace(".BK", "") if ticker.endswith(".BK") else ticker

    rsi_clr = "#FF5252" if rsi >= 70 else ("#00E676" if rsi <= 30 else "#90CAF9")
    rsi_tag = "🔺" if rsi >= 70 else ("🔻" if rsi <= 30 else "✅")
    rr_txt  = f"R:R 1:{rr:.1f}" if rr and rr > 0 else ""

    return {
        "type": "box",
        "layout": "vertical",
        "margin": "sm",
        "action": {"type": "uri", "uri": chart_url},
        "contents": [
            # Row 1: badge | ticker | name | price
            {"type": "box", "layout": "horizontal",
             "alignItems": "center", "contents": [
                # Signal badge pill
                {"type": "box", "layout": "vertical", "flex": 0,
                 "backgroundColor": bc, "cornerRadius": "4px",
                 "paddingStart": "5px", "paddingEnd": "5px",
                 "paddingTop": "2px", "paddingBottom": "2px",
                 "contents": [{"type": "text", "text": arrow,
                               "color": "#000000", "size": "xxs", "weight": "bold"}]},
                # Ticker + name
                {"type": "box", "layout": "vertical", "flex": 4,
                 "paddingStart": "8px", "contents": [
                     {"type": "text", "text": display,
                      "color": "#FFFFFF", "size": "sm", "weight": "bold"},
                     {"type": "text", "text": name,
                      "color": "#546E7A", "size": "xxs", "wrap": False},
                 ]},
                # Price
                {"type": "text", "text": f"{currency}{price:,.2f}",
                 "color": bc, "size": "sm", "weight": "bold",
                 "flex": 3, "align": "end"},
            ]},
            # Row 2: RSI | R:R | tap hint
            {"type": "box", "layout": "horizontal",
             "margin": "xs", "paddingStart": "20px", "contents": [
                {"type": "text", "text": f"RSI {rsi:.0f} {rsi_tag}",
                 "color": rsi_clr, "size": "xxs", "flex": 2},
                {"type": "text", "text": rr_txt,
                 "color": "#FFD54F", "size": "xxs", "flex": 2, "align": "center"},
                {"type": "text", "text": "📊 →",
                 "color": "#37474F", "size": "xxs", "flex": 1, "align": "end"},
            ]},
        ]
    }

def flex_compact_sector_bubble(sector_emoji, sector_name, signals):
    """
    Build one bubble for a sector.
    signals: list of (ticker, sig, price, rsi, rr, currency, chart_url)
    """
    hbg, hfg = SECTOR_HEADER_COLORS.get(sector_name, ("#111827", "#9CA3AF"))
    now = datetime.now(TZ_THAI).strftime("%d %b  %H:%M")

    buy_n  = sum(1 for _, s, *_ in signals if s == "BUY")
    sell_n = len(signals) - buy_n
    pill_parts = []
    if buy_n:
        pill_parts.append({"type": "text", "text": f"▲{buy_n} BUY",
                           "color": "#00E676", "size": "xxs", "weight": "bold"})
    if buy_n and sell_n:
        pill_parts.append({"type": "text", "text": "  ", "size": "xxs"})
    if sell_n:
        pill_parts.append({"type": "text", "text": f"▼{sell_n} SELL",
                           "color": "#FF5252", "size": "xxs", "weight": "bold"})

    rows = []
    for i, (ticker, sig, price, rsi, rr, currency, chart_url) in enumerate(signals):
        if i > 0:
            rows.append(_sep())
        rows.append(_signal_row(ticker, sig, price, rsi, rr, currency, chart_url))

    return {
        "type": "bubble", "size": "kilo",
        "header": {
            "type": "box", "layout": "vertical",
            "backgroundColor": hbg, "paddingAll": "12px", "spacing": "xs",
            "contents": [
                {"type": "box", "layout": "horizontal",
                 "alignItems": "center", "contents": [
                    {"type": "text",
                     "text": f"{sector_emoji} {sector_name}",
                     "weight": "bold", "size": "sm", "color": hfg, "flex": 1},
                    {"type": "text", "text": now,
                     "size": "xxs", "color": "#37474F", "align": "end"},
                ]},
                {"type": "box", "layout": "horizontal",
                 "contents": pill_parts},
            ]
        },
        "body": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#0A1020", "paddingAll": "12px",
            "spacing": "none", "contents": rows,
        }
    }

def build_compact_carousels(all_signals, push_fn, alt_prefix="📡 Signals"):
    """
    Group signals by sector, build compact bubbles, send as carousel(s).

    all_signals: list of dicts:
        {ticker, sig, price, rsi, rr, currency, chart_url}

    push_fn: callable(list_of_messages)
    """
    if not all_signals:
        return

    # Group by sector preserving order of first appearance
    sector_order = []
    sector_map: dict[str, list] = {}
    for s in all_signals:
        emoji, name = get_sector(s["ticker"])
        key = f"{emoji} {name}"
        if key not in sector_map:
            sector_map[key] = []
            sector_order.append((emoji, name, key))
        sector_map[key].append((
            s["ticker"], s["sig"], s["price"], s["rsi"],
            s.get("rr", 0), s["currency"], s["chart_url"]
        ))

    # Build bubbles
    bubbles = []
    for emoji, name, key in sector_order:
        bubbles.append(
            flex_compact_sector_bubble(emoji, name, sector_map[key])
        )

    # Send in chunks of 10
    import time as _time
    total       = len(all_signals)
    total_pages = (len(bubbles) + 9) // 10

    # When split across multiple messages, send a plain-text summary first
    # so the user knows how many carousel messages to scroll through.
    if total_pages > 1:
        sector_names = [name for _, name, _ in sector_order]
        summary_lines = [f"📊 {alt_prefix}"]
        summary_lines.append(f"พบ {total} สัญญาณ ใน {total_pages} ชุดข้อความ — เลื่อนขึ้นเพื่อดูทั้งหมด ↑")
        summary_lines.append("")
        for i in range(0, len(sector_names), 10):
            chunk_names = sector_names[i:i + 10]
            pg = i // 10 + 1
            summary_lines.append(f"ชุดที่ {pg}: {', '.join(chunk_names)}")
        push_fn([{
            "type": "text",
            "text": "\n".join(summary_lines),
        }])
        _time.sleep(0.3)

    for i in range(0, len(bubbles), 10):
        chunk    = bubbles[i:i + 10]
        page_num = i // 10 + 1
        # Include sector names covered by this page in the altText
        page_sectors = [name for _, name, _ in sector_order[i:i + 10]]
        sectors_str  = ", ".join(page_sectors)
        if total_pages > 1:
            alt = f"{alt_prefix} ({page_num}/{total_pages}) — {sectors_str}"
        else:
            alt = f"{alt_prefix} — {total} สัญญาณ | {sectors_str}"
        push_fn([{
            "type": "flex",
            "altText": alt,
            "contents": {"type": "carousel", "contents": chunk},
        }])
        if i + 10 < len(bubbles):
            _time.sleep(0.5)
