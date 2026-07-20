import feedparser
import requests
import time
import random
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}

BULLISH_WHITELIST = ["盈喜", "回購", "註銷", "增持", "私有化", "中標", "分拆", "債務豁免", "勝訴", "預增", "扭虧"]
BULLISH_BLACKLIST = ["框架協議", "意向", "備忘錄", "MOU", "政府補助", "一次性", "出售資產", "傳聞", "籌劃", "可能", "預計"]

def _sleep():
    time.sleep(random.uniform(2.0, 4.0))

def fetch_webb_rss():
    news = []
    try:
        url = "https://webb-site.com/rss/hkeqna.xml"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            news.append({
                "title": entry.title,
                "time": datetime(*entry.published_parsed[:6]),
                "source": "港交所公告",
                "url": entry.link
            })
    except Exception as e:
        print(f"Webb RSS 抓取失敗: {e}")
    return news

def fetch_single_stock_rss(code, name):
    news = []
    # Yahoo RSS
    try:
        url = f"https://finance.yahoo.com/rss/{code}.HK"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:5]:
            news.append({
                "title": entry.title,
                "time": datetime(*entry.published_parsed[:6]),
                "source": "Yahoo Finance",
                "url": entry.link
            })
        _sleep()
    except Exception as e:
        print(f"Yahoo {code} 失敗: {e}")
    # Google News RSS
    try:
        query = f"{code}+{name}+港股"
        url = f"https://news.google.com/rss/search?q={query}&hl=zh-HK&gl=HK&ceid=HK:zh-HK"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:5]:
            news.append({
                "title": entry.title,
                "time": datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %Z"),
                "source": "Google News",
                "url": entry.link
            })
        _sleep()
    except Exception as e:
        print(f"Google {code} 失敗: {e}")
    # RSSHub 富途
    try:
        url = f"https://rsshub.app/futunn/stock/{code}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:5]:
            news.append({
                "title": entry.title,
                "time": datetime(*entry.published_parsed[:6]),
                "source": "富途快訊",
                "url": entry.link
            })
        _sleep()
    except Exception as e:
        print(f"RSSHub {code} 失敗: {e}")
    return news

def fetch_all_rss(stock_pool):
    all_news = []
    all_news.extend(fetch_webb_rss())
    _sleep()
    for stock in stock_pool:
        code = stock["code"]
        name = stock["name"]
        all_news.extend(fetch_single_stock_rss(code, name))
        time.sleep(random.uniform(1.2, 2.0))
    return all_news

def first_filter(news_list, stock_pool, valid_hour=48):
    cutoff = datetime.now() - timedelta(hours=valid_hour)
    news_list = [n for n in news_list if n["time"] >= cutoff]
    valid_news = []
    for n in news_list:
        title = n["title"]
        match = None
        for s in stock_pool:
            if s["code"] in title or s["name"][:2] in title:
                match = s
                break
        if not match:
            continue
        n["stock"] = match
        in_white = any(k in title for k in BULLISH_WHITELIST)
        in_black = any(k in title for k in BULLISH_BLACKLIST)
        if in_white and not in_black:
            valid_news.append(n)
    seen = set()
    unique = []
    for n in valid_news:
        key = f"{n['stock']['code']}_{n['title']}_{n['time'].strftime('%Y%m%d')}"
        if key not in seen:
            seen.add(key)
            unique.append(n)
    return unique
