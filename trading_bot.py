"""
SKA Paired Cycle Trading Bot
Connects to SKA-API, polls entropy per tick, applies paired cycle logic.

Usage:
    python trading_bot.py --symbol XRPUSDT
    python trading_bot.py --symbol BTCUSDT --api https://api.quantiota.org
"""

import argparse
import csv
import logging
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

# ── State machine ─────────────────────────────────────────────────────────────

WAIT_PAIR  = 'WAIT_PAIR'
IN_NEUTRAL = 'IN_NEUTRAL'
READY      = 'READY'
EXIT_WAIT  = 'EXIT_WAIT'


@dataclass
class Position:
    side:            str
    entry_price:     float
    entry_trade_id:  int
    entry_time:      str
    exit_state:      str = field(default=WAIT_PAIR)
    nn_count:        int = field(default=0)


class TradingBot:

    def __init__(self, symbol: str, api_url: str, poll_interval: float):
        self.symbol        = symbol
        self.api_url       = api_url
        self.poll_interval = poll_interval
        self.position: Optional[Position] = None
        self.last_trade_id = 0
        self.last_price    = None

        self.total_trades  = 0
        self.winners       = 0
        self.losers        = 0
        self.total_pnl     = 0.0

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.results_file = f'trading_bot_{symbol}_{ts}.csv'
        self._csv_written  = False

    def fetch_ticks(self):
        try:
            r = requests.get(
                f"{self.api_url}/ticks/{self.symbol}",
                params={"since": self.last_trade_id},
                timeout=5
            )
            r.raise_for_status()
            return r.json().get("ticks", [])
        except Exception as e:
            logging.warning(f"API error: {e}")
            return []

    def get_transitions(self, ticks):
        results = []
        prices = [t['price'] for t in ticks]
        for i in range(2, len(prices)):
            dp      = prices[i]   - prices[i-1]
            prev_dp = prices[i-1] - prices[i-2]
            regime      = 1 if dp > 0 else (2 if dp < 0 else 0)
            prev_regime = 1 if prev_dp > 0 else (2 if prev_dp < 0 else 0)
            code = prev_regime * 3 + regime
            names = {
                0: 'n→n',    1: 'n→bull',  2: 'n→bear',
                3: 'bull→n', 6: 'bear→n',
            }
            results.append((ticks[i], names.get(code, 'other')))
        return results

    def process(self, tick, name):
        trade_id = tick['trade_id']
        price    = tick['price']
        ts       = tick['timestamp']

        if self.position is None:
            if name == 'n→bull':
                self.position = Position('LONG', price, trade_id, ts)
                logging.info(f">>> OPEN LONG  @ {price:.4f} | trade_id={trade_id}")
            elif name == 'n→bear':
                self.position = Position('SHORT', price, trade_id, ts)
                logging.info(f">>> OPEN SHORT @ {price:.4f} | trade_id={trade_id}")
            return

        pos = self.position

        if pos.side == 'LONG':
            if pos.exit_state == WAIT_PAIR:
                if name == 'bull→n':
                    pos.exit_state = IN_NEUTRAL
                    logging.info(f"--- LONG pair confirmed | IN_NEUTRAL | trade_id={trade_id}")
            elif pos.exit_state == IN_NEUTRAL:
                if name == 'n→n':
                    pos.nn_count += 1
                else:
                    if pos.nn_count >= MIN_NEUTRAL_GAP:
                        pos.exit_state = READY
                        logging.info(f"--- LONG gap closed nn={pos.nn_count} | READY | trade_id={trade_id}")
                    else:
                        pos.nn_count = 0
            elif pos.exit_state == READY:
                if name == 'n→bull':
                    pos.exit_state = WAIT_PAIR
                    pos.nn_count   = 0
                    logging.info(f"--- LONG cycle repeat | WAIT_PAIR | trade_id={trade_id}")
                elif name == 'n→bear':
                    pos.exit_state = EXIT_WAIT
                    logging.info(f"--- LONG exit wait | EXIT_WAIT | trade_id={trade_id}")
            elif pos.exit_state == EXIT_WAIT:
                if name == 'bear→n':
                    pnl = price - pos.entry_price
                    self._record(pnl, price, 'LONG')
                    logging.info(f"<<< CLOSE LONG @ {price:.4f} | PnL={pnl*10000:+.1f} pips")
                    self.position = Position('SHORT', price, trade_id, ts)
                    logging.info(f">>> OPEN SHORT @ {price:.4f} | trade_id={trade_id}")
                elif name == 'n→bull':
                    pos.exit_state = WAIT_PAIR
                    pos.nn_count   = 0

        elif pos.side == 'SHORT':
            if pos.exit_state == WAIT_PAIR:
                if name == 'bear→n':
                    pos.exit_state = IN_NEUTRAL
                    logging.info(f"--- SHORT pair confirmed | IN_NEUTRAL | trade_id={trade_id}")
            elif pos.exit_state == IN_NEUTRAL:
                if name == 'n→n':
                    pos.nn_count += 1
                else:
                    if pos.nn_count >= MIN_NEUTRAL_GAP:
                        pos.exit_state = READY
                        logging.info(f"--- SHORT gap closed nn={pos.nn_count} | READY | trade_id={trade_id}")
                    else:
                        pos.nn_count = 0
            elif pos.exit_state == READY:
                if name == 'n→bear':
                    pos.exit_state = WAIT_PAIR
                    pos.nn_count   = 0
                    logging.info(f"--- SHORT cycle repeat | WAIT_PAIR | trade_id={trade_id}")
                elif name == 'n→bull':
                    pos.exit_state = EXIT_WAIT
                    logging.info(f"--- SHORT exit wait | EXIT_WAIT | trade_id={trade_id}")
            elif pos.exit_state == EXIT_WAIT:
                if name == 'bull→n':
                    pnl = pos.entry_price - price
                    self._record(pnl, price, 'SHORT')
                    logging.info(f"<<< CLOSE SHORT @ {price:.4f} | PnL={pnl*10000:+.1f} pips")
                    self.position = Position('LONG', price, trade_id, ts)
                    logging.info(f">>> OPEN LONG  @ {price:.4f} | trade_id={trade_id}")
                elif name == 'n→bear':
                    pos.exit_state = WAIT_PAIR
                    pos.nn_count   = 0

    def _record(self, pnl, exit_price, side):
        self.total_trades += 1
        self.total_pnl    += pnl
        if pnl > 0:
            self.winners += 1
        else:
            self.losers += 1
        row = {
            'side':     side,
            'entry':    self.position.entry_price,
            'exit':     exit_price,
            'pnl':      pnl,
            'pnl_pips': round(pnl / 0.0001, 1),
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

    def run(self):
        logging.info(f"SKA Trading Bot | symbol={self.symbol} | api={self.api_url}")
        logging.info(f"MIN_NEUTRAL_GAP={MIN_NEUTRAL_GAP}")

        try:
            while True:
                ticks = self.fetch_ticks()
                if len(ticks) >= 3:
                    transitions = self.get_transitions(ticks)
                    for tick, name in transitions:
                        self.process(tick, name)
                    self.last_trade_id = ticks[-1]['trade_id']

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            logging.info("Stopped by user")
        finally:
            self.print_stats()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SKA Paired Cycle Trading Bot')
    parser.add_argument('--symbol', default=SYMBOL,         help='Trading symbol (default: XRPUSDT)')
    parser.add_argument('--api',    default=API_URL,         help='SKA-API URL')
    parser.add_argument('--poll',   type=float, default=1.0, help='Poll interval seconds')
    args = parser.parse_args()

    bot = TradingBot(symbol=args.symbol, api_url=args.api, poll_interval=args.poll)
    bot.run()
