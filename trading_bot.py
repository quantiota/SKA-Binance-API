"""
SKA Paired Cycle Trading Bot
Connects to SKA-API, polls entropy per tick, applies paired cycle logic.

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

Usage:
    python trading_bot.py --symbol XRPUSDT
    python trading_bot.py --symbol BTCUSDT --api https://api.quantiota.org
"""

import argparse
import csv
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# ── User configuration ────────────────────────────────────────────────────────

SYMBOL          = "XRPUSDT"
MIN_NEUTRAL_GAP = 3          # Structural filter — do not change unless you know why
API_URL         = "https://api.quantiota.org"
POLL_INTERVAL   = 1.0        # seconds
ENGINE_RESET_AT = 3500       # SKA engine resets every 3500 trades

# ── State machine ─────────────────────────────────────────────────────────────

WAIT_PAIR  = 'WAIT_PAIR'
IN_NEUTRAL = 'IN_NEUTRAL'
READY      = 'READY'
EXIT_WAIT  = 'EXIT_WAIT'

TRANSITION_NAMES = {
    0: 'neutral→neutral', 1: 'neutral→bull', 2: 'neutral→bear',
    3: 'bull→neutral',    4: 'bull→bull',    5: 'bull→bear',
    6: 'bear→neutral',    7: 'bear→bull',    8: 'bear→bear',
}


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

    def __init__(self, symbol: str, api_url: str, poll_interval: float):
        self.symbol        = symbol
        self.api_url       = api_url
        self.poll_interval = poll_interval
        self.position: Optional[Position] = None
        self.last_trade_id = 0

        self.total_trades  = 0
        self.winners       = 0
        self.losers        = 0
        self.total_pnl     = 0.0

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.results_file = f'trading_bot_{symbol}_{ts}.csv'
        self._csv_written  = False

    # ── API ───────────────────────────────────────────────────────────────────

    def fetch_ticks(self):
        """Fetch ticks since last_trade_id - 2 (two-tick overlap for transition continuity)."""
        since = max(0, self.last_trade_id - 2)
        try:
            r = requests.get(
                f"{self.api_url}/ticks/{self.symbol}",
                params={"since": since},
                timeout=5
            )
            r.raise_for_status()
            return r.json().get("ticks", [])
        except Exception as e:
            logging.warning(f"API error: {e}")
            return []

    # ── Transition computation ────────────────────────────────────────────────

    def get_transitions(self, ticks):
        """
        Compute regime transitions from consecutive ticks.
        Mirrors the SQL LAG() logic in trading_bot_v1.py.
        Returns only new transitions (trade_id > last_trade_id).
        Probability P = exp(-|Δentropy / entropy|) — same as original bot.
        """
        ticks = sorted(ticks, key=lambda t: t['trade_id'])
        results = []
        for i in range(2, len(ticks)):
            t0, t1, t2 = ticks[i-2], ticks[i-1], ticks[i]

            dp      = t2['price'] - t1['price']
            prev_dp = t1['price'] - t0['price']

            regime      = 1 if dp > 0      else (2 if dp < 0      else 0)
            prev_regime = 1 if prev_dp > 0 else (2 if prev_dp < 0 else 0)
            code = prev_regime * 3 + regime
            name = TRANSITION_NAMES.get(code, 'unknown')

            # Transition probability from entropy (same formula as original)
            e      = t2.get('entropy')
            e_prev = t1.get('entropy')
            if e is not None and e_prev is not None and e != 0:
                P = math.exp(-abs((e - e_prev) / e))
            else:
                P = None

            # Skip already-processed ticks (overlap region)
            if t2['trade_id'] <= self.last_trade_id:
                continue

            results.append({
                'trade_id':  t2['trade_id'],
                'timestamp': t2['timestamp'],
                'price':     t2['price'],
                'P':         P,
                'transition_code': code,
                'transition_name': name,
            })
        return results

    # ── State machine ─────────────────────────────────────────────────────────

    def process(self, transition):
        trade_id = transition['trade_id']
        price    = transition['price']
        name     = transition['transition_name']
        P        = transition['P']
        ts       = transition['timestamp']

        # === NO POSITION: look for entry ===
        if self.position is None:
            if name == 'neutral→bull':
                self.position = Position('LONG', price, trade_id, ts, name)
                p_str = f"{P:.4f}" if P is not None else "n/a"
                logging.info(f">>> OPEN LONG  @ {price:.6f} | P={p_str} | trade_id={trade_id}")
            elif name == 'neutral→bear':
                self.position = Position('SHORT', price, trade_id, ts, name)
                p_str = f"{P:.4f}" if P is not None else "n/a"
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
                    logging.info(f"--- LONG exit wait | EXIT_WAIT | trade_id={trade_id}")

            elif pos.exit_state == EXIT_WAIT:
                if name == 'bear→neutral':
                    pnl = price - pos.entry_price
                    self._record(pnl, price, 'LONG')
                    logging.info(f"<<< CLOSE LONG @ {price:.6f} | PnL={pnl*10000:+.1f} pips")
                    self.position = Position('SHORT', price, trade_id, ts, 'neutral→bear')
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
                    logging.info(f"--- SHORT exit wait | EXIT_WAIT | trade_id={trade_id}")

            elif pos.exit_state == EXIT_WAIT:
                if name == 'bull→neutral':
                    pnl = pos.entry_price - price
                    self._record(pnl, price, 'SHORT')
                    logging.info(f"<<< CLOSE SHORT @ {price:.6f} | PnL={pnl*10000:+.1f} pips")
                    self.position = Position('LONG', price, trade_id, ts, 'neutral→bull')
                    logging.info(f">>> OPEN LONG  @ {price:.6f} | trade_id={trade_id}")
                elif name == 'neutral→bear':
                    pos.exit_state = WAIT_PAIR
                    pos.neutral_neutral_count = 0
                    logging.info(f"--- SHORT bull aborted | WAIT_PAIR | trade_id={trade_id}")

    # ── Recording ─────────────────────────────────────────────────────────────

    def _record(self, pnl, exit_price, side):
        self.total_trades += 1
        self.total_pnl    += pnl
        if pnl > 0:
            self.winners += 1
        else:
            self.losers += 1
        row = {
            'side':             side,
            'entry':            self.position.entry_price,
            'exit':             exit_price,
            'pnl':              pnl,
            'pnl_pips':         round(pnl / 0.0001, 1),
            'entry_transition': self.position.entry_transition,
        }
        with open(self.results_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not self._csv_written:
                writer.writeheader()
                self._csv_written = True
            writer.writerow(row)

    def print_stats(self):
        wr = self.winners / self.total_trades * 100 if self.total_trades else 0
        logging.info(
            f"=== Trades={self.total_trades} | W={self.winners} L={self.losers} | "
            f"Win={wr:.1f}% | PnL={self.total_pnl*10000:+.1f} pips"
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        logging.info(f"SKA Trading Bot | symbol={self.symbol} | api={self.api_url}")
        logging.info(f"MIN_NEUTRAL_GAP={MIN_NEUTRAL_GAP} | ENGINE_RESET_AT={ENGINE_RESET_AT}")

        try:
            while True:
                ticks = self.fetch_ticks()
                if len(ticks) >= 3:
                    transitions = self.get_transitions(ticks)
                    for t in transitions:
                        self.process(t)
                    if ticks:
                        self.last_trade_id = max(t['trade_id'] for t in ticks)

                if self.last_trade_id >= ENGINE_RESET_AT:
                    logging.info("Engine reset — closing position and restarting")
                    self.position      = None
                    self.last_trade_id = 0

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            logging.info("Stopped by user")
        finally:
            self.print_stats()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SKA Paired Cycle Trading Bot')
    parser.add_argument('--symbol', default=SYMBOL,        help='Trading pair (default: XRPUSDT)')
    parser.add_argument('--api',    default=API_URL,        help='SKA-API base URL')
    parser.add_argument('--poll',   type=float, default=1.0, help='Poll interval seconds')
    args = parser.parse_args()

    bot = TradingBot(symbol=args.symbol, api_url=args.api, poll_interval=args.poll)
    bot.run()
