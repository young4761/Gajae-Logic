# GAJAE Core Trading Formulas & Logic

This document consolidates all the quantitative analysis logic and market judgment formulas developed for the "Gajae" AI assistant.

## 1. Quantitative Market Condition Formulas

The primary logic used to determine whether to execute trades based on global market indicators.

| Status | Formula (Logic) | Action | Reasoning Template |
| :--- | :--- | :--- | :--- |
| **🚨 DANGER** | `F&G < 25` OR `F&G > 74` OR `VIX >= 30` | **✅ TRADE** | `🚨 [Volatility/Contrarian] F&G at extreme (${score}) or VIX high (${vix}).` |
| **⚠️ CAUTION** | `F&G < 50` OR `VIX >= 20` | **❌ WAIT** | `⚠️ [Wait] F&G (${score}) or VIX (${vix}) at caution levels.` |
| **✅ NORMAL** | All other cases | **❌ WAIT** | `✅ [Stable] Market indices are normal (F&G: ${score}).` |

---

## 2. News Sentiment Analysis Logic

Logic used for analyzing headlines and determining market psychological state.

### Keywords
- **Positive**: `계약 체결`, `수주`, `흑자 전환`, `대규모 투자`, `신제품 출시`, `MOU`, `상한가`, `돌파`, `강세`
- **Negative**: `적자`, `소송`, `횡령`, `배임`, `상장폐지`, `대주주 매도`, `공매도`, `하한가`, `급락`, `약세`

### Thresholds
- **🟢 Positive Sentiment**: `pos_count >= 3`
- **🔴 Negative Sentiment**: `neg_count >= 2`

---

## 3. Market Sentiment Indicators (VIX & Oil)

| Indicator | Threshold | Sentiment |
| :--- | :--- | :--- |
| **VIX** | `> 30` | 🔴 Extreme Fear (극도의 공포) |
| **VIX** | `20 - 30` | 🟡 Fear (공포) |
| **VIX** | `< 15` | 🟢 Optimism (낙관) |
| **S&P 500** | `< -2%` | 📉 High probability of Korean market drop |
| **Oil (WTI)** | `> +3%` | 🛢️ Inflation concerns / Defense & Energy focus |
| **Foreign Ratio**| `> 51%` | 🟢 Good liquidity |
| **Foreign Ratio**| `< 49%` | 🔴 Liquidity withdrawal |

---

## 4. Trading Implementation Strategy

### Automated Workflow (Gajae-System)
1. **Collector**: Python scripts collect data (F&G, VIX, KOSPI, USD/KRW).
2. **Analyzer**: Applies the formulas above to set `CONDITION` and `TRADE_ALLOWED`.
3. **Execution**: If `TRADE_ALLOWED` is TRUE, send commands to the execution layer (`chapter_7`).

### Report Structure
```text
📊 오늘의 시황 브리핑 · {yyyy-MM-dd}

📈 시장 지표
• 공탐지수: {score} ({rating})
• VIX: {vix}
• S&P500 선물: {sp500}
• 원/달러: {usd_krw}
• 코스피: {kospi}

🧠 시황 해석
(Correlation-based analysis, e.g., "Rising USD/KRW is pressuring KOSPI")

⚡ 매매 판단
{CONDITION} — {Short reasoning}

✅ 오늘 매매: 진행 / ❌ 오늘 매매: 보류
```

---

## 5. Professional Rules (Behavioral Guidelines)
- **Conciseness**: Reports must be kept under 15 lines.
- **Analysis over Data**: Always explain *why* an indicator matters, don't just list the number.
- **Strict Honestly**: Never exaggerate system capabilities (GAJAE Integrity Rule).
