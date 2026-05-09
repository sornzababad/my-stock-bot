"""
ticker_info.py — Sector classification and display names for all tickers.
"""

SECTORS = {
    "💻 Tech":          ["AAPL","MSFT","GOOGL","META","NFLX","ORCL","ADBE","CRM",
                         "NOW","WDAY","INTU","TEAM","DDOG","SNOW","NET","CRWD",
                         "SHOP","DELTA.BK","ADVANC.BK","TRUE.BK","INTUCH.BK"],
    "🔬 Semiconductor": ["NVDA","AMD","AVGO","INTC","QCOM","TXN","AMAT","MU",
                         "LRCX","MRVL","ON","KLAC","ASML","SOXX","HANA.BK","KCE.BK"],
    "🏦 Finance":       ["JPM","BAC","WFC","GS","MS","BLK","AXP","PYPL","SCHW",
                         "C","COF","SQ","HOOD","V","MA",
                         "KBANK.BK","SCB.BK","BBL.BK","KTB.BK","TTB.BK","BAY.BK","TISCO.BK"],
    "🏥 Health":        ["UNH","JNJ","PFE","ABBV","MRK","LLY","TMO",
                         "ISRG","AMGN","GILD","REGN","VRTX","MRNA",
                         "BDMS.BK","BH.BK","BCH.BK","CHG.BK"],
    "⚡ Energy":        ["XOM","CVX","COP","SLB","EOG","OXY","MPC","HAL","XLE",
                         "PTT.BK","PTTEP.BK","TOP.BK","OR.BK","BCP.BK","GULF.BK","GPSC.BK"],
    "🛒 Consumer":      ["WMT","COST","TGT","HD","NKE","SBUX","MCD","KO","PEP",
                         "BABA","MELI","XLY","XLP",
                         "CPALL.BK","CRC.BK","HMPRO.BK","BJC.BK","MAKRO.BK","CBG.BK"],
    "🚗 EV / Auto":     ["TSLA","RIVN","F","GM"],
    "₿ Crypto":         ["COIN","MSTR","RIOT","MARA","PLTR","HOOD","SQ"],
    "🏭 Industrial":    ["XLI"],
    "🏘 Property":      ["LH.BK","AP.BK","CPN.BK"],
    "🚌 Transport":     ["AOT.BK","BEM.BK","BTS.BK"],
    "📊 Broad ETF":     ["SPY","QQQ","QQQM","VOO","IWM","SCHD","XLK","XLF","XLV"],
    "🥇 Gold / Metal":  ["GLD","IAU","GDX","GDXJ","SLV"],
    "🏦 Bond ETF":      ["TLT"],
}

_TICKER_SECTOR: dict[str, tuple[str, str]] = {}
for _label, _tickers in SECTORS.items():
    _emoji, _name = _label.split(" ", 1)
    for _t in _tickers:
        _TICKER_SECTOR[_t] = (_emoji, _name)


def get_sector(ticker: str) -> tuple[str, str]:
    if ticker in _TICKER_SECTOR:
        return _TICKER_SECTOR[ticker]
    if ticker.endswith(".BK"):
        return ("🇹🇭", "Thai")
    return ("📈", "Other")


TICKER_NAMES: dict[str, str] = {
    "AAPL":"Apple","MSFT":"Microsoft","NVDA":"Nvidia","AMD":"AMD",
    "META":"Meta Platforms","GOOGL":"Alphabet","AMZN":"Amazon","TSLA":"Tesla",
    "AVGO":"Broadcom","ORCL":"Oracle","NFLX":"Netflix","ADBE":"Adobe",
    "CRM":"Salesforce","INTC":"Intel","QCOM":"Qualcomm",
    "MU":"Micron","LRCX":"Lam Research","AMAT":"Applied Materials",
    "TXN":"Texas Instruments","MRVL":"Marvell","ON":"ON Semi",
    "KLAC":"KLA Corp","ASML":"ASML",
    "NOW":"ServiceNow","WDAY":"Workday","INTU":"Intuit","TEAM":"Atlassian",
    "DDOG":"Datadog","SNOW":"Snowflake","NET":"Cloudflare","CRWD":"CrowdStrike",
    "PLTR":"Palantir","COIN":"Coinbase","MSTR":"MicroStrategy",
    "HOOD":"Robinhood","SQ":"Block","RIOT":"Riot Platforms","MARA":"Marathon Digital",
    "JPM":"JPMorgan Chase","BAC":"Bank of America","GS":"Goldman Sachs",
    "MS":"Morgan Stanley","WFC":"Wells Fargo","C":"Citigroup",
    "BLK":"BlackRock","SCHW":"Charles Schwab",
    "V":"Visa","MA":"Mastercard","AXP":"American Express","PYPL":"PayPal","COF":"Capital One",
    "XOM":"ExxonMobil","CVX":"Chevron","COP":"ConocoPhillips","SLB":"Schlumberger",
    "EOG":"EOG Resources","OXY":"Occidental","MPC":"Marathon Petroleum","HAL":"Halliburton",
    "UNH":"UnitedHealth","JNJ":"Johnson & Johnson","PFE":"Pfizer","ABBV":"AbbVie",
    "LLY":"Eli Lilly","MRK":"Merck","AMGN":"Amgen","GILD":"Gilead",
    "REGN":"Regeneron","VRTX":"Vertex","MRNA":"Moderna","TMO":"Thermo Fisher","ISRG":"Intuitive Surgical",
    "WMT":"Walmart","COST":"Costco","TGT":"Target","HD":"Home Depot",
    "NKE":"Nike","SBUX":"Starbucks","MCD":"McDonald's","KO":"Coca-Cola",
    "PEP":"PepsiCo","BABA":"Alibaba","MELI":"MercadoLibre","SHOP":"Shopify",
    "F":"Ford","GM":"General Motors","RIVN":"Rivian",
    "SPY":"S&P 500 ETF","QQQ":"Nasdaq 100 ETF","QQQM":"Invesco Nasdaq 100 ETF",
    "VOO":"Vanguard S&P 500 ETF","IWM":"Russell 2000 ETF","SCHD":"Schwab Dividend ETF",
    "GLD":"SPDR Gold ETF","IAU":"iShares Gold ETF","GDX":"Gold Miners ETF",
    "GDXJ":"Jr Gold Miners ETF","SLV":"iShares Silver ETF",
    "TLT":"20Y Treasury ETF","SOXX":"Semiconductor ETF",
    "XLK":"Tech Sector ETF","XLF":"Finance Sector ETF","XLE":"Energy Sector ETF","XLV":"Health Sector ETF",
    "KBANK.BK":"Kasikorn Bank","SCB.BK":"SCB","BBL.BK":"Bangkok Bank",
    "KTB.BK":"Krungthai Bank","TTB.BK":"TMB Thanachart","BAY.BK":"Bank of Ayudhya","TISCO.BK":"TISCO",
    "PTT.BK":"PTT","PTTEP.BK":"PTTEP","TOP.BK":"Thai Oil",
    "OR.BK":"OR","BCP.BK":"Bangchak","GULF.BK":"Gulf Energy","GPSC.BK":"GPSC",
    "DELTA.BK":"Delta Electronics","ADVANC.BK":"AIS","TRUE.BK":"True Corp",
    "INTUCH.BK":"Intouch Holdings","HANA.BK":"Hana Microelectronics","KCE.BK":"KCE Electronics",
    "BDMS.BK":"BDMS","BH.BK":"Bumrungrad Hospital","BCH.BK":"Bangkok Chain","CHG.BK":"Chularat Hospital",
    "CPALL.BK":"CP All","CRC.BK":"Central Retail","HMPRO.BK":"HomePro",
    "BJC.BK":"BJC","MAKRO.BK":"Makro","CBG.BK":"Carabao Group",
    "AOT.BK":"Airports of Thailand","BEM.BK":"BEM","BTS.BK":"BTS Group",
    "LH.BK":"Land & Houses","AP.BK":"AP Thailand","CPN.BK":"CPN",
}


def get_name(ticker: str) -> str:
    if ticker in TICKER_NAMES:
        return TICKER_NAMES[ticker]
    if ticker.endswith(".BK"):
        return ticker.replace(".BK", "")
    return ticker
