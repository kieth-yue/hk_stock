import random
import time
import json
import os
import yaml
from rss_fetcher import fetch_all_stock_rss, match_news_to_stocks
from ai_filter import analyze_news_batch
from feishu_push import send_feishu_card

def main():
    # 讀取配置文件
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # 讀取環境變量密鑰
    stock_pool_raw = os.environ["STOCK_POOL"]
    stock_list = json.loads(stock_pool_raw)
    FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

    # 讀取48小時推送緩存
    cache_file = config["cache_file"]
    cache_set = set()
    if os.path.exists(cache_file) and config["enable_push_cache"]:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
            cache_set = set(cache_data)

    # 開頭隨機等待防風控
    max_wait = config["scan_random_delay_max"]
    print(f"隨機等待0-{max_wait//60}分鐘防風控...")
    wait_time = random.randint(0, max_wait)
    print(f"本次等待 {wait_time//60} 分 {wait_time%60} 秒")
    time.sleep(wait_time)

    print("="*50)
    print("開始掃描新聞")
    print("="*50)

    # 抓取所有RSS新聞
    all_raw_news = fetch_all_stock_rss(stock_list)
    print(f"✅ 抓取原始新聞總數：{len(all_raw_news)}")

    # 雙重匹配新聞
    match_news = match_news_to_stocks(all_raw_news, stock_list)
    print(f"✅ 匹配成功，送入AI分析新聞數：{len(match_news)}")

    if len(match_news) == 0:
        print("ℹ️ 本輪無相關新聞，結束掃描")
        return

    # AI批量分析
    print("="*50)
    print("開始AI智能分析")
    print("="*50)
    valid_bullish = analyze_news_batch(match_news, GEMINI_API_KEY, config["bullish_min_score"])

    # 緩存去重
    push_list = []
    for item in valid_bullish:
        cache_key = f"{item['target_code']}_{item['title']}_{item['pub_time'][:10]}"
        if cache_key not in cache_set:
            push_list.append(item)
            cache_set.add(cache_key)

    print(f"✅ 去重後最終推送數量：{len(push_list)}")

    # 推送飛書
    if push_list:
        send_feishu_card(push_list, FEISHU_WEBHOOK)
        print(f"🎉 已成功推送 {len(push_list)} 條重大利好至飛書")
    else:
        print("ℹ️ 本輪無符合門檻的重大利好，不發送飛書")

    # 保存緩存
    if config["enable_push_cache"]:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(list(cache_set), f, ensure_ascii=False, indent=2)
        print("💾 推送緩存已保存")
    print("="*50)
    print("本輪掃描完畢")

if __name__ == "__main__":
    main()
