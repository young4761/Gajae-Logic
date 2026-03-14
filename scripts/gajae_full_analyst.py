#!/usr/bin/env python3
"""
gajae_full_analyst.py
n8n 없이 가재(Gajae)가 직접 시장 지표와 뉴스를 분석하여 보고하는 통합 스크립트
"""

import os
import requests
import json
import time
from datetime import datetime

# ─────────────────────────────────────────
# 1. 환경 설정 및 자격 증명
# ─────────────────────────────────────────
# 사용자로부터 입수된 SERP_API_KEY (remote backup에서 추출)
SERP_API_KEY = os.environ.get("SERP_API_KEY", "87f70223f137ef1b37d78ee8868be18614480d5af04e84cf4788c5848c6335c2")
TELEGRAM_TOKEN = "7970537683:AAH0QmWImg0LKzEjHY7fn5kWwcpgIzVmoWY"
TELEGRAM_CHAT_ID = "1290448372"

# ─────────────────────────────────────────
# 2. 분석 키워드 (뉴스 심리 분석용)
# ─────────────────────────────────────────
POSITIVE_KEYWORDS = ["계약 체결", "수주", "흑자 전환", "대규모 투자", "신제품 출시", "MOU", "상한가", "돌파", "강세"]
NEGATIVE_KEYWORDS = ["적자", "소송", "횡령", "배임", "상장폐지", "대주주 매도", "공매도", "하한가", "급락", "약세"]

# ─────────────────────────────────────────
# 3. 데이터 수집 함수
# ─────────────────────────────────────────

def fetch_fear_and_greed():
    """Fear & Greed Index 수집"""
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.cnn.com/markets/fear-and-greed"
    }
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        data = res.json()
        score = round(data['fear_and_greed']['score'])
        rating = data['fear_and_greed']['rating']
        return score, rating
    except Exception as e:
        print(f"⚠️ F&G 수집 실패: {e}")
        return 50, "Neutral"

def fetch_market_indices():
    """SerpApi를 사용하여 VIX, S&P500 선물, 환율, 코스피 수집"""
    results = {
        "vix": {"price": "N/A", "movement": "N/A"},
        "sp500": {"price": "N/A", "movement": "N/A"},
        "usd_krw": {"price": "N/A", "movement": "N/A"},
        "kospi": {"price": "N/A", "movement": "N/A"}
    }
    
    if not SERP_API_KEY:
        return results

    url = "https://serpapi.com/search.json"
    
    # 1. VIX (Google Finance)
    try:
        params = {"engine": "google_finance", "q": "VIX:INDEXCBOE", "api_key": SERP_API_KEY}
        res = requests.get(url, params=params, timeout=15).json()
        summary = res.get("summary", {})
        results["vix"] = {
            "price": summary.get("price", "N/A"), 
            "movement": summary.get("price_movement", {}).get("movement", "N/A")
        }
    except Exception as e: print(f"⚠️ VIX 수집 실패: {e}")

    # 2. S&P 500 (Google Finance)
    try:
        params = {"engine": "google_finance", "q": ".INX:INDEXSP", "api_key": SERP_API_KEY}
        res = requests.get(url, params=params, timeout=15).json()
        summary = res.get("summary", {})
        results["sp500"] = {
            "price": summary.get("price", "N/A"), 
            "movement": summary.get("price_movement", {}).get("movement", "N/A")
        }
    except Exception as e: print(f"⚠️ SP500 수집 실패: {e}")

    # 3. USD/KRW (Google Finance)
    try:
        params = {"engine": "google_finance", "q": "USD-KRW", "api_key": SERP_API_KEY}
        res = requests.get(url, params=params, timeout=15).json()
        summary = res.get("summary", {})
        results["usd_krw"] = {
            "price": summary.get("price", "N/A"), 
            "movement": summary.get("price_movement", {}).get("movement", "N/A")
        }
    except Exception as e: print(f"⚠️ USD/KRW 수집 실패: {e}")

    # 4. KOSPI (Google Finance)
    try:
        params = {"engine": "google_finance", "q": "KOSPI:KRX", "api_key": SERP_API_KEY}
        res = requests.get(url, params=params, timeout=15).json()
        summary = res.get("summary", {})
        results["kospi"] = {
            "price": summary.get("price", "N/A"), 
            "movement": summary.get("price_movement", {}).get("movement", "N/A")
        }
    except Exception as e: print(f"⚠️ KOSPI 수집 실패: {e}")
        
    return results

def fetch_serp_news(query="한국 증시"):
    """SERP API를 통해 뉴스 검색"""
    if not SERP_API_KEY: return []
    url = "https://serpapi.com/search.json"
    params = {"engine": "google_news", "q": query, "api_key": SERP_API_KEY, "gl": "kr", "hl": "ko"}
    try:
        res = requests.get(url, params=params, timeout=15).json()
        return res.get("news_results", [])
    except: return []

# ─────────────────────────────────────────
# 4. 분석 로직
# ─────────────────────────────────────────

def analyze_market_condition(score, vix_val):
    """n8n 정량적 수식 적용"""
    try:
        vix_str = str(vix_val).replace(",", "")
        vix = float(vix_str)
    except:
        vix = 20.0

    if score < 25 or score > 74 or vix >= 30:
        return "DANGER", True, f"🚨 [변동성 확대/역발상 기회] 탐욕지수가 극단치({score})이거나 VIX({vix})가 높아 매매를 고려합니다."
    elif score < 50 or vix >= 20:
        return "CAUTION", False, f"⚠️ [시장 관망] 탐욕지수({score}) 또는 VIX({vix})가 경계 수준에 있어 매매를 보류합니다."
    else:
        return "NORMAL", False, f"✅ [안정적 시장] 시장 지표가 안정적(F&G: {score})이므로 오늘 매매는 쉽니다."

def analyze_news_sentiment(news_items):
    """알고파 뉴스 심리 분석"""
    pos_total, neg_total = 0, 0
    top_news = []
    
    for item in news_items[:10]:
        content = (item.get("title", "") + " " + item.get("snippet", "")).lower()
        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in content)
        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in content)
        
        sentiment = "⚪"
        if pos_count >= 3: sentiment = "🟢"; pos_total += 1
        elif neg_count >= 2: sentiment = "🔴"; neg_total += 1
        
        if sentiment != "⚪":
            top_news.append(f"{sentiment} {item.get('title')}")
            
    return pos_total, neg_total, top_news

# ─────────────────────────────────────────
# 5. 보고서 생성 및 전송
# ─────────────────────────────────────────

def generate_briefing():
    now_str = datetime.now().strftime("%Y-%m-%d")
    
    # 데이터 수집
    score, rating = fetch_fear_and_greed()
    indices = fetch_market_indices()
    news = fetch_serp_news()
    
    # 분석
    condition, trade_allowed, reason = analyze_market_condition(score, indices["vix"]["price"])
    pos_news, neg_news, important_headlines = analyze_news_sentiment(news)
    
    # 브리핑 조립
    lines = [
        f"📊 <b>오늘의 시황 브리핑</b> · {now_str}",
        "",
        "<b>📈 시장 지표</b>",
        f"• 공탐지수: {score} ({rating})",
        f"• VIX: {indices['vix']['price']} ({indices['vix']['movement']})",
        f"• S&P500: {indices['sp500']['price']} ({indices['sp500']['movement']})",
        f"• 원/달러: {indices['usd_krw']['price']} ({indices['usd_krw']['movement']})",
        f"• 코스피: {indices['kospi']['price']} ({indices['kospi']['movement']})",
        "",
        "<b>🧠 시황 해석</b>",
        f"- 현재 시장은 {condition} 상태입니다.",
        f"- {reason}",
        f"- 뉴스 감지: 긍정 {pos_news}건, 부정 {neg_news}건이 포착되었습니다." if (pos_news+neg_news)>0 else "- 특이한 뉴스 흐름은 발견되지 않았습니다.",
        "",
        "<b>⚡ 매매 판단</b>",
        f"{condition} — {'실전 매매를 검토합니다.' if trade_allowed else '보수적 접근이 필요합니다.'}",
        "",
        f"{'✅ 오늘 매매: 진행' if trade_allowed else '❌ 오늘 매매: 보류'}",
        "",
        "────────────────",
        "<i>가재(Gajae)의 독립 분석 보고입니다.</i> 🦞"
    ]
    
    return "\n".join(lines)

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        return res.ok
    except Exception as e:
        print(f"⚠️ 텔레그램 전송 오류: {e}")
        return False

if __name__ == "__main__":
    print("🚀 가재 통합 분석 시스템 기동...")
    briefing = generate_briefing()
    print("\n[생성된 브리핑]")
    print(briefing)
    print("\n텔레그램 전송 중...")
    if send_to_telegram(briefing):
        print("✅ 텔레그램 보고 완료")
    else:
        print("❌ 텔레그램 전송 실패")
