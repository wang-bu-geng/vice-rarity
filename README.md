# vice-rarity

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/wang-bu-geng/vice-rarity/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/wang-bu-geng/vice-rarity/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

An offline Python forecaster for the five quantiles of each GTA VI PS5 trophy's published Exophase earn rate.

## Run it

```sh
MAKEFUN_INPUT_DIR=../gta6-trophy-rarity-forecast-01-kit/input \
MAKEFUN_OUTPUT_DIR=/tmp/vice-rarity-output python3 main.py
```

The grader uses Python 3.13 and the default directories, `/input` and `/output`. Each input case produces one JSON forecast. The program uses the standard library and a fixed random seed.

## Model

Identical page reads collapse into refresh epochs. Changes in tracked players form arrival cohorts. Forecast scenarios vary the next refresh time and the pace of new arrivals, allowing new players to dilute rates while existing players continue earning trophies.

Trophy descriptions and tiers supply broad priors for time to unlock. The model weights candidate unlock curves by their fit to observed earn counts and blends in a damped recent count trend when the history supports one. Small-count smoothing, an explicit probability of staying at the ceiling, and rounding to the page's precision represent uncertainty at both boundaries.

---
<sub>Built for [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
