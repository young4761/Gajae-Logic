# GAJAE Core Trading Formulas & Logic

This document consolidates all the quantitative analysis logic and market judgment formulas developed for the "Gajae" AI assistant.

## 1. Advanced Market Scoring System (v2.0)

Instead of individual indicators, we now use a composite **TOTAL_MARKET_SCORE (0-100)** to determine trading actions.

### 🧮 Math Formulas

| Component | Weight | Calculation (Normalization) |
| :--- | :--- | :--- |
| **Fear & Greed (FG)** | 40% (0.4) | `Score = FG_Index_Value` (0-100) |
| **Volatility (VIX)** | 30% (0.3) | `Score = 15(100) to 30(0) range inversion` |
| **News Sentiment** | 30% (0.3) | `Score = (Positive / Total_News) * 100` |

**Total Score** = `(FG_Score * 0.4) + (VIX_Score * 0.3) + (Sentiment_Score * 0.3)`

---

### 🚦 Trade Judgment Thresholds

| Status | Total Score | Risk Multiplier | Action |
| :--- | :--- | :--- | :--- |
| **🚨 DANGER/HIGH** | `>= 75` | **1.2x** | **✅ ACTIVE TRADE** (High energy/Opportunity) |
| **⚠️ CAUTION** | `>= 50` | **0.8x** | **✅ CONSERVATIVE** (Recovery/Edge) |
| **✅ NORMAL** | `< 50` | **0.0x** | **❌ WAIT** (Stable or Low Signal) |

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

## 4. Visual Reporting & Intelligence (v2.1)

The system now features automated **Visual Trend Analysis** to help human analysts spot patterns over time.

### 📈 Market Trend Graphs
Every daily briefing includes a 15-day trend graph containing:
- **Total Market Score**: A line chart showing the composite score relative to Danger/Caution zones.
- **Volatility (VIX)**: A trend line tracking the fear index.

### 📂 Data Persistence
Historical data is stored in the workspace for long-term analysis:
- **File**: `workspace/scripts/gajae_history.csv`
- **Columns**: `date`, `total_score`, `vix` (Used for automatic plot generation).

---

## 5. Professional Rules (Behavioral Guidelines)
...
- **Conciseness**: Reports must be kept under 15 lines.
- **Analysis over Data**: Always explain *why* an indicator matters, don't just list the number.
- **Strict Honestly**: Never exaggerate system capabilities (GAJAE Integrity Rule).
