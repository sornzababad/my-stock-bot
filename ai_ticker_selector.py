"""
ai_ticker_selector.py — AI-driven dynamic ticker selection
Fetches S&P 500 + most-active screener data, scores candidates by momentum,
then asks Claude Haiku to pick the best 20-25 US tickers to scan today.
Returns [] on any failure so callers fall back to hardcoded lists unchanged.
"""
import os, json, time
import pandas as pd
import yfinance as yf
import anthropic
from datetime import datetime


def _fetch_sp500() -> list:
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            attrs={"id": "constituents"}
        )
        tickers = tables[0]["Symbol"].tolist()
        # Wikipedia uses dots (BRK.B), yfinance uses dashes (BRK-B)
        return [t.replace(".", "-") for t in tickers]
    except Exception as e:
        print(f"[AI_SELECT] SP500 fetch failed: {e}")
        return []


def _fetch_screener_tickers() -> list:
    results = []
    for query_name in ["most_actives", "day_gainers"]:
        try:
            sc = yf.Screener()
            sc.set_default_body({"scrIds": query_name, "size": 25})
            quotes = sc.response.get("quotes", [])
            results.extend(q["symbol"] for q in quotes if "symbol" in q)
        except Exception as e:
            print(f"[AI_SELECT] Screener {query_name} failed: {e}")
    return list(dict.fromkeys(results))


def _score_candidates(screener_tickers: list, sp500_set: set) -> list:
    if not screener_tickers:
        return list(sp500_set)[:40]
    try:
        batch = screener_tickers[:50]
        df = yf.download(
            batch, period="5d", interval="1d",
            progress=False, auto_adjust=True, group_by="ticker"
        )
    except Exception as e:
        print(f"[AI_SELECT] Batch download failed: {e}")
        return screener_tickers[:40]

    scores = {}
    for ticker in batch:
        try:
            close = df["Close"][ticker].dropna()
            vol   = df["Volume"][ticker].dropna()
            if len(close) < 2:
                continue
            chg  = abs((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100
            avgv = float(vol.iloc[-3:].mean())
            scores[ticker] = chg * avgv
        except Exception:
            continue

    ranked = sorted(scores, key=lambda t: scores[t], reverse=True)
    combined = list(dict.fromkeys(
        ranked[:25] + [t for t in ranked if t in sp500_set][:20]
    ))
    return combined[:45]


def _ask_claude(candidates: list, api_key: str) -> list:
    if not candidates or not api_key:
        return []
    today = datetime.now().strftime("%Y-%m-%d %A")
    prompt = (
        f"Today is {today}. You are a quantitative trader selecting tickers for a US stock scanner.\n"
        f"From this list of active/moving US tickers, pick the best 20-25 to scan today.\n"
        f"Prefer: high momentum, trending sectors (AI/semis/energy/biotech/finance), "
        f"recent news catalysts, post-earnings movers, macro-sensitive names.\n"
        f"Exclude ETFs, US-listed only.\n"
        f"Candidates: {', '.join(candidates)}\n\n"
        f"Respond ONLY with a JSON array of ticker strings, no markdown:\n"
        f'["AAPL","NVDA",...]'
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        picks = json.loads(raw)
        return [t.upper() for t in picks if isinstance(t, str) and not t.endswith(".BK")][:25]
    except Exception as e:
        print(f"[AI_SELECT] Claude call failed: {e}")
        return []


def get_ai_tickers(api_key: str = None) -> list:
    """
    Returns 20-25 AI-selected US tickers based on today's market activity.
    Returns [] on any failure so callers fall back to hardcoded lists unchanged.
    """
    if api_key is None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
    t0 = time.time()
    print("[AI_SELECT] Starting dynamic ticker selection...")
    sp500      = _fetch_sp500()
    screener   = _fetch_screener_tickers()
    print(f"[AI_SELECT] SP500={len(sp500)}, screener={len(screener)}")
    candidates = _score_candidates(screener, set(sp500))
    picks      = _ask_claude(candidates, api_key)
    print(f"[AI_SELECT] Done: {len(picks)} tickers selected in {time.time()-t0:.1f}s")
    return picks
