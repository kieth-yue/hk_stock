import random
import time
import json
import os
from rss_fetcher import fetch_all_stock_rss
from ai_filter import analyze_news_batch
from feishu_push import send_feishu_card

# 讀取股票清單
stock_pool_raw = os.environ["STOCK_POOL"]
stock_list = json.loads(stock_pool_raw)
# 讀取環境變數
FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# 讀取緩存文件（避免48小時重複推送）
cache_file = "push_cache.json"
cache_set = set()
if os.path.exists(cache_file):
    with open(cache_file, "r", encoding="utf-8") as f:
        cache_data = json.load(f)
        cache_set = set(cache_data)

# 開頭0~15分鐘隨機等待防風控
print("隨機等待0-15分鐘防風控...")
time.sleep(random.randint(0, 900))

print("開始掃描新聞")
# 抓取全部RSS新聞
all_raw_news = fetch_all_stock_rss(stock_list)
total_raw_count = len(all_raw_news)
print(f"抓取新聞總數：{total_raw_count}")

# 關鍵字匹配過濾
match_news = []
for stock in stock_list:
    stock_code = stock["code"]
    stock_short = stock["name"][:2]
    for news in all_raw_news:
        title = news["title"]
        # 匹配股票名前兩字 OR 股票數字代碼
        if stock_short in title or stock_code in title:
            news["target_code"] = stock_code
            news["target_name"] = stock["name"]
            match_news.append(news)

match_count = len(match_news)
print(f"關鍵字過濾後，送入AI分析新聞數：{match_count}")

# 調用Gemini AI打分
bullish_threshold = 88
valid_bullish = analyze_news_batch(match_news, GEMINI_API_KEY, bullish_threshold)
push_list = []
for item in valid_bullish:
    cache_key = f"{item['target_code']}_{item['title']}_{item['time'][:10]}"
    if cache_key not in cache_set:
        push_list.append(item)
        cache_set.add(cache_key)

push_count = len(push_list)
print(f"AI打分達標、準備推送飛書消息數：{push_count}")

# 推送飛書
if push_list:
    send_feishu_card(push_list, FEISHU_WEBHOOK)
    print(f"已成功推送 {push_count} 條極大利好至飛書群組")
else:
    print("本輪無符合門檻極大利好，不發送飛書消息")

# 保存更新緩存
with open(cache_file, "w", encoding="utf-8") as f:
    json.dump(list(cache_set), f, ensure_ascii=False, indent=2)
print("推送緩存已保存完畢，48小時內重複利好不再推送")
