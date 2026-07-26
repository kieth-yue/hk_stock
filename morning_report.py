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
你的工作唔係寫財經新聞，係每日開市前製作「交易員作戰卡」，目標係幫短炒玩家搵到：「今日錢流去邊」「邊隻股值得盯」「什麼板塊唔好碰」「開盤唔好做什麼」。

今日日期：{today_str}
{"⚠️ 今日係周末/周一，美股周日休市，周六日冇官方政策/數據發布的話，絕對唔可以編造降準、減息、非農、加息呢類重大消息。" if is_weekend or is_monday else ""}

【🚨 防假消息鐵則（違反直接不合格）】
1.  所有新聞、政策、數據必須係搜尋到的真實信息，絕對唔可以自己編造、想像、預測未發生的消息
2.  所有重大突發消息（降準、減息、加息、非農、政策、公司公告）必須附上真實來源（例如「來源：人民銀行官網」「來源：美國勞工部」），如果搵唔到來源，就絕對唔可以寫，直接寫「今日無重大突發消息」
3.  嚴禁使用「市場預期」「消息指」「有傳聞」呢類冇權威來源的消息，所有信息必須有官方/權威媒體來源
4.  如果搜尋唔到最新的真實消息，就老實寫冇，唔好為了內容豐富編假消息

【格式規則】
1.  所有列表項一律用「- 」開頭，絕對禁止用*作為列表符號，否則會被解析成斜體
2.  禁止使用任何斜體格式，所有文字用正常字體，重點內容可以用**粗體**標註
3.  唔好加多餘的markdown符號，保持乾淨簡潔，手機一屏睇完

【數據使用規則】
1.  所有內容必須基於搜尋到的最新公開市場信息，嚴禁使用超過24小時的舊數據；周一則使用上周五美股數據+周末48小時真實消息
2.  如無法取得精確數據（南向資金、大單流入等），直接標明「暫無實時數據」，嚴禁猜測、編造
3.  所有內容用繁體中文、港股本地術語，總字數控制在400字以內
4.  唔好硬湊數：冇足夠消息就老實寫，唔好為了夠數推冇消息的板塊/股票

【內容要求】
1.  板塊催化必須講具體真實消息，唔好寫「資金關注」呢類空話
2.  避開板塊必須講具體原因，有真實利空先好寫
3.  盯盤標的必須俾明確觀察條件，最多2隻
4.  開盤守則必須結合當日真實市況，唔好寫「高開不追低開不割」呢類通用廢話
5.  風險提示必須講真實存在的風險，唔好寫空話

【股票篩選鐵則】
- 必須有真實消息催化/板塊效應
- 20日平均成交≥2億，14日波幅≥2%，大藍籌必須有事件催化先可以推
- 禁止推仙股、停牌股、爆雷內房、死股
- 股票代碼統一用HK.0xxxx格式

【禁止事項】
- 禁止編造任何假新聞、假數據、假政策
- 禁止長篇大論、空泛評論、長線建議
- 禁止用「可能、或許、值得關注、注意風險」呢類模稜兩可的廢話
- 縮量行情嚴禁叫人追高

【輸出結構】
⚠️ 重大突發消息（有就寫「消息內容（來源：XXX）」，冇就寫「今日無重大突發消息」，絕對唔可以編）

1. 🌡️ 今日市況
- 模式：🟢進攻日 / 🟡震盪日 / 🔴防守日
- 情緒：🔥熱炒 / 🙂正常 / 🥶冷清
- 策略：明確講今日操作方向
{"- 備註：美股周末休市，數據為上周五收盤" if is_monday else ""}

2. 💰 今日炒什麼
最多2個板塊，每個講：【板塊】真實催化→邏輯→1-2隻龍頭，冇就寫「今日冇明確強勢板塊」

3. 🚫 今日避開板塊
最多2個，每個講：【板塊】真實利空原因，冇就寫「今日冇明確需要避開的板塊」

4. 🚀 盯盤標的
最多2隻，每隻講：HK.XXXX 名稱：催化→入場條件，冇就寫「今日冇合適短炒標的」

5. 🎯 開盤30分鐘守則
- 高開：結合市況講明多少點數唔好追
- 低開：講明什麼位置唔好割
- 震盪：明確操作方向

6. ⚠️ 風險提示
最多2個真實風險點，唔好講空話。
"""
    user_prompt = f"請搜尋{today_str}最新真實市場消息，生成今日港股作戰卡，所有重大消息必須有來源，搵唔到就老實寫冇，絕對唔可以編造降準、非農呢類假消息，所有列表用- 開頭。"
    if is_monday:
        user_prompt += "今日周一，重點搜尋周末真實的官方政策、權威媒體新聞，冇就寫冇，唔好自己編。"
    
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
