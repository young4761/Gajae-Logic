/**
 * skill_news.js
 * 스킬5: 뉴스 & 공시 감지
 * - DART 전자공시 API 연동 (opendart.fss.or.kr)
 * - 네이버 금융 RSS 뉴스 수집
 * - 키워드 필터링 후 Telegram 알림
 * - 공시 종류 필터링 (유상증자, 자기주식, 공급계약 등)
 */

const fs = require("fs");

// ─────────────────────────────────────────
// 전역 설정
// ─────────────────────────────────────────
const NEWS_DART_API_KEY = process.env.DART_API_KEY || "";
const NEWS_TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN || "";
const NEWS_TELEGRAM_CHATID = process.env.TELEGRAM_CHAT_ID || "";

// (기존) 감시 종목코드. "ALL"이 포함되어 있으면 한국시장 전체 종목 스캔 모드로 동작
let NEWS_WATCH_CODES = (process.env.NEWS_WATCH_CODES || "ALL").split(",");

// 전체 주식 종목 보관용 변수 (stk_cd string 배열)
let FULL_KRX_STOCK_CODES = [];

// 키워드 필터 (제목에 포함 시 알림)
const POSITIVE_KEYWORDS = [
    "계약 체결", "수주", "흑자 전환", "대규모 투자", "신제품 출시", "MOU", "상한가", "돌파", "강세"
];

const NEGATIVE_KEYWORDS = [
    "적자", "소송", "횡령", "배임", "상장폐지", "대주주 매도", "공매도", "하한가", "급락", "약세", "주의", "경고"
];

const NEUTRAL_IGNORE_KEYWORDS = [
    "공시", "IR", "배당 기준일", "단순 가격 정보", "특징주", "마감", "시황"
];

// DART 전용 키워드 (기존 유지)
const DART_ALERT_KEYWORDS = [
    "유상증자", "무상증자", "상장폐지", "관리종목",
    "최대주주", "공급계약", "자기주식", "실적",
    "영업정지", "횡령", "배당", "합병",
];

// 공시 감시 간격 (기본 10분)
const NEWS_POLL_INTERVAL = parseInt(process.env.NEWS_POLL_MIN || "10") * 60 * 1000;

// 이미 전송한 공시 ID 캐시 (중복 방지)
const NEWS_SENT_CACHE = new Set();

// 폴링 타이머
let NEWS_POLL_TIMER = null;

// ─────────────────────────────────────────
// Telegram 전송
// ─────────────────────────────────────────
async function telegram_send(message) {
    if (!NEWS_TELEGRAM_TOKEN || !NEWS_TELEGRAM_CHATID) return;
    const url = `https://api.telegram.org/bot${NEWS_TELEGRAM_TOKEN}/sendMessage`;
    await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            chat_id: NEWS_TELEGRAM_CHATID,
            text: message,
            parse_mode: "HTML",
        }),
    });
}

// ─────────────────────────────────────────
// DART 종목코드 → corp_code 변환
// (최초 1회 DART 회사코드 목록 다운로드 필요)
// ─────────────────────────────────────────
const DART_CODE_CACHE_FILE = "./dart_corp_codes.json";
let DART_CODE_MAP = {};  // stk_cd(6자리) → corp_code(8자리)

async function dart_load_corp_codes() {
    // 로컬 캐시 있으면 로드
    if (fs.existsSync(DART_CODE_CACHE_FILE)) {
        try {
            DART_CODE_MAP = JSON.parse(fs.readFileSync(DART_CODE_CACHE_FILE, "utf-8"));
            console.log(`[News] DART 코드 캐시 로드: ${Object.keys(DART_CODE_MAP).length}개`);
            return;
        } catch { }
    }

    // DART API로 전체 회사 목록 다운로드 (ZIP → XML)
    // 주의: DART API가 ZIP 파일을 반환하므로 Node.js에서 압축 해제 필요
    // 간소화: 직접 API 검색으로 corp_code 조회
    console.log("[News] DART 코드 캐시 없음 - API 검색 모드로 전환");
}

async function dart_get_corp_code(stkCd) {
    // 캐시 확인
    if (DART_CODE_MAP[stkCd]) return DART_CODE_MAP[stkCd];

    // DART 회사검색 API로 조회
    const url = `https://opendart.fss.or.kr/api/company.json?crtfc_key=${NEWS_DART_API_KEY}&stock_code=${stkCd}`;
    try {
        const res = await fetch(url);
        const data = await res.json();
        if (data.status === "000" && data.corp_code) {
            DART_CODE_MAP[stkCd] = data.corp_code;
            // 실시간 저장 주석처리 (전체 종목 감시 시 IO 부하 방지용)
            // fs.writeFileSync(DART_CODE_CACHE_FILE, JSON.stringify(DART_CODE_MAP, null, 2));
            return data.corp_code;
        }
    } catch (e) {
        // console.error(`[News] DART corp_code 조회 실패 (${stkCd}):`, e.message); // 너무 많으면 스팸되므로 주석처리
    }
    return null;
}

// ─────────────────────────────────────────
// 네이버 증권 전체 종목코드 로드 (KOSPI & KOSDAQ)
// ─────────────────────────────────────────
async function load_all_krx_codes() {
    try {
        console.log("[News] 한국 주식 전체 종목코드(약 4,000개)를 불러옵니다...");
        const urlKOSPI = "https://m.stock.naver.com/api/json/sise/siseListJson.nhn?menu=market_sum&sosok=0&pageSize=3000&page=1";
        const urlKOSDAQ = "https://m.stock.naver.com/api/json/sise/siseListJson.nhn?menu=market_sum&sosok=1&pageSize=3000&page=1";

        const [resK, resQ] = await Promise.all([fetch(urlKOSPI), fetch(urlKOSDAQ)]);
        const [dataK, dataQ] = await Promise.all([resK.json(), resQ.json()]);

        const kCodes = (dataK?.result?.itemList || []).map(i => i.cd);
        const qCodes = (dataQ?.result?.itemList || []).map(i => i.cd);

        FULL_KRX_STOCK_CODES = [...new Set([...kCodes, ...qCodes])];
        console.log(`[News] 💡 전체 종목코드 로드 완료 (총 ${FULL_KRX_STOCK_CODES.length}개)`);
    } catch (e) {
        console.error("[News] ❌ 전체 종목코드 불러오기 실패:", e.message);
        // 실패 시 삼성전자/SK하이닉스라도 기본 할당
        if (FULL_KRX_STOCK_CODES.length === 0) {
            FULL_KRX_STOCK_CODES = ["005930", "000660"];
        }
    }
}

// ─────────────────────────────────────────
// DART 공시 조회
// ─────────────────────────────────────────
async function dart_fetch_disclosures(corpCode) {
    if (!NEWS_DART_API_KEY) return [];

    const today = new Date();
    const bgn_de = new Date(today - 7 * 86400000) // 7일 전
        .toISOString().slice(0, 10).replace(/-/g, "");
    const end_de = today.toISOString().slice(0, 10).replace(/-/g, "");

    const url = (
        `https://opendart.fss.or.kr/api/list.json` +
        `?crtfc_key=${NEWS_DART_API_KEY}` +
        `&corp_code=${corpCode}` +
        `&bgn_de=${bgn_de}` +
        `&end_de=${end_de}` +
        `&page_count=20`
    );

    try {
        const res = await fetch(url);
        const data = await res.json();
        if (data.status !== "000") return [];
        return data.list || [];
    } catch {
        return [];
    }
}

function dart_check_keyword(title) {
    return DART_ALERT_KEYWORDS.some(kw => title.includes(kw));
}

function dart_build_message(item, stockName, stkCd) {
    const dartUrl = `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${item.rcept_no}`;
    return (
        `🚨 <b>[공시 감지]</b>\n\n` +
        `📋 <b>${stockName}</b> (${stkCd})\n` +
        `📄 ${item.report_nm}\n` +
        `📅 ${item.rcept_dt}\n` +
        `🏢 제출인: ${item.flr_nm}\n` +
        `🔗 <a href="${dartUrl}">공시 원문 보기</a>`
    );
}

// ─────────────────────────────────────────
// 네이버 금융 RSS (모바일 API) 뉴스 조회
// ─────────────────────────────────────────
async function news_fetch_naver_rss(stkCd) {
    const url = `https://m.stock.naver.com/api/news/stock/${stkCd}?pageSize=20`;
    try {
        const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/json" } });
        const data = await res.json();

        let items = [];
        if (Array.isArray(data) && data.length > 0 && data[0].items) {
            items = data[0].items;
        } else if (data && data.items) {
            items = data.items;
        }

        const newsList = [];
        for (const item of items) {
            const title = item.tit || item.title || "";
            const dt = item.dt || item.datetime || "";
            const provider = item.offNm || item.officeName || "";
            const link = `https://m.stock.naver.com/investment/news/article/${item.officeId || ""}/${item.articleId || ""}`;

            if (title && link) {
                newsList.push({ title, link, dt, provider, code: stkCd });
            }
        }
        return newsList;
    } catch {
        return [];
    }
}

function news_check_keyword_list(title) {
    const title_lower = title.toLowerCase();

    // 1. 무시할 키워드 (제일 먼저)
    for (const kw of NEUTRAL_IGNORE_KEYWORDS) {
        if (title_lower.includes(kw.toLowerCase())) {
            return { level: 0, signal_type: "⚪", matched: [kw] };
        }
    }

    const matched_positive = [];
    const matched_negative = [];

    for (const kw of POSITIVE_KEYWORDS) {
        if (title_lower.includes(kw.toLowerCase())) matched_positive.push(kw);
    }

    for (const kw of NEGATIVE_KEYWORDS) {
        if (title_lower.includes(kw.toLowerCase())) matched_negative.push(kw);
    }

    if (matched_negative.length > 0) {
        return { level: 2, signal_type: "🔴", matched: matched_negative };
    }

    if (matched_positive.length > 0) {
        return { level: 2, signal_type: "🟢", matched: matched_positive };
    }

    return { level: 0, signal_type: "⚪", matched: [] };
}

// ─────────────────────────────────────────
// 전체 폴링 실행
// ─────────────────────────────────────────

// 지연을 위한 비동기 sleep 헬퍼
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function news_poll_once() {
    console.log(`[News] 공시/뉴스 폴링 시작... (${new Date().toLocaleTimeString()})`);

    // 타겟 목록 결정: ALL 이면 전체 모니터링, 아니면 특정 종목만
    let targetCodes = NEWS_WATCH_CODES.includes("ALL") ? FULL_KRX_STOCK_CODES : NEWS_WATCH_CODES;
    if (targetCodes.length === 0) targetCodes = ["005930"];

    for (const stkCd of targetCodes) {
        const code = stkCd.trim();
        if (!code) continue;

        // 1. DART 공시 감지 (약 4천개를 모두 DART조회하면 블락당할 수 있어 DART는 제한적으로 하거나 천천히 요청)
        // **중요**: 4,000개 전체 종목 DART 폴링은 API Limits(분당 1,000회 등)를 초과할 수 있으므로
        // 전체 모드(ALL)일 때는 DART 개별 조회를 생략하거나, 네이버 모바일 API 뉴스에 집중하는 것이 안전합니다.
        // 현재 로직상 전체 종목일때 DART API를 쏘면 바로 차단되므로, NEWS_WATCH_CODES 에 명시된 경우만 DART 조회를 하도록 백업처리합니다.
        if (NEWS_DART_API_KEY && !NEWS_WATCH_CODES.includes("ALL")) {
            const corpCode = await dart_get_corp_code(code);
            if (corpCode) {
                const disclosures = await dart_fetch_disclosures(corpCode);
                for (const item of disclosures) {
                    const cacheKey = `dart_${item.rcept_no}`;
                    if (NEWS_SENT_CACHE.has(cacheKey)) continue;
                    if (!dart_check_keyword(item.report_nm)) continue;

                    const stockName = item.corp_name || code;
                    const msg = dart_build_message(item, stockName, code);
                    await telegram_send(msg);
                    NEWS_SENT_CACHE.add(cacheKey);
                    console.log(`[News] DART 공시 전송: ${code} - ${item.report_nm}`);
                }
            }
        }

        // 2. 네이버 뉴스 키워드 감지
        const fetchedNews = await news_fetch_naver_rss(code);
        for (const item of fetchedNews) {
            const cacheKey = `news_${code}_${item.title}`;
            if (NEWS_SENT_CACHE.has(cacheKey)) continue;

            const signalInfo = news_check_keyword_list(item.title);

            // 중요 뉴스(Level 2)만 알림 전송
            if (signalInfo.level === 2) {
                const keywordsStr = signalInfo.matched.join(", ");
                const msg = (
                    `<b>${signalInfo.signal_type} [중요 뉴스 감지]</b>\n\n` +
                    `<b>종목코드:</b> ${code}\n` +
                    `<b>제목:</b> ${item.title}\n` +
                    `<b>매칭 키워드:</b> ${keywordsStr}\n` +
                    `<b>발행:</b> ${item.dt} (${item.provider})\n` +
                    `<b>링크:</b> <a href="${item.link}">원문 보기</a>\n` +
                    `⏰ ${new Date().toLocaleTimeString("ko-KR")}`
                );
                await telegram_send(msg);
                console.log(`[News] 뉴스 전송: ${code} - ${item.title} (${signalInfo.signal_type})`);
            }

            // 처리 완료 표시 (Level 0, Level 1 노이즈 무시)
            NEWS_SENT_CACHE.add(cacheKey);
        }

        // 너무 잦은 API 요청(4,000건) 방지를 위한 짧은 휴식 (25ms ~ 50ms)
        // 전체 스캔에 약 1~2분 소요
        if (NEWS_WATCH_CODES.includes("ALL")) {
            await sleep(30);
        }
    }
    console.log(`[News] 이번 주기의 뉴스 폴링 검사 완료. (종목 수: ${targetCodes.length})`);
}

function news_start_polling() {
    if (NEWS_POLL_TIMER) return;
    news_poll_once(); // 시작 즉시 1회 실행
    NEWS_POLL_TIMER = setInterval(news_poll_once, NEWS_POLL_INTERVAL);
    console.log(`[News] 폴링 시작 (간격: ${NEWS_POLL_INTERVAL / 60000}분)`);
}

function news_stop_polling() {
    if (NEWS_POLL_TIMER) {
        clearInterval(NEWS_POLL_TIMER);
        NEWS_POLL_TIMER = null;
        console.log("[News] 폴링 중지");
    }
}

// ─────────────────────────────────────────
// OpenClaw 스킬 진입점
// ─────────────────────────────────────────
module.exports = {
    name: "news",
    description: "전체 주식시장 4,200여 종목 뉴스 키워드 감지 후 메신저 알림을 전송합니다.",

    onLoad: () => {
        load_all_krx_codes().then(() => {
            dart_load_corp_codes().then(() => news_start_polling());
        });
    },
    onUnload: () => { news_stop_polling(); },

    commands: {
        /**
         * /news check 005930   → 즉시 공시/뉴스 조회
         * /news add 035720      → 감시 종목 추가
         * /news list            → 감시 종목 목록
         * /news keywords        → 키워드 목록 확인
         * /news start           → 폴링 시작
         * /news stop            → 폴링 중지
         */
        news: async (args) => {
            const sub = (args[0] || "list").toLowerCase();
            const code = args[1]?.trim();

            if (sub === "check") {
                if (!code) return "⚠️ 사용법: /news check [종목코드]";

                let result = `🔍 <b>${code}</b> 공시/뉴스 즉시 조회\n\n`;

                // DART 조회
                if (NEWS_DART_API_KEY) {
                    const corpCode = await dart_get_corp_code(code);
                    const disclosures = corpCode ? await dart_fetch_disclosures(corpCode) : [];
                    result += `📋 최근 공시 ${disclosures.length}건\n`;
                    for (const d of disclosures.slice(0, 3)) {
                        result += `• ${d.rcept_dt} ${d.report_nm}\n`;
                    }
                } else {
                    result += "⚠️ DART API 키 없음 - 환경변수 DART_API_KEY 설정 필요\n";
                }

                // 네이버 뉴스
                const fetchedNews = await news_fetch_naver_rss(code);
                result += `\n📰 최근 뉴스 헤드라인\n`;
                for (const h of fetchedNews.slice(0, 3)) {
                    result += `• <a href="${h.link}">${h.title}</a> (${h.provider}, ${h.dt})\n`;
                }

                return result;
            }

            if (sub === "list") {
                const isAll = NEWS_WATCH_CODES.includes("ALL");
                return `📋 <b>감시 모드</b>: ${isAll ? "전체 한국 주식 약 4,200개 종목 뉴스 스캔 중" : NEWS_WATCH_CODES.join(", ")}\n\n` +
                    `🔑 <b>DART 키워드</b>\n${DART_ALERT_KEYWORDS.join(", ")}\n\n` +
                    `🟢 <b>긍정 키워드</b>\n${POSITIVE_KEYWORDS.join(", ")}\n\n` +
                    `🔴 <b>부정 키워드</b>\n${NEGATIVE_KEYWORDS.join(", ")}`;
            }

            if (sub === "keywords") {
                return `🔑 <b>DART 키워드</b>\n${DART_ALERT_KEYWORDS.join(", ")}\n` +
                    `🟢 <b>긍정 키워드</b>\n${POSITIVE_KEYWORDS.join(", ")}\n` +
                    `🔴 <b>부정 키워드</b>\n${NEGATIVE_KEYWORDS.join(", ")}`;
            }

            if (sub === "start") { news_start_polling(); return "✅ 뉴스/공시 감시 시작"; }
            if (sub === "stop") { news_stop_polling(); return "✅ 뉴스/공시 감시 중지"; }

            return "⚠️ 사용법: /news [check|list|keywords|start|stop]";
        },
    },
};
