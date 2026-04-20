"""
weekly_summary.py  —  Friday weekly recap
Sends a Flex Message summary of:
  • Top gainers / losers from watchlist this week
  • Portfolio P/L summary
  • AI market outlook for next week
"""
import yfinance as yf
import pandas as pd
import requests
import anthropic
import os, time, json
from users import load_users
from datetime import datetime, timezone, timedelta

TZ_THAI    = timezone(timedelta(hours=7))
LINE_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
LINE_UID   = os.getenv('USER_ID')

STOCKS = [
    'AAPL','MSFT','GOOGL','NVDA','META','TSLA','AMZN','SPY','QQQ',
    'PTT.BK','KBANK.BK','AOT.BK','CPALL.BK','ADVANC.BK','DELTA.BK',
    'SCB.BK','BBL.BK','GULF.BK','BDMS.BK','SCC.BK',
]

def push_flex(obj):
    uids = load_users()
    if not uids: return
    alt = obj.get('altText', '')
    msgs = [{'type': 'text', 'text': alt}, obj] if alt else [obj]
    requests.post('https://api.line.me/v2/bot/message/multicast',
                  headers={'Content-Type':'application/json','Authorization':f'Bearer {LINE_TOKEN}'},
                  json={'to':uids,'messages':msgs}, timeout=10)

def push_text(msg):
    uids = load_users()
    if not uids: return
    requests.post('https://api.line.me/v2/bot/message/multicast',
                  headers={'Content-Type':'application/json','Authorization':f'Bearer {LINE_TOKEN}'},
                  json={'to':uids,'messages':[{'type':'text','text':msg}]}, timeout=10)

def get_weekly_change(ticker):
    try:
        df = yf.download(ticker, period="10d", interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if len(df) >= 5:
            w_open = float(df['Close'].iloc[-5])
            w_close= float(df['Close'].iloc[-1])
            return round((w_close - w_open) / w_open * 100, 2), round(w_close, 2)
    except: pass
    return None, None

def get_portfolio_summary():
    try:
        with open('portfolio.json','r') as f: portfolio = json.load(f)
    except: return None

    if not portfolio.get('holdings'): return None
    try:
        df = yf.download('THBUSD=X', period='2d', interval='1d',
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        fx = float(df['Close'].iloc[-1])
    except: fx = 0.033

    total_cost, total_val = 0, 0
    for ticker, h in portfolio['holdings'].items():
        try:
            df = yf.download(ticker, period='2d', interval='1d',
                             auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            curr = float(df['Close'].iloc[-1])
            total_val  += curr * h['qty']
            total_cost += h['avg_price'] * h['qty']
        except: total_cost += h['avg_price'] * h['qty']

    pnl = total_val - total_cost
    pct = (pnl / total_cost * 100) if total_cost > 0 else 0
    return {'pnl_usd': round(pnl,2), 'pnl_thb': round(pnl/fx,2),
            'pct': round(pct,2), 'value_usd': round(total_val,2)}

def ai_weekly_outlook(gainers, losers):
    try:
        client = anthropic.Anthropic()
        g_txt  = ", ".join(f"{t}({c:+.1f}%)" for t,c,_ in gainers[:3])
        l_txt  = ", ".join(f"{t}({c:+.1f}%)" for t,c,_ in losers[:3])
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=300,
            messages=[{"role":"user","content":
                f"สัปดาห์นี้: ขึ้น {g_txt} | ลง {l_txt}\n"
                f"วิเคราะห์ภาษาไทย 3 บรรทัด:\n"
                f"1. ภาพรวมตลาดสัปดาห์นี้\n"
                f"2. Theme/กลุ่มที่น่าจับตาสัปดาห์หน้า\n"
                f"3. ความเสี่ยงที่ควรระวัง"}])
        return msg.content[0].text
    except Exception as e:
        print(f"[CLAUDE] {e}"); return "ไม่สามารถวิเคราะห์ได้ในขณะนี้"

def build_weekly_flex(gainers, losers, port_summary, ai_outlook):
    now     = datetime.now(TZ_THAI).strftime("%d %b %Y")
    icon    = "✅" if (port_summary and port_summary['pnl_usd'] >= 0) else "❌"

    def stock_row(ticker, chg, price, color):
        arrow = "▲" if chg >= 0 else "▼"
        return {"type":"box","layout":"horizontal","margin":"xs","contents":[
            {"type":"text","text":ticker.replace('.BK',''),"color":"#ECEFF1","size":"xs","flex":2},
            {"type":"text","text":f"{arrow} {abs(chg):.1f}%","color":color,"size":"xs","flex":1,"align":"end","weight":"bold"},
            {"type":"text","text":f"{price:.2f}","color":"#90CAF9","size":"xs","flex":2,"align":"end"},
        ]}

    body_contents = [
        {"type":"text","text":f"สัปดาห์ที่ผ่านมา ({now})","color":"#90CAF9","size":"xs"},
        {"type":"separator","color":"#37474F","margin":"sm"},
    ]

    if gainers:
        body_contents.append({"type":"text","text":"📈 Top Gainers","color":"#00C851","size":"xs","weight":"bold","margin":"sm"})
        for t,c,p in gainers[:5]:
            body_contents.append(stock_row(t,c,p,"#00C851"))

    if losers:
        body_contents.append({"type":"text","text":"📉 Top Losers","color":"#FF4444","size":"xs","weight":"bold","margin":"sm"})
        for t,c,p in losers[:5]:
            body_contents.append(stock_row(t,c,p,"#FF4444"))

    if port_summary:
        body_contents += [
            {"type":"separator","color":"#37474F","margin":"sm"},
            {"type":"text","text":f"{icon} พอร์ตสัปดาห์นี้","color":"#FFD54F","size":"xs","weight":"bold"},
            {"type":"box","layout":"horizontal","contents":[
                {"type":"text","text":"P/L:","color":"#78909C","size":"xs","flex":1},
                {"type":"text","text":f"{port_summary['pnl_usd']:+,.2f} USD  ({port_summary['pct']:+.1f}%)",
                 "color":"#00C851" if port_summary['pnl_usd']>=0 else "#FF4444","size":"xs","flex":3},
            ]},
            {"type":"box","layout":"horizontal","contents":[
                {"type":"text","text":"P/L (THB):","color":"#78909C","size":"xs","flex":1},
                {"type":"text","text":f"{port_summary['pnl_thb']:+,.0f} บาท",
                 "color":"#00C851" if port_summary['pnl_thb']>=0 else "#FF4444","size":"xs","flex":3},
            ]},
        ]

    body_contents += [
        {"type":"separator","color":"#37474F","margin":"sm"},
        {"type":"text","text":"🤖 AI มองสัปดาห์หน้า","color":"#FFD54F","size":"xs","weight":"bold"},
        {"type":"text","text":ai_outlook,"color":"#CFD8DC","size":"xs","wrap":True,"margin":"xs"},
    ]

    return {
        "type":"flex","altText":"📋 Weekly Stock Summary",
        "contents":{"type":"bubble","size":"kilo",
            "header":{"type":"box","layout":"vertical","backgroundColor":"#1A237E","paddingAll":"16px","contents":[
                {"type":"text","text":"📋 Weekly Summary","weight":"bold","size":"md","color":"#FFFFFF"},
                {"type":"text","text":now,"size":"xs","color":"#90CAF9","margin":"xs"},
            ]},
            "body":{"type":"box","layout":"vertical","backgroundColor":"#1E2A3A",
                    "paddingAll":"14px","spacing":"xs","contents":body_contents},
        }
    }

def main():
    print(f"[WEEKLY] {datetime.now(TZ_THAI).strftime('%Y-%m-%d %H:%M')}")
    results = []
    for ticker in STOCKS:
        chg, price = get_weekly_change(ticker)
        if chg is not None:
            results.append((ticker, chg, price))
        time.sleep(0.2)

    results.sort(key=lambda x: x[1], reverse=True)
    gainers = [r for r in results if r[1] > 0]
    losers  = [r for r in results if r[1] < 0][::-1]

    port_summary = get_portfolio_summary()
    ai_outlook   = ai_weekly_outlook(gainers, losers)
    flex         = build_weekly_flex(gainers, losers, port_summary, ai_outlook)

    push_flex(flex)
    print("[WEEKLY] Done")

if __name__ == "__main__":
    main()
