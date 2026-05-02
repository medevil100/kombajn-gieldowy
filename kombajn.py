
// neon_breakout_scanner_single_module.js
// Jednomodułowy skaner: real-time, TOP10 wybicia, trendy S/M/L, 52W, pivot, TP/SL, AI analiza

// =========================
// KONFIGURACJA
// =========================
const CONFIG = {
  api: {
    baseRest: "https://your-broker-rest-endpoint",
    baseWs: "wss://your-broker-ws-endpoint",
    secretKeyHeader: "x-api-key"
    // klucz trzymasz w secrecie na stimi / env, NIE w kodzie
  },
  refreshIntervalsMinutes: [1, 2, 3, 5, 10],
  defaultRefreshMinutes: 1,
  maxCandlesHistory: 200,
  topBreakoutLimit: 10
};

// =========================
// STAN APLIKACJI
// =========================
const STATE = {
  watchlist: [],          // lista symboli
  tickers: {},            // symbol -> TickerData
  ws: null,               // WebSocket
  refreshTimer: null,
  refreshMinutes: CONFIG.defaultRefreshMinutes,
  aiSelected: new Set(),  // symbole wybrane do AI
  lastTop10: []           // ostatnia lista TOP10
};

// =========================
// TYPY / STRUKTURY
// =========================
/**
 * @typedef {Object} TickerData
 * @property {string} symbol
 * @property {number} bid
 * @property {number} ask
 * @property {number} last
 * @property {number} volume
 * @property {string} time
 * @property {number[]} closes
 * @property {number[]} highs
 * @property {number[]} lows
 * @property {number[]} volumes
 * @property {number} ema10
 * @property {number} ema50
 * @property {number} ema200
 * @property {number} rsi14
 * @property {number} high52w
 * @property {number} low52w
 * @property {{P:number,R1:number,S1:number}} pivot
 * @property {{short:string,mid:string,long:string,score:number}} trend
 * @property {{tp:number,sl:number}} tpSl
 * @property {number} breakoutScore
 * @property {{signal:string,tp:number,sl:number,notes:string[]}|null} ai
 */

// =========================
// FUNKCJE POMOCNICZE (MATH)
// =========================
function ema(values, period) {
  if (!values || values.length === 0) return NaN;
  const k = 2 / (period + 1);
  let emaVal = values[0];
  for (let i = 1; i < values.length; i++) {
    emaVal = values[i] * k + emaVal * (1 - k);
  }
  return emaVal;
}

function sma(values, period) {
  if (!values || values.length < period) return NaN;
  const slice = values.slice(-period);
  const sum = slice.reduce((a, b) => a + b, 0);
  return sum / period;
}

function rsi(values, period = 14) {
  if (!values || values.length <= period) return NaN;
  let gains = 0;
  let losses = 0;
  for (let i = values.length - period; i < values.length; i++) {
    const diff = values[i] - values[i - 1];
    if (diff > 0) gains += diff;
    else losses -= diff;
  }
  const avgGain = gains / period;
  const avgLoss = losses / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

// =========================
// TREND / PIVOT / TP-SL / BREAKOUT
// =========================
function calcTrend(close, ema10, ema50, ema200) {
  const s = Math.sign(close - ema10);
  const m = Math.sign(close - ema50);
  const l = Math.sign(close - ema200);
  const score = 1 * s + 2 * m + 3 * l;

  const toTrend = (x) => (x > 0 ? "UP" : x < 0 ? "DOWN" : "NEUTRAL");

  return {
    short: toTrend(s),
    mid: toTrend(m),
    long: toTrend(l),
    score
  };
}

function calcPivots(prevHigh, prevLow, prevClose) {
  const P = (prevHigh + prevLow + prevClose) / 3;
  const R1 = 2 * P - prevLow;
  const S1 = 2 * P - prevHigh;
  return { P, R1, S1 };
}

function calcTpSl(ticker) {
  const tp = ticker.high52w || ticker.pivot.R1 || ticker.last * 1.05;
  const sl = ticker.low52w || ticker.pivot.S1 || ticker.last * 0.95;
  return { tp, sl };
}

function calcBreakoutScore(ticker) {
  const dist52 = ticker.high52w
    ? (ticker.last - ticker.high52w) / ticker.high52w
    : 0;
  const volSma20 = sma(ticker.volumes, 20);
  const volRel = volSma20 ? ticker.volume / volSma20 : 1;
  const mom = ticker.rsi14 ? ticker.rsi14 / 100 : 0.5;
  return 3 * dist52 + 2 * volRel + 1 * mom;
}

function signalFromTrendScore(score) {
  if (score >= 4) return "BUY";
  if (score <= -2) return "SELL";
  return "HOLD";
}

// =========================
// REAL-TIME / REST
// =========================
async function fetchWatchlist() {
  // TODO: podłącz do własnego źródła (plik, API, baza)
  // Na razie przykładowo:
  STATE.watchlist = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"];
}

async function fetchHistoryForSymbol(symbol) {
  // TODO: REST history endpoint
  // Zwróć przykładowe dane (mock) – do podmiany na realne
  const candles = [];
  const now = Date.now();
  let price = 100;
  for (let i = 0; i < CONFIG.maxCandlesHistory; i++) {
    const high = price * (1 + Math.random() * 0.01);
    const low = price * (1 - Math.random() * 0.01);
    const close = low + Math.random() * (high - low);
    const volume = 1000 + Math.random() * 5000;
    candles.push({
      time: new Date(now - (CONFIG.maxCandlesHistory - i) * 60000).toISOString(),
      high,
      low,
      close,
      volume
    });
    price = close;
  }
  return candles;
}

async function initTicker(symbol) {
  const candles = await fetchHistoryForSymbol(symbol);
  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const volumes = candles.map((c) => c.volume);

  const ema10 = ema(closes, 10);
  const ema50 = ema(closes, 50);
  const ema200 = ema(closes, 200);
  const rsi14 = rsi(closes, 14);

  const lastClose = closes[closes.length - 1];
  const prev = candles[candles.length - 2] || candles[candles.length - 1];
  const pivot = calcPivots(prev.high, prev.low, prev.close);

  const high52w = Math.max(...highs);
  const low52w = Math.min(...lows);

  const trend = calcTrend(lastClose, ema10, ema50, ema200);
  const tpSl = calcTpSl({
    last: lastClose,
    high52w,
    low52w,
    pivot
  });
  const breakoutScore = calcBreakoutScore({
    last: lastClose,
    high52w,
    volume: volumes[volumes.length - 1],
    volumes,
    rsi14
  });

  /** @type {TickerData} */
  const ticker = {
    symbol,
    bid: lastClose * 0.999,
    ask: lastClose * 1.001,
    last: lastClose,
    volume: volumes[volumes.length - 1],
    time: new Date().toISOString(),
    closes,
    highs,
    lows,
    volumes,
    ema10,
    ema50,
    ema200,
    rsi14,
    high52w,
    low52w,
    pivot,
    trend,
    tpSl,
    breakoutScore,
    ai: null
  };

  STATE.tickers[symbol] = ticker;
}

function connectWebSocket() {
  // TODO: podłącz do realnego WS brokera
  // Tu mock: co kilka sekund aktualizujemy last/bid/ask/volume
  setInterval(() => {
    STATE.watchlist.forEach((symbol) => {
      const t = STATE.tickers[symbol];
      if (!t) return;
      const delta = (Math.random() - 0.5) * 0.5;
      const newLast = Math.max(0.01, t.last + delta);
      t.last = newLast;
      t.bid = newLast * 0.999;
      t.ask = newLast * 1.001;
      t.volume = t.volume + Math.random() * 1000;
      t.time = new Date().toISOString();

      // aktualizacja wskaźników na podstawie nowej ceny
      t.closes.push(newLast);
      if (t.closes.length > CONFIG.maxCandlesHistory) t.closes.shift();
      t.ema10 = ema(t.closes, 10);
      t.ema50 = ema(t.closes, 50);
      t.ema200 = ema(t.closes, 200);
      t.rsi14 = rsi(t.closes, 14);
      t.trend = calcTrend(t.last, t.ema10, t.ema50, t.ema200);
      t.tpSl = calcTpSl(t);
      t.breakoutScore = calcBreakoutScore(t);
    });
  }, 3000);
}

// =========================
// AI ANALIZA
// =========================
async function analyzeWithAI(ticker) {
  // TODO: podłącz do prawdziwego endpointu AI (klucz z secreta)
  // Tu mock – szybka, konkretna odpowiedź
  const signal = signalFromTrendScore(ticker.trend.score);
  const tp = ticker.tpSl.tp;
  const sl = ticker.tpSl.sl;
  const notes = [
    `Trend S/M/L: ${ticker.trend.short}/${ticker.trend.mid}/${ticker.trend.long}`,
    `RSI14: ${ticker.rsi14.toFixed(1)}`,
    `Cena vs 52W High: ${ticker.last.toFixed(2)} / ${ticker.high52w.toFixed(2)}`
  ];
  ticker.ai = { signal, tp, sl, notes };
  return ticker.ai;
}

// =========================
// LOGIKA TOP10 WYBICIA
// =========================
function computeTop10Breakouts() {
  const list = Object.values(STATE.tickers);
  const sorted = list
    .slice()
    .sort((a, b) => b.breakoutScore - a.breakoutScore)
    .slice(0, CONFIG.topBreakoutLimit);
  STATE.lastTop10 = sorted.map((t) => t.symbol);
  return sorted;
}

// =========================
// RENDER (NA RAZIE: KONSOLE / JSON)
// =========================
function renderTable() {
  const rows = Object.values(STATE.tickers).map((t) => {
    const signal = signalFromTrendScore(t.trend.score);
    return {
      symbol: t.symbol,
      bidAsk: `${t.bid.toFixed(2)} / ${t.ask.toFixed(2)}`,
      last: t.last.toFixed(2),
      trendS: t.trend.short,
      trendM: t.trend.mid,
      trendL: t.trend.long,
      signal,
      high52w: t.high52w.toFixed(2),
      low52w: t.low52w.toFixed(2),
      pivotP: t.pivot.P.toFixed(2),
      tp: t.tpSl.tp.toFixed(2),
      sl: t.tpSl.sl.toFixed(2),
      breakoutScore: t.breakoutScore.toFixed(2),
      aiSignal: t.ai ? t.ai.signal : null
    };
  });

  console.clear();
  console.log("=== NEON BREAKOUT SCANNER (ALL) ===");
  console.table(rows);

  const top10 = computeTop10Breakouts().map((t) => t.symbol);
  console.log("TOP10 BREAKOUT:", top10.join(", "));
}

// =========================
// ODŚWIEŻANIE
// =========================
function setRefreshInterval(minutes) {
  STATE.refreshMinutes = minutes;
  if (STATE.refreshTimer) clearInterval(STATE.refreshTimer);
  STATE.refreshTimer = setInterval(() => {
    renderTable();
  }, minutes * 60 * 1000);
}

function manualRefresh() {
  renderTable();
}

// =========================
// AI ANALIZA DLA WYBRANYCH
// =========================
async function runAiForSelected() {
  const symbols = Array.from(STATE.aiSelected);
  for (const symbol of symbols) {
    const t = STATE.tickers[symbol];
    if (!t) continue;
    await analyzeWithAI(t);
  }
  renderTable();
}

// =========================
// API DLA UI (PRZYCISKI, CHECKBOXY)
// =========================
function toggleAiForSymbol(symbol) {
  if (STATE.aiSelected.has(symbol)) STATE.aiSelected.delete(symbol);
  else STATE.aiSelected.add(symbol);
}

function getStateSnapshot() {
  return {
    watchlist: STATE.watchlist,
    tickers: STATE.tickers,
    top10: STATE.lastTop10,
    aiSelected: Array.from(STATE.aiSelected),
    refreshMinutes: STATE.refreshMinutes
  };
}

// =========================
// START
// =========================
async function startNeonScanner() {
  await fetchWatchlist();
  for (const symbol of STATE.watchlist) {
    await initTicker(symbol);
  }
  connectWebSocket();
  setRefreshInterval(CONFIG.defaultRefreshMinutes);
  manualRefresh();
}

// Uruchomienie (jeśli plik odpalany bezpośrednio w Node)
if (require.main === module) {
  startNeonScanner().catch(console.error);

  // przykładowo: po 10 sekundach włącz AI dla pierwszego symbolu
  setTimeout(() => {
    const first = STATE.watchlist[0];
    if (first) {
      toggleAiForSymbol(first);
      runAiForSelected();
    }
  }, 10000);
}

// Eksport do użycia w UI (np. w NEON COMMANDER)
module.exports = {
  startNeonScanner,
  manualRefresh,
  setRefreshInterval,
  toggleAiForSymbol,
  runAiForSelected,
  getStateSnapshot,
  CONFIG,
  STATE
};
