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
# 4. 고급 분석 로직 (Scoring System)
# ─────────────────────────────────────────

# 가중치 설정 (Weights)
W_FG = 0.4    # Fear & Greed 가중치
W_VIX = 0.3   # VIX 가중치
W_NEWS = 0.3  # 뉴스 심리 가중치

# 임계값 설정 (Thresholds)
TH_TRADE_HIGH = 75  # 적극 매매 구간
TH_TRADE_MIN = 50   # 보수 매매 구간

def calculate_market_score(fg_score, vix_val, pos_news, neg_news):
    """지표별 점수 산출 및 통합 점수 계산"""
    
    # 1. F&G 점수 (0-100 그대로 활용)
    s_fg = fg_score
    
    # 2. VIX 점수 (역산: 15이하=100, 30이상=0)
    try:
        vix = float(str(vix_val).replace(",", ""))
        if vix <= 15: s_vix = 100
        elif vix >= 30: s_vix = 0
        else: s_vix = 100 - ((vix - 15) * (100 / 15))
    except:
        s_vix = 50
        
    # 3. 뉴스 점수 (0-100)
    total_news = pos_news + neg_news
    if total_news == 0:
        s_news = 50
    else:
        s_news = (pos_news / total_news) * 100
        
    # 종합 점수 계산
    total_score = (s_fg * W_FG) + (s_vix * W_VIX) + (s_news * W_NEWS)
    
    # 기여도 분석
    contributions = {
        "공탐지수": round(s_fg * W_FG, 1),
        "VIX": round(s_vix * W_VIX, 1),
        "뉴스심리": round(s_news * W_NEWS, 1)
    }
    
    return round(total_score, 1), contributions

def analyze_market_condition(total_score):
    """종합 점수 기반 매매 판단"""
    if total_score >= TH_TRADE_HIGH:
        return "🚨 DANGER/HIGH", True, 1.2, "시장 에너지가 매우 강하거나 역발상 기회가 큽니다. 적극적 매매를 검토합니다."
    elif total_score >= TH_TRADE_MIN:
        return "⚠️ CAUTION", True, 0.8, "시장이 완만한 회복세 또는 경계 구간에 있습니다. 보수적 매매를 검토합니다."
    else:
        return "✅ NORMAL/STABLE", False, 0.0, "지표가 기준 미달이거나 너무 안정적입니다. 관망을 유지합니다."

def analyze_news_sentiment(news_items):
    """알고파 뉴스 심리 분석"""
    pos_total, neg_total = 0, 0
    
    for item in news_items[:10]:
        content = (item.get("title", "") + " " + item.get("snippet", "")).lower()
        if any(kw in content for kw in POSITIVE_KEYWORDS): pos_total += 1
        if any(kw in content for kw in NEGATIVE_KEYWORDS): neg_total += 1
            
    return pos_total, neg_total

# ─────────────────────────────────────────
# 5. 보고서 생성 및 전송
# ─────────────────────────────────────────

def generate_briefing():
    now_str = datetime.now().strftime("%Y-%m-%d")
    
    # 데이터 수집
    score_fg, rating_fg = fetch_fear_and_greed()
    indices = fetch_market_indices()
    news = fetch_serp_news()
    
    # 분석
    pos_news, neg_news = analyze_news_sentiment(news)
    total_score, contr = calculate_market_score(score_fg, indices["vix"]["price"], pos_news, neg_news)
    condition, trade_allowed, risk_mult, reason = analyze_market_condition(total_score)
    
    # 기여도 상위 정렬
    sorted_contr = sorted(contr.items(), key=lambda x: x[1], reverse=True)
    contr_str = ", ".join([f"{k}({v}점)" for k, v in sorted_contr])
    
    # 브리핑 조립
    lines = [
        f"📊 <b>오늘의 시황 종합 분석</b> · {now_str}",
        "",
        f"<b>🎯 종합 시장 점수: {total_score} / 100</b>",
        f"• 상태: {condition} (리스크 배율: {risk_mult}x)",
        f"• 기여도: {contr_str}",
        "",
        "<b>📈 세부 지표</b>",
        f"• 공탐지수: {score_fg} ({rating_fg})",
        f"• VIX: {indices['vix']['price']} ({indices['vix']['movement']})",
        f"• 뉴스: 긍정 {pos_news}건, 부정 {neg_news}건",
        f"• 원/달러: {indices['usd_krw']['price']}",
        "",
        "<b>🧠 전략적 해석</b>",
        f"- {reason}",
        "",
        f"{'✅ 실전 매매: 진행' if trade_allowed else '❌ 실전 매매: 보류'}",
        "",
        "────────────────",
        "<i>Gajae Advanced Logic System</i> 🦞"
    ]
    
    return "\n".join(lines)

def send_to_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 텔레그램 설정이 없습니다.")
        return False
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
    print("🚀 가재 고급 분석 시스템 기동...")
    briefing = generate_briefing()
    print("\n[생성된 브리핑]")
    print(briefing)
    
    # 실제 전송 여부 확인 (환경변수나 설정을 통해 제어 가능)
    # 여기서는 시연을 위해 전송 시도
    print("\n텔레그램 보고 전송 중...")
    if send_to_telegram(briefing):
        print("✅ 보고 완료")
    else:
        print("❌ 전송 실패")
