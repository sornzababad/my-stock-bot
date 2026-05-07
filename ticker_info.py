"""
ticker_info.py — Shared ticker metadata
Provides company names and sector classification for all scanners.
"""

# ── Sector definitions ────────────────────────────────────────────

SECTORS = {
    "💻 Tech":          ["AAPL","MSFT","GOOGL","META","NFLX","ORCL","ADBE","CRM",
                         "UBER","LYFT","ABNB","DASH","RBLX","ZM","DOCU","TWLO",
                         "OKTA","MDB","SHOP","ETSY","PINS","SNAP","SPOT","MSTR",
                         "GTLB","RDDT","DUOL","APP","SERV","SOUN","BBAI","AI",
                         "ADVICE.BK","BE8.BK","INET.BK","INSET.BK","ITEL.BK",
                         "MFEC.BK","NETBAY.BK","SCI.BK",
                         "DELTA.BK","ADVANC.BK","TRUE.BK","INTUCH.BK"],

    "🔬 Semiconductor": ["NVDA","AMD","AVGO","INTC","QCOM","TXN","AMAT","MU",
                         "LRCX","PANW","ARM","SMCI","CRWD","SNOW","DDOG","NET",
                         "COIN","MRVL","ON","KLAC","ASML","SOXX","CIBR","BOTZ",
                         "HANA.BK","KCE.BK",
                         "RKLB","ASTS","IONQ","CRDO","NVTS"],

    "🏦 Finance":       ["JPM","BAC","WFC","GS","MS","BLK","AXP","PYPL","SCHW",
                         "C","USB","PNC","TFC","COF","SQ","HOOD","V","MA",
                         "UPST","AFRM","OPEN","DKNG",
                         "KBANK.BK","SCB.BK","BBL.BK","KTB.BK","TTB.BK",
                         "BAY.BK","TISCO.BK","KKP.BK","MTC.BK","TIDLOR.BK",
                         "SAWAD.BK","AEONTS.BK","JMART.BK","JMT.BK"],

    "🏥 Health":        ["UNH","JNJ","PFE","ABBV","MRK","LLY","TMO","DHR",
                         "ISRG","AMGN","GILD","REGN","VRTX","MRNA","BMY",
                         "CVS","CI","CLOV",
                         "BDMS.BK","BH.BK","BCH.BK","CHG.BK"],

    "⚡ Energy":        ["XOM","CVX","COP","SLB","EOG","OXY","MPC","HAL",
                         "XLE","USO","UNG",
                         "PTT.BK","PTTEP.BK","TOP.BK","OR.BK","BCP.BK",
                         "PTTGC.BK","IVL.BK","BANPU.BK","TPIPP.BK","SUPER.BK",
                         "SPCG.BK","GULF.BK","GPSC.BK","BGRIM.BK","EA.BK",
                         "EGCO.BK","RATCH.BK"],

    "🛒 Consumer":      ["WMT","COST","TGT","HD","LOW","NKE","SBUX","MCD",
                         "KO","PEP","BABA","JD","PDD","MELI","SE","TTWO",
                         "XLY","XLP","DBA",
                         "CPALL.BK","CPAXT.BK","BJC.BK","HMPRO.BK","CRC.BK",
                         "CBG.BK","OSP.BK","TU.BK","MINT.BK","GFPT.BK","TFG.BK",
                         "MAKRO.BK","COM7.BK","LEO.BK","HUMAN.BK","JWD.BK"],

    "🚗 EV / Auto":     ["TSLA","RIVN","F","GM","ACHR","JOBY","LUNR"],

    "₿ Crypto":         ["COIN","MSTR","RIOT","MARA","CIFR","CLSK"],

    "🏭 Industrial":    ["BA","CAT","DE","GE","MMM","HON","RTX","LMT","NOC",
                         "UPS","FDX","XLI",
                         "SCC.BK","SCGP.BK","CK.BK","STEC.BK","WHA.BK","AMATA.BK"],

    "🏘 Property":      ["CPN.BK","LH.BK","AP.BK","SIRI.BK","ORI.BK","SPALI.BK",
                         "AWC.BK","XLRE"],

    "🚌 Transport":     ["AOT.BK","BA.BK","BEM.BK","BTS.BK","CENTEL.BK"],

    "🌏 International": ["EWJ","EEM","FXI","VEA","EWZ"],

    "📊 Broad ETF":     ["SPY","VOO","QQQ","IWM","DIA","VTI","SCHD","VIG","ARKK","ICLN"],

    "🥇 Gold / Metal":  ["GLD","IAU","GDX","GDXJ","SLV","DBB"],

    "🏦 Bond ETF":      ["TLT","IEF","HYG","LQD","SHY"],

    "🛢️ Commodity ETF": ["PDBC","DBA"],

    "🚀 Small-Cap":     ["PLTR","RKLB","ASTS","SOUN","BBAI","AI","RDDT","DUOL",
                         "APP","SERV","UPST","AFRM","DKNG","CIFR","CLSK","CRDO",
                         "NVTS","CLOV","IONQ",
                         "ADVICE.BK","BE8.BK","INET.BK","INSET.BK","ITEL.BK",
                         "JMART.BK","JMT.BK","HUMAN.BK","MFEC.BK","NETBAY.BK",
                         "SCI.BK","JWD.BK","LEO.BK"],
}

# Build reverse lookup: ticker → (emoji, sector_name)
_TICKER_SECTOR: dict[str, tuple[str, str]] = {}
for _label, _tickers in SECTORS.items():
    _emoji, _name = _label.split(" ", 1)
    for _t in _tickers:
        _TICKER_SECTOR[_t] = (_emoji, _name)


def get_sector(ticker: str) -> tuple[str, str]:
    """Return (emoji, sector_name) for a ticker. Falls back by suffix."""
    if ticker in _TICKER_SECTOR:
        return _TICKER_SECTOR[ticker]
    if ticker.endswith(".BK"):
        return ("🇹🇭", "Thai")
    etf_keywords = {"ETF","XL","VO","VT","SC","IA","GD","TL","HY","LQ","SH","EW","DB","PD"}
    if any(ticker.startswith(k) for k in etf_keywords) or len(ticker) <= 4 and ticker.isupper():
        return ("📦", "ETF")
    return ("📈", "Other")


# ── Company / ETF display names ───────────────────────────────────

TICKER_NAMES: dict[str, str] = {
    # US Mega-cap Tech
    "AAPL":  "Apple",           "MSFT":  "Microsoft",       "GOOGL": "Alphabet",
    "META":  "Meta",            "AMZN":  "Amazon",          "NFLX":  "Netflix",
    "ORCL":  "Oracle",          "ADBE":  "Adobe",           "CRM":   "Salesforce",
    # Semiconductor
    "NVDA":  "Nvidia",          "AMD":   "AMD",             "AVGO":  "Broadcom",
    "INTC":  "Intel",           "QCOM":  "Qualcomm",        "TXN":   "Texas Instr",
    "AMAT":  "Applied Matls",   "MU":    "Micron",          "LRCX":  "Lam Research",
    "PANW":  "Palo Alto",       "ARM":   "ARM Holdings",    "SMCI":  "Supermicro",
    "CRWD":  "CrowdStrike",     "SNOW":  "Snowflake",       "DDOG":  "Datadog",
    "NET":   "Cloudflare",      "MRVL":  "Marvell",         "ON":    "ON Semi",
    "KLAC":  "KLA Corp",        "ASML":  "ASML",
    # Finance
    "JPM":   "JPMorgan",        "BAC":   "Bank of America", "WFC":   "Wells Fargo",
    "GS":    "Goldman Sachs",   "MS":    "Morgan Stanley",  "BLK":   "BlackRock",
    "AXP":   "Amex",            "PYPL":  "PayPal",          "SCHW":  "Schwab",
    "C":     "Citigroup",       "COF":   "Capital One",     "SQ":    "Block",
    "HOOD":  "Robinhood",       "V":     "Visa",            "MA":    "Mastercard",
    "UPST":  "Upstart",         "AFRM":  "Affirm",          "DKNG":  "DraftKings",
    # Health
    "UNH":   "UnitedHealth",    "JNJ":   "J&J",             "PFE":   "Pfizer",
    "ABBV":  "AbbVie",          "MRK":   "Merck",           "LLY":   "Eli Lilly",
    "TMO":   "Thermo Fisher",   "DHR":   "Danaher",         "ISRG":  "Intuitive Surg",
    "AMGN":  "Amgen",           "GILD":  "Gilead",          "REGN":  "Regeneron",
    "VRTX":  "Vertex",          "MRNA":  "Moderna",         "BMY":   "BMS",
    "CVS":   "CVS Health",      "CI":    "Cigna",
    # Energy
    "XOM":   "ExxonMobil",      "CVX":   "Chevron",         "COP":   "ConocoPhillips",
    "SLB":   "Schlumberger",    "EOG":   "EOG Resources",   "OXY":   "Occidental",
    "MPC":   "Marathon Petro",  "HAL":   "Halliburton",
    # Consumer
    "WMT":   "Walmart",         "COST":  "Costco",          "TGT":   "Target",
    "HD":    "Home Depot",      "LOW":   "Lowe's",          "NKE":   "Nike",
    "SBUX":  "Starbucks",       "MCD":   "McDonald's",      "KO":    "Coca-Cola",
    "PEP":   "PepsiCo",         "BABA":  "Alibaba",         "JD":    "JD.com",
    "PDD":   "Temu/Pinduoduo",  "MELI":  "MercadoLibre",    "SE":    "Sea Ltd",
    # EV/Auto
    "TSLA":  "Tesla",           "RIVN":  "Rivian",          "F":     "Ford",
    "GM":    "General Motors",  "ACHR":  "Archer Aviation", "JOBY":  "Joby Aviation",
    # Crypto/Fintech
    "COIN":  "Coinbase",        "MSTR":  "MicroStrategy",   "RIOT":  "Riot Platforms",
    "MARA":  "Marathon Digital","PLTR":  "Palantir",
    # Industrial
    "BA":    "Boeing",          "CAT":   "Caterpillar",     "DE":    "Deere",
    "GE":    "GE Aerospace",    "MMM":   "3M",              "HON":   "Honeywell",
    "RTX":   "Raytheon",        "LMT":   "Lockheed Martin", "NOC":   "Northrop",
    "UPS":   "UPS",             "FDX":   "FedEx",
    # Growth/Small-cap
    "RKLB":  "Rocket Lab",      "ASTS":  "AST SpaceMobile", "SOUN":  "SoundHound",
    "BBAI":  "BigBear.ai",      "AI":    "C3.ai",           "GTLB":  "GitLab",
    "RDDT":  "Reddit",          "DUOL":  "Duolingo",        "APP":   "AppLovin",
    "SERV":  "Serve Robotics",  "IONQ":  "IonQ",
    # Broad ETF
    "SPY":   "S&P 500 ETF",     "VOO":   "Vanguard S&P",   "QQQ":   "Nasdaq 100 ETF",
    "IWM":   "Russell 2000",    "DIA":   "Dow Jones ETF",   "VTI":   "Total Mkt ETF",
    "SCHD":  "Dividend ETF",    "VIG":   "Div Growth ETF",  "ARKK":  "ARK Innov ETF",
    "ICLN":  "Clean Energy ETF","SOXX":  "Semicon ETF",     "BOTZ":  "Robotics ETF",
    "CIBR":  "Cybersec ETF",
    # Sector ETF
    "XLK":   "Tech Sector ETF", "XLF":   "Finance ETF",    "XLE":   "Energy ETF",
    "XLV":   "Health ETF",      "XLI":   "Industrl ETF",   "XLY":   "Cons Disc ETF",
    "XLP":   "Cons Stpl ETF",   "XLB":   "Materials ETF",  "XLRE":  "Real Estate ETF",
    # Gold/Commodity ETF
    "GLD":   "SPDR Gold",       "IAU":   "iShares Gold",   "GDX":   "Gold Miners ETF",
    "GDXJ":  "Jr Miners ETF",   "SLV":   "Silver ETF",
    # Bond ETF
    "TLT":   "20Y Treasury ETF","IEF":   "7-10Y Bond ETF", "HYG":   "High Yield ETF",
    "LQD":   "Corp Bond ETF",   "SHY":   "1-3Y T-Bill ETF",
    # International ETF
    "EWJ":   "Japan ETF",       "EEM":   "Emerg Mkt ETF",  "FXI":   "China ETF",
    "VEA":   "Dev Mkt ETF",     "EWZ":   "Brazil ETF",
    # Commodity ETF
    "USO":   "Oil ETF",         "UNG":   "Nat Gas ETF",    "DBA":   "Agri ETF",
    "DBB":   "Base Metals ETF", "PDBC":  "Commodity ETF",
    # Thai stocks
    "PTT.BK":"PTT",             "PTTEP.BK":"PTTEP",        "TOP.BK": "Thai Oil",
    "OR.BK": "OR",              "BCP.BK": "Bangchak",      "PTTGC.BK":"PTTGC",
    "IVL.BK":"Indorama",        "CPALL.BK":"CP All",       "CPAXT.BK":"CPAXT",
    "BJC.BK":"BJC",             "HMPRO.BK":"HomePro",      "CRC.BK": "Central Retail",
    "CPN.BK":"CPN",             "AOT.BK": "Airports of TH","BA.BK":  "Bangkok Air",
    "BEM.BK":"BEM",             "BTS.BK": "BTS Group",     "WHA.BK": "WHA Corp",
    "AMATA.BK":"Amata",         "ADVANC.BK":"AIS",         "TRUE.BK":"True Corp",
    "INTUCH.BK":"Intouch",      "DELTA.BK":"Delta Electr", "HANA.BK":"Hana Micro",
    "KCE.BK":"KCE Electr",      "KBANK.BK":"Kasikorn Bank","SCB.BK": "SCB",
    "BBL.BK":"Bangkok Bank",    "KTB.BK": "Krungthai Bank","TTB.BK": "TMB Thanachart",
    "BAY.BK":"Bank of Ayudhya", "TISCO.BK":"TISCO",        "KKP.BK": "Kiatnakin Phatra",
    "BDMS.BK":"BDMS",           "BH.BK":  "Bumrungrad",    "BCH.BK": "Bangkok Chain",
    "CHG.BK":"Chularat Hosp",   "GULF.BK":"Gulf Energy",   "GPSC.BK":"GPSC",
    "BGRIM.BK":"B.Grimm Power", "EA.BK":  "Energy Absolute","EGCO.BK":"Electricity Gen",
    "RATCH.BK":"Ratch Group",   "BANPU.BK":"Banpu",        "SCC.BK": "SCG",
    "SCGP.BK":"SCG Packaging",  "CBG.BK": "Carabao",       "OSP.BK": "Osotspa",
    "TU.BK":  "Thai Union",     "MINT.BK":"Minor Intl",    "LH.BK":  "Land & Houses",
    "AP.BK":  "AP Thailand",    "SIRI.BK":"Siri",          "AWC.BK": "Asset World",
    "CENTEL.BK":"Central Plaza", "MTC.BK":"Muangthai Cap", "TIDLOR.BK":"Tidlor",
    "SAWAD.BK":"Sawad",         "AEONTS.BK":"AEON TH",     "ORI.BK": "Origin Prop",
    "SPALI.BK":"Supalai",       "STEC.BK":"Sino-Thai Eng", "CK.BK":  "Ch. Karnchang",
    "MAKRO.BK":"Makro",         "COM7.BK":"Com7",          "GFPT.BK":"GFPT",
    "TFG.BK": "Thai Foods",     "TPIPP.BK":"TPIPP",        "SUPER.BK":"Super Energy",
    "SPCG.BK":"SPCG",           "ADVICE.BK":"Advice IT",   "BE8.BK": "BE8",
    "INET.BK":"iNet",           "INSET.BK":"Inset",        "ITEL.BK":"iTEL",
    "JMART.BK":"Jaymart",       "JMT.BK": "JMT Network",   "HUMAN.BK":"Human",
    "MFEC.BK":"MFEC",           "NETBAY.BK":"Netbay",      "SCI.BK": "SCI",
    "JWD.BK": "JWD Info",       "LEO.BK": "Leo Global",
}


def get_name(ticker: str) -> str:
    """Return display name for a ticker."""
    if ticker in TICKER_NAMES:
        return TICKER_NAMES[ticker]
    if ticker.endswith(".BK"):
        return ticker.replace(".BK", "")
    return ticker
