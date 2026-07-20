import requests
import json

def send_feishu_card(news_list, webhook_url):
    # 先去重，避免同一條新聞重複推送
    unique_news = []
    seen = set()
    for news in news_list:
        key = f"{news['target_code']}_{news['title']}"
        if key not in seen:
            seen.add(key)
            unique_news.append(news)
    news_list = unique_news

    elements = []
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**📢 本輪掃描發現 {len(news_list)} 隻股票重大利好催化劑**"
        }
    })
    elements.append({"tag": "hr"})

    for idx, news in enumerate(news_list, 1):
        # 加上Unknown映射，解決KeyError
        price_in_text = {
            "Low": "🟢 低（未炒作）",
            "Medium": "🟡 中（部分反應）",
            "High": "🔴 高（已炒高）",
            "Unknown": "⚪ 未知（無股價數據）"
        }.get(news["price_in"], "⚪ 未知")

        risk_text = {
            "低": "🟢 低風險",
            "中": "🟡 中風險",
            "高": "🔴 高風險"
        }.get(news["risk"], "🟡 中風險")

        urgency_text = {
            "Immediate": "⚡ 即日反應",
            "1-3 Days": "📅 1-3日",
            "Long Term": "⏳ 長期"
        }.get(news["urgency"], "📅 1-3日")

        content = f"""
**{idx}. {news['target_name']} ({news['target_code']})**
> ✅ 利好分類：{news['category']}
> ⭐ 利好評分：**{news['score']}/100**
> ⚡ 緊急度：{urgency_text}
> 🎯 置信度：{news['confidence']}%
> 📈 預期消化：{price_in_text}
> ⚠️ 風險等級：{risk_text}
> 📝 點評：{news['reason']}
> 🔗 來源：{news['source']} | [查看新聞]({news['link']})
        """
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": content.strip()
            }
        })
        elements.append({"tag": "hr"})

    elements.append({
        "tag": "note",
        "elements": [
            {
                "tag": "plain_text",
                "content": "⚠️ 以上僅為事件驅動提醒，不構成任何投資建議，交易請自行判斷風險"
            }
        ]
    })

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "🚀 港股重大利好提醒"},
                "template": "green"
            },
            "elements": elements
        }
    }

    try:
        resp = requests.post(webhook_url, json=card, timeout=10)
        resp.raise_for_status()
        print("飛書卡片推送成功")
        return True
    except Exception as e:
        print(f"飛書推送失敗: {str(e)}")
        return False
