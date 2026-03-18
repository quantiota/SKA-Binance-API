# SKA Binance API
The system does not simulate the market. It observes the market as it truly operates across the nine regime transitions.

## Architecture

```mermaid
flowchart TD
    BINANCE[(Binance Tick Data)]
    API["SKA API"]
    BOT@{ shape: diamond, label: "Trading Bot" }

    BINANCE -- "symbol" --> API
    API -- "entropy" --> BOT

    BOT --> LONG
    BOT --> SHORT

    subgraph LONG["LONG"]
        direction TB
        L1["neutral→bull<br/><i>OPEN / WAIT_PAIR</i>"]
        L2["bull→neutral<br/><i>pair confirmed / IN_NEUTRAL</i>"]
        L3["neutral→neutral × N (N≥3)<br/><i>neutral gap / READY</i>"]
        L4["neutral→bear<br/><i>opp. cycle opens / EXIT_WAIT</i>"]
        L5["bear→neutral<br/><i>opp. pair confirmed / CLOSE LONG</i>"]
        L1 --> L2 --> L3 --> L4 --> L5
        L3 -. "↺ repeats" .-> L1
    end

    subgraph SHORT["SHORT"]
        direction TB
        S1["neutral→bear<br/><i>OPEN / WAIT_PAIR</i>"]
        S2["bear→neutral<br/><i>pair confirmed / IN_NEUTRAL</i>"]
        S3["neutral→neutral × N (N≥3)<br/><i>neutral gap / READY</i>"]
        S4["neutral→bull<br/><i>opp. cycle opens / EXIT_WAIT</i>"]
        S5["bull→neutral<br/><i>opp. pair confirmed / CLOSE SHORT</i>"]
        S1 --> S2 --> S3 --> S4 --> S5
        S3 -. "↺ repeats" .-> S1
    end

    classDef data      fill:#E3F2FD,stroke:#1E88E5,stroke-width:2px;
    classDef process   fill:#E8F5E9,stroke:#43A047,stroke-width:2px;
    classDef longOpen  fill:#A8DFBC,stroke:#AAAAAA,color:#000,stroke-width:1.5px;
    classDef longPair  fill:#C8F0A8,stroke:#AAAAAA,color:#000,stroke-width:1.5px;
    classDef shortOpen fill:#FFAAAA,stroke:#AAAAAA,color:#000,stroke-width:1.5px;
    classDef shortPair fill:#FFD0A0,stroke:#AAAAAA,color:#000,stroke-width:1.5px;
    classDef neutral   fill:#E8E8E8,stroke:#AAAAAA,color:#000,stroke-width:1.5px;

    class BINANCE data;
    class API,BOT process;
    class L1 longOpen;
    class L2 longPair;
    class L3 neutral;
    class L4 shortOpen;
    class L5 shortPair;
    class S1 shortOpen;
    class S2 shortPair;
    class S3 neutral;
    class S4 longOpen;
    class S5 longPair;
```


## Supported Symbols

`XRPUSDT` · `BTCUSDT` · `ETHUSDT` · `SOLUSDT`



## API

**Base URL:** `https://api.quantiota.org`

### `GET /ticks/{symbol}`

Returns the latest ticks with entropy for the given symbol.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol`  | path | —       | Trading pair (`XRPUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`) |
| `since`   | query | `0`   | Return only ticks with `trade_id > since` |

**Response**

```json
{
  "symbol": "XRPUSDT",
  "since": 0,
  "count": 3,
  "ticks": [
    {
      "trade_id": 1001,
      "timestamp": "2026-03-18T10:00:00.000000Z",
      "price": 2.3451,
      "volume": 120.5,
      "entropy": 0.182
    }
  ]
}
```



## Monitor

`bot_monitor.py` watches the folder for result CSVs, computes cumulative P&L after each new file, saves a report, and sends it by email.

```bash
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
export GMAIL_FROM="your@gmail.com"
export GMAIL_TO="your@gmail.com"
python bot_monitor.py
```


## Getting Started

**Requirements:** Python 3.9+

```bash
git clone https://github.com/quantiota/SKA-Binance-API.git
cd SKA-Binance-API/ska_api_client
pip install -r requirements.txt
python trading_bot.py --symbol XRPUSDT
```

The bot connects to `https://api.quantiota.org` by default and saves trades to a CSV file (`trading_bot_XRPUSDT_<timestamp>.csv`). The SKA-API restarts and resets every 3500 trades — the bot handles this transparently via the `since` parameter.

**Arguments**

| Argument   | Default                        | Description          |
|------------|--------------------------------|----------------------|
| `--symbol` | `XRPUSDT`                     | Trading pair         |
| `--api`    | `https://api.quantiota.org`   | SKA-API base URL     |
| `--poll`   | `1.0`                         | Poll interval (sec)  |

## Prototype

A ready-to-use trading bot prototype is provided as a starting point. It demonstrates how to consume the API and apply the signal logic — not intended for production deployment.

## User Customization

```python
SYMBOL          = "XRPUSDT"   # XRPUSDT · BTCUSDT · ETHUSDT · SOLUSDT
MIN_NEUTRAL_GAP = 3            # Structural filter
```



## ToDo

- [ ] Add Binance API credentials (key + secret)
- [ ] Define position size
- [ ] Implement order execution on OPEN and CLOSE signals


## Contents

```
├── README.md           — documentation
├── requirements.txt    — dependencies
├── trading_bot.py      — PCT state machine, polls /ticks/{symbol}
└── bot_monitor.py      — scans results, generates reports, sends email
```

## Dashboard

Each panel displays 4 metrics per symbol, reset every 3500 trades: price, regime transition probabilities, accumulated volume, and entropy.

- [XRPUSDT](https://grafana.quantiota.org/public-dashboards/6506763639364be8bab7e6c60cc8432a)

- BTCUSDT

- ETHUSDT

- SOLUSDT

## Contributing

Contributions are welcome — strategy variants, new symbols, execution integrations, or performance improvements.

Open an issue or submit a pull request.

