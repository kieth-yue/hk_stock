import os
import json
import time
import random
import yaml
from rss_fetcher import fetch_all_rss, first_filter
from ai_filter import init_gemini, judge_news, filter_bullish
from feishu_push import send_feishu

if __name__ == "__main__":
    print("隨機等待0-30分鐘防風控...")
    time.sleep(random.randint(0, 1800))
    print("開始掃描新聞")
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    STOCK_POOL = json.loads(os.getenv("STOCK_POOL"))
    pushed_cache = set()
    if os.path.exists(config["cache_file"]):
        try:
            with open(config["cache_file"], "r", encoding="utf-8") as f:
                pushed_cache = set(json.load(f))
        except:
            pushed_cache = set()
    all_news = fetch_all_rss(STOCK_POOL)
    print(f"抓取新聞總數：{len(all_news)}")
    filter_news = first_filter(all_news, STOCK_POOL, config["news_valid_hour"])
    print(f"關鍵字過濾後：{len(filter_news)}條")
    model = init_gemini(GEMINI_API_KEY)
    for item in filter_news:
        judge_news(model, item)
        time.sleep(1)
    bullish_list = filter_bullish(filter_news, config["bullish_min_score"])
    final_list = []
    for item in bullish_list:
        key = f"{item['stock']['code']}_{item['title']}_{item['time'].strftime('%Y%m%d')}"
        if key not in pushed_cache:
            final_list.append(item)
            pushed_cache.add(key)
    print(f"符合條件極大利好：{len(final_list)}條")
    send_feishu(FEISHU_WEBHOOK, final_list)
    with open(config["cache_file"], "w", encoding="utf-8") as f:
        json.dump(list(pushed_cache)[-500:], f)
    print("本輪掃描完畢")
