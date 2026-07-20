from google import genai
from google.genai import types
import json
import time
import re

# 精簡版System Prompt（500字，核心規則無遺漏）
SYSTEM_PROMPT = """
你是港股事件驅動對沖基金經理，專門從新聞中篩選未來48小時-2周可能引發股價大幅上漲的重大催化劑。

【核心判斷】
只有事件滿足以下至少2點才判定為重大利好：
1. 事件已正式落實，非傳聞/計劃/猜測
2. 可實質改變公司未來1-3年盈利能力
3. 可引發公司估值重估
4. 可吸引持續資金流入
5. 非一次性收益、非市場已廣泛預期

【重大催化劑包括但不限於】
超預期業績/盈喜、巨額合同、回購註銷、私有化、AI/科技合作、政策受益、新產品/技術突破、海外拓展、監管批准、超預期派息、納入指數(恆指/港股通/MSCI)、分拆上市、大額融資(利好型)
*請按公司市值規模判斷事件重要性，小公司小訂單也算利好，大公司小訂單不算。

【評分規則】
95-100：極重大催化劑，可能引發數周估值重估，單日漲幅10%+
85-94：明確重大利好，可能推動股價持續上漲
<85：普通利好/中性/利空，直接忽略

【置信度規則】
95：港交所/公司官方公告
90：彭博/路透/信報等主流權威媒體報道
60：自媒體/市場消息
30：傳聞/猜測/未經證實

【緊急度規則】
Immediate：消息剛出，股價即日會有強烈反應（如FDA批准、突發大訂單）
1-3 Days：中线利好，1-3天內逐步反應（如業績、合作）
Long Term：長期利好，短期股價反應不大

【注意事項】
1. 信息不足、無法驗證真實性的消息，一律判定為非利好，不要猜測
2. 沒有股價數據時，price_in一律填"Unknown"，不要瞎猜是否已經炒高
3. 嚴格按照JSON格式輸出，不要任何額外解釋
4. 我會一次給你10條新聞，按編號順序返回對應的JSON數組

【輸出格式】
返回JSON數組，每個元素對應一條新聞，字段如下：
{
  "is_major_bullish": true/false,
  "score": 0-100,
  "category": "分類：超預期業績/重大合同/回購註銷/私有化/AI合作/政策受惠/新產品突破/技術突破/海外拓展/監管批准/超預期派息/納入指數/分拆上市/大額融資/其他",
  "confidence": 0-100,
  "reason": "80字以內中文點評，說明利好邏輯",
  "risk": "低/中/高",
  "price_in": "Unknown",
  "urgency": "Immediate/1-3 Days/Long Term"
}
"""

# 非貪婪正則，支持提取單個對象/JSON數組
JSON_ARRAY_PATTERN = re.compile(r'\[.*?\]', re.DOTALL)
JSON_OBJECT_PATTERN = re.compile(r'\{.*?\}', re.DOTALL)

def _extract_json(text):
    """智能提取JSON，優先提取數組，其次提取對象，處理Markdown包裹"""
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    # 先嘗試提取數組（批量調用）
    arr_match = JSON_ARRAY_PATTERN.search(text)
    if arr_match:
        try:
            return json.loads(arr_match.group())
        except:
            pass
    # 再嘗試提取單個對象
    obj_match = JSON_OBJECT_PATTERN.search(text)
    if obj_match:
        try:
            return [json.loads(obj_match.group())]
        except:
            pass
    return None

def _call_gemini_with_backoff(client, news_batch):
    """指數退避重試調用Gemini，最多重試4次"""
    # 構建批量prompt，給每條新聞編號
    prompt_parts = ["請按編號順序分析以下新聞，返回JSON數組：\n"]
    for idx, news in enumerate(news_batch, 1):
        negative_tip = "\n⚠️ 注意：該新聞包含負面關鍵詞，請仔細判斷是否為「扭虧為盈」等邊界利好，不要單純因為有負面詞就判斷為非利好。" if news.get("negative_hint") else ""
        prompt_parts.append(f"""
=== 新聞{idx} ===
股票：{news['target_name']} ({news['target_code']})
來源：{news['source']}
時間：{news['pub_time'].strftime('%Y-%m-%d %H:%M')}
標題：{news['title']}
摘要：{news['summary'] if news['summary'] else '無摘要'}
{negative_tip}
""")
    prompt = "\n".join(prompt_parts)

    # 指數退避重試
    backoff_times = [1, 2, 4, 8]
    for wait_time in backoff_times:
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0, # 完全確定性輸出，零幻覺
                    top_p=1.0,
                    response_mime_type="application/json" # 強制JSON輸出，減少解析錯誤
                )
            )
            result = _extract_json(resp.text)
            if result and isinstance(result, list) and len(result) == len(news_batch):
                return result
        except Exception as e:
            print(f"[重試] 調用失敗，等待{wait_time}秒後重試: {str(e)}")
            time.sleep(wait_time)
    # 重試全部失敗，返回全部非利好
    print("[錯誤] 批量調用重試全部失敗，該批新聞標記為非利好")
    return [{"is_major_bullish": False, "score": 0} for _ in news_batch]

def analyze_news_batch(news_list, api_key, threshold=85):
    """
    批量分析新聞，每10條打包一次調用
    """
    client = genai.Client(api_key=api_key)
    valid_bullish = []
    total = len(news_list)
    batch_size = 10 # 每10條一次調用，速度/準確率平衡

    # 分批處理
    for batch_idx in range(0, total, batch_size):
        batch = news_list[batch_idx:batch_idx+batch_size]
        batch_start = batch_idx + 1
        batch_end = min(batch_idx + batch_size, total)
        print(f"AI批量分析進度: [{batch_start}-{batch_end}/{total}] ...")

        # 批量調用
        batch_results = _call_gemini_with_backoff(client, batch)

        # 處理結果，綁定新聞元數據
        for news, result in zip(batch, batch_results):
            # 字段校驗，補全默認值
            result.setdefault("is_major_bullish", False)
            result.setdefault("score", 0)
            result.setdefault("category", "其他")
            result.setdefault("confidence", 0)
            result.setdefault("reason", "")
            result.setdefault("risk", "高")
            result.setdefault("price_in", "Unknown")
            result.setdefault("urgency", "Long Term")
            # 綁定新聞信息
            result["title"] = news["title"]
            result["link"] = news["link"]
            result["source"] = news["source"]
            result["target_code"] = news["target_code"]
            result["target_name"] = news["target_name"]
            result["pub_time"] = news["pub_time"].strftime("%Y-%m-%d %H:%M")

            # 過濾規則
            if (result["is_major_bullish"]
                and result["score"] >= threshold
                and result["confidence"] >= 70
                # 後續接股價API後可打開，現在price_in都是Unknown暫時不過濾
                # and result["price_in"] != "High"
                ):
                valid_bullish.append(result)
                print(f"✅ 發現重大利好: {result['target_name']} {result['score']}分 {result['category']} | 緊急度:{result['urgency']}")

        # 批量之間稍作休息，避免限流
        time.sleep(1)

    # 按緊急度+分數排序，最急最高分分的排最前面
    urgency_order = {"Immediate": 0, "1-3 Days": 1, "Long Term": 2}
    valid_bullish.sort(key=lambda x: (urgency_order.get(x["urgency"], 3), -x["score"]))
    print(f"AI分析完成，符合條件重大利好: {len(valid_bullish)} 條")
    return valid_bullish
