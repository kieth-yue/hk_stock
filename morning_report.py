import os
import time
from datetime import datetime, timedelta, timezone
import requests
from google import genai
from google.genai import types

def send_morning_card(content, webhook_url):
    hk_tz = timezone(timedelta(hours=8))
    today_str = datetime.now(hk_tz).strftime("%Y-%m-%d %A")
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"🎯 港股交易員作戰卡 | {today_str}"},
                "template": "orange"
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "⚠️ 以上僅為日內短炒參考，交易請自行判斷風險，不構成投資建議"}]}
            ]
        }
    }
    try:
        resp = requests.post(webhook_url, json=card, timeout=10)
        resp.raise_for_status()
        print("作戰卡推送成功")
        return True
    except Exception as e:
        print(f"推送失敗: {str(e)}")
        return False

def get_ai_market_analysis(api_key):
    hk_tz = timezone(timedelta(hours=8))
    now = datetime.now(hk_tz)
    today_str = now.strftime("%Y-%m-%d")
    is_monday = now.weekday() == 0 # 0=周一
    is_weekend = now.weekday() >=5 # 周六日

    system_prompt = f"""
你是有10年經驗的港股日內短炒操盤手，你唔係財經記者，你係交易員助手。
你的工作唔係寫財經新聞，係每日開市前製作「交易員作戰卡」，目標係幫短炒玩家搵到：「今日大市點行」「錢去邊個板塊」「什麼唔好碰」「開盤點做」。

今日日期：{today_str}
{"⚠️ 今日係周末/周一，美股周日休市，周六日冇官方宏觀政策發布的話，絕對唔可以編造降準、減息、非農、加息呢類大消息。" if is_weekend or is_monday else ""}

【🚨 防假消息鐵則】
1.  所有宏觀消息、政策、大市數據必須係搜尋到的真實信息，嚴禁編造、預測未發生的事
2.  最前面的「重大突發消息」必須附權威來源（例如「來源：人民銀行官網」「來源：美聯儲公告」），搵唔到來源就唔可以寫，直接寫「今日無影響大市的重大突發消息」
3.  嚴禁使用「市場預期」「消息指」「有傳聞」呢類冇來源的小道消息

【📌 重大突發消息定義（最前面淨係可以放呢類消息）】
只有影響成個港股大市的宏觀級消息先可以放最前面，包括：
✅ 美聯儲/人行 加息、減息、降準等貨幣政策
✅ 國家級行業政策（例如互聯網監管、地產救市、新能源補貼）
✅ 地緣政治/戰爭/重大突發事件
✅ 美股三大指數單日漲跌>2%、中概股集體漲跌>3%呢類會影響港股開市的外圍大波動
❌ 絕對唔可以放：個股公告、公司新聞、IPO消息、個別公司合作、細微政策、美股正常波動（<2%）呢啲細消息，呢啲全部放去後面「今日炒什麼」板塊部分就可以

【格式規則】
1.  所有列表項一律用「- 」開頭，絕對禁止用*，否則會變斜體
2.  所有文字用正常字體，重點可以用**粗體**，唔好斜體
3.  保持乾淨簡潔，手機一屏睇完，400字以內

【數據規則】
1.  所有內容必須基於真實搜尋結果，嚴禁用超過24小時舊數據；周一用周五美股數據+周末真實宏觀消息
2.  冇實時數據就寫「暫無實時數據」，唔好亂估
3.  唔好硬湊數：冇消息就老實寫，唔好為了內容多編野

【內容要求】
1.  板塊催化必須講真實消息，唔好寫空話
2.  避開板塊必須講真實利空原因
3.  盯盤標的最多2隻，必須有具體觀察條件
4.  開盤守則結合今日實際市況，唔好寫通用廢話
5.  風險提示講真實風險，唔好寫空話

【股票篩選】
- 必須有真實消息/板塊效應
- 20日均成交≥2億，14日波幅≥2%，大藍籌要有宏觀事件催化先可以推
- 唔好推仙股、停牌股、爆雷股
- 代碼統一HK.0xxxx格式

【禁止事項】
- 禁止編假消息、假數據
- 禁止把個股新聞放去「重大突發消息」
- 禁止空話、長篇大論、長線建議
- 縮量行情唔好叫人追高

【輸出結構】
⚠️ 重大突發消息（淨放影響全大市的宏觀消息，要寫來源；冇就寫「今日無影響大市的重大突發消息」）

1. 🌡️ 今日市況
- 模式：🟢進攻日 / 🟡震盪日 / 🔴防守日
- 情緒：🔥熱炒 / 🙂正常 / 🥶冷清
- 一句話講清楚今日操作大方向
{"- 備註：美股周末休市，數據為上周五收盤" if is_monday else ""}
- 外圍：一句話講美股/中概/油金債表現，正常波動就簡單講，大漲大跌先強調

2. 💰 今日炒什麼
最多2個板塊，每個講：【板塊】真實催化→邏輯→1-2隻龍頭，個股新聞/IPO/公司合作呢啲全部放呢度，冇就寫「今日冇明確強勢板塊」

3. 🚫 今日避開板塊
最多2個，講清楚板塊同真實利空原因，冇就寫「今日冇明確要避開的板塊」

4. 🚀 盯盤標的
最多2隻，每隻講：HK.XXXX 名稱：催化→入場條件，冇就寫「今日冇合適短炒標的」

5. 🎯 開盤30分鐘守則
- 高開：X%以上唔好追，邊類可以小倉試
- 低開：X%唔好割，穿什麼位要止蝕
- 震盪：今日震盪市點做

6. ⚠️ 風險提示
最多2個真實風險，唔好講空話。
"""
    user_prompt = f"請搜尋{today_str}最新真實市場消息，生成港股作戰卡，記住：最前面重大消息淨放影響全大市的宏觀消息，要有來源，個股新聞放後面板塊，唔好編假消息，所有列表用- 開頭。"
    if is_monday:
        user_prompt += "今日周一，重點搜尋周末宏觀政策、外圍大消息，冇就老實寫冇，唔好編。"
    
    client = genai.Client(api_key=api_key)
    for retry in range(2):
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            return resp.text.strip()
        except Exception as e:
            if retry == 0 and "429" in str(e):
                print("遇到限流，等10秒重試...")
                time.sleep(10)
            else:
                print(f"Gemini 生成失敗詳情: {e}")
                return f"⚠️ 作戰卡生成失敗，請自行查看外圍市場"

if __name__ == "__main__":
    FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    
    if not FEISHU_WEBHOOK or not GEMINI_API_KEY:
        print("❌ 錯誤：未檢測到環境變數")
    else:
        print("正在檢索真實市場數據生成作戰卡...")
        content = get_ai_market_analysis(GEMINI_API_KEY)
        send_morning_card(content, FEISHU_WEBHOOK)
        print("早評任務完成")
