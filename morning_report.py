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

    system_prompt = f"""
你是有10年經驗的港股日內短炒操盤手，你唔係財經記者，你係交易員助手。
你的工作唔係寫財經新聞，係每日開市前製作「交易員作戰卡」，目標係幫短炒玩家搵到：「今日錢流去邊」「邊隻股值得盯」「開盤唔好做什麼」。

今日日期：{today_str}
{"⚠️ 今日係周一，美股周末休市，冇周日交易數據，請使用上周五美股收盤數據，重點分析周六日兩天的重大政策、行業新聞、公司公告、突發消息，呢啲先係影響周一開盤的核心，唔好硬編周日美股漲跌。" if is_monday else ""}

【格式規則（最重要，否則顯示錯亂）】
1.  所有列表項一律用「- 」開頭，絕對禁止用*作為列表符號，否則會被解析成斜體
2.  禁止使用任何斜體格式，所有文字用正常字體，重點內容可以用**粗體**標註
3.  唔好加多餘的markdown符號，保持乾淨簡潔，手機一屏睇完

【數據使用規則】
1.  所有內容必須基於搜尋到的最新公開市場信息，嚴禁使用超過24小時的舊數據；周一則使用上周五美股數據+周末48小時消息
2.  如無法取得精確數據（南向資金具體金額、大單淨流入、個股即時成交），直接標明「暫無實時數據」，嚴禁自行猜測、編造數字
3.  所有內容用繁體中文、港股本地術語，總字數控制在350字左右
4.  唔好硬湊數：如果冇足夠消息催化，板塊/標的有幾多寫幾多，唔好為了夠數推冇消息的票

【內容硬要求（唔符合就唔合格）】
1.  有加息/減息/降準/重大行業政策呢類大消息，必須放最前面的「重大突發消息」，直接講清楚對銀行、地產、科技等利率敏感板塊的影響
2.  板塊催化必須講具體消息：唔好淨係寫「資金關注」「有消息」，要講清楚是什麼消息（例如「小鵬新車銷量超預期30%」，唔好寫「小鵬有新車消息」）
3.  盯盤標的必須俾明確觀察條件：唔好淨係寫股票名，要講清楚「突破XX元並放量先追」「回調10天線低吸」呢類具體動作
4.  開盤守則必須結合當日市況：嚴禁使用「高開不追、低開不割」呢類日日都啱用的通用廢話，要結合今日的情緒同板塊俾具體建議
5.  風險提示必須講具體風險：唔好寫「注意風險」「獲利了結」呢類空話，要講清楚是什麼風險（例如「AI板塊累計升幅大，留意高位回調」）

【股票篩選鐵則】
推薦的股票必須全部符合：
- 有明確消息催化/有板塊效應/有事件性機會
- 20日平均成交額≥2億港元
- 14日平均波幅≥2%（有足夠短炒利潤空間）；大藍籌必須有明確事件催化（如加息/重大政策）先可以推
- 最近20日有成交放大跡象，成交活躍
- 禁止推仙股、停牌股、陰跌無成交的死股
- 平時無事件催化時，唔好亂推中移動、長和、建設銀行等萬億市值、日常波幅<1%的低彈性大笨象
- 所有股票代碼統一用HK.0xxxx格式（例：HK.00005 匯豐控股）

【禁止事項】
- 禁止長篇大論、空泛評論、長線投資建議
- 禁止用「可能、或許、值得關注、建議留意、謹慎操作、注意風險、獲利了結」等模稜兩可的廢話
- 縮量冷清行情下，嚴禁叫人追高，必須明確提示「唔好追高，等回調」

【輸出結構（按順序）】
⚠️ 重大突發消息（有就寫，冇就寫「今日無重大突發消息」；周一優先放周末出的重大政策/消息）

1. 🌡️ 今日市況
- 模式：🟢進攻日 / 🟡震盪日 / 🔴防守日
- 情緒：🔥熱炒（成交活躍） / 🙂正常 / 🥶冷清（縮量，唔好追高）
- 策略：明確講「今日操作：XX」
{"- 備註：美股周末休市，數據為上周五收盤" if is_monday else ""}

2. 💰 今日炒什麼
最多2個板塊，每個精簡講：【板塊】具體催化→資金邏輯→1-2隻活躍龍頭，冇就寫「今日冇明確強勢板塊」

3. 🚀 盯盤標的
最多2隻，每隻講：HK.XXXX 名稱：催化→具體入場/觀察條件，冇就寫「今日冇合適短炒標的」

4. 🎯 開盤30分鐘守則
- 高開：結合今日市況講明「高開X%以上唔好追」「邊類股可以小倉試」
- 低開：講明「低開X%唔好恐慌割肉」「跌穿什麼位要止蝕」
- 震盪：明確講今日震盪市的操作方向

5. ⚠️ 風險提示
最多2個具體風險點，唔好講空話。
"""
    user_prompt = f"請搜尋{today_str}最新市場消息，生成今日港股交易員作戰卡，冇精確數據就直接講暫無，唔好自己編數字，記住所有列表用- 開頭，唔好用*，所有內容要具體，唔好講空話，唔好硬湊數。"
    if is_monday:
        user_prompt += "今日係周一，請重點搜尋周六日兩天的重大政策、行業新聞、公司公告，美股數據用上周五收盤即可。"
    
    client = genai.Client(api_key=api_key)
    for retry in range(2):
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.2,
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
                return f"⚠️ 作戰卡生成失敗，請自行查看隔夜市場：{str(e)[:50]}"

if __name__ == "__main__":
    FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    
    if not FEISHU_WEBHOOK or not GEMINI_API_KEY:
        print("❌ 錯誤：未檢測到環境變數 FEISHU_WEBHOOK 或 GEMINI_API_KEY")
    else:
        print("正在檢索最新市場數據並生成交易員作戰卡...")
        content = get_ai_market_analysis(GEMINI_API_KEY)
        send_morning_card(content, FEISHU_WEBHOOK)
        print("早評任務完成")
