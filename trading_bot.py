"""
trading_bot.py  —  Daily close scanner
Sends LINE Flex Message cards with:
  • TradingView chart link (EMA20/50/200 preset)
  • Chart snapshot image
  • AI analysis (Claude Haiku)
  • TP / SL / R:R
"""
import yfinance as yf
import pandas as pd
import requests
import anthropic
import os, re, time, json
from users import load_users
from datetime import datetime, timezone, timedelta
from gold_etf_alerts import send_gold_etf_alerts

TZ_THAI = timezone(timedelta(hours=7))
LINE_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
LINE_UID   = os.getenv('USER_ID')

# ── TradingView helpers ───────────────────────────────────────────

def tv_symbol(ticker: str) -> str:
    """Convert yfinance ticker → TradingView symbol."""
    if ticker.endswith(".BK"):
        return "SET:" + ticker.replace(".BK", "")
    # Common exchange prefixes
    etfs = {'SPY','VOO','QQQ','DIA','VTI','SCHD','TLT','GLD','SLV',
            'USO','XLK','XLF','XLE','XLV','XLI','XLY','XLP',
            'SOXX','ARKK','BOTZ','CIBR','ICLN','GDX','GDXJ','VIG','VYM'}
    if ticker in etfs:
        return "AMEX:" + ticker
    return "NASDAQ:" + ticker   # fallback — TV auto-resolves most

def tv_chart_url(ticker: str) -> str:
    """
    Deep-link to TradingView chart with EMA 20/50/200 studies preset.
    Uses the /chart/ URL with studies query param.
    """
    sym    = tv_symbol(ticker)
    studies = "STD;EMA%4020%2C%2050%2C%20200"   # EMA triple preset
    return (
        f"https://www.tradingview.com/chart/"
        f"?symbol={sym}"
        f"&interval=D"
        f"&studies={studies}"
    )

def tv_snapshot_url(ticker: str) -> str:
    """
    TradingView mini-chart snapshot (public, no auth needed).
    Returns a static PNG URL embeddable in LINE image messages.
    """
    sym = tv_symbol(ticker)
    return (
        f"https://charts.tradingview.com/mini-chart/"
        f"?symbol={sym}&interval=D&width=500&height=300"
        f"&dateRange=6M&colorTheme=dark&trendLineColor=%2300C851"
        f"&underLineColor=%230D3321&fontColor=%23CFD8DC"
        f"&isTransparent=false&locale=th"
    )

# ── LINE push ─────────────────────────────────────────────────────

def push_messages(messages: list) -> bool:
    if not LINE_TOKEN:
        print("[ERROR] TOKEN MISSING")
        return False
    uids = load_users()
    if not uids:
        print("[ERROR] No users registered")
        return False
    for i in range(0, len(messages), 5):
        r = requests.post(
            'https://api.line.me/v2/bot/message/multicast',
            headers={'Content-Type':'application/json',
                     'Authorization':f'Bearer {LINE_TOKEN}'},
            json={'to': uids, 'messages': messages[i:i+5]},
            timeout=10
        )
        print(f"[LINE] {r.status_code} | {r.text[:120]}")
        if r.status_code != 200:
            return False
        time.sleep(0.3)
    return True

# ── Flex builders ─────────────────────────────────────────────────

def _pill(text, bg, fg):
    return {"type":"box","layout":"vertical","backgroundColor":bg,
            "cornerRadius":"20px","paddingStart":"8px","paddingEnd":"8px",
            "paddingTop":"4px","paddingBottom":"4px",
            "contents":[{"type":"text","text":text,"color":fg,
                         "size":"xs","weight":"bold","align":"center"}]}

def _kv(label, value):
    return {"type":"box","layout":"horizontal","margin":"xs","contents":[
        {"type":"text","text":label,"color":"#78909C","size":"xs","flex":2},
        {"type":"text","text":value,"color":"#ECEFF1","size":"xs","flex":5,"wrap":True}]}

def _sep():
    return {"type":"separator","color":"#37474F","margin":"sm"}

def flex_header(flag, market, idx_name, idx_price, idx_chg,
                scan_n, scan_s, buy_n, watch_n, exit_n, ai_fil, summary):
    now  = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")
    up   = idx_chg >= 0
    cc   = "#00C851" if up else "#FF4444"
    ct   = f"{'↑+' if up else '↓'}{idx_chg:.2f}%"
    return {
        "type":"flex","altText":f"{flag} {market} Alert — Market Close",
        "contents":{"type":"bubble","size":"kilo",
            "header":{"type":"box","layout":"vertical","backgroundColor":"#1A237E","paddingAll":"16px","contents":[
                {"type":"text","text":f"{flag} {market} Alert — Market Close 📊","weight":"bold","size":"sm","color":"#FFFFFF","wrap":True},
                {"type":"text","text":now,"size":"xs","color":"#90CAF9","margin":"sm"}
            ]},
            "body":{"type":"box","layout":"vertical","backgroundColor":"#1E2A3A","paddingAll":"14px","spacing":"sm","contents":[
                {"type":"box","layout":"horizontal","contents":[
                    {"type":"text","text":idx_name,"color":"#FFFFFF","size":"sm","weight":"bold","flex":1},
                    {"type":"text","text":f"{idx_price:,.2f}","color":"#FFFFFF","size":"sm","weight":"bold"},
                    {"type":"text","text":f"  {ct}","color":cc,"size":"sm","weight":"bold"},
                ]},
                _sep(),
                {"type":"text","text":f"🔎 สแกน {scan_n} หุ้น  ⏱ {scan_s:.1f}s","color":"#B0BEC5","size":"xs"},
                {"type":"box","layout":"horizontal","spacing":"md","contents":[
                    _pill(f"🟢 BUY {buy_n}","#00C851","#FFFFFF"),
                    _pill(f"🟡 WATCH {watch_n}","#FFB300","#000000"),
                    _pill(f"🔴 EXIT {exit_n}","#FF4444","#FFFFFF"),
                ]},
                {"type":"text","text":f"🤖 AI กรองออก {ai_fil} สัญญาณ","color":"#90CAF9","size":"xs"},
                _sep(),
                {"type":"text","text":summary,"color":"#CFD8DC","size":"xs","wrap":True},
            ]}
        }
    }

def flex_stock(ticker, sig, price, rsi, atr, ema_cross, bb_pos,
               reasons, ai_text, conviction, tp=None, sl=None, currency="$"):
    is_buy  = sig == "BUY"
    is_exit = not is_buy and conviction >= 4
    if is_buy:
        bc,bt,hbg = "#00C851","🟢  BUY / ซื้อ","#0D3321"
    elif is_exit:
        bc,bt,hbg = "#FF4444","🔴  EXIT / ขาย","#3E0A0A"
    else:
        bc,bt,hbg = "#FFB300","🟡  WATCH / เฝ้าดู","#3E2E00"

    rsi_bar = "█"*int(rsi/10) + "░"*(10-int(rsi/10))
    rsi_z   = "Oversold 🔻" if rsi<=30 else ("Overbought 🔺" if rsi>=70 else "Normal ✅")
    ma_t    = "Golden Cross ✨" if ema_cross=="golden" else "Death Cross ☠️"
    bb_t    = {"above":"Breakout 🔺","below":"Squeeze 🔻","inside":"Normal ➡️"}.get(bb_pos,"")
    stars   = "⭐"*conviction + "☆"*(5-conviction)
    str_t   = "STRONG 💪" if conviction>=4 else ("MODERATE 👍" if conviction==3 else "WEAK 👀")

    body = [
        {"type":"box","layout":"horizontal","contents":[
            {"type":"text","text":ticker,"weight":"bold","size":"xl","color":"#FFFFFF","flex":1},
            {"type":"text","text":f"{currency}{price:,.2f}","weight":"bold","size":"lg","color":bc,"align":"end"},
        ]},
        {"type":"text","text":reasons[0] if reasons else "","color":"#90CAF9","size":"sm","margin":"xs"},
        _sep(),
        _kv("📊 RSI",  f"[{rsi_bar}]  {rsi:.1f}  {rsi_z}"),
        _kv("📈 MA",   ma_t),
        _kv("📉 BB",   bb_t),
        _kv("📐 ATR",  f"{atr:.4f}"),
    ]
    if tp and sl and price > sl:
        rr = (tp-price)/(price-sl)
        body += [_sep(),
                 _kv("🎯 TP",  f"{currency}{tp:.2f}"),
                 _kv("🛡 SL",  f"{currency}{sl:.2f}"),
                 _kv("📏 R:R", f"1 : {rr:.1f}")]
    body += [_sep(),
             {"type":"box","layout":"horizontal","contents":[
                 {"type":"text","text":"🤖 AI","color":"#B0BEC5","size":"xs","flex":0},
                 {"type":"text","text":f"  {stars}  {str_t}","color":"#FFD54F","size":"xs","flex":1,"wrap":True},
             ]}]
    if ai_text:
        lines = [l.strip() for l in ai_text.strip().split("\n") if l.strip()][:3]
        body.append({"type":"text","text":"\n".join(lines),"color":"#CFD8DC","size":"xs","wrap":True,"margin":"xs"})

    chart_url = tv_chart_url(ticker)

    return {
        "type":"flex","altText":f"{bt}  {ticker}  {currency}{price:,.2f}",
        "contents":{"type":"bubble","size":"kilo",
            "header":{"type":"box","layout":"vertical","backgroundColor":hbg,"paddingAll":"12px","contents":[
                {"type":"text","text":bt,"weight":"bold","size":"sm","color":bc}
            ]},
            "body":{"type":"box","layout":"vertical","backgroundColor":"#1E2A3A","paddingAll":"14px","spacing":"xs","contents":body},
            "footer":{"type":"box","layout":"vertical","backgroundColor":"#263238","paddingAll":"10px","contents":[
                {"type":"button","action":{"type":"uri","label":"📊 ดูกราฟ + EMA20/50/200","uri":chart_url},
                 "style":"primary","color":bc,"height":"sm"}
            ]}
        }
    }

def flex_no_signal(flag, market, idx_name, idx_price, idx_chg, scan_n, scan_s):
    now = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")
    up  = idx_chg >= 0
    cc  = "#00C851" if up else "#FF4444"
    ct  = f"{'↑+' if up else '↓'}{idx_chg:.2f}%"
    return {
        "type":"flex","altText":f"{flag} {market} — ไม่พบสัญญาณวันนี้",
        "contents":{"type":"bubble","size":"kilo",
            "header":{"type":"box","layout":"vertical","backgroundColor":"#1A237E","paddingAll":"16px","contents":[
                {"type":"text","text":f"{flag} {market} Alert — Market Close 📊","weight":"bold","size":"sm","color":"#FFFFFF","wrap":True},
                {"type":"text","text":now,"size":"xs","color":"#90CAF9","margin":"sm"},
            ]},
            "body":{"type":"box","layout":"vertical","backgroundColor":"#1E2A3A","paddingAll":"14px","spacing":"sm","contents":[
                {"type":"box","layout":"horizontal","contents":[
                    {"type":"text","text":idx_name,"color":"#FFFFFF","size":"sm","weight":"bold","flex":1},
                    {"type":"text","text":f"{idx_price:,.2f}  ","color":"#FFFFFF","size":"sm","weight":"bold"},
                    {"type":"text","text":ct,"color":cc,"size":"sm","weight":"bold"},
                ]},
                _sep(),
                {"type":"text","text":f"🔎 สแกน {scan_n} หุ้น  ⏱ {scan_s:.1f}s","color":"#B0BEC5","size":"xs"},
                {"type":"text","text":"🟢 BUY 0   🟡 WATCH 0   🔴 EXIT 0","color":"#B0BEC5","size":"xs"},
                _sep(),
                {"type":"text","text":"😴 ไม่พบสัญญาณที่ผ่าน AI filter","color":"#90CAF9","size":"sm","weight":"bold"},
                {"type":"text","text":"ตลาดยังไม่มี setup ที่ชัดเจนพอในวันนี้","color":"#CFD8DC","size":"xs","wrap":True},
            ]}
        }
    }

# ── chart image message ───────────────────────────────────────────

def image_msg(ticker: str) -> dict | None:
    """
    Returns a LINE image message using TradingView mini-chart snapshot.
    Falls back to None if the URL can't be verified.
    """
    url = tv_snapshot_url(ticker)
    try:
        r = requests.head(url, timeout=5)
        if r.status_code == 200:
            return {"type":"image","originalContentUrl":url,"previewImageUrl":url}
    except:
        pass
    return None

# ── index / claude / signal (unchanged logic) ─────────────────────

def get_index(ticker):
    try:
        df = yf.download(ticker, period="5d", interval="1d", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if len(df) >= 2:
            p, c = float(df['Close'].iloc[-2]), float(df['Close'].iloc[-1])
            return round(c,2), round((c-p)/p*100,2)
    except Exception as e: print(f"[INDEX] {e}")
    return 0.0, 0.0

def analyze_with_claude(ticker, sig, price, rsi, atr, tp=None, sl=None):
    try:
        client = anthropic.Anthropic()
        tp_sl  = f"TP:{tp:.2f} SL:{sl:.2f}" if tp and sl else ""
        msg    = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=250,
            messages=[{"role":"user","content":
                f"วิเคราะห์หุ้น {ticker} สัญญาณ {sig} ราคา {price:.2f} RSI {rsi:.1f} ATR {atr:.2f} {tp_sl}\n"
                f"ภาษาไทย ไม่เกิน 3 บรรทัด แล้วให้คะแนน Conviction: X/5"}])
        return msg.content[0].text
    except Exception as e:
        print(f"[CLAUDE] {e}"); return None

def get_conviction(txt):
    try:
        m = re.search(r'Conviction:\s*(\d)', txt or "")
        return int(m.group(1)) if m else 3
    except: return 3

def check_signal(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        for span,col in [(20,'EMA20'),(50,'EMA50'),(200,'EMA200')]:
            df[col] = df['Close'].ewm(span=span, adjust=False).mean()
        d = df['Close'].diff()
        df['RSI'] = 100-(100/(1+d.where(d>0,0).rolling(14).mean()/(-d.where(d<0,0)).rolling(14).mean()))
        hl = df['High']-df['Low']
        df['ATR'] = pd.concat([hl,abs(df['High']-df['Close'].shift()),abs(df['Low']-df['Close'].shift())],axis=1).max(axis=1).rolling(14).mean()
        df['VOL'] = df['Volume'] > df['Volume'].rolling(20).mean()*1.3
        last,prev = df.iloc[-1],df.iloc[-2]
        price = float(last['Close'])
        atr   = float(last['ATR']) if not pd.isna(last['ATR']) else 0
        rsi   = float(last['RSI']) if not pd.isna(last['RSI']) else 0
        e_up  = float(prev['EMA20'])<float(prev['EMA200']) and float(last['EMA20'])>float(last['EMA200'])
        e_dn  = float(prev['EMA20'])>float(prev['EMA200']) and float(last['EMA20'])<float(last['EMA200'])
        aln   = float(last['EMA20'])>float(last['EMA50'])>float(last['EMA200'])
        ec    = "golden" if float(last['EMA20'])>float(last['EMA200']) else "death"
        bm    = float(df['Close'].rolling(20).mean().iloc[-1])
        bs    = float(df['Close'].rolling(20).std().iloc[-1])
        bp    = "above" if price>bm+2*bs else ("below" if price<bm-2*bs else "inside")
        vol   = bool(last['VOL'])
        if e_up and (45<rsi<75) and aln:
            vt = "Volume Surge ✅" if vol else "Volume ปกติ"
            return ("BUY", price,rsi,atr,ec,bp,[f"EMA Golden Cross  {vt}",f"RSI {rsi:.1f}"],price+4*atr,price-2*atr)
        elif e_dn:
            return ("SELL",price,rsi,atr,ec,bp,["EMA Death Cross ☠️",f"RSI {rsi:.1f}"],None,None)
        return None
    except Exception as e:
        print(f"[ERROR] {ticker}: {e}"); return None

def check_smallcap_signal(ticker):
    try:
        df = yf.download(ticker, period="3mo", interval="1d",
                         progress=False, auto_adjust=True)
        if df.empty or len(df) < 25:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        vol_avg  = df['Volume'].rolling(20).mean()
        d        = df['Close'].diff()
        gain     = d.where(d > 0, 0).rolling(14).mean()
        loss     = (-d.where(d < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain / loss))
        last     = df.iloc[-1]
        price    = float(last['Close'])
        rsi      = float(last['RSI'])   if not pd.isna(last['RSI'])   else 0
        ema20    = float(last['EMA20']) if not pd.isna(last['EMA20']) else 0
        vol_last = float(last['Volume'])
        vol_mean = float(vol_avg.iloc[-1])
        if vol_mean <= 0 or ema20 <= 0:
            return None
        vol_ratio = vol_last / vol_mean
        if vol_ratio < 1.5:           return None
        if not (45 <= rsi <= 75):     return None
        if price <= ema20:            return None
        pct_above_ema20 = (price - ema20) / ema20 * 100
        return (price, rsi, vol_ratio, pct_above_ema20)
    except Exception as e:
        print(f"[SMALLCAP ERROR] {ticker}: {e}"); return None

def format_smallcap_message(hits_us, hits_th):
    if not hits_us and not hits_th:
        return None
    now   = datetime.now(TZ_THAI).strftime("%d %b %Y  %H:%M")
    total = len(hits_us) + len(hits_th)

    contents = [
        {"type":"text","text":"🚀 Small-Cap Momentum Alert",
         "weight":"bold","size":"md","color":"#FFFFFF"},
        {"type":"text","text":now,"size":"xs","color":"#78909C","margin":"xs"},
        {"type":"separator","color":"#37474F","margin":"sm"},
    ]

    if hits_us:
        contents.append({"type":"text","text":"🇺🇸 US Small-Caps",
                          "size":"sm","color":"#90CAF9","weight":"bold","margin":"sm"})
        for ticker, price, rsi, vol_ratio, pct_ema20 in hits_us:
            contents.append({"type":"text","wrap":True,"size":"xs","color":"#CFD8DC","margin":"xs",
                              "text":f"• {ticker}  ${price:,.2f}  RSI {rsi:.0f}  Vol ×{vol_ratio:.1f}  +{pct_ema20:.1f}% EMA20"})

    if hits_th:
        contents.append({"type":"text","text":"🇹🇭 TH Small-Caps",
                          "size":"sm","color":"#90CAF9","weight":"bold","margin":"sm"})
        for ticker, price, rsi, vol_ratio, pct_ema20 in hits_th:
            display = ticker.replace(".BK","")
            contents.append({"type":"text","wrap":True,"size":"xs","color":"#CFD8DC","margin":"xs",
                              "text":f"• {display}  ฿{price:,.2f}  RSI {rsi:.0f}  Vol ×{vol_ratio:.1f}  +{pct_ema20:.1f}% EMA20"})

    contents += [
        {"type":"separator","color":"#37474F","margin":"sm"},
        {"type":"text","wrap":True,"size":"xxs","color":"#546E7A","margin":"xs",
         "text":f"พบ {total} ตัวผ่านเกณฑ์  Vol>1.5x  RSI 45-75  Price>EMA20"},
    ]

    return {
        "type":"flex",
        "altText":f"🚀 Small-Cap Alert — {total} สัญญาณ momentum",
        "contents":{
            "type":"bubble","size":"kilo",
            "header":{
                "type":"box","layout":"vertical",
                "backgroundColor":"#0D1B2A","paddingAll":"14px",
                "contents":[
                    {"type":"text","text":"📡 Small-Cap Growth Scanner",
                     "weight":"bold","size":"sm","color":"#64B5F6"}
                ]
            },
            "body":{
                "type":"box","layout":"vertical",
                "backgroundColor":"#1E2A3A","paddingAll":"14px",
                "spacing":"xs","contents":contents
            }
        }
    }

def send_smallcap_alerts():
    print(f"[SMALLCAP] Scanning {len(SMALLCAP_STOCKS)} tickers...")
    t0 = time.time()
    hits_us, hits_th = [], []
    for ticker in SMALLCAP_STOCKS:
        res = check_smallcap_signal(ticker)
        if not res:
            continue
        price, rsi, vol_ratio, pct_ema20 = res
        print(f"[SMALLCAP HIT] {ticker}  RSI={rsi:.1f}  Vol×{vol_ratio:.1f}")
        entry = (ticker, price, rsi, vol_ratio, pct_ema20)
        (hits_th if ticker.endswith(".BK") else hits_us).append(entry)
    print(f"[SMALLCAP] {len(hits_us)+len(hits_th)} hits in {round(time.time()-t0,1)}s")
    msg = format_smallcap_message(hits_us, hits_th)
    if msg:
        push_messages([msg])
    else:
        print("[SMALLCAP] No signals — skipping LINE push")

def mkt_summary(chg):
    if abs(chg)<0.1:  return "⬛ ทรงตัว ไม่มีทิศทางชัดเจน"
    elif chg>1.0:     return "🚀 ปรับขึ้นแรง มีแรงซื้อเข้ามาหนุน"
    elif chg>0:       return "🟢 ปรับขึ้นเล็กน้อย แนวโน้มเป็นบวก"
    elif chg<-1.0:    return "💥 ปรับลงแรง แรงขายครอบงำตลาด"
    else:             return "🔴 ปรับลงเล็กน้อย ควรระวังความเสี่ยง"

# ── WATCHLIST ─────────────────────────────────────────────────────

STOCKS = list(dict.fromkeys([
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
]))

# ── SMALL-CAP GROWTH WATCHLIST ────────────────────────────────────

SMALLCAP_STOCKS_US = [
    'RKLB','ASTS','ACHR','JOBY','LUNR',           # Space / eVTOL
    'SOUN','BBAI','AI','GTLB','RDDT','DUOL',       # AI / Software
    'APP','SERV','UPST','AFRM','OPEN',             # Fintech / Growth
    'DKNG','MARA','CIFR','CLSK','CRDO','NVTS',     # Crypto / Semi
    'CLOV','TTWO','IONQ',                           # Other
]

SMALLCAP_STOCKS_TH = [
    'ADVICE.BK','BE8.BK','INET.BK','INSET.BK',
    'ITEL.BK','JMART.BK','JMT.BK','HUMAN.BK',
    'MFEC.BK','NETBAY.BK','SCI.BK','JWD.BK','LEO.BK',
]

SMALLCAP_STOCKS = SMALLCAP_STOCKS_US + SMALLCAP_STOCKS_TH

# ── send one market ───────────────────────────────────────────────

def send_market(sigs, flag, market, idx_name, idx_price, idx_chg,
                scan_n, scan_s, ai_fil):
    buy_n   = sum(1 for t,_,_ in sigs if t=="BUY")
    watch_n = sum(1 for t,c,_ in sigs if t=="SELL" and c<4)
    exit_n  = sum(1 for t,c,_ in sigs if t=="SELL" and c>=4)

    if not sigs:
        push_messages([flex_no_signal(flag,market,idx_name,idx_price,idx_chg,scan_n,scan_s)])
        return

    header = flex_header(flag,market,idx_name,idx_price,idx_chg,
                         scan_n,scan_s,buy_n,watch_n,exit_n,ai_fil,
                         mkt_summary(idx_chg))

    bubbles = [header['contents']]
    for _, _, (card, _) in sigs:
        bubbles.append(card['contents'])

    carousel = {
        "type": "flex",
        "altText": header.get('altText', f"{flag} {market} Alert"),
        "contents": {"type": "carousel", "contents": bubbles[:12]}
    }
    push_messages([carousel])

# ── MAIN ─────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(f"[START] {datetime.now(TZ_THAI).strftime('%Y-%m-%d %H:%M:%S')} | {len(STOCKS)} หุ้น")

    set_p,  set_c   = get_index("^SET.BK")
    sp_p,   sp_c    = get_index("^GSPC")

    thai_sigs, us_sigs, filtered = [], [], 0

    for ticker in STOCKS:
        res = check_signal(ticker)
        if not res: continue
        sig,price,rsi,atr,ec,bp,reasons,tp,sl = res
        print(f"[SIGNAL] {ticker} {sig}")

        ai   = analyze_with_claude(ticker, sig, price, rsi, atr, tp, sl)
        conv = get_conviction(ai)
        print(f"[CONV] {ticker}: {conv}/5")
        if conv < 3: filtered += 1; continue

        is_thai  = ticker.endswith(".BK")
        cur      = "฿" if is_thai else "$"
        display  = ticker.replace(".BK","") if is_thai else ticker
        card     = flex_stock(display,sig,price,rsi,atr,ec,bp,reasons,ai,conv,tp,sl,cur)
        bucket   = thai_sigs if is_thai else us_sigs
        bucket.append((sig, conv, (card, display)))

    scan_s     = round(time.time()-t0, 1)
    thai_count = sum(1 for s in STOCKS if s.endswith(".BK"))
    us_count   = len(STOCKS)-thai_count
    print(f"[DONE] Thai={len(thai_sigs)} US={len(us_sigs)} filtered={filtered} {scan_s}s")

    send_market(thai_sigs,"🏦","SET","SET Index",set_p,set_c,thai_count,scan_s,filtered)
    time.sleep(1)
    send_market(us_sigs,"🗽","US","S&P 500",sp_p,sp_c,us_count,scan_s,filtered)
    time.sleep(1)
    send_smallcap_alerts()
    time.sleep(1)
    send_gold_etf_alerts(push_messages)

if __name__ == "__main__":
    main()
