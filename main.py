"""Pump.fun Bot Sprint R3: Second-Wind Dip Rider (v3).

Strategy, found by measuring the kit v2 dev dataset with slot-faithful
fills (every order fills at the price two slots after the decision, the way
the replay engine actually settles them):

- v1/v2 chased the burst: a coin that takes in >= 15 SOL of buys within its
  first 15 trades. Trade-by-trade that looked like +2.60 SOL. It was an
  illusion: during a burst a dozen trades land in one slot, so the buy fills
  two slots later, deep into the pump, and the sell fills two slots later,
  after the dump has started. Measured with real fill timing the same rule
  is -0.66 SOL in simulation and -0.34 SOL on grade-local. Latency eats
  every strategy that buys a rising price.
- The same fill timing FLATTERS a contrarian entry: buy while the price is
  falling and the fill lands lower than the decision price; sell while the
  price is rising and the fill lands higher. So this version rides the
  second wind: it waits for a coin that already proved it can pump (first
  peak >= 3x its creation price), lets it fall 30% off that peak, and
  enters on the first trade that bounces 20% off the running low. It exits
  at +20% over the fill price, or after 40 trades, whichever comes first.
  The other angles measured the same way are all negative: sniping the
  creator's first trade (-5.9 SOL), late-curve entries (-1.3 SOL), buying
  the fall without a bounce (-0.28 SOL at best), creator-exit riders.
- The dip rule is the only one that measured positive on the dev window
  (+0.18 SOL over 34 coins, 19 wins), and the margin is thin -- this is a
  small edge on a small sample, not a landslide. The stress test is the
  arbiter; if it does not hold there, this entry is repo-only.

Rules (all deterministic: no clock, no randomness, no network):
- One probe per mint, never a re-entry. Probe = 0.15 SOL (capped at 90%
  of the per-mint size cap the hello message carries).
- Entry: peak >= 3x creation price, then a pullback to <= 70% of that
  peak, then the first trade at >= 1.20x the running low since the peak.
- Exit: sell everything at the first trade at >= 1.20x the probe fill
  price, or once 40 trades have printed since the fill.
- At most 5 open positions (the hello caps), at most 16 orders per batch.
- Every rule is tested after EVERY trade, using that trade's own
  reserves: the winning coins arrive in bursts, and a bot that checks
  once per batch sees a coin jump past its whole window in one batch.

The bot speaks agent-fun/replay/v2: the harness sends hello, then one batch
per slot, then done. Each batch carries the slot's events, marks and fills;
the bot answers with one reply per batch echoing its seq, listing the
orders decided on that slot.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bot

LAM = makefun_bot.LAMPORTS_PER_SOL

PROBE_SOL = 0.15
PEAK_MIN = 3.0            # first peak must reach this x the creation price
PULLBACK = 0.30           # then fall this far off the peak before arming
BOUNCE = 1.20             # enter on the first trade this x the running low
TAKE_PROFIT = 1.20        # exit at this x the probe fill price
HOLD_TRADES = 40          # or after this many trades since the fill
BUY_SLIPPAGE_BPS = 2000
SELL_SLIPPAGE_BPS = 2000
SIZE_FRACTION_BPS = 9000   # use 90% of the per-mint size cap


class Coin:
    """Per-mint dip state, built from the batches the harness sends."""

    __slots__ = (
        "trades",
        "creation_price",
        "peak",
        "low",
        "armed",
        "entered",
        "fill_price",
        "fill_trades",
        "exit_sent",
    )

    def __init__(self):
        self.trades = 0
        self.creation_price = 0.0
        self.peak = 0.0
        self.low = 0.0
        self.armed = False
        self.entered = False
        self.fill_price = 0.0
        self.fill_trades = 0
        self.exit_sent = False


COINS = {}


def coin_for(mint):
    coin = COINS.get(mint)
    if coin is None:
        coin = Coin()
        COINS[mint] = coin
    return coin


def probe_size_lamports(state, mint, want_sol):
    """min(want, 90% of the mint's size cap); 0 when the cap is unknown."""
    cap = state.max_buy_lamports(mint)
    if cap <= 0:
        return 0
    want = int(want_sol * LAM)
    return min(want, cap * SIZE_FRACTION_BPS // 10000)


def on_batch(state, batch):
    orders = []

    # 1. Fold this batch's fills in first: record probe fill prices (and the
    #    trade count at the fill, which anchors the hold), and clear the
    #    exit flag of a sell the harness rejected so it can be retried.
    for fill in batch["fills"]:
        coin = COINS.get(fill["mint"])
        if coin is None:
            continue
        if fill["status"] == "rejected":
            if fill["side"] == "buy" and coin.entered and coin.fill_price == 0.0:
                coin.entered = False
            elif fill["side"] == "sell":
                coin.exit_sent = False
            continue
        if fill["status"] != "filled":
            continue
        if fill["side"] == "buy" and coin.fill_price == 0.0:
            tokens = int(fill["token_amount"])
            if tokens > 0:
                coin.fill_price = int(fill["quote_lamports"]) / tokens
                coin.fill_trades = coin.trades

    # 2. Walk this batch's trades one by one. The creation price comes from
    #    the mint's CreateEvent; the dip state machine runs on every trade
    #    after that, using that trade's own reserves, so a burst of trades
    #    in one slot is still judged trade by trade.
    for event in batch["events"]:
        kind = event["event"]
        mint = event["mint"]
        coin = coin_for(mint)
        if kind == "CreateEvent":
            token_reserves = int(event["virtual_token_reserves"])
            if token_reserves > 0:
                coin.creation_price = (
                    int(event["virtual_quote_reserves"]) / token_reserves
                )
            continue
        if kind != "TradeEvent":
            continue
        if coin.creation_price <= 0.0:
            continue
        coin.trades += 1
        token_reserves = int(event["virtual_token_reserves"])
        if token_reserves <= 0:
            continue
        price = int(event["virtual_quote_reserves"]) / token_reserves
        mult = price / coin.creation_price

        if coin.fill_price > 0.0:
            # Position open: exit at the take-profit touch, or after the
            # hold expires. A rejected sell clears exit_sent (step 1), so
            # the next trade retries it.
            since_fill = coin.trades - coin.fill_trades
            if not coin.exit_sent and (
                price >= coin.fill_price * TAKE_PROFIT
                or since_fill >= HOLD_TRADES
            ):
                holding = state.positions.get(mint)
                if holding is not None and int(holding.token_amount) > 0:
                    orders.append(
                        {
                            "side": "sell",
                            "mint": mint,
                            "token_amount": int(holding.token_amount),
                            "max_slippage_bps": SELL_SLIPPAGE_BPS,
                        }
                    )
                    coin.exit_sent = True
            continue

        if coin.entered:
            continue
        if coin.peak == 0.0:
            # No peak yet: watch for the first trade at >= PEAK_MIN x.
            if mult >= PEAK_MIN:
                coin.peak = mult
                coin.low = mult
            continue
        # The low is the running minimum since the peak, frozen once the
        # pullback arms the trade -- exactly the definition the offline
        # measurement used, so the bounce threshold does not drift down
        # while the price keeps falling after arming.
        if not coin.armed and mult < coin.low:
            coin.low = mult
        if not coin.armed and coin.low <= coin.peak * (1.0 - PULLBACK):
            coin.armed = True
        if coin.armed and mult >= coin.low * BOUNCE:
            if state.committed_position_count() >= state.hello["caps"][
                "max_open_positions"
            ]:
                continue
            size = probe_size_lamports(state, mint, PROBE_SOL)
            if size <= 0 or state.free_cash_lamports() < size + state.tx_fee_lamports():
                continue
            curve = state.curves.get(mint)
            if curve is not None and curve.complete:
                continue
            orders.append(
                {
                    "side": "buy",
                    "mint": mint,
                    "quote_lamports": size,
                    "max_slippage_bps": BUY_SLIPPAGE_BPS,
                }
            )
            coin.entered = True

    return orders


makefun_bot.run(on_batch)
