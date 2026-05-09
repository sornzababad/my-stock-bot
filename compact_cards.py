"""
compact_cards.py — Compact sector-grouped Flex bubbles.
Each bubble = one sector, each row = one signal with BUY/SELL, price, RSI, TP, SL.
"""
from datetime import datetime, timezone, timedelta
from ticker_info import get_name, get_sector

TZ_THAI = timezone(timedelta(hours=7))

SECTOR_COLORS = {
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
    "Broad ETF":     ("#1A1A0D", "#E6EE9C"),
    "Gold / Metal":  ("#1A1200", "#FFD54F"),
    "Bond ETF":      ("#0D0D2A", "#B0BEC5"),
    "Thai":          ("#1A0D0D", "#EF9A9A"),
    "Other":         ("#111827", "#9CA3AF"),
}


def _sep():
    return {"type": "separator", "color": "#1E2D3D", "margin": "sm"}


def _signal_row(ticker, sig, price, rsi, rr, tp, sl, currency, chart_url):
    is_buy  = sig == "BUY"
    bc      = "#00E676" if is_buy else "#FF5252"
    arrow   = "▲" if is_buy else "▼"
    name    = get_name(ticker)
    display = ticker.replace(".BK", "") if ticker.endswith(".BK") else ticker

    rsi_clr = "#FF5252" if rsi >= 70 else ("#00E676" if rsi <= 30 else "#90CAF9")
    rsi_tag = "🔺" if rsi >= 70 else ("🔻" if rsi <= 30 else "")

    pct_tp = f"{(tp - price) / price * 100:+.1f}%" if tp and price else ""
    pct_sl = f"{(sl - price) / price * 100:+.1f}%" if sl and price else ""
    tp_txt = f"TP {currency}{tp:,.2f} {pct_tp}" if tp else ""
    sl_txt = f"SL {currency}{sl:,.2f} {pct_sl}" if sl else ""

    return {
        "type": "box", "layout": "vertical", "margin": "sm",
        "action": {"type": "uri", "uri": chart_url},
        "contents": [
            # Row 1: badge | ticker | company name | price
            {"type": "box", "layout": "horizontal", "alignItems": "center", "contents": [
                {"type": "box", "layout": "vertical", "flex": 0,
                 "backgroundColor": bc, "cornerRadius": "3px",
                 "paddingStart": "4px", "paddingEnd": "4px",
                 "paddingTop": "1px", "paddingBottom": "1px",
                 "contents": [{"type": "text", "text": arrow,
                               "color": "#000000", "size": "xxs", "weight": "bold"}]},
                {"type": "box", "layout": "vertical", "flex": 4, "paddingStart": "7px",
                 "contents": [
                     {"type": "text", "text": display,
                      "color": "#FFFFFF", "size": "sm", "weight": "bold"},
                     {"type": "text", "text": name,
                      "color": "#607D8B", "size": "xxs", "wrap": False},
                 ]},
                {"type": "text", "text": f"{currency}{price:,.2f}",
                 "color": bc, "size": "sm", "weight": "bold",
                 "flex": 3, "align": "end"},
            ]},
            # Row 2: RSI | TP | SL
            {"type": "box", "layout": "horizontal",
             "margin": "xs", "paddingStart": "18px", "contents": [
                {"type": "text", "text": f"RSI {rsi:.0f} {rsi_tag}",
                 "color": rsi_clr, "size": "xxs", "flex": 2},
                {"type": "text", "text": tp_txt,
                 "color": "#69F0AE", "size": "xxs", "flex": 3, "align": "center"},
                {"type": "text", "text": sl_txt,
                 "color": "#FF8A80", "size": "xxs", "flex": 3, "align": "end"},
            ]},
        ]
    }


def flex_sector_bubble(sector_emoji, sector_name, signals):
    """
    One Flex bubble for a sector.
    signals: list of (ticker, sig, price, rsi, rr, tp, sl, currency, chart_url)
    """
    hbg, hfg = SECTOR_COLORS.get(sector_name, ("#111827", "#9CA3AF"))
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
    for i, sig_data in enumerate(signals):
        if i > 0:
            rows.append(_sep())
        rows.append(_signal_row(*sig_data))

    return {
        "type": "bubble", "size": "kilo",
        "header": {
            "type": "box", "layout": "vertical",
            "backgroundColor": hbg, "paddingAll": "10px", "spacing": "xs",
            "contents": [
                {"type": "box", "layout": "horizontal", "alignItems": "center", "contents": [
                    {"type": "text", "text": f"{sector_emoji} {sector_name}",
                     "weight": "bold", "size": "sm", "color": hfg, "flex": 1},
                    {"type": "text", "text": now,
                     "size": "xxs", "color": "#37474F", "align": "end"},
                ]},
                {"type": "box", "layout": "horizontal", "contents": pill_parts},
            ]
        },
        "body": {
            "type": "box", "layout": "vertical",
            "backgroundColor": "#0A1020", "paddingAll": "10px",
            "spacing": "none", "contents": rows,
        }
    }


def build_compact_carousels(all_signals, push_fn, alt_prefix="📡 Signals"):
    """
    Group signals by sector and send as compact carousel(s).

    all_signals: list of dicts with keys:
        ticker, sig, price, rsi, rr, tp, sl, currency, chart_url
    push_fn: callable(list_of_messages)
    """
    if not all_signals:
        return

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
            s.get("rr", 0), s.get("tp"), s.get("sl"),
            s["currency"], s["chart_url"],
        ))

    bubbles = [flex_sector_bubble(e, n, sector_map[k]) for e, n, k in sector_order]

    import time as _time
    total       = len(all_signals)
    total_pages = (len(bubbles) + 9) // 10

    if total_pages > 1:
        sector_names = [n for _, n, _ in sector_order]
        lines = [f"📊 {alt_prefix}",
                 f"พบ {total} สัญญาณ ใน {total_pages} ชุดข้อความ — เลื่อนขึ้นเพื่อดูทั้งหมด ↑", ""]
        for i in range(0, len(sector_names), 10):
            pg = i // 10 + 1
            lines.append(f"ชุดที่ {pg}: {', '.join(sector_names[i:i+10])}")
        push_fn([{"type": "text", "text": "\n".join(lines)}])
        _time.sleep(0.3)

    for i in range(0, len(bubbles), 10):
        chunk        = bubbles[i:i + 10]
        page_num     = i // 10 + 1
        page_sectors = [n for _, n, _ in sector_order[i:i + 10]]
        if total_pages > 1:
            alt = f"{alt_prefix} ({page_num}/{total_pages}) — {', '.join(page_sectors)}"
        else:
            alt = f"{alt_prefix} — {total} สัญญาณ | {', '.join(page_sectors)}"
        push_fn([{
            "type": "flex",
            "altText": alt,
            "contents": {"type": "carousel", "contents": chunk},
        }])
        if i + 10 < len(bubbles):
            _time.sleep(0.5)
