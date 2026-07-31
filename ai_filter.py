import json
import re
import time
import random
from google import genai
from google.genai import types

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
3. 嚴格返回JSON數組，順序同輸入新聞順序完全一致，不要額外解釋

【輸出格式】
返回JSON數組，每個元素字段：
{
  "is_major_bullish": true/false, "score": 0-100,
  "category": "利好分類", "confidence": 0-100,
  "reason": "80字以內中文點評", "risk": "低/中/高",
  "price_in": "Unknown", "urgency": "Immediate/1-3 Days/Long Term"
}
"""

RISK_BATCH_PROMPT = """
你是港股風控分析師，按編號順序分析每組新聞對應股票的潛在風險，每個風險提示40字以內。

【重大利空（必須標註🔴）】：配股/供股抽水、立案調查、財務造假、盈警、大股東減持>5%、退市風險、重大處罰
【輕微利空（標註🟡）】：小股東減持、行業政策小幅收緊、業績略遜預期、短期波動風險
【無明顯利空】：直接寫「近期未見明顯利空」

注意：不要過度解讀，有事實先講，冇就寫無，不要猜測。嚴格返回JSON數組，順序同輸入完全一致，格式：
[{"risk_warning": "風險提示內容"}, ...]
"""

MAJOR_RISK_KEYWORDS = ["配股", "供股", "抽水", "立案", "調查", "造假", "盈警", "虧損", "減持", "退市", "處罰", "罰款", "制裁"]
MINOR_RISK_KEYWORDS = ["小股東減持", "業績略遜", "政策收緊", "波動", "回調"]

def _extract_json(text):
    if not text:
        return None
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.replace('\ufeff', '').strip()
    text = re.sub(r',\s*([}\]])', r'\1', text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    arr_match = re.search(r'\[.*\]', text, re.DOTALL)
    if arr_match:
        try:
            return json.loads(arr_match.group())
        except Exception:
            pass
    dict_match = re.search(r'\{.*\}', text, re.DOTALL)
    if dict_match:
        try:
            return [json.loads(dict_match.group())]
        except Exception:
            pass
    return None

def _local_risk_fallback(news_batch):
    results = []
    for news in news_batch:
        content = f"{news.get('title', '')} {news.get('summary', '')}"
        risk = "近期未見明顯利空"
        for kw in MAJOR_RISK_KEYWORDS:
            if kw in content:
                risk = f"🔴 潛在風險：新聞提及{kw}，請注意核實"
                break
        if risk == "近期未見明顯利空":
            for kw in MINOR_RISK_KEYWORDS:
                if kw in content:
                    risk = f"🟡 輕微風險：新聞提及{kw}"
                    break
        results.append({"risk_warning": risk})
    return results

def _call_gemini_with_backoff(client, news_batch, system_prompt, is_risk=False):
    prompt_parts = ["請按編號順序分析以下內容，嚴格按順序返回JSON數組：\n"]
    for idx, news in enumerate(news_batch, 1):
        stock_name = news.get("target_name", news.get("stock_name", "未知股票"))
        stock_code = news.get("target_code", news.get("stock_code", "00000"))
        pub_time = news['pub_time'].strftime('%Y-%m-%d %H:%M') if hasattr(news['pub_time'], 'strftime') else str(news['pub_time'])
        negative_tip = "\n⚠️ 注意：該新聞包含負面關鍵詞，請仔細判斷是否為「扭虧為盈」等邊界利好。" if news.get("negative_hint") else ""
        prompt_parts.append(f"""
=== 編號{idx} ===
股票：{stock_name} ({stock_code})
來源：{news['source']}
時間：{pub_time}
標題：{news['title']}
摘要：{news['summary'] if news['summary'] else '無摘要'}
{negative_tip}
""")
    prompt = "\n".join(prompt_parts)

    backoff_schedule = [10, 20, 40, 60]
    for attempt, wait_base in enumerate(backoff_schedule):
        try:
            # 修復：timeout放喺request_options入面，唔好放喺config
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0,
                    response_mime_type="application/json"
                ),
                request_options={"timeout": 60}
            )
            result = _extract_json(resp.text)
            if result and isinstance(result, list) and len(result) == len(news_batch):
                return result
            else:
                raise ValueError(f"返回長度不符（返回{len(result) if result else 0}，期望{len(news_batch)}）")
        except Exception as e:
            err_msg = str(e).lower()
            is_need_backoff = any(k in err_msg for k in ["429", "quota", "rate limit", "too many requests", "resource exhausted", "timeout", "timed out", "validation"])
            wait_time = wait_base + random.randint(-3, 7)
            wait_time = max(wait_time, 8)
            if attempt < len(backoff_schedule) - 1:
                print(f"[調用異常] 第{attempt+1}次重試，等待{wait_time}秒: {str(e)[:80]}")
                time.sleep(wait_time)
            else:
                print(f"[重試用盡] AI調用失敗: {str(e)[:100]}")
                if is_risk:
                    print("⚠️  啟用本地規則兜底生成風險提示")
                    return _local_risk_fallback(news_batch)
                else:
                    return [{"is_major_bullish": False, "score": 0} for _ in news_batch]

def analyze_news_batch(news_list, all_news, api_key, threshold=85):
    client = genai.Client(api_key=api_key)
    valid_bullish = []
    total = len(news_list)
    batch_size = 30

    # 利好分析
    for batch_idx in range(0, total, batch_size):
        batch = news_list[batch_idx:batch_idx+batch_size]
        batch_start = batch_idx + 1
        batch_end = min(batch_idx + batch_size, total)
        print(f"AI利好分析進度: [{batch_start}-{batch_end}/{total}] ...")

        batch_results = _call_gemini_with_backoff(client, batch, SYSTEM_PROMPT, is_risk=False)
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
            result["pub_time"] = news["pub_time"].strftime("%Y-%m-%d %H:%M") if hasattr(news['pub_time'], 'strftime') else str(news['pub_time'])

            if result["is_major_bullish"] and result["score"] >= threshold and result["confidence"] >= 70:
                valid_bullish.append(result)
                print(f"✅ 發現重大利好: {result['target_name']} {result['score']}分 {result['category']} | 緊急度:{result['urgency']}")
        
        time.sleep(random.randint(4, 8))

    # 同股票去重
    bullish_dict = {}
    for item in valid_bullish:
        code = item["target_code"]
        if code not in bullish_dict or item["score"] > bullish_dict[code]["score"]:
            bullish_dict[code] = item
    valid_bullish = list(bullish_dict.values())
    print(f"✅ 去重後有效利好: {len(valid_bullish)} 隻股票")

    # 風險分析
    if valid_bullish:
        print("="*50)
        print(f"開始對{len(valid_bullish)}隻利好股票做批量風險分析...")
        print("="*50)
        risk_input = []
        for bull in valid_bullish:
            code = bull["target_code"]
            related_news = [n for n in all_news if n.get("stock_code") == code]
            if related_news:
                related_news.sort(key=lambda x: x["pub_time"], reverse=True)
                risk_input.append(related_news[0])
            else:
                risk_input.append({
                    "stock_name": bull["target_name"],
                    "stock_code": code,
                    "source": "系統",
                    "pub_time": bull["pub_time"],
                    "title": "近期無相關新聞",
                    "summary": ""
                })

        risk_batch_size = 25
        all_risk_results = []
        for risk_idx in range(0, len(risk_input), risk_batch_size):
            risk_batch = risk_input[risk_idx:risk_idx+risk_batch_size]
            batch_risk_results = _call_gemini_with_backoff(client, risk_batch, RISK_BATCH_PROMPT, is_risk=True)
            all_risk_results.extend(batch_risk_results)
            time.sleep(random.randint(3, 6))

        for i, bull in enumerate(valid_bullish):
            if i < len(all_risk_results):
                bull["risk_warning"] = all_risk_results[i].get("risk_warning", "近期未見明顯利空")
            else:
                bull["risk_warning"] = "近期未見明顯利空"
            print(f"⚠️  {bull['target_name']} 風險: {bull['risk_warning']}")

    urgency_order = {"Immediate": 0, "1-3 Days": 1, "Long Term": 2}
    valid_bullish.sort(key=lambda x: (urgency_order.get(x["urgency"], 3), -x["score"]))
    print(f"AI分析完成，符合條件重大利好: {len(valid_bullish)} 條")
    return valid_bullish
