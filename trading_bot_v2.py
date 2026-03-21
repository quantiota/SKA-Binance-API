"""
SKA Paired Cycle Trading Bot — entropy-derived probability regime transitions (ΔP).

Regime definition:
  P(n)    = exp(-|ΔH/H|)   where  ΔH/H = (H(n) - H(n-1)) / H(n)
  δP_tick = P(n) - P(n-1)  consecutive change in probability

  δP_tick < -BEAR_THRESHOLD                    →  bear    (large P drop)
  -BEAR_THRESHOLD ≤ δP_tick < -BULL_THRESHOLD  →  bull    (moderate P drop)
  δP_tick ≥ -BULL_THRESHOLD                    →  neutral

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
    python trading_bot.py --symbol XRPUSDT                        # dry run
    python trading_bot.py --symbol XRPUSDC --live                 # live trading
    python trading_bot.py --symbol BTCUSDT --api https://api.quantiota.org
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
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dotenv import load_dotenv

load_dotenv()   # load .env from the current directory before reading os.environ

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# ── User configuration ────────────────────────────────────────────────────────

VERSION         = 2          # ← change this to switch between bot versions
SYMBOL          = "XRPUSDT"
MIN_NEUTRAL_GAP = 3          # Structural filter — do not change unless you know why
API_URL         = "https://api.quantiota.org"
POLL_INTERVAL   = 1.0        # seconds
ENGINE_RESET_AT = 3500       # SKA engine resets every 3500 trades

# P band positions — universal constants at convergence scale, confirmed XRPUSDT+BTCUSDT
P_NEUTRAL_NEUTRAL = 1.00
P_NEUTRAL_BULL    = 0.66
P_X_NEUTRAL       = 0.51   # bull→neutral = bear→neutral
P_NEUTRAL_BEAR    = 0.14

# Thresholds derived from P band positions
BULL_THRESHOLD = P_NEUTRAL_NEUTRAL - P_NEUTRAL_BULL   # = 0.34
BEAR_THRESHOLD = P_NEUTRAL_NEUTRAL - P_NEUTRAL_BEAR   # = 0.86

# ΔP_pair — paired transition gap at convergence scale (observational reference)
DP_PAIR_BULL = P_NEUTRAL_BULL - P_X_NEUTRAL    # = 0.15
DP_PAIR_BEAR = P_X_NEUTRAL   - P_NEUTRAL_BEAR  # = 0.37

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


@dataclass
class Position:
    side:                  str
    entry_price:           float
    entry_trade_id:        int
    entry_time:            str
    entry_transition:      str
    exit_state:            str = field(default=WAIT_PAIR)
    neutral_neutral_count: int = field(default=0)


class TradingBot:
    """SKA paired cycle trading bot — regime classified from ΔP where P = exp(-|ΔH/H|).

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
        self.last_trade_id = 0
        self.tick_count    = 0   # counts processed transitions; resets with engine
        self._private_key  = None
        self._lot_filter   = None   # populated in run() when dry_run=False

        self.total_trades  = 0
        self.winners       = 0
        self.losers        = 0

        # PnL split: LONG = real spot execution, SHORT = synthetic signal tracking
        self.spot_pnl      = 0.0   # realized from real exchange LONGs only
        self.synthetic_pnl = 0.0   # synthetic SHORTs — no exchange orders
        self._csv_written  = False

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.results_file = f'bot_results_v{VERSION}_{symbol}_{ts}.csv'

    # ── SKA API ───────────────────────────────────────────────────────────────

    def fetch_transitions(self):
        """Fetch pre-computed regime transitions from /ska_bot/{symbol}."""
        try:
            r = requests.get(
                f"{self.api_url}/ska_bot/{self.symbol}",
                params={"since": self.last_trade_id},
                timeout=5
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
        qty = math.floor(qty / step) * step
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

    # ── State machine ─────────────────────────────────────────────────────────

    def process(self, transition):
        trade_id = transition['trade_id']
        price    = transition['price']
        name     = transition['transition_name']
        P        = transition['P']
        ts       = transition['timestamp']
        p_str    = f"{P:.4f}" if P is not None else "n/a"

        # === NO POSITION: look for entry ===
        if self.position is None:
            if name == 'neutral→bull':
                if not self.dry_run:
                    if not self._execute_buy(price):
                        logging.error("[ORDER] BUY failed — LONG not opened")
                        return
                self.position = Position('LONG', price, trade_id, ts, name)
                logging.info(f">>> OPEN LONG  @ {price:.6f} | P={p_str} | trade_id={trade_id}")
            elif name == 'neutral→bear':
                self.position = Position('SHORT', price, trade_id, ts, name)
                # No exchange order: SHORT tracked synthetically only
                logging.info(f">>> OPEN SHORT @ {price:.6f} | P={p_str} | trade_id={trade_id}")
            return

        pos = self.position

        # === LONG POSITION ===
        if pos.side == 'LONG':

            if pos.exit_state == WAIT_PAIR:
                if name == 'bull→neutral':
                    pos.exit_state = IN_NEUTRAL
                    logging.info(f"--- LONG pair confirmed | IN_NEUTRAL | trade_id={trade_id}")

            elif pos.exit_state == IN_NEUTRAL:
                if name == 'neutral→neutral':
                    pos.neutral_neutral_count += 1
                else:
                    if pos.neutral_neutral_count >= MIN_NEUTRAL_GAP:
                        pos.exit_state = READY
                        logging.info(
                            f"--- LONG gap closed ({name}) | READY "
                            f"| nn={pos.neutral_neutral_count} | trade_id={trade_id}"
                        )
                    else:
                        pos.neutral_neutral_count = 0

            elif pos.exit_state == READY:
                if name == 'neutral→bull':
                    pos.exit_state = WAIT_PAIR
                    pos.neutral_neutral_count = 0
                    logging.info(f"--- LONG cycle repeat | WAIT_PAIR | trade_id={trade_id}")
                elif name == 'neutral→bear':
                    pos.exit_state = EXIT_WAIT
                    logging.info(f"--- LONG opposite open | EXIT_WAIT | trade_id={trade_id}")

            elif pos.exit_state == EXIT_WAIT:
                if name == 'bear→neutral':
                    if not self.dry_run:
                        if not self._execute_sell(price):
                            logging.error("[ORDER] SELL failed — LONG not closed")
                            return
                    pnl = price - pos.entry_price
                    pnl_pct = (pnl / pos.entry_price) * 100
                    self._record(pnl, pnl_pct, price)
                    logging.info(
                        f"<<< CLOSE LONG @ {price:.6f} | "
                        f"PnL={pnl*10000:+.1f} pips ({pnl_pct:+.4f}%)"
                    )
                    self.position = Position('SHORT', price, trade_id, ts, 'neutral→bear')
                    # No exchange order: SHORT tracked synthetically — BUY re-enters LONG when SHORT closes
                    logging.info(f">>> OPEN SHORT @ {price:.6f} | trade_id={trade_id}")
                elif name == 'neutral→bull':
                    pos.exit_state = WAIT_PAIR
                    pos.neutral_neutral_count = 0
                    logging.info(f"--- LONG bear aborted | WAIT_PAIR | trade_id={trade_id}")

        # === SHORT POSITION ===
        elif pos.side == 'SHORT':

            if pos.exit_state == WAIT_PAIR:
                if name == 'bear→neutral':
                    pos.exit_state = IN_NEUTRAL
                    logging.info(f"--- SHORT pair confirmed | IN_NEUTRAL | trade_id={trade_id}")

            elif pos.exit_state == IN_NEUTRAL:
                if name == 'neutral→neutral':
                    pos.neutral_neutral_count += 1
                else:
                    if pos.neutral_neutral_count >= MIN_NEUTRAL_GAP:
                        pos.exit_state = READY
                        logging.info(
                            f"--- SHORT gap closed ({name}) | READY "
                            f"| nn={pos.neutral_neutral_count} | trade_id={trade_id}"
                        )
                    else:
                        pos.neutral_neutral_count = 0

            elif pos.exit_state == READY:
                if name == 'neutral→bear':
                    pos.exit_state = WAIT_PAIR
                    pos.neutral_neutral_count = 0
                    logging.info(f"--- SHORT cycle repeat | WAIT_PAIR | trade_id={trade_id}")
                elif name == 'neutral→bull':
                    pos.exit_state = EXIT_WAIT
                    logging.info(f"--- SHORT opposite open | EXIT_WAIT | trade_id={trade_id}")

            elif pos.exit_state == EXIT_WAIT:
                if name == 'bull→neutral':
                    if not self.dry_run:
                        if not self._execute_buy(price):
                            logging.error("[ORDER] BUY failed — SHORT not closed / LONG not re-entered")
                            return
                    pnl = pos.entry_price - price
                    pnl_pct = (pnl / pos.entry_price) * 100
                    self._record(pnl, pnl_pct, price)
                    logging.info(
                        f"<<< CLOSE SHORT @ {price:.6f} | "
                        f"PnL={pnl*10000:+.1f} pips ({pnl_pct:+.4f}%)"
                    )
                    self.position = Position('LONG', price, trade_id, ts, 'neutral→bull')
                    # No exchange order for OPEN LONG here — BUY already fired above to re-enter LONG inventory
                    logging.info(f">>> OPEN LONG  @ {price:.6f} | trade_id={trade_id}")
                elif name == 'neutral→bear':
                    pos.exit_state = WAIT_PAIR
                    pos.neutral_neutral_count = 0
                    logging.info(f"--- SHORT bull aborted | WAIT_PAIR | trade_id={trade_id}")

    # ── Recording ─────────────────────────────────────────────────────────────

    def _record(self, pnl, pnl_pct, exit_price):
        self.total_trades += 1
        if pnl > 0:
            self.winners += 1
        else:
            self.losers += 1

        is_real = (self.position.side == 'LONG')
        if is_real:
            self.spot_pnl += pnl
        else:
            self.synthetic_pnl += pnl

        row = {
            'side':             self.position.side,
            'real':             is_real,
            'entry':            self.position.entry_price,
            'exit':             exit_price,
            'pnl':              pnl,
            'entry_transition': self.position.entry_transition,
        }
        with open(self.results_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not self._csv_written:
                writer.writeheader()
                self._csv_written = True
            writer.writerow(row)

    def print_stats(self):
        wr       = self.winners / self.total_trades * 100 if self.total_trades else 0
        combined = self.spot_pnl + self.synthetic_pnl
        logging.info(
            f"=== Trades={self.total_trades} | W={self.winners} L={self.losers} | "
            f"Win={wr:.1f}% | "
            f"Spot PnL (real): {self.spot_pnl*10000:+.1f} pips | "
            f"Synthetic PnL: {self.synthetic_pnl*10000:+.1f} pips | "
            f"Combined: {combined*10000:+.1f} pips"
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        logging.info(
            f"SKA Trading Bot | symbol={self.symbol} | api={self.api_url} | "
            f"dry_run={self.dry_run}"
        )
        logging.info(f"MIN_NEUTRAL_GAP={MIN_NEUTRAL_GAP} | ENGINE_RESET_AT={ENGINE_RESET_AT}")
        logging.info(f"BULL_THRESHOLD={BULL_THRESHOLD} | BEAR_THRESHOLD={BEAR_THRESHOLD}")

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
                    self.process(t)
                    self.tick_count += 1
                if transitions:
                    self.last_trade_id = transitions[-1]['trade_id']

                if self.tick_count >= ENGINE_RESET_AT:
                    logging.info(f"Auto-stop: {self.tick_count} ticks >= {ENGINE_RESET_AT}")
                    break

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
                self._record(pnl, pnl_pct, close_price)
                logging.info(
                    f"<<< CLOSE {self.position.side} (end of run) @ {close_price:.6f} | "
                    f"PnL={pnl*10000:+.1f} pips | exit_state={self.position.exit_state}"
                )
                self.position = None
            self.print_stats()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SKA Paired Cycle Trading Bot')
    parser.add_argument('--symbol', default=SYMBOL,         help='Trading pair (default: XRPUSDT)')
    parser.add_argument('--api',    default=API_URL,         help='SKA-API base URL')
    parser.add_argument('--poll',   type=float, default=1.0, help='Poll interval seconds')
    parser.add_argument('--live',   action='store_true',     help='Enable live trading (default: dry run)')
    args = parser.parse_args()

    bot = TradingBot(
        symbol=args.symbol,
        api_url=args.api,
        poll_interval=args.poll,
        dry_run=not args.live,
    )
    bot.run()
