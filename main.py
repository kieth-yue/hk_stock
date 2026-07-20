import random
import time
import json
import os
from rss_fetcher import fetch_all_stock_rss, match_news_to_stocks
from ai_filter import analyze_news_batch
from feishu_push import send_feishu_card

def main():
    # 讀取環境變量
    stock_pool_raw = os.environ["STOCK_POOL"]
    stock_list = json.loads(stock_pool_raw)
    FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

    # 讀取48小時推送緩存，避免重複推送
    cache_file = "push_cache.json"
    cache_set = set()
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
            cache_set = set(cache_data)

    # 開頭0-15分鐘隨機等待防風控
    print("隨機等待0-15分鐘防風控...")
    wait_time = random.randint(0, 900)
    print(f"本次等待 {wait_time//60} 分 {wait_time%60} 秒")
    time.sleep(wait_time)

    print("="*50)
    print("開始掃描新聞")
    print("="*50)

    # 第一步：抓取所有RSS新聞
    all_raw_news = fetch_all_stock_rss(stock_list)
    total_raw_count = len(all_raw_news)
    print(f"✅ 抓取原始新聞總數：{total_raw_count}")

    # 第二步：關鍵字雙重匹配
    match_news = match_news_to_stocks(all_raw_news, stock_list)
    match_count = len(match_news)
    print(f"✅ 匹配成功，送入AI分析新聞數：{match_count}")

    if match_count == 0:
        print("ℹ️ 本輪無相關新聞，結束掃描")
        return

    # 第三步：Gemini AI分析過濾
    print("="*50)
    print("開始AI智能分析")
    print("="*50)
    bullish_threshold = 85
    valid_bullish = analyze_news_batch(match_news, GEMINI_API_KEY, bullish_threshold)

    # 第四步：緩存去重
    push_list = []
    for item in valid_bullish:
        cache_key = f"{item['target_code']}_{item['title']}_{item['pub_time'][:10]}"
        if cache_key not in cache_set:
            push_list.append(item)
            cache_set.add(cache_key)

    push_count = len(push_list)
    print(f"✅ 去重後最終推送數量：{push_count}")

    # 第五步：推送飛書
    if push_list:
        send_feishu_card(push_list, FEISHU_WEBHOOK)
        print(f"🎉 已成功推送 {push_count} 條重大利好至飛書")
    else:
        print("ℹ️ 本輪無符合門檻的重大利好，不發送飛書")

    # 保存更新緩存
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(list(cache_set), f, ensure_ascii=False, indent=2)
    print("💾 推送緩存已保存，48小時內重複利好不再推送")
    print("="*50)
    print("本輪掃描完畢")

if __name__ == "__main__":
    main()
