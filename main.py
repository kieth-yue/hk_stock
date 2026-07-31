import random
import time
import json
import os
import yaml
import argparse
from rss_fetcher import fetch_all_stock_rss, match_news_to_stocks
from ai_filter import analyze_news_batch
from feishu_push import send_feishu_card

def main():
    # 解析命令行參數
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pool1", "pool2"], default="pool1", 
                        help="運行模式：pool1=300隻Gemini主池, pool2=250隻GLM副池")
    args = parser.parse_args()

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # 讀取股票池開關（預設全開，向後兼容舊config）
    enable_pool1 = config.get("enable_stock_pool1", True)
    enable_pool2 = config.get("enable_stock_pool2", True)

    # 根據模式+開關決定是否執行
    if args.mode == "pool1":
        if not enable_pool1:
            print("⚠️  主池Pool1（300隻）已在config.yaml中關閉，跳過執行")
            return
        # 加載主池配置
        stock_pool_raw = os.environ["STOCK_POOL"]
        api_key = os.environ["GEMINI_API_KEY"]
        model_name = "gemini-2.5-flash"
        cache_file = "push_cache_pool1.json"
        print(f"🚀 啟動模式：主池Pool1（300隻股票，Gemini 2.5 Flash）")
    else:
        if not enable_pool2:
            print("⚠️  副池Pool2（250隻）已在config.yaml中關閉，跳過執行")
            return
        # 加載副池配置
        stock_pool_raw = os.environ["STOCK_POOL_2"]
        api_key = os.environ["SILICONFLOW_API_KEY"]
        model_name = "THUDM/GLM-Z1-9B-0414"
        cache_file = "push_cache_pool2.json"
        print(f"🚀 啟動模式：副池Pool2（250隻股票，SiliconFlow GLM-Z1-9B）")

    # 解析股票池
    data = json.loads(stock_pool_raw)
    stock_list = data["stock_pool"]
    FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]

    # 加載推送緩存
    cache_set = set()
    if os.path.exists(cache_file) and config["enable_push_cache"]:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
            cache_set = set(cache_data)

    max_wait = config["scan_random_delay_max"]
    print(f"隨機等待0-{max_wait//60}分鐘防風控...")
    wait_time = random.randint(0, max_wait)
    print(f"本次等待 {wait_time//60} 分 {wait_time%60} 秒")
    time.sleep(wait_time)

    print("="*50)
    print("開始掃描新聞（僅抓取36小時內新聞）")
    print("="*50)

    all_raw_news = fetch_all_stock_rss(stock_list, config)
    print(f"✅ 抓取原始新聞總數：{len(all_raw_news)}")

    match_news = match_news_to_stocks(all_raw_news, stock_list)
    print(f"✅ 匹配成功，送入AI分析新聞數：{len(match_news)}")

    if len(match_news) == 0:
        print("ℹ️ 本輪無相關新聞，結束掃描")
        return

    print("="*50)
    print("開始AI智能分析")
    print("="*50)
    # 傳入對應API Key、模型、分數閾值
    valid_bullish = analyze_news_batch(match_news, all_raw_news, api_key, model_name, config["bullish_min_score"])

    push_list = []
    for item in valid_bullish:
        cache_key = f"{item['target_code']}_{item['title']}_{item['pub_time'][:10]}"
        if cache_key not in cache_set:
            push_list.append(item)
            cache_set.add(cache_key)

    print(f"✅ 去重後最終推送數量：{len(push_list)}")

    if push_list:
        send_feishu_card(push_list, FEISHU_WEBHOOK)
        print(f"🎉 已成功推送 {len(push_list)} 條重大利好至飛書")
    else:
        print("ℹ️ 本輪無符合門檻的重大利好，不發送飛書")

    if config["enable_push_cache"]:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(list(cache_set), f, ensure_ascii=False, indent=2)
        print("💾 推送緩存已保存")
    print("="*50)
    print("本輪掃描完畢")

if __name__ == "__main__":
    main()
