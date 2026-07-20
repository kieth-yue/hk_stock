import google.generativeai as genai
import json
import os

SYSTEM_PROMPT = """
你係港股專業分析師，嚴格按照以下標準判斷新聞係唔係「極大利好」：
1. 極大利好定義：
   - 公司已經正式發布公告，唔係傳聞、意向
   - 對公司長期價值有實質正面影響，包括：業績盈喜（淨利潤增長50%以上）、大額回購註銷、大股東增持1%以上、高溢價私有化、已簽約的百億級訂單、分拆上市、全額債務豁免、重大訴訟勝訴
2. 必須排除的假利好：
   - 框架協議、意向書、無約束力備忘錄、政府補助、一次性出售資產收益、傳聞、籌劃中事項、小額回購/增持
3. 輸出要求：
   必須輸出標準JSON，唔好有其他多餘內容，格式：
   {"is_bullish": true/false, "score": 0-100, "reason": "50字以內判斷理由"}
   - is_bullish: true先係極大利好
   - score: 88分以上先算高質量利好
   - reason: 簡潔講清楚核心利好邏輯
"""

def init_gemini(api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
    return model

def judge_news(model, news_item):
    try:
        prompt = f"股票：{news_item['stock']['name']}({news_item['stock']['code']})\n新聞標題：{news_item['title']}\n新聞來源：{news_item['source']}"
        resp = model.generate_content(prompt)
        text = resp.text.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        news_item["is_bullish"] = result.get("is_bullish", False)
        news_item["score"] = result.get("score", 0)
        news_item["reason"] = result.get("reason", "")
        return news_item
    except Exception as e:
        print(f"AI分析異常：{e}")
        news_item["is_bullish"] = False
        news_item["score"] = 0
        news_item["reason"] = "分析失敗"
        return news_item

def filter_bullish(news_list, min_score=88):
    return [n for n in news_list if n["is_bullish"] and n["score"] >= min_score]
