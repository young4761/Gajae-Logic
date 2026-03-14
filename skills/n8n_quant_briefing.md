# n8n Quantitative Briefing Skill

## Overview
This skill defines the rules and formulas for Gajae's market briefings, ensuring alignment with n8n automated trading workflows.

## Market Judgment Formulas
Gajae must evaluate market conditions based on the following threshold logic:

### 🚨 DANGER (High Volatility / Contrarian Opportunity)
- **Criteria**: `Fear & Greed < 25` OR `Fear & Greed > 74` OR `VIX >= 30`
- **Action**: Trade Allowed (Reverse entry or risk management required).
- **Sentiment**: `EXTREME_FEAR`, `EXTREME_GREED`, or `VIX_VOLATILITY_SPIKE`.

### ⚠️ CAUTION (Watch & Wait)
- **Criteria**: `Fear & Greed < 50` OR `VIX >= 20`
- **Action**: Trade Prohibited.
- **Sentiment**: `MARKET_CAUTION`.

### ✅ NORMAL (Stable Market)
- **Criteria**: All other cases.
- **Action**: Trade Prohibited (Safe zone, typically no action needed unless a trend is confirmed).
- **Sentiment**: `MARKET_NORMAL`.

## Reporting Format
Every briefing must follow this structure strictly:

📊 **오늘의 시황 브리핑** · {yyyy-MM-dd}

**📈 시장 지표**
• 공탐지수: {score} ({rating})
• VIX: {vix} ({vix_movement})
• S&P500 선물: {sp500} ({sp500_movement})
• 원/달러: {usd_krw} ({usd_krw_movement})
• 코스피: {kospi} ({kospi_movement})

**🧠 시황 해석**
(2~3 lines. Focus on correlations between indicators. Do not repeat numbers unnecessary.)

**⚡ 매매 판단**
{CONDITION} — (Short reasoning)

**✅ 오늘 매매: 진행** or **❌ 오늘 매매: 보류**

## Unified Execution
The above logic is implemented and automated in `c:/Users/yscho/.openclaw/gajae_full_analyst.py`. Use this script to generate independent briefings without n8n.

## N8N Webhook Protocol (N8N_ALERT)
When receiving a message starting with `N8N_ALERT:`, follow these steps:
1. **Parse JSON**: Extract the event data (e.g., `topic`, `symbol`, `price`, `change`).
2. **Contextual Analysis**: Compare the alert data with current market indices (VIX, F&G).
3. **Emergency Briefing**: Generate a 5-10 line urgent update.
4. **Action recommendation**: Explicitly state if this changes the `trade_allowed` status for today.

## Rules
1. **Conciseness**: Total response must be within 15 lines.
2. **Analysis**: Don't just list data; explain *why* (e.g., "Rising USD/KRW is putting pressure on KOSPI").
3. **Condition-Specific Advice**: In `DANGER`, mention both risks and potential contrarian opportunities.
4. **Formatting**: Use bold and bullets for clarity. No code blocks.
5. **Language**: Always in Korean.
