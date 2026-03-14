#!/usr/bin/env python3
"""
한국증시 전망 브리핑 스크립트 (개선판)
매일 오전 8시 30분 실행
"""

import os
import requests
import json
import time
from datetime import datetime, timedelta

# 환경변수
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "HC43E8OVZWXDG3FD")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "e13423a3474d30c80747d062b26a1322")
ECOS_API_KEY = os.environ.get("ECOS_API_KEY", "CDJL3MV8FGEZU8JV0JMD")
KIWOOM_APP_KEY = os.environ.get("KIWOOM_MOCK_REST_API_APP_KEY")
KIWOOM_SECRET_KEY = os.environ.get("KIWOOM_MOCK_REST_API_SECRET_KEY")


def get_us_market():
    """미국 시장 전날 동향 (SPY, QQQ) + 유가"""
    results = {}
    
    # 주요 지수 + 유가
    symbols = ["SPY", "QQQ", "CL=F"]  # CL=F = WTI 원유 선물
    
    for symbol in symbols:
        try:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHAVANTAGE_API_KEY}"
            response = requests.get(url, timeout=10)
            data = response.json()
            quote = data.get("Global Quote", {})
            
            results[symbol] = {
                "price": quote.get("05. price", "N/A"),
                "change_percent": quote.get("10. change percent", "N/A")
            }
        except:
            results[symbol] = {"price": "N/A", "change_percent": "N/A"}
        
        time.sleep(12)  # 속도 제한 회피
    
    return results


def get_vix():
    """VIX 공포지수 (FRED API)"""
    try:
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id=VIXCLS&api_key={FRED_API_KEY}&file_type=json&limit=5&sort_order=desc"
        response = requests.get(url, timeout=10)
        data = response.json()
        obs = data.get("observations", [])
        
        if obs:
            return {
                "value": obs[0]["value"],
                "date": obs[0]["date"]
            }
    except Exception as e:
        pass
    
    return {"value": "N/A", "date": "N/A"}


def get_korea_rates():
    """한국 주요 경제지표 (ECOS API)"""
    results = {}
    
    try:
        # 주요 경제지표
        url = f"http://ecos.bok.or.kr/api/KeyStatisticList/{ECOS_API_KEY}/json/kr/1/20"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        rows = data.get("KeyStatisticList", {}).get("row", [])
        
        for row in rows:
            name = row.get("KEYSTAT_NAME", "")
            value = row.get("DATA_VALUE", "")
            unit = row.get("UNIT_NAME", "")
            
            if "원/달러" in name:
                results["usd_krw"] = {"value": value, "unit": unit}
            elif "원/엔" in name:
                results["jpy_krw"] = {"value": value, "unit": unit}
            elif "M2" in name and "광의" in name:
                results["m2"] = {"value": value, "unit": unit}
    except Exception as e:
        pass
    
    return results


def get_korea_market():
    """한국 주요 종목 + 코스피/코스닥 지수 + 외국인 수급 (키움증권 API)"""
    results = {"stocks": {}, "index": {}, "foreigner": {}}
    
    # 토큰 발급
    try:
        url = "https://mockapi.kiwoom.com/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "appkey": KIWOOM_APP_KEY,
            "secretkey": KIWOOM_SECRET_KEY
        }
        response = requests.post(url, json=data, timeout=10)
        token = response.json().get("token")
        
        if not token:
            return results
        
        # 1. 코스피/코스닥 지수 조회
        for code, name in [("0001", "코스피"), ("1001", "코스닥")]:
            try:
                url = "https://mockapi.kiwoom.com/api/dostk/stkinfo"
                headers = {
                    "Content-Type": "application/json;charset=UTF-8",
                    "Authorization": f"Bearer {token}",
                    "api-id": "ka10001"
                }
                response = requests.post(url, headers=headers, json={"stk_cd": code}, timeout=10)
                data = response.json()
                
                if data.get("return_code") == 0:
                    results["index"][name] = {
                        "price": data.get("cur_prc", "N/A"),
                        "change_rate": data.get("flu_rt", "N/A")
                    }
            except:
                pass
            time.sleep(0.2)
        
        # 2. 주요 종목 조회
        stocks = {
            "005930": "삼성전자",
            "000660": "SK하이닉스",
            "035420": "NAVER",
            "068270": "셀트리온",
            "005935": "삼성전자우"
        }
        
        for code, name in stocks.items():
            try:
                url = "https://mockapi.kiwoom.com/api/dostk/stkinfo"
                headers = {
                    "Content-Type": "application/json;charset=UTF-8",
                    "Authorization": f"Bearer {token}",
                    "api-id": "ka10001"
                }
                response = requests.post(url, headers=headers, json={"stk_cd": code}, timeout=10)
                data = response.json()
                
                if data.get("return_code") == 0:
                    results["stocks"][code] = {
                        "name": data.get("stk_nm", name),
                        "price": data.get("cur_prc", "N/A"),
                        "change_rate": data.get("flu_rt", "N/A"),
                        "foreign_ratio": data.get("for_exh_rt", "N/A")  # 외국인 비율
                    }
            except:
                pass
            time.sleep(0.2)
        
        # 3. 외국인 수급 (거래대금 기준)
        try:
            url = "https://mockapi.kiwoom.com/api/dostk/stkinfo"
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "Authorization": f"Bearer {token}",
                "api-id": "ka10001"
            }
            # 코스피 외국인 수급 (삼성전자 기준)
            response = requests.post(url, headers=headers, json={"stk_cd": "005930"}, timeout=10)
            data = response.json()
            
            if data.get("return_code") == 0:
                results["foreigner"]["삼성전자_외국인비율"] = data.get("for_exh_rt", "N/A")
        except:
            pass
            
    except:
        pass
    
    return results


def analyze_market_sentiment(vix, us_market, korea_data):
    """시장 심리 분석"""
    sentiments = []
    
    # VIX 분석
    if vix["value"] != "N/A":
        vix_val = float(vix["value"])
        if vix_val > 30:
            sentiments.append("🔴 VIX 30 초과: 극도의 공포 상태")
        elif vix_val > 20:
            sentiments.append("🟡 VIX 20-30: 공포 상태")
        elif vix_val > 15:
            sentiments.append("🟢 VIX 15-20: 보통 상태")
        else:
            sentiments.append("🟢 VIX 15 미만: 낙관 상태")
    
    # 미국 시장 분석
    spy_change = us_market.get("SPY", {}).get("change_percent", "N/A")
    if spy_change != "N/A":
        change = float(spy_change.replace("%", ""))
        if change < -2:
            sentiments.append("📉 S&P 500 급락: 한국 시장 약세 예상")
        elif change < -1:
            sentiments.append("📉 S&P 500 하락: 한국 시장 혼조 예상")
        elif change > 1:
            sentiments.append("📈 S&P 500 상승: 한국 시장 강세 예상")
    
    # 유가 분석
    oil_change = us_market.get("CL=F", {}).get("change_percent", "N/A")
    if oil_change != "N/A":
        change = float(oil_change.replace("%", ""))
        if change > 3:
            sentiments.append(f"🛢️ 유가 급등 (+{change:.1f}%): 인플레이션 우려 ↑")
        elif change > 1:
            sentiments.append(f"🛢️ 유가 상승 (+{change:.1f}%): 에너지/방산 관련주 주목")
        elif change < -2:
            sentiments.append(f"🛢️ 유가 하락 ({change:.1f}%): 에너지주 압박")
    
    # 외국인 수급 분석
    foreign_ratio = korea_data.get("foreigner", {}).get("삼성전자_외국인비율", "N/A")
    if foreign_ratio != "N/A":
        try:
            ratio = float(foreign_ratio)
            if ratio > 51:
                sentiments.append(f"🟢 외국인 비율 {ratio}%: 수급 양호")
            elif ratio < 49:
                sentiments.append(f"🔴 외국인 비율 {ratio}%: 수급 악화")
        except:
            pass
    
    return sentiments


def generate_briefing():
    """한국증시 전망 브리핑 생성"""
    now = datetime.now()
    
    print("데이터 수집 중...")
    
    # 데이터 수집
    us_market = get_us_market()
    print("✅ 미국 시장 + 유가 데이터")
    
    vix = get_vix()
    print(f"✅ VIX: {vix['value']}")
    
    korea_rates = get_korea_rates()
    print("✅ 한국 경제지표")
    
    korea_data = get_korea_market()
    print(f"✅ 한국 지수/종목: {len(korea_data.get('index', {}))}개 지수, {len(korea_data.get('stocks', {}))}개 종목")
    
    # 심리 분석
    sentiments = analyze_market_sentiment(vix, us_market, korea_data)
    
    # 브리핑 생성
    lines = [
        f"## 📊 한국증시 전망 브리핑 ({now.strftime('%Y-%m-%d %H:%M')})",
        "",
        "### 🇺🇸 전일 미국 시장 동향",
        "",
        "| 지수 | 종가 | 등락률 |",
        "|------|------|--------|",
    ]
    
    spy = us_market.get("SPY", {})
    qqq = us_market.get("QQQ", {})
    oil = us_market.get("CL=F", {})
    
    spy_change = spy.get("change_percent", "N/A")
    spy_emoji = "📉" if spy_change != "N/A" and float(spy_change.replace('%', '')) < 0 else "📈"
    
    qqq_change = qqq.get("change_percent", "N/A")
    qqq_emoji = "📉" if qqq_change != "N/A" and float(qqq_change.replace('%', '')) < 0 else "📈"
    
    oil_change = oil.get("change_percent", "N/A")
    oil_emoji = "📈" if oil_change != "N/A" and float(oil_change.replace('%', '')) > 0 else "📉"
    
    lines.append(f"| {spy_emoji} S&P 500 | ${spy.get('price', 'N/A')} | {spy_change} |")
    lines.append(f"| {qqq_emoji} 나스닥 100 | ${qqq.get('price', 'N/A')} | {qqq_change} |")
    
    # 유가 추가
    lines.extend([
        "",
        "### 🛢️ 유가 동향 (WTI)",
        "",
        "| 지표 | 가격 | 등락률 |",
        "|------|------|--------|",
    ])
    lines.append(f"| {oil_emoji} WTI 원유 | ${oil.get('price', 'N/A')}/배럴 | {oil_change} |")
    
    # VIX
    lines.extend([
        "",
        "### 📉 VIX 공포지수",
        "",
        f"| VIX | 값 | 기준일 |",
        f"|-----|-----|--------|",
        f"| {'🔴' if vix['value'] != 'N/A' and float(vix['value']) > 20 else '🟢'} VIX | {vix['value']} | {vix['date']} |",
    ])
    
    # 환율
    lines.extend([
        "",
        "### 💱 환율 동향",
        "",
        "| 통화 | 환율 |",
        "|------|------|",
    ])
    
    usd_krw = korea_rates.get("usd_krw", {})
    jpy_krw = korea_rates.get("jpy_krw", {})
    
    lines.append(f"| 원/달러 | {usd_krw.get('value', 'N/A')} {usd_krw.get('unit', '')} |")
    lines.append(f"| 원/100엔 | {jpy_krw.get('value', 'N/A')} {jpy_krw.get('unit', '')} |")
    
    # 코스피/코스닥 지수
    korea_index = korea_data.get("index", {})
    if korea_index:
        lines.extend([
            "",
            "### 📊 전일 한국 지수",
            "",
            "| 지수 | 종가 | 등락률 |",
            "|------|------|--------|",
        ])
        
        for name, data in korea_index.items():
            change = data.get("change_rate", "N/A")
            try:
                emoji = "📉" if change != "N/A" and change and float(change) < 0 else "📈"
            except:
                emoji = "📊"
            lines.append(f"| {emoji} {name} | {data.get('price', 'N/A')} | {change}% |")
    
    # 한국 주요 종목
    korea_stocks = korea_data.get("stocks", {})
    if korea_stocks:
        lines.extend([
            "",
            "### 🇰🇷 한국 주요 종목 (전일 종가)",
            "",
            "| 종목 | 종가 | 등락률 | 외국인비율 |",
            "|------|------|--------|------------|",
        ])
        
        for code, stock in korea_stocks.items():
            change = stock.get("change_rate", "N/A")
            try:
                emoji = "📉" if change != "N/A" and change and float(change) < 0 else "📈"
            except:
                emoji = "📊"
            foreign = stock.get("foreign_ratio", "N/A")
            lines.append(f"| {emoji} {stock.get('name', code)} | {stock.get('price', 'N/A')}원 | {change}% | {foreign}% |")
    
    # 시장 심리 분석
    if sentiments:
        lines.extend([
            "",
            "### 🎯 시장 심리 분석",
            "",
        ])
        
        for s in sentiments:
            lines.append(f"- {s}")
    
    # 오늘 전망
    lines.extend([
        "",
        "### 📈 오늘 한국 시장 전망",
        "",
    ])
    
    # 미국 시장 기반 예상
    if spy_change != "N/A":
        change = float(spy_change.replace("%", ""))
        if change < -1:
            lines.append("- ⚠️ 미국 시장 하락 → 한국 시장 **약세** 예상")
        elif change < 0:
            lines.append("- 📊 미국 시장 소폭 하락 → 한국 시장 **혼조** 예상")
        else:
            lines.append("- ✅ 미국 시장 상승 → 한국 시장 **강세** 예상")
    
    # 유가 기반 예상
    if oil_change != "N/A":
        oil_val = float(oil_change.replace("%", ""))
        if oil_val > 2:
            lines.append(f"- 🛢️ 유가 급등({oil_val:+.1f}%) → **에너지/방산/조선** 관련주 강세 예상")
        elif oil_val > 0:
            lines.append(f"- 🛢️ 유가 상승({oil_val:+.1f}%) → 에너지 섹터 주목")
    
    # 이란 전쟁 특수 상황
    lines.append("- 🎯 이란 전쟁 리스크 지속 → **방산/에너지/조선** 관련주 모니터링")
    
    # 주의사항
    lines.extend([
        "",
        "---",
        "*본 브리핑은 참고용이며, 투자 결정은 본인의 판단에 따라 하시기 바랍니다.*"
    ])
    
    return "\n".join(lines)


if __name__ == "__main__":
    briefing = generate_briefing()
    print("\n" + "=" * 60)
    print(briefing)
    print("=" * 60)
    
    # 결과 저장
    output_path = "/root/.openclaw/workspace/data/korea_market_briefing.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(briefing)
    
    print(f"\n✅ 브리핑 저장: {output_path}")