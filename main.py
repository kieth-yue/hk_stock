import random
import time
import json
import os
import yaml
from rss_fetcher import fetch_all_stock_rss, match_news_to_stocks
from ai_filter import analyze_news_batch
from feishu_push import send_feishu_card


def run_single_pool(mode, config):
    enable_flag = f"enable_stock_pool{mode[-1]}"
    if not config.get(enable_flag, True):
        pool_name = "主池300隻" if mode == "pool1" else "副池250隻"
        print(f"⚠️  {pool_name}已在config中關閉，跳過")
        return

    if mode == "pool1":
        stock_pool_env = os.environ["STOCK_POOL"]
        cache_file = "push_cache_pool1.json"
        print(f"\n{'='*60}")
        print(f"🚀 開始掃描主池：300隻港股")
        print(f"{'='*60}")
    else:
        stock_pool_env = os.environ["STOCK_POOL_2"]
        cache_file = "push_cache_pool2.json"
        print(f"\n{'='*60}")
        print(f"🚀 開始掃描副池：250隻港股")
        print(f"{'='*60}")
    
    api_key = os.environ["GEMINI_API_KEY"]
    # 兼容兩種JSON格式
    data = json.loads(stock_pool_env)
    stock_list = data if isinstance(data, list) else data["stock_pool"]
    FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]

    # 加載去重緩存
    cache_set = set()
    if os.path.exists(cache_file) and config["enable_push_cache"]:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_set = set(json.load(f))

    # 開場隨機等待
    max_wait = config["scan_random_delay_max"]
    wait_time = random.randint(0, max_wait)
    print(f"⏳ 隨機等待 {wait_time//60}分{wait_time%60}秒 錯峰防封")
    time.sleep(wait_time)

    # 爬取新聞
    print("📰 開始抓取36小時內新聞...")
    all_raw_news = fetch_all_stock_rss(stock_list, config)
    print(f"✅ 抓到原始新聞：{len(all_raw_news)}條")

    match_news = match_news_to_stocks(all_raw_news, stock_list)
    print(f"✅ 匹配目標新聞：{len(match_news)}條")

    if len(match_news) == 0:
        print("ℹ️ 本池無相關新聞")
        return

    # AI分析
    print("🤖 開始AI利好分析...")
    valid_bullish = analyze_news_batch(match_news, all_raw_news, api_key, config["bullish_min_score"])

    # 去重
    push_list = []
    for item in valid_bullish:
        cache_key = f"{item['target_code']}_{item['title']}_{item['pub_time'][:10]}"
        if cache_key not in cache_set:
            push_list.append(item)
            cache_set.add(cache_key)

    print(f"✅ 最終推送：{len(push_list)}條")

    # 推飛書
    if push_list:
        send_feishu_card(push_list, FEISHU_WEBHOOK)
        print(f"🎉 已推送{len(push_list)}條利好到飛書")
    else:
        print("ℹ️ 無符合門檻嘅利好，唔推送")

    # 存緩存
    if config["enable_push_cache"]:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(list(cache_set), f, ensure_ascii=False, indent=2)
        print("💾 緩存已保存")

    print(f"✅ {mode} 完成")


def main():
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 固定順序：先跑300隻主池，再跑250隻副池
    run_single_pool("pool1", config)
    
    # 兩個池中間歇1分鐘，避免連續高頻請求
    if config.get("enable_stock_pool2", True):
        print("\n⏳ 主池完成，休息1分鐘再跑副池...")
        time.sleep(60)
        run_single_pool("pool2", config)

    print("\n" + "="*60)
    print("🎉 全部掃描完成")
    print("="*60)


if __name__ == "__main__":
    main()
