import requests

def send_feishu(webhook, bullish_list):
    if not bullish_list:
        return
    elements = []
    for n in bullish_list:
        stock = n["stock"]
        time_str = n["time"].strftime("%Y-%m-%d %H:%M")
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**📈 {stock['name']}({stock['code']}) | 利好評分：{n['score']}分**\n來源：{n['source']} | 時間：{time_str}\n標題：{n['title']}\n💡分析：{n['reason']}\n[原文鏈接]({n['url']})"
            }
        })
        elements.append({"tag": "hr"})
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🔥港股極大利好提醒（共{len(bullish_list)}條）"},
                "template": "green"
            },
            "elements": elements[:-1]
        }
    }
    try:
        requests.post(webhook, json=card, timeout=10)
        print("飛書推送成功")
    except Exception as e:
        print(f"飛書推送失敗：{e}")
