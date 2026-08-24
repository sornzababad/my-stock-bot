"""
support_resistance.py — Confluence-based support/resistance zones.

Implements 6 of the 7 methods from the "7 วิธีหาแนวรับ-แนวต้านให้แม่นขึ้น" guide
(Volume Profile is excluded — yfinance daily bars don't carry the
volume-at-price data it needs, so it can't be done accurately here):

  1. Swing High / Swing Low zones      (score 3 per zone, needs 2+ touches)
  2. Trendline zone                    (score 2, needs 3+ swing points, R² >= 0.7)
  3. EMA20/50 ribbon zone              (score 2, only when clearly sloped)
  4. Fibonacci golden zone (0.5-0.618) (score 2, from the clearest recent leg)
  5. Round-number zones                (score 1 each, scaled to price magnitude)
  6. Classic pivot points (P/R1/S1)    (score 1 each)

Overlapping levels are merged and their scores summed, matching the guide's
confluence table. Only zones scoring 3+ ("เฝ้าดู" or better) are considered
worth surfacing — below that the guide says to skip it.
"""
import math
import numpy as np
import pandas as pd


def _true_range_atr(df, period=14):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return float(val) if not pd.isna(val) else 0.0


def _find_swing_points(df, window=2):
    """Swing High/Low per the guide's mechanical definition (ch. 01)."""
    highs = df['High'].values
    lows  = df['Low'].values
    n     = len(highs)
    swing_highs, swing_lows = [], []
    for i in range(window, n - window):
        if all(highs[i] >= highs[i - j] for j in range(1, window + 1)) and \
           all(highs[i] >= highs[i + j] for j in range(1, window + 1)):
            swing_highs.append((i, float(highs[i])))
        if all(lows[i] <= lows[i - j] for j in range(1, window + 1)) and \
           all(lows[i] <= lows[i + j] for j in range(1, window + 1)):
            swing_lows.append((i, float(lows[i])))
    return swing_highs, swing_lows


def _cluster_to_zones(values, score, label, tol_pct=0.012, min_touches=2):
    """Group nearby swing prices into zones; a zone needs 2+ touches (ch. 01)."""
    if not values:
        return []
    vals = sorted(values)
    clusters, current = [], [vals[0]]
    for v in vals[1:]:
        if (v - current[-1]) / current[-1] <= tol_pct:
            current.append(v)
        else:
            clusters.append(current)
            current = [v]
    clusters.append(current)
    zones = []
    for c in clusters:
        if len(c) >= min_touches:
            zones.append({'low': min(c), 'high': max(c), 'score': score,
                           'label': f"{label} x{len(c)}"})
    return zones


def _ema_ribbon_zone(df, lookback=10):
    """EMA20-50 ribbon as a dynamic S/R zone — only when clearly sloped (ch. 03)."""
    close = df['Close']
    if len(close) < 50 + lookback:
        return None
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    prev50 = ema50.iloc[-1 - lookback]
    if prev50 == 0:
        return None
    slope_pct = (ema50.iloc[-1] - prev50) / prev50
    if abs(slope_pct) < 0.01:  # flat ribbon = unreliable, per the guide
        return None
    e20, e50 = float(ema20.iloc[-1]), float(ema50.iloc[-1])
    aligned = (slope_pct > 0 and e20 > e50) or (slope_pct < 0 and e20 < e50)
    if not aligned:
        return None
    return {'low': min(e20, e50), 'high': max(e20, e50), 'score': 2,
            'label': 'EMA20-50 Ribbon'}


def _fibonacci_golden_zone(df, lookback=60):
    """Golden zone (0.5-0.618) of the clearest recent leg (ch. 04)."""
    window = df.tail(min(lookback, len(df)))
    if len(window) < 10:
        return None
    hi_pos = window['High'].values.argmax()
    lo_pos = window['Low'].values.argmin()
    hi = float(window['High'].iloc[hi_pos])
    lo = float(window['Low'].iloc[lo_pos])
    if hi <= lo:
        return None
    leg = hi - lo
    if lo_pos < hi_pos:   # up-leg (low happened first) -> retrace down from high
        top = hi - 0.5 * leg
        bot = hi - 0.618 * leg
    else:                 # down-leg (high happened first) -> retrace up from low
        bot = lo + 0.5 * leg
        top = lo + 0.618 * leg
    return {'low': min(top, bot), 'high': max(top, bot), 'score': 2,
            'label': 'Fib Golden Zone'}


def _trendline_zone(df, swing_highs, swing_lows, min_points=3, r2_min=0.7):
    """Linear trendline through recent swing points (ch. 02).

    Only counted when there's a clear EMA50 trend, the swing points move
    consistently with it, and the fit is tight (R² >= r2_min) — the guide
    warns this is the most subjective of the methods, so this keeps it
    to cases with real statistical support rather than a line forced to fit.
    """
    close = df['Close']
    if len(close) < 51:
        return None
    ema50 = close.ewm(span=50, adjust=False).mean()
    trend_up = bool(ema50.iloc[-1] > ema50.iloc[-11])

    pts = swing_lows if trend_up else swing_highs
    if len(pts) < min_points:
        return None
    pts = pts[-min_points:]

    xs = np.array([p[0] for p in pts], dtype=float)
    ys = np.array([p[1] for p in pts], dtype=float)

    if trend_up and not (ys[-1] > ys[0]):
        return None
    if not trend_up and not (ys[-1] < ys[0]):
        return None

    slope, intercept = np.polyfit(xs, ys, 1)
    pred = slope * xs + intercept
    ss_res = float(np.sum((ys - pred) ** 2))
    ss_tot = float(np.sum((ys - ys.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    if r2 < r2_min:
        return None

    last_idx = len(df) - 1
    proj = float(slope * last_idx + intercept)
    atr = _true_range_atr(df)
    pad = atr * 0.5 if atr else proj * 0.01
    return {'low': proj - pad, 'high': proj + pad, 'score': 2, 'label': 'Trendline'}


def _round_number_zones(price):
    """Nearest round numbers above/below, scaled to the asset's price magnitude (ch. 05)."""
    if price <= 0:
        return []
    if price < 10:
        step = 0.5 if price < 2 else 1
    else:
        step = 10 ** (len(str(int(price))) - 2)
    lower = math.floor(price / step) * step
    upper = math.ceil(price / step) * step
    if upper == lower:
        upper += step
    if lower == price:
        lower -= step
    pad = step * 0.05
    return [
        {'low': lower - pad, 'high': lower + pad, 'score': 1, 'label': f'Round {lower:g}'},
        {'low': upper - pad, 'high': upper + pad, 'score': 1, 'label': f'Round {upper:g}'},
    ]


def _pivot_zones(df):
    """Classic pivot points from the previous period's H/L/C (ch. 07)."""
    if len(df) < 2:
        return []
    prev = df.iloc[-2]
    H, L, C = float(prev['High']), float(prev['Low']), float(prev['Close'])
    P  = (H + L + C) / 3
    R1 = 2 * P - L
    S1 = 2 * P - H
    pad = (H - L) * 0.05 if H > L else P * 0.005
    return [
        {'low': P - pad,  'high': P + pad,  'score': 1, 'label': 'Pivot P'},
        {'low': R1 - pad, 'high': R1 + pad, 'score': 1, 'label': 'Pivot R1'},
        {'low': S1 - pad, 'high': S1 + pad, 'score': 1, 'label': 'Pivot S1'},
    ]


def _merge_zones(levels, tol_pct=0.012):
    """Merge zones whose midpoints are within tol_pct of each other, summing scores (ch. 08)."""
    if not levels:
        return []
    levels = sorted(levels, key=lambda z: (z['low'] + z['high']) / 2)
    merged = [dict(levels[0], labels=[levels[0]['label']])]
    for z in levels[1:]:
        last = merged[-1]
        mid_last = (last['low'] + last['high']) / 2
        mid_z    = (z['low'] + z['high']) / 2
        if mid_last != 0 and abs(mid_z - mid_last) / mid_last <= tol_pct:
            last['low']  = min(last['low'], z['low'])
            last['high'] = max(last['high'], z['high'])
            last['score'] += z['score']
            last['labels'].append(z['label'])
        else:
            merged.append(dict(z, labels=[z['label']]))
    for z in merged:
        z['label'] = ' + '.join(z['labels'])
        del z['labels']
    return merged


MIN_SCORE = 3  # below this the guide says to skip the zone entirely


def find_key_zones(df, price):
    """
    Find the nearest qualifying support zone (below price) and resistance
    zone (above price), scored by confluence across the 6 methods.

    Returns (support, resistance), each either None or a dict with
    low/high/score/label.
    """
    try:
        if df is None or len(df) < 30:
            return None, None

        swing_highs, swing_lows = _find_swing_points(df)

        raw = []
        raw += _cluster_to_zones([p for _, p in swing_highs], score=3, label='Swing High')
        raw += _cluster_to_zones([p for _, p in swing_lows],  score=3, label='Swing Low')

        ema_z = _ema_ribbon_zone(df)
        if ema_z:
            raw.append(ema_z)

        fib_z = _fibonacci_golden_zone(df)
        if fib_z:
            raw.append(fib_z)

        tl_z = _trendline_zone(df, swing_highs, swing_lows)
        if tl_z:
            raw.append(tl_z)

        raw += _round_number_zones(price)
        raw += _pivot_zones(df)

        merged = _merge_zones(raw)

        support_candidates    = [z for z in merged if z['high'] < price and z['score'] >= MIN_SCORE]
        resistance_candidates = [z for z in merged if z['low']  > price and z['score'] >= MIN_SCORE]

        support    = max(support_candidates, key=lambda z: z['high']) if support_candidates else None
        resistance = min(resistance_candidates, key=lambda z: z['low']) if resistance_candidates else None

        return support, resistance
    except Exception as e:
        print(f"[SR] error: {e}")
        return None, None
