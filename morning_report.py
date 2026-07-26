import os
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types
import requests

def send_morning_card(content, webhook_url):
    hk_tz = timezone(timedelta(hours=8))
    today_str = datetime.now(hk_tz).strftime("%Y-%m-%d %A")
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"🌅 港股早盤策略 | {today_str}"},
                "template": "orange"
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "⚠️ 以上僅為短炒策略參考，交易請自行判斷風險"}]}
            ]
        }
    }
    try:
        resp = requests.post(webhook_url, json=card, timeout=10)
        resp.raise_for_status()
        print("早盤策略推送成功")
        return True
    except Exception as e:
        print(f"推送失敗: {str(e)}")
        return False

def get_ai_market_analysis(api_key):
    hk_tz = timezone(timedelta(hours=8))
    today_str = datetime.now(hk_tz).strftime("%Y-%m-%d")
    # 優化後的短炒專用Prompt，唔講廢話，全部俾實操建議
    system_prompt = f"""
你是有10年經驗的港股日內短炒操盤手，專注炒消息、炒板塊、炒資金流向，唔講廢話，所有內容直接俾實操建議。
今日是{today_str}港股交易日，請結合隔夜市場表現、最新政策消息、資金流向，生成開盤前早盤策略，嚴格按照以下結構輸出，全部用繁體中文，港股本地術語，唔好寫長篇大論，每部分最多3點，一屏睇得完：

1. 🌍 【隔夜市場與宏觀風向】
- 重點講美股三大指數收市表現、中概股表現、美元/美債/油價走勢
- 有重大政策（降準/降息/房企救市/行業政策）直接講重點，唔好鋪墊
- 簡單講外圍資金情緒：偏樂觀/中性/偏審慎

2. 📈 【今日重點關注板塊】
- 最多3個板塊，每個講清楚催化邏輯，順便講1-2隻對應的活躍龍頭
- 例子：「AI算力板塊：隔夜NVDA漲3.2%，AI服務器訂單超預期，關注商湯-W、中芯國際」
- 唔好講空話，一定要有具體催化原因

3. ⚠️ 【今日避險/偏空板塊】
- 最多2個板塊，講清楚風險原因，例子：「內房板塊：碧桂園債務展期失敗，避開相關債務重組股」
- 有大的系統性風險直接講，唔好收收埋埋

4. 💡 【今日交易提示】
- 1-2句說話，直接講今日操作心態，例子：「今日外圍偏暖，大市高開機會大，唔好追高，等回調吸強勢板塊」

注意：
- 唔好講長線價值投資、唔好模棱兩可、唔好講廢話
- 如果有突發重大消息（比如央行突發降息、行業重大政策），放在最前面用⚠️重點標註
- 全部內容控制在300字以內，飛書卡片一屏睇完
"""
    user_prompt = "請生成今日港股早盤短炒策略"
    client = genai.Client(api_key=api_key)
    try:
        resp = client.models.generate_content(
            model="gemini-1.5-pro",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3
            )
        )
        return resp.text.strip()
    except Exception as e:
        return f"⚠️ 早盤策略生成失敗，請自行查看隔夜市場：{str(e)[:50]}"

if __name__ == "__main__":
    FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    print("正在生成早盤策略...")
    content = get_ai_market_analysis(GEMINI_API_KEY)
    send_morning_card(content, FEISHU_WEBHOOK)
    print("早評任務完成")
