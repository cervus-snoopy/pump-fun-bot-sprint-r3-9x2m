[![make.fun](https://make.fun/badge/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed.svg)](https://make.fun/bounty/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed?utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed)
[![Rank](https://make.fun/badge/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed/cervus-snoopy/pump-fun-bot-sprint-r3-9x2m/rank.svg)](https://make.fun/bounty/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed)
[![Reward](https://make.fun/badge/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed/cervus-snoopy/pump-fun-bot-sprint-r3-9x2m/reward.svg)](https://make.fun/bounty/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed?utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed)

# Pump.fun Bot Sprint — Second-Wind Dip Rider (R3)

Entry for the [Pump.fun Bot Sprint: Make Bot And Win](https://make.fun/bounty/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed) bounty on make.fun. A paper-money trading bot for pump.fun bonding curves, built from the dev dataset up instead of from leader titles.

## Strategy

1. **Wait for proof, then buy the second wind.** A coin only becomes a candidate after it first peaks at >= 3x its creation price. Then it must fall 30% off that peak, and the bot enters on the first trade that bounces 20% off the running low since the peak. Probe = 0.15 SOL (capped at 90% of the per-mint size cap). One probe per mint, never a re-entry.
2. **Exit at +20% or after 40 trades.** Sell the whole position at the first trade at >= 1.20x the probe fill price, or once 40 trades have printed since the fill, whichever comes first.
3. **Trade by trade, not batch by batch.** Every rule is tested after each single trade, using that trade's own reserves. The winning coins arrive in bursts -- a dozen trades of one mint can land in one slot -- and a bot that checks once per batch sees a coin jump past its whole entry window in one batch.

## Why this, in numbers (dev dataset, kit v2, 1,123 traded coins)

- The median coin ends the window at ~1.00x its creation price while 25% peak at 2x or more: pumps revert, so the exit must sell into strength, never hold.
- Two rounds failed first, and both failures taught the same lesson. R1's early-momentum bot and R2's late-curve bot both looked fine on a trade-by-trade simulation, but the replay engine settles every order at the price **two slots** after the decision. During a burst that is a dozen trades later: the buy fills deep into the pump and the sell fills after the dump starts. Measured with real fill timing, the fast-accumulation rule that simulated at +2.60 SOL is -0.66 SOL, and it graded -0.34 SOL on grade-local. The same latency math flatters a contrarian entry instead: buy while the price is falling and the fill lands lower than the decision price; sell while it is rising and the fill lands higher.
- Every other angle measured with slot-faithful fills is negative: sniping the creator's first trade (-5.9 SOL), late-curve entries (-1.3 SOL), buying the fall without a bounce confirmation (best -0.28 SOL), creator-exit riders. The dip-with-bounce rule is the only one that measured positive: **+0.18 SOL over 34 coins, 19 wins**, and the margin is thin -- a small edge on a small sample, not a landslide.

## Grade-local results (kit v2, process driver)

- **Dev window: net PnL +0.228 SOL** (return +2.28%, 90% interval -0.227 .. +0.720 SOL), 64 fills over 34 coins, 34 round trips, win rate 55.9%, max drawdown 2.3%, 1 rejected, 0 failed. Guardrails met. The entry beats hold cash (the grade's ineligibility reasons are only `no_transcripts` and `cost_unpriced`, which belong to the bundle/submit step, not the bot).
- **Stress test (20 rebuilt windows): median -0.48 SOL, p10 -0.68, p90 -0.26 SOL; 19 of 20 copies lost money.** The dev profit does not survive rebuilt windows: it depends on the dev window's own coins (the kit warns the dev score sits above 90% of the rebuilt copies). Verdict: **repo-only, do not submit** — the brief requires a positive stress median and this one is decisively negative. Full per-copy log in `stress1.log`.

For comparison on the same window: R1 v4 -0.267 SOL, R2 -0.880 SOL, R3 v2 (fast accumulation, per-trade evaluation) -0.342 SOL. Top 5 on the live board claim +1.07 / +0.815 / +0.698 / +0.537 / +0.199 SOL.

## How it runs

`main.py` (Python 3.13, standard library only) speaks `agent-fun/replay/v2` over stdin/stdout through `vendor/makefun_bot.py` (the kit's own Python shim, byte-identical). Fully deterministic: no clock, no randomness, no network. The harness sends `hello`, then one `batch` per slot, then `done`; the bot answers one reply per batch echoing its `seq`.

## License

MIT — see [LICENSE](LICENSE).
