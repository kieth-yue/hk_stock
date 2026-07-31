import random
import time
import json
import os
import yaml
import argparse
from datetime import datetime, timedelta, timezone
from rss_fetcher import fetch_all_stock_rss, match_news_to_stocks
from ai_filter import analyze_news_batch
from feishu_push import send_feishu_card


def run_single_pool(mode, config):
    enable_flag = f"enable_stock_pool{mode[-1]}"
    if not config.get(enable_flag, True):
        pool_name = "主池Pool1（300隻）" if mode == "pool1" else "副池Pool2（250隻）"
        print(f"⚠️  {pool_name}已在config中關閉，跳過執行")
        return

    if mode == "pool1":
        stock_pool_env = os.environ["STOCK_POOL"]
        cache_file = "push_cache_pool1.json"
        print(f"\n{'='*60}")
        print(f"🚀 開始執行：主池Pool1（300隻股票，Gemini 2.5 Flash）")
        print(f"{'='*60}")
    else:
        stock_pool_env = os.environ["STOCK_POOL_2"]
        cache_file = "push_cache_pool2.json"
        print(f"\n{'='*60}")
        print(f"🚀 開始執行：副池Pool2（250隻股票，Gemini 2.5 Flash）")
        print(f"{'='*60}")
    
    # 統一用Gemini API
    api_key = os.environ["GEMINI_API_KEY"]
    data = json.loads(stock_pool_env)
    stock_list = data["stock_pool"]
    FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]

    cache_set = set()
    if os.path.exists(cache_file) and config["enable_push_cache"]:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
            cache_set = set(cache_data)

    max_wait = config["scan_random_delay_max"]
    print(f"⏳ 隨機等待0-{max_wait//60}分鐘錯峰防封禁...")
    wait_time = random.randint(0, max_wait)
    print(f"本次等待 {wait_time//60} 分 {wait_time%60} 秒")
    time.sleep(wait_time)

    print("📰 開始掃描新聞（僅抓取36小時內新聞）")
    all_raw_news = fetch_all_stock_rss(stock_list, config)
    print(f"✅ 抓取原始新聞總數：{len(all_raw_news)}")

    match_news = match_news_to_stocks(all_raw_news, stock_list)
    print(f"✅ 關鍵詞匹配完成，送入AI分析新聞數：{len(match_news)}")

    if len(match_news) == 0:
        print("ℹ️ 本池本輪無相關新聞，結束執行")
        return

    print("🤖 開始AI利好識別與風險分析")
    valid_bullish = analyze_news_batch(match_news, all_raw_news, api_key, config["bullish_min_score"])

    push_list = []
    for item in valid_bullish:
        cache_key = f"{item['target_code']}_{item['title']}_{item['pub_time'][:10]}"
        if cache_key not in cache_set:
            push_list.append(item)
            cache_set.add(cache_key)

    print(f"✅ 去重後最終推送數量：{len(push_list)}")

    if push_list:
        send_feishu_card(push_list, FEISHU_WEBHOOK)
        print(f"🎉 已成功推送 {len(push_list)} 條重大利好至飛書群")
    else:
        print("ℹ️ 本池本輪無符合門檻的重大利好，不發送飛書通知")

    if config["enable_push_cache"]:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(list(cache_set), f, ensure_ascii=False, indent=2)
        print("💾 本池推送去重緩存已保存")

    print(f"✅ {mode} 執行完畢")
    time.sleep(random.randint(60, 120))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pool1", "pool2"], default=None)
    args = parser.parse_args()

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if args.mode:
        run_single_pool(args.mode, config)
    else:
        event_name = os.getenv("GITHUB_EVENT_NAME", "workflow_dispatch")
        utc_now = datetime.now(timezone.utc)
        hkt_now = utc_now + timedelta(hours=8)

        if event_name == "workflow_dispatch":
            print(f"⚙️  手動觸發模式（HKT時間：{hkt_now.strftime('%Y-%m-%d %H:%M')}），自動執行所有已開啟的股票池")
            run_single_pool("pool2", config)
            run_single_pool("pool1", config)
        else:
            hkt_hour = hkt_now.hour
            hkt_minute = hkt_now.minute
            run_pool1 = False
            run_pool2 = False

            print(f"⏰ 定時觸發模式，當前HKT時間：{hkt_now.strftime('%Y-%m-%d %H:%M')}，自動執行對應時段任務")
            if hkt_hour == 6 and 40 <= hkt_minute <= 60:
                run_pool2 = True
            elif hkt_hour == 12 and 20 <= hkt_minute <= 40:
                run_pool2 = True
            elif hkt_hour == 21 and 40 <= hkt_minute <= 60:
                run_pool2 = True
            elif hkt_hour == 7 and 20 <= hkt_minute <= 40:
                run_pool1 = True
            elif hkt_hour == 11 and 0 <= hkt_minute <= 20:
                run_pool1 = True
            elif hkt_hour == 23 and 40 <= hkt_minute <= 60:
                run_pool1 = True

            if run_pool2:
                run_single_pool("pool2", config)
            if run_pool1:
                run_single_pool("pool1", config)

    print("\n" + "="*60)
    print("🎉 所有任務執行完畢")
    print("="*60)


if __name__ == "__main__":
    main()
