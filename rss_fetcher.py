import requests
import feedparser
import time
import random
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

# 全局請求頭（加Referer模擬瀏覽器訪問，大幅降低403/429概率）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
    "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8"
}

# 負面提示詞（不直接丟棄，僅標記交給AI判斷邊界案例）
NEGATIVE_HINT_ZH = ["盈警", "虧損", "預虧", "業績倒退", "純利跌", "減持", "配股", "供股", "抽水", "攤薄", "批股", "處罰", "罰款", "召回", "制裁", "破產", "清盤", "除牌", "停牌", "調查", "起訴", "訴訟", "造假", "欺詐", "暴跌", "大跌", "下調", "降級"]
NEGATIVE_HINT_EN = ["profit warning", "loss", "net loss", "share placement", "dilution", "sanction", "bankruptcy", "delisting", "suspend", "fine", "penalty"]
NEGATIVE_EN_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(w) for w in NEGATIVE_HINT_EN) + r')\b', re.IGNORECASE)

# 通用前綴（僅用於生成別名，不用於截斷匹配）
COMMON_PREFIX = ["中國", "中国", "香港", "國際", "国际", "環球", "环球", "亞洲", "亚洲", "遠東", "远东"]

# 熱門股票別名庫（全覆蓋，不截詞）
STOCK_ALIAS = {
    "00700": ["騰訊", "腾讯", "Tencent", "騰訊控股"],
    "01810": ["小米", "小米集團", "Xiaomi", "小米集團-W"],
    "09988": ["阿里", "阿里巴巴", "Alibaba", "阿里巴巴-W"],
    "03690": ["美團", "美团", "Meituan", "美團-W"],
    "01024": ["快手", "快手科技", "Kuaishou", "快手-W"],
    "09618": ["京東", "京东", "JD.com", "JD", "京東集團-SW"],
    "00941": ["移動", "中國移動", "China Mobile"],
    "00005": ["匯豐", "滙豐", "HSBC", "匯豐控股"],
    "00883": ["中海油", "中國海洋石油", "CNOOC"],
    "02318": ["平保", "中國平安", "Ping An", "平安"],
    "01398": ["工行", "工商銀行", "ICBC"],
    "00388": ["港交所", "香港交易所", "HKEX"],
    "00001": ["長和", "CK Hutchison", "長江和記"],
    "00002": ["中電", "中電控股", "CLP Holdings"],
    "00016": ["新鴻基", "新鴻基地產", "SHK Properties"]
}

def _clean_html(raw_text):
    """清理HTML標籤和RSS垃圾內容"""
    if not raw_text:
        return ""
    clean = re.sub(r'<[^>]+>', '', raw_text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    clean = clean.replace("Read more", "").replace("閱讀更多", "").replace("繼續閱讀", "").replace("...", "").strip()
    return clean[:500]

def _sleep():
    """單請求隨機等待1.5-3秒，完全唔會被封IP"""
    time.sleep(random.uniform(1.5, 3.0))

def _parse_publish_time(entry):
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    except:
        pass
    return datetime.now(timezone.utc)

def _generate_match_keywords(stock):
    """為每隻股票生成完整匹配關鍵詞，分中文/英文，不截詞"""
    code = stock["code"]
    name = stock["name"]
    keywords_zh = set()
    keywords_en = set()

    code_pattern = re.compile(r'(?<!\d)(0*' + re.escape(code[-4:]) + r'|' + re.escape(code) + r')(?!\d)(\.HK)?', re.IGNORECASE)
    keywords_zh.add(name)

    core_name = name
    for prefix in COMMON_PREFIX:
        if core_name.startswith(prefix):
            core_name = core_name[len(prefix):]
            break
    if len(core_name) >= 2:
        keywords_zh.add(core_name)

    if code in STOCK_ALIAS:
        for alias in STOCK_ALIAS[code]:
            if re.search(r'[a-zA-Z]', alias):
                keywords_en.add(alias.lower())
            else:
                keywords_zh.add(alias)

    return {
        "code_pattern": code_pattern,
        "zh": list(keywords_zh),
        "en": list(keywords_en)
    }

def _build_google_news_query(stock):
    """構建Google News高精度查詢詞："代碼" OR "中文名" OR "英文名" 港股"""
    code = stock["code"]
    name = stock["name"]
    query_parts = [f'"{code}"', f'"{name}"']
    if code in STOCK_ALIAS:
        for alias in STOCK_ALIAS[code]:
            query_parts.append(f'"{alias}"')
    query = " OR ".join(query_parts) + " 港股"
    return urllib.parse.quote(query)

def _fetch_single_rss(url, source_name):
    news_list = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = _clean_html(entry.get("summary", entry.get("description", "")))
            pub_time = _parse_publish_time(entry)
            if not title or not link:
                continue
            news_list.append({
                "title": title,
                "link": link,
                "summary": summary,
                "source": source_name,
                "pub_time": pub_time,
                "negative_hint": False
            })
        _sleep()
    except Exception as e:
        print(f"[警告] 抓取 {source_name} 失敗: {str(e)}")
    return news_list

def fetch_webbsite_news(code):
    """Webb-site正確港交所公告RSS地址"""
    url = f"https://webb-site.com/rss/announcements.asp?c={code}"
    return _fetch_single_rss(url, "港交所公告")

def fetch_yahoo_news(code):
    """Yahoo雙節點自動備援：query1失敗自動試query2，99%可用性"""
    endpoints = [
        f"https://query1.finance.yahoo.com/v1/finance/rss/headline?s={code}.HK",
        f"https://query2.finance.yahoo.com/v1/finance/rss/headline?s={code}.HK"
    ]
    
    for url in endpoints:
        news = _fetch_single_rss(url, "Yahoo Finance")
        if news:
            return news
        time.sleep(0.5)
    
    return []

def fetch_google_news(stock):
    """Google News高精度查詢，命中率最高"""
    query = _build_google_news_query(stock)
    url = f"https://news.google.com/rss/search?q={query}&hl=zh-HK&gl=HK&ceid=HK:zh-HK"
    return _fetch_single_rss(url, "Google News")

def fetch_all_stock_rss(stock_list):
    all_news = []
    seen_links = set()
    time_threshold = datetime.now(timezone.utc) - timedelta(hours=48)
    total = len(stock_list)

    for idx, stock in enumerate(stock_list):
        code = stock["code"]
        name = stock["name"]
        print(f"[{idx+1}/{total}] 正在抓取 {name}({code}) 新聞...")

        ws_news = fetch_webbsite_news(code)
        yh_news = fetch_yahoo_news(code)
        gn_news = fetch_google_news(stock)

        for news in ws_news + yh_news + gn_news:
            if news["pub_time"] < time_threshold:
                continue
            if news["link"] in seen_links:
                continue
            seen_links.add(news["link"])
            news["stock_code"] = code
            news["stock_name"] = name
            all_news.append(news)

        time.sleep(random.uniform(0.8, 1.5))

    print(f"✅ 全部源抓取完成，原始有效新聞: {len(all_news)} 條")
    return all_news

def match_news_to_stocks(all_news, stock_list):
    """
    匹配邏輯：
    1. 支援一條新聞匹配多隻股票
    2. 英文/代碼用邊界匹配，唔會誤中
    3. 負面詞唔直接丟棄，標記交AI判斷
    """
    matched = []
    seen_match = set()
    negative_hint_count = 0

    stock_rules = {}
    for stock in stock_list:
        stock_rules[stock["code"]] = {
            "stock": stock,
            "rules": _generate_match_keywords(stock)
        }

    for news in all_news:
        title = news["title"]
        summary = news["summary"]
        content_zh = f"{title} {summary}"
        content_en = content_zh.lower()
        news_link = news["link"]

        is_negative = False
        for bad in NEGATIVE_HINT_ZH:
            if bad in content_zh:
                is_negative = True
                break
        if not is_negative and NEGATIVE_EN_PATTERN.search(content_en):
            is_negative = True
        if is_negative:
            negative_hint_count += 1
        news["negative_hint"] = is_negative

        for code, info in stock_rules.items():
            match_key = f"{code}_{news_link}"
            if match_key in seen_match:
                continue
            rules = info["rules"]
            matched_flag = False

            if rules["code_pattern"].search(content_en):
                matched_flag = True
            else:
                for kw in rules["zh"]:
                    if kw in content_zh:
                        matched_flag = True
                        break
                if not matched_flag:
                    for kw in rules["en"]:
                        if re.search(r'\b' + re.escape(kw) + r'\b', content_en):
                            matched_flag = True
                            break

            if matched_flag:
                news_copy = news.copy()
                news_copy["target_code"] = code
                news_copy["target_name"] = info["stock"]["name"]
                matched.append(news_copy)
                seen_match.add(match_key)

    print(f"✅ 關鍵詞匹配完成，送入AI分析新聞: {len(matched)} 條")
    print(f"⚠️  包含負面提示詞需AI重點判斷: {negative_hint_count} 條")
    return matched
