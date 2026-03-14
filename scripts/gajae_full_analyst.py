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
# 2. 가중치 기반 분석 키워드 (v2.5)
# ─────────────────────────────────────────
# 개별 단어가 시장에 미치는 강도를 수치화
NEWS_WEIGHTS = {
    # 🔴 강한 부정 (-2.0)
    "상장폐지": -2.0, "법정관리": -2.0, "어닝쇼크": -2.0, "횡령": -1.5, "배임": -1.5,
    # 🔴 일반 부정 (-1.0)
    "적자": -1.0, "소송": -1.0, "하한가": -1.0, "급락": -1.0, "약세": -1.0, "공매도": -0.8,
    # 🟢 강한 긍정 (+1.5 ~ +2.0)
    "어닝서프라이즈": 2.0, "상한가": 1.5, "대규모 투자": 1.5, "흑자 전환": 1.5,
    # 🟢 일반 긍정 (+1.0)
    "계약 체결": 1.0, "수주": 1.0, "신제품 출시": 1.0, "MOU": 1.0, "돌파": 1.0, "강세": 1.0
}

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
    
    # 지표 수집 (최적화를 위해 통합 호출 구조로 변경 가능하지만 현재는 개별 호출 유지)
    queries = {
        "vix": "VIX:INDEXCBOE",
        "sp500": ".INX:INDEXSP",
        "usd_krw": "USD-KRW",
        "kospi": "KOSPI:KRX"
    }
    
    for key, q in queries.items():
        try:
            params = {"engine": "google_finance", "q": q, "api_key": SERP_API_KEY}
            res = requests.get(url, params=params, timeout=15).json()
            summary = res.get("summary", {})
            results[key] = {
                "price": summary.get("price", "N/A"), 
                "movement": summary.get("price_movement", {}).get("movement", "N/A")
            }
        except Exception as e: print(f"⚠️ {key} 수집 실패: {e}")
        
    return results

def fetch_serp_news(query):
    """SERP API를 통해 뉴스 검색"""
    if not SERP_API_KEY: return []
    url = "https://serpapi.com/search.json"
    params = {"engine": "google_news", "q": query, "api_key": SERP_API_KEY, "gl": "kr", "hl": "ko"}
    try:
        res = requests.get(url, params=params, timeout=15).json()
        return res.get("news_results", [])
    except: return []

# ─────────────────────────────────────────
# 4. 고급 분석 로직 (Scoring System v2.5)
# ─────────────────────────────────────────

# 가중치 설정 (Weights)
W_FG = 0.35    # Fear & Greed 가중치
W_VIX = 0.25   # VIX 가중치
W_MARKET_NEWS = 0.20  # 시장 전체 뉴스 가중치
W_STOCK_NEWS = 0.20   # 개별 종목 뉴스 가중치

# 임계값 설정 (Thresholds)
TH_TRADE_HIGH = 75
TH_TRADE_MIN = 50

def calculate_weighted_news_score(news_items):
    """뉴스 단위별 가중치 합산하여 0-100 점수 변환"""
    if not news_items: return 50.0
    
    total_score = 0
    match_count = 0
    
    for item in news_items[:10]:
        content = (item.get("title", "") + " " + item.get("snippet", "")).lower()
        item_score = 0
        for kw, weight in NEWS_WEIGHTS.items():
            if kw in content:
                item_score += weight
                match_count += 1
        total_score += item_score
        
    # 점수 정규화 (기본 50점에서 출발하여 가중치 합산만큼 변동, 0-100 클리핑)
    # 가 합산이 -5.0 이하면 0점, +5.0 이상이면 100점으로 매핑
    final_score = 50 + (total_score * 10)
    return max(0, min(100, final_score))

def calculate_market_score(fg_score, vix_val, m_news_score, s_news_score):
    """종합 점수 계산기"""
    # VIX 정규화
    try:
        vix = float(str(vix_val).replace(",", ""))
        s_vix = 100 - ((vix - 15) * (100 / 15)) if 15 < vix < 30 else (100 if vix <= 15 else 0)
    except: s_vix = 50
        
    # 종합 점수 (Weighted Sum)
    total_score = (fg_score * W_FG) + (s_vix * W_VIX) + (m_news_score * W_MARKET_NEWS) + (s_news_score * W_STOCK_NEWS)
    
    contributions = {
        "공탐": round(fg_score * W_FG, 1),
        "변동성": round(s_vix * W_VIX, 1),
        "시장뉴스": round(m_news_score * W_MARKET_NEWS, 1),
        "종목뉴스": round(s_news_score * W_STOCK_NEWS, 1)
    }
    
    return round(total_score, 1), contributions

def analyze_market_condition(total_score):
    if total_score >= TH_TRADE_HIGH:
        return "🚨 DANGER/HIGH", True, 1.2, "강력한 매수 신호 또는 공포 끝물 역발상 구간입니다."
    elif total_score >= TH_TRADE_MIN:
        return "⚠️ CAUTION", True, 0.8, "심리가 개선 중이나 여전히 경계가 필요한 구간입니다."
    else:
        return "✅ NORMAL/STABLE", False, 0.0, "신호가 부족하거나 시장이 너무 정체되어 있습니다."

import pandas as pd
import matplotlib.pyplot as plt
import io
import asyncio
from telegram import Bot

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "gajae_history.csv")

def update_history(date_str, score, vix):
    new_data = pd.DataFrame([[date_str, score, vix]], columns=["date", "total_score", "vix"])
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        if date_str not in df['date'].values:
            df = pd.concat([df, new_data], ignore_index=True)
    else: df = new_data
    df.to_csv(HISTORY_FILE, index=False)
    return df.tail(15)

def plot_market_report(df):
    plt.rc('font', family='Malgun Gothic')
    plt.rcParams['axes.unicode_minus'] = False
    fig, axes = plt.subplots(2, 1, figsize=(8, 8), sharex=True)
    
    axes[0].plot(df['date'], df['total_score'], marker='o', label='Market Score', color='#1f77b4', linewidth=2)
    axes[0].axhline(75, color='red', linestyle='--', alpha=0.4)
    axes[0].axhline(50, color='orange', linestyle='--', alpha=0.4)
    axes[0].set_title('GAJAE Intelligence - Market Score Trend')
    axes[0].grid(True, alpha=0.2)
    
    vix_p = [float(str(v).replace(",","")) if str(v)!="N/A" else 20.0 for v in df['vix']]
    axes[1].plot(df['date'], vix_p, color='#ff7f0e', marker='s', label='VIX Index')
    axes[1].grid(True, alpha=0.2)
    
    plt.xticks(rotation=45)
    fig.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    buf.seek(0); plt.close()
    return buf

# ─────────────────────────────────────────
# 5. 보고서 생성 및 전송
# ─────────────────────────────────────────

async def generate_and_send_report():
    now_str = datetime.now().strftime("%Y-%m-%d")
    print(f"🚀 가재 가중치 분석 기동 ({now_str})")
    
    # 1. 지표 수집
    score_fg, rating_fg = fetch_fear_and_greed()
    indices = fetch_market_indices()
    
    # 2. 이원화 뉴스 분석 (시장 vs 종목)
    m_news = fetch_serp_news("국내 증시 시황")
    s_news = fetch_serp_news("반도체 2차전지 실적 전망")
    
    m_news_score = calculate_weighted_news_score(m_news)
    s_news_score = calculate_weighted_news_score(s_news)
    
    # 3. 종합 점수 및 판단
    total_score, contr = calculate_market_score(score_fg, indices["vix"]["price"], m_news_score, s_news_score)
    condition, trade_allowed, risk_mult, reason = analyze_market_condition(total_score)
    
    # 4. 데이터 적재 및 시각화
    df_hist = update_history(now_str, total_score, indices["vix"]["price"])
    sorted_contr = sorted(contr.items(), key=lambda x: x[1], reverse=True)
    contr_str = ", ".join([f"{k}({v})" for k, v in sorted_contr])
    
    # 5. 브리핑 생성
    lines = [
        f"📊 <b>가재 지능형 시황 분석 (v2.5)</b>",
        f"일시: {now_str}",
        "",
        f"<b>🎯 종합 점수: {total_score}점</b>",
        f"• 판단: {condition} (배율: {risk_mult}x)",
        f"• 엔진 가중치: {contr_str}",
        "",
        "<b>📰 뉴스 심리 스코어</b>",
        f"• 시장 뉴스 점수: {m_news_score}점",
        f"• 테마/종목 점수: {s_news_score}점",
        "",
        "<b>📈 핵심 지표</b>",
        f"• VIX: {indices['vix']['price']} / F&G: {score_fg}",
        f"• 원/달러: {indices['usd_krw']['price']}",
        "",
        "<b>🧠 전술적 해석</b>",
        f"- {reason}",
        "",
        f"{'✅ 매매 진행 가능' if trade_allowed else '❌ 매매 보류 권고'}",
        "────────────────",
        "<i>Gajae Weighted Intelligence</i> 🦞"
    ]
    text = "\n".join(lines)
    
    if not TELEGRAM_TOKEN: 
        print(text); return

    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        photo = plot_market_report(df_hist)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode='HTML')
        await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=photo, caption="Market Intelligence Chart")
        print("✅ 리포트 전송 성공")
    except Exception as e: print(f"❌ 오류: {e}")

if __name__ == "__main__":
    asyncio.run(generate_and_send_report())
