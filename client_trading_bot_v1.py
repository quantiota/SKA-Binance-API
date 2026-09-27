"""
SKA Paired Cycle Trading Bot v1 — implements Version 1 of state_machine_diagram.md
(entropy-derived probability regime transitions, ΔP).

Regime definition:
  P(n)    = exp(-|ΔH/H|)   where  ΔH/H = (H(n) - H(n-1)) / H(n)
  δP_tick = P(n) - P(n-1)  consecutive change in probability

  |ΔP(n) − (−0.86)| ≤ K × 0.14  →  regime = 2  ("bear"    — neutral→bear, tol=0.004)
  |ΔP(n) − (−0.34)| ≤ K × 0.66  →  regime = 1  ("bull"    — neutral→bull, tol=0.020)
  else                             →  regime = 0  (neutral)

  P band positions — universal constants at convergence scale (asset-independent):
    P_NEUTRAL_NEUTRAL = 1.00
    P_NEUTRAL_BULL    = 0.66
    P_X_NEUTRAL       = 0.51   (bull→neutral = bear→neutral)
    P_NEUTRAL_BEAR    = 0.14

  BULL_THRESHOLD = P_NEUTRAL_NEUTRAL − P_NEUTRAL_BULL = 0.34
  BEAR_THRESHOLD = P_NEUTRAL_NEUTRAL − P_NEUTRAL_BEAR = 0.86

  DP_PAIR_BULL = 0.15  # P_NEUTRAL_BULL − P_X_NEUTRAL  (market constant at convergence)
  DP_PAIR_BEAR = 0.37  # P_X_NEUTRAL   − P_NEUTRAL_BEAR

Signal logic:

  LONG:
    neutral→bull               (OPEN LONG — WAIT_PAIR)
    bull→neutral               (pair confirmed — IN_NEUTRAL)
    neutral→neutral × N        (neutral gap — stay IN_NEUTRAL)
    <first non-neutral>        (gap closes — READY)
    neutral→bull               (cycle repeats — WAIT_PAIR)
    neutral→bear               (opposite cycle opens — EXIT_WAIT)
    bear→neutral               (opposite pair confirmed — CLOSE LONG)

  SHORT:
    neutral→bear               (OPEN SHORT — WAIT_PAIR)
    bear→neutral               (pair confirmed — IN_NEUTRAL)
    neutral→neutral × N        (neutral gap — stay IN_NEUTRAL)
    <first non-neutral>        (gap closes — READY)
    neutral→bear               (cycle repeats — WAIT_PAIR)
    neutral→bull               (opposite cycle opens — EXIT_WAIT)
    bull→neutral               (opposite pair confirmed — CLOSE SHORT)

Execution model (spot only — no margin/futures):
  LONG open  (neutral→bull, or SHORT close → re-enter) : BUY on exchange
  LONG close (bear→neutral)                            : SELL on exchange
  SHORT                                                : synthetic only, no exchange orders
  Exchange state sequence: BUY → SELL → [flat, tracking SHORT] → BUY → SELL → ...

  Signal source: SKA API at api.quantiota.org — proprietary engine, transitions only.

Usage:
    python client_trading_bot_v1.py --symbol XRPUSDT                        # dry run
    python client_trading_bot_v1.py --symbol XRPUSDC --live                 # live trading
    python client_trading_bot_v1.py --symbol BTCUSDT --api https://api.quantiota.org
"""

import argparse
import base64
import csv
import logging
import math
import os
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests
import urllib3
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()   # load .env from the current directory before reading os.environ

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# ── User configuration ────────────────────────────────────────────────────────

VERSION         = 1          # ← change this to switch between bot versions
SYMBOL          = "XRPUSDT"
MIN_NN_COUNT    = 3          # Structural filter — do not change unless you know why
API_URL         = "https://api.quantiota.org"
POLL_INTERVAL   = 1.0        # seconds
DP_PAIR_CUTOFF  = 3200       # stop recording ΔP_pair before engine reset

RESULTS_DIR     = 'bot_results_v1'

# P band positions — universal constants at convergence scale, confirmed XRPUSDT+BTCUSDT
P_NEUTRAL_NEUTRAL = 1.00
P_NEUTRAL_BULL    = 0.66
P_X_NEUTRAL       = 0.51   # bull→neutral = bear→neutral
P_NEUTRAL_BEAR    = 0.14

# Proportional tolerance: tol per transition = K × P_curr_structural
K         = 0.03
TOL_BEAR  = K * P_NEUTRAL_BEAR   # = 0.0042  neutral→bear band
TOL_BULL  = K * P_NEUTRAL_BULL   # = 0.0198  neutral→bull band
TOL_CLOSE = K * P_X_NEUTRAL      # = 0.0153  bull→neutral = bear→neutral band

# ΔP centers for regime classification (negative — P drops from neutral)
DP_NEUTRAL_BEAR = -(P_NEUTRAL_NEUTRAL - P_NEUTRAL_BEAR)  # = -0.86
DP_NEUTRAL_BULL = -(P_NEUTRAL_NEUTRAL - P_NEUTRAL_BULL)  # = -0.34

# ΔP_pair — paired transition gap at convergence scale (observational reference)
DP_PAIR_BULL = P_NEUTRAL_BULL - P_X_NEUTRAL    # = 0.15
DP_PAIR_BEAR = P_X_NEUTRAL   - P_NEUTRAL_BEAR  # = 0.37

# SKA API key — required for /ska_bot/ endpoint
SKA_API_KEY = os.environ.get('SKA_API_KEY', '')

# Binance API — loaded lazily; validated in run() only when dry_run=False
BINANCE_API_KEY          = os.environ.get('BINANCE_API_KEY')
BINANCE_PRIVATE_KEY_PATH = os.environ.get('BINANCE_PRIVATE_KEY_PATH')
BINANCE_BASE_URL         = 'https://api.binance.com'

ORDER_QUANTITY = {
    'XRPUSDT':  7.0,      # ~$10 at $1.43
    'XRPUSDC':  7.0,
    'BTCUSDT':  0.0001,   # ~$8.5 at $85,000
    'BTCUSDC':  0.0001,
    'ETHUSDT':  0.005,    # ~$10 at $2,000
    'ETHUSDC':  0.005,
    'SOLUSDC':  0.1,      # ~$15 at $150
}

# ── State machine ─────────────────────────────────────────────────────────────

WAIT_PAIR  = 'WAIT_PAIR'
IN_NEUTRAL = 'IN_NEUTRAL'
READY      = 'READY'
EXIT_WAIT  = 'EXIT_WAIT'

# Direct jumps (false_start.md) — recognised by their own P so that V1 can IGNORE them, as drawn
JUMP_BULL_BEAR = (0.015, 0.022)   # bull→bear, P ≈ 0.018
JUMP_BEAR_BULL = (0.44, 0.46)     # bear→bull, P ≈ 0.45


@dataclass
class Position:
    side:                  str
    entry_price:           float
    entry_trade_id:        int
    entry_time:            str
    entry_transition:      str
    exit_state:            str = field(default=WAIT_PAIR)
    neutral_neutral_count: int = field(default=0)
    bull_pair_count:       int = field(default=0)
    bear_pair_count:       int = field(default=0)


class TradingBot:
    """SKA paired cycle trading bot v1 — regime classified from ΔP tolerance bands where P = exp(-|ΔH/H|).

    Execution model (spot only — no margin/futures):
      LONG open  (neutral→bull, or SHORT close → re-enter) : BUY on exchange
      LONG close (bear→neutral)                            : SELL on exchange
      SHORT                                                : synthetic only, no exchange orders
    Exchange state sequence: BUY → SELL → [flat, tracking SHORT] → BUY → SELL → ...
    """

    def __init__(self, symbol: str, api_url: str, poll_interval: float, dry_run: bool = True):
        self.symbol        = symbol
        self.api_url       = api_url
        self.poll_interval = poll_interval
        self.dry_run       = dry_run
        self.position: Optional[Position] = None
        self.last_trade_id = None
        self._private_key  = None
        self._lot_filter   = None   # populated in run() when dry_run=False

        self.total_trades   = 0
        self.winning_trades = 0
        self.losing_trades  = 0

        # PnL split: LONG = real spot execution, SHORT = synthetic signal tracking
        self.spot_pnl      = 0.0   # realized from real exchange LONGs only
        self.synthetic_pnl = 0.0   # synthetic SHORTs — no exchange orders
        self._csv_written  = False

        # ΔP_pair tracking
        self._last_open_name  = None
        self._last_open_P     = None
        self._already_long    = False  # BUY already on exchange after CLOSE_SHORT
        self._reg             = 'neutral'  # current regime, to recognise direct jumps (ignored in V1)
        self._dp_pair_written = False
        self._entropy_count   = 0

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.results_file = f'{RESULTS_DIR}/bot_results_v{VERSION}_{symbol}_{ts}.csv'
        self.dp_pair_file = f'{RESULTS_DIR}/dp_pair_v{VERSION}_{symbol}_{ts}.csv'

    # ── SKA API ───────────────────────────────────────────────────────────────

    def fetch_transitions(self):
        """Fetch pre-computed regime transitions from /ska_bot/{symbol}."""
        try:
            r = requests.get(
                f"{self.api_url}/ska_bot/{self.symbol}",
                params={"since": self.last_trade_id or 0},
                headers={"X-API-Key": SKA_API_KEY},
                timeout=5,
                verify=False
            )
            r.raise_for_status()
            return r.json().get("transitions", [])
        except Exception as e:
            logging.warning(f"API error: {e}")
            return []

    # ── Binance exchange ──────────────────────────────────────────────────────

    def _fetch_lot_filter(self) -> dict:
        """Fetch LOT_SIZE and NOTIONAL filters from Binance exchangeInfo (public, no auth)."""
        url = f"{BINANCE_BASE_URL}/api/v3/exchangeInfo?symbol={self.symbol}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                raise RuntimeError(f"exchangeInfo returned HTTP {resp.status_code}")
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"[FILTERS] Failed to fetch exchangeInfo for {self.symbol}: {e}") from e

        symbols = data.get('symbols', [])
        if not symbols:
            raise RuntimeError(f"[FILTERS] No symbol data returned for {self.symbol}")

        filter_map = {f['filterType']: f for f in symbols[0].get('filters', [])}
        if 'LOT_SIZE' not in filter_map:
            raise RuntimeError(f"[FILTERS] LOT_SIZE filter missing for {self.symbol}")
        lot = filter_map['LOT_SIZE']

        notional_filter = filter_map.get('NOTIONAL') or filter_map.get('MIN_NOTIONAL') or {}
        result = {
            'step_size':    float(lot['stepSize']),
            'min_qty':      float(lot['minQty']),
            'max_qty':      float(lot['maxQty']),
            'min_notional': float(notional_filter.get('minNotional', 0)),
            'step_str':     lot['stepSize'],
        }
        logging.info(
            f"[FILTERS] {self.symbol} stepSize={result['step_size']} "
            f"minQty={result['min_qty']} maxQty={result['max_qty']} "
            f"minNotional={result['min_notional']}"
        )
        return result

    def _quantize_qty(self, qty: float, price: float) -> float:
        """Floor qty to stepSize, enforce minQty and minNotional. No-op in dry run."""
        if self._lot_filter is None:
            return qty
        f = self._lot_filter
        step = f['step_size']
        # floor to step size using integer arithmetic to avoid float drift
        qty = math.floor(qty / step) * step
        # round to the number of decimals in stepSize string
        step_str = f['step_str'].rstrip('0')
        decimals = len(step_str.split('.')[1]) if '.' in step_str else 0
        qty = round(qty, decimals)
        if qty < f['min_qty']:
            raise ValueError(f"{self.symbol}: qty {qty} < minQty {f['min_qty']} — increase ORDER_QUANTITY")
        if qty > f['max_qty']:
            raise ValueError(f"{self.symbol}: qty {qty} > maxQty {f['max_qty']} — decrease ORDER_QUANTITY")
        notional = qty * price
        if notional < f['min_notional']:
            raise ValueError(
                f"{self.symbol}: notional {notional:.4f} < minNotional {f['min_notional']} "
                f"— increase ORDER_QUANTITY"
            )
        return qty

    def _load_private_key(self) -> Ed25519PrivateKey:
        """Load Ed25519 private key from PEM file."""
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        with open(BINANCE_PRIVATE_KEY_PATH, 'rb') as f:
            return load_pem_private_key(f.read(), password=None)

    def _binance_order(self, side: str, quantity: float) -> bool:
        """Place a market order on Binance using Ed25519 signature. Returns True only if status=FILLED."""
        params = {
            'symbol':    self.symbol,
            'side':      side,
            'type':      'MARKET',
            'quantity':  quantity,
            'timestamp': int(time.time() * 1000),
        }
        query = '&'.join(f"{k}={v}" for k, v in params.items())
        signature = urllib.parse.quote(
            base64.b64encode(self._private_key.sign(query.encode('ASCII'))).decode()
        )
        url = f"{BINANCE_BASE_URL}/api/v3/order?{query}&signature={signature}"
        headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
        try:
            resp = requests.post(url, headers=headers, timeout=10)
            data = resp.json()
            order_status = data.get('status')
            if resp.status_code == 200 and order_status == 'FILLED':
                logging.info(
                    f"[ORDER] {side} {quantity} {self.symbol} FILLED "
                    f"orderId={data.get('orderId')} fills={data.get('fills')}"
                )
                return True
            logging.error(f"[ORDER] {side} not filled: HTTP {resp.status_code} status={order_status} {data}")
            return False
        except Exception as e:
            logging.error(f"[ORDER] {side} exception: {e}")
            return False

    def _execute_buy(self, price: float) -> bool:
        qty = self._quantize_qty(ORDER_QUANTITY.get(self.symbol, 1.0), price)
        logging.info(f"[EXECUTE] BUY {self.symbol} @ {price:.6f} qty={qty}")
        return self._binance_order('BUY', qty)

    def _execute_sell(self, price: float) -> bool:
        qty = self._quantize_qty(ORDER_QUANTITY.get(self.symbol, 1.0), price)
        logging.info(f"[EXECUTE] SELL {self.symbol} @ {price:.6f} qty={qty}")
        return self._binance_order('SELL', qty)

    # ── ΔP_pair recording ─────────────────────────────────────────────────────

    def _record_dp_pair(self, pair_type, p1, p2):
        # p1 = P at opening transition (neutral→bull or neutral→bear)
        # p2 = P at closing transition (bull→neutral or bear→neutral)
        # ΔP_pair = p2 - p1 → negative for bull, positive for bear
        if p1 is None or p2 is None:
            return
        dp = p2 - p1
        row = {
            'pair_type': pair_type,
            'p1':        round(p1, 4),
            'p2':        round(p2, 4),
            'dp_pair':   round(dp, 4),
        }
        with open(self.dp_pair_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not self._dp_pair_written:
                writer.writeheader()
                self._dp_pair_written = True
            writer.writerow(row)
        logging.info(f"ΔP_pair [{pair_type}] P={p1:.4f}→{p2:.4f} ΔP={dp:+.4f}")

    # ── State machine ─────────────────────────────────────────────────────────

    def _grammar(self, name, P):
        """ΔP bands give the paired-regime openings; the transition after an opening is a direct jump
        (bull→bear / bear→bull) when its P is in the jump band, otherwise the return to neutral."""
        if self._reg == 'bull':
            if P is not None and JUMP_BULL_BEAR[0] <= P <= JUMP_BULL_BEAR[1]:
                name, self._reg = 'bull→bear', 'bear'
            else:
                name, self._reg = 'bull→neutral', 'neutral'
        elif self._reg == 'bear':
            if P is not None and JUMP_BEAR_BULL[0] <= P <= JUMP_BEAR_BULL[1]:
                name, self._reg = 'bear→bull', 'bull'
            else:
                name, self._reg = 'bear→neutral', 'neutral'
        else:
            if name not in ('neutral→neutral', 'neutral→bull', 'neutral→bear'):
                name = 'neutral→neutral'
            self._reg = {'neutral→bull': 'bull', 'neutral→bear': 'bear'}.get(name, 'neutral')
        return name

    def process_signal(self, transition):
        trade_id = transition['trade_id']
        price    = transition['price']
        name     = transition['transition_name']
        P        = transition['P']
        ts       = transition['timestamp']

        if self.last_trade_id is not None and trade_id <= self.last_trade_id:
            return
        self.last_trade_id = trade_id

        name = self._grammar(name, P)   # direct jumps recognised by their P

        # Direct jumps (bull→bear, bear→bull) are localized entropy shocks — mean-reversion expected
        # Do NOT react — keep position open through the spike
        if name in ('bull→bear', 'bear→bull'):
            logging.info(f"--- Direct jump {name} ignored (localized entropy shock) | trade_id={trade_id}")
            return

        # ΔP_pair: gap within paired transition neutral→bull→neutral or neutral→bear→neutral
        # ΔP = P(closing) − P(opening) → negative for bull, positive for bear
        PAIR_CLOSE = {'neutral→bull': 'bull→neutral', 'neutral→bear': 'bear→neutral'}
        if name in ('neutral→bull', 'neutral→bear'):
            self._last_open_name = name
            self._last_open_P    = P
        elif (name in ('bull→neutral', 'bear→neutral') and
              self._last_open_name is not None and
              PAIR_CLOSE.get(self._last_open_name) == name and
              self._entropy_count < DP_PAIR_CUTOFF):
            pair_type = 'bull' if name == 'bull→neutral' else 'bear'
            self._record_dp_pair(pair_type, self._last_open_P, P)
            if self.position is not None:
                if pair_type == 'bull':
                    self.position.bull_pair_count += 1
                else:
                    self.position.bear_pair_count += 1
            self._last_open_name = None
            self._last_open_P    = None

        p_str = f"{P:.4f}" if P is not None else "n/a"

        # === NO POSITION: look for entry ===
        if self.position is None:
            if name == 'neutral→bull':
                if not self.dry_run and not self._already_long:
                    if not self._execute_buy(price):
                        logging.error("[ORDER] BUY failed — LONG not opened")
                        return
                self._already_long = False
                self.position = Position(
                    side='LONG', entry_price=price,
                    entry_trade_id=trade_id, entry_time=str(ts),
                    entry_transition=name, exit_state=WAIT_PAIR
                )
                logging.info(
                    f">>> OPEN LONG @ {price:.6f} | P={p_str} | trade_id={trade_id} "
                    f"| waiting: bull→neutral"
                )
            elif name == 'neutral→bear':
                self.position = Position(
                    side='SHORT', entry_price=price,
                    entry_trade_id=trade_id, entry_time=str(ts),
                    entry_transition=name, exit_state=WAIT_PAIR
                )
                logging.info(
                    f">>> OPEN SHORT @ {price:.6f} | P={p_str} | trade_id={trade_id} "
                    f"| waiting: bear→neutral"
                )
                # No exchange order: spot cannot short-sell — SHORT tracked synthetically only
            return

        # === LONG POSITION ===
        if self.position.side == 'LONG':

            if self.position.exit_state == WAIT_PAIR:
                if name == 'bull→neutral':
                    self.position.exit_state = IN_NEUTRAL
                    logging.info(
                        f"--- UP pair confirmed (bull→neutral) @ {price:.6f} "
                        f"| IN_NEUTRAL | trade_id={trade_id}"
                    )

            elif self.position.exit_state == IN_NEUTRAL:
                if name == 'neutral→neutral':
                    self.position.neutral_neutral_count += 1
                    logging.info(
                        f"--- Neutral gap nn_count={self.position.neutral_neutral_count} @ {price:.6f} "
                        f"| IN_NEUTRAL | trade_id={trade_id}"
                    )
                else:
                    if self.position.neutral_neutral_count >= MIN_NN_COUNT:
                        self.position.exit_state = READY
                        logging.info(
                            f"--- Neutral gap closed ({name}) @ {price:.6f} "
                            f"| READY | nn_count={self.position.neutral_neutral_count} | trade_id={trade_id}"
                        )
                    else:
                        logging.info(
                            f"--- Neutral gap too short nn_count={self.position.neutral_neutral_count} "
                            f"(min={MIN_NN_COUNT}) — reset | trade_id={trade_id}"
                        )
                        self.position.neutral_neutral_count = 0

            elif self.position.exit_state == READY:
                if name == 'neutral→bull':
                    self.position.exit_state = WAIT_PAIR
                    self.position.neutral_neutral_count = 0
                    logging.info(
                        f"--- UP cycle repeating (neutral→bull) @ {price:.6f} "
                        f"| WAIT_PAIR | trade_id={trade_id}"
                    )
                elif name == 'neutral→bear':
                    self.position.exit_state = EXIT_WAIT
                    logging.info(
                        f"--- Opposite cycle opening (neutral→bear) @ {price:.6f} "
                        f"| EXIT_WAIT | trade_id={trade_id}"
                    )

            elif self.position.exit_state == EXIT_WAIT:
                if name == 'bear→neutral' and P is not None and abs(P - P_X_NEUTRAL) <= TOL_CLOSE:
                    if not self.dry_run:
                        if not self._execute_sell(price):
                            logging.error("[ORDER] SELL failed — LONG not closed")
                            return
                    pnl = price - self.position.entry_price
                    pnl_pct = (pnl / self.position.entry_price) * 100
                    self._record_trade(pnl, pnl_pct, price)
                    logging.info(
                        f"<<< CLOSE LONG (bear→neutral) @ {price:.6f} | "
                        f"PnL={pnl:+.6f} ({pnl_pct:+.4f}%) | entry={self.position.entry_price:.6f}"
                    )
                    self.position = None

        # === SHORT POSITION ===
        elif self.position.side == 'SHORT':

            if self.position.exit_state == WAIT_PAIR:
                if name == 'bear→neutral':
                    self.position.exit_state = IN_NEUTRAL
                    logging.info(
                        f"--- DOWN pair confirmed (bear→neutral) @ {price:.6f} "
                        f"| IN_NEUTRAL | trade_id={trade_id}"
                    )

            elif self.position.exit_state == IN_NEUTRAL:
                if name == 'neutral→neutral':
                    self.position.neutral_neutral_count += 1
                    logging.info(
                        f"--- Neutral gap nn_count={self.position.neutral_neutral_count} @ {price:.6f} "
                        f"| IN_NEUTRAL | trade_id={trade_id}"
                    )
                else:
                    if self.position.neutral_neutral_count >= MIN_NN_COUNT:
                        self.position.exit_state = READY
                        logging.info(
                            f"--- Neutral gap closed ({name}) @ {price:.6f} "
                            f"| READY | nn_count={self.position.neutral_neutral_count} | trade_id={trade_id}"
                        )
                    else:
                        logging.info(
                            f"--- Neutral gap too short nn_count={self.position.neutral_neutral_count} "
                            f"(min={MIN_NN_COUNT}) — reset | trade_id={trade_id}"
                        )
                        self.position.neutral_neutral_count = 0

            elif self.position.exit_state == READY:
                if name == 'neutral→bear':
                    self.position.exit_state = WAIT_PAIR
                    self.position.neutral_neutral_count = 0
                    logging.info(
                        f"--- DOWN cycle repeating (neutral→bear) @ {price:.6f} "
                        f"| WAIT_PAIR | trade_id={trade_id}"
                    )
                elif name == 'neutral→bull':
                    self.position.exit_state = EXIT_WAIT
                    logging.info(
                        f"--- Opposite cycle opening (neutral→bull) @ {price:.6f} "
                        f"| EXIT_WAIT | trade_id={trade_id}"
                    )

            elif self.position.exit_state == EXIT_WAIT:
                if name == 'bull→neutral' and P is not None and abs(P - P_X_NEUTRAL) <= TOL_CLOSE:
                    if not self.dry_run:
                        if not self._execute_buy(price):
                            logging.error("[ORDER] BUY failed — SHORT not closed / LONG not re-entered")
                            return
                    pnl = self.position.entry_price - price
                    pnl_pct = (pnl / self.position.entry_price) * 100
                    self._record_trade(pnl, pnl_pct, price)
                    logging.info(
                        f"<<< CLOSE SHORT (bull→neutral) @ {price:.6f} | "
                        f"PnL={pnl:+.6f} ({pnl_pct:+.4f}%) | entry={self.position.entry_price:.6f}"
                    )
                    self._already_long = True
                    self.position = None

    # ── Recording ─────────────────────────────────────────────────────────────

    def _record_trade(self, pnl, pnl_pct, exit_price):
        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        # Route PnL to the correct bucket
        is_real = (self.position.side == 'LONG')   # LONGs are backed by real exchange orders
        if is_real:
            self.spot_pnl += pnl
        else:
            self.synthetic_pnl += pnl

        trade = {
            'side':             self.position.side,
            'real':             is_real,
            'entry':            self.position.entry_price,
            'exit':             exit_price,
            'pnl':              pnl,
            'entry_transition': self.position.entry_transition,
            'bull_pairs':       self.position.bull_pair_count,
            'bear_pairs':       self.position.bear_pair_count,
        }
        with open(self.results_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'side', 'real', 'entry', 'exit', 'pnl', 'entry_transition', 'bull_pairs', 'bear_pairs'
            ])
            if not self._csv_written:
                writer.writeheader()
                self._csv_written = True
            writer.writerow(trade)

    def print_stats(self):
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        combined = self.spot_pnl + self.synthetic_pnl
        logging.info(
            f"=== STATS === Trades: {self.total_trades} | "
            f"Win: {self.winning_trades} | Lose: {self.losing_trades} | "
            f"Win rate: {win_rate:.1f}% | "
            f"Spot PnL (real): {self.spot_pnl:+.6f} | "
            f"Synthetic PnL: {self.synthetic_pnl:+.6f} | "
            f"Combined signal PnL: {combined:+.6f}"
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        logging.info(
            f"SKA Trading Bot v{VERSION} | symbol={self.symbol} | api={self.api_url} | "
            f"dry_run={self.dry_run}"
        )
        logging.info(f"MIN_NN_COUNT={MIN_NN_COUNT} | K={K}")
        logging.info(f"TOL_BULL={TOL_BULL:.4f} | TOL_BEAR={TOL_BEAR:.4f} | TOL_CLOSE={TOL_CLOSE:.4f}")

        if not self.dry_run:
            if not BINANCE_API_KEY:
                raise RuntimeError("BINANCE_API_KEY env var is not set")
            if not BINANCE_PRIVATE_KEY_PATH:
                raise RuntimeError("BINANCE_PRIVATE_KEY_PATH env var is not set")
            self._lot_filter  = self._fetch_lot_filter()
            self._private_key = self._load_private_key()
            logging.info("Ed25519 private key loaded")

        try:
            while True:
                transitions = self.fetch_transitions()
                for t in transitions:
                    self.process_signal(t)
                    self._entropy_count += 1

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            logging.info("Stopped by user")
        finally:
            if self.position:
                transitions = self.fetch_transitions()
                close_price = transitions[-1]['price'] if transitions else self.position.entry_price

                if not self.dry_run and self.position.side == 'LONG':
                    logging.warning("[END] Live LONG open at shutdown — sending emergency SELL")
                    sold = self._execute_sell(close_price)
                    if not sold:
                        logging.error(
                            "[END] Emergency SELL failed — manual intervention required: "
                            f"sell {ORDER_QUANTITY.get(self.symbol, '?')} {self.symbol} on Binance"
                        )

                if self.position.side == 'LONG':
                    pnl = close_price - self.position.entry_price
                else:
                    pnl = self.position.entry_price - close_price
                pnl_pct = (pnl / self.position.entry_price) * 100
                self._record_trade(pnl, pnl_pct, close_price)
                logging.info(
                    f"<<< CLOSE {self.position.side} (end of run) @ {close_price:.6f} | "
                    f"PnL={pnl:+.6f} ({pnl_pct:+.4f}%) | exit_state={self.position.exit_state}"
                )
                self.position = None
            self.print_stats()


if __name__ == '__main__':
    os.makedirs(RESULTS_DIR, exist_ok=True)

    parser = argparse.ArgumentParser(description='SKA Paired Cycle Trading Bot')
    parser.add_argument('--symbol', default=SYMBOL,         help='Trading pair (default: XRPUSDT)')
    parser.add_argument('--api',    default=API_URL,         help='SKA-API base URL')
