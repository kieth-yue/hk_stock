from google import genai
from google.genai import types
import json
import time
import re

SYSTEM_PROMPT = """
你是港股事件驅動對沖基金經理，專門從新聞中篩選未來48小時-2周可能引發股價大幅上漲的重大催化劑。
【核心判斷】
只有事件滿足以下至少2點才判定為重大利好：
1. 事件已正式落實，非傳聞/計劃/猜測
2. 可實質改變公司未來1-3年盈利能力
3. 可引發公司估值重估
4. 可吸引持續資金流入
5. 非一次性收益、非市場已廣泛預期
【重大催化劑分類】
超預期業績/盈喜、巨額合同、回購註銷、私有化、AI/科技合作、政策受益、新產品/技術突破、海外拓展、監管批准、超預期派息、納入指數(恆指/港股通/MSCI)、分拆上市、大額融資(利好型)
【評分規則】
95-100：極重大催化劑，單日漲幅10%+；85-94：明確重大利好；<85：忽略
【置信度規則】
95=官方公告；90=權威媒體；60=市場消息；30=傳聞
【緊急度規則】
Immediate：即日反應；1-3 Days：中线反應；Long Term：長期影響
【注意】
1. 信息不足一律返回false，不要猜測
2. 無股價數據時price_in="Unknown"，不要亂判
3. 嚴格返回JSON數組，不要額外解釋
【輸出格式】
返回JSON數組，每個元素字段：
{
  "is_major_bullish": true/false, "score": 0-100,
  "category": "利好分類", "confidence": 0-100,
  "reason": "80字以內中文點評", "risk": "低/中/高",
  "price_in": "Unknown", "urgency": "Immediate/1-3 Days/Long Term"
}
"""

RISK_PROMPT = """
你是港股風控分析師，根據給定的股票近期新聞，簡短總結是否有影響股價的利空風險，40字以內。
【重大利空（必須明確標註🔴）】：配股/供股抽水、立案調查、財務造假、盈警、大股東減持>5%、退市風險、重大處罰、產品安全事故
【輕微利空（標註🟡）】：小股東減持、行業政策小幅收緊、業績略遜預期、短期波動風險
【無明顯利空】：直接寫「近期未見明顯利空」
注意：不要過度解讀，有事實先講，冇就寫無，不要猜測。直接返回JSON對象，格式：{"risk_warning": "風險提示內容"}
"""

JSON_ARRAY_PATTERN = re.compile(r'\[.*?\]', re.DOTALL)
JSON_OBJECT_PATTERN = re.compile(r'\{.*?\}', re.DOTALL)

def _extract_json(text):
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    arr_match = JSON_ARRAY_PATTERN.search(text)
    if arr_match:
        try: return json.loads(arr_match.group())
        except: pass
    obj_match = JSON_OBJECT_PATTERN.search(text)
    if obj_match:
        try: return [json.loads(obj_match.group())]
        except: pass
    return None

def _call_gemini_with_backoff(client, news_batch, system_prompt, is_json_array=True):
    prompt_parts = ["請按編號順序分析以下新聞，返回JSON：\n"]
    for idx, news in enumerate(news_batch, 1):
        negative_tip = "\n⚠️ 注意：該新聞包含負面關鍵詞，請仔細判斷是否為「扭虧為盈」等邊界利好。" if news.get("negative_hint") else ""
        prompt_parts.append(f"""
=== 新聞{idx} ===
股票：{news['target_name']} ({news['target_code']})
來源：{news['source']}
時間：{news['pub_time'].strftime('%Y-%m-%d %H:%M') if hasattr(news['pub_time'], 'strftime') else news['pub_time']}
標題：{news['title']}
摘要：{news['summary'] if news['summary'] else '無摘要'}
{negative_tip}
""")
    prompt = "\n".join(prompt_parts)
    backoff_times = [1, 2, 4, 8]
    for wait_time in backoff_times:
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0,
                    response_mime_type="application/json"
                )
            )
            result = _extract_json(resp.text)
            if result:
                if is_json_array and isinstance(result, list) and len(result) == len(news_batch):
                    return result
                if not is_json_array and isinstance(result, dict):
                    return result
        except Exception as e:
            print(f"[重試] 調用失敗，等待{wait_time}秒: {str(e)}")
            time.sleep(wait_time)
    if is_json_array:
        return [{"is_major_bullish": False, "score": 0} for _ in news_batch]
    return {"risk_warning": "風險分析失敗"}

def analyze_news_batch(news_list, all_news, api_key, threshold=85):
    client = genai.Client(api_key=api_key)
    valid_bullish = []
    total = len(news_list)
    batch_size = 10
    for batch_idx in range(0, total, batch_size):
        batch = news_list[batch_idx:batch_idx+batch_size]
        batch_start = batch_idx + 1
        batch_end = min(batch_idx + batch_size, total)
        print(f"AI利好分析進度: [{batch_start}-{batch_end}/{total}] ...")
        batch_results = _call_gemini_with_backoff(client, batch, SYSTEM_PROMPT, is_json_array=True)
        for news, result in zip(batch, batch_results):
            result.setdefault("is_major_bullish", False)
            result.setdefault("score", 0)
            result.setdefault("category", "其他")
            result.setdefault("confidence", 0)
            result.setdefault("reason", "")
            result.setdefault("risk", "高")
            result.setdefault("price_in", "Unknown")
            result.setdefault("urgency", "Long Term")
            result["title"] = news["title"]
            result["link"] = news["link"]
            result["source"] = news["source"]
            result["target_code"] = news["target_code"]
            result["target_name"] = news["target_name"]
            result["pub_time"] = news["pub_time"].strftime("%Y-%m-%d %H:%M")
            if result["is_major_bullish"] and result["score"] >= threshold and result["confidence"] >= 70:
                valid_bullish.append(result)
                print(f"✅ 發現重大利好: {result['target_name']} {result['score']}分 {result['category']} | 緊急度:{result['urgency']}")
        time.sleep(1)

    # 對重大利好股票做利空風險分析
    if valid_bullish:
        print("="*50)
        print(f"開始對{len(valid_bullish)}隻利好股票做風險分析...")
        print("="*50)
        # 按股票分組已抓的所有新聞
        stock_news_map = {}
        for news in all_news:
            code = news["stock_code"]
            if code not in stock_news_map:
                stock_news_map[code] = []
            stock_news_map[code].append(news)
        
        for bull in valid_bullish:
            code = bull["target_code"]
            related_news = stock_news_map.get(code, [])
            if not related_news:
                bull["risk_warning"] = "近期未見明顯利空"
                continue
            # 最多拿最近5條新聞做風險分析，節省token
            risk_news = related_news[:5]
            risk_result = _call_gemini_with_backoff(client, risk_news, RISK_PROMPT, is_json_array=False)
            bull["risk_warning"] = risk_result.get("risk_warning", "風險分析失敗")
            print(f"⚠️  {bull['target_name']} 風險: {bull['risk_warning']}")
            time.sleep(0.5)

    urgency_order = {"Immediate": 0, "1-3 Days": 1, "Long Term": 2}
    valid_bullish.sort(key=lambda x: (urgency_order.get(x["urgency"], 3), -x["score"]))
    print(f"AI分析完成，符合條件重大利好: {len(valid_bullish)} 條")
    return valid_bullish
