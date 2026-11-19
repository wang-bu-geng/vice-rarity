"""Forecast published trophy rates from cohort age and refresh histories."""
import json
import math
import os
import random
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from statistics import median

LEVELS = (0.05, 0.25, 0.50, 0.75, 0.95)


def day(value):
    return datetime.fromisoformat(value).timestamp() / 86400


def logit(p):
    p = min(1 - 1e-8, max(1e-8, p))
    return math.log(p / (1 - p))


def progression(trophy):
    words = trophy["description"].lower()
    chapter = re.search(r"complete chapter (\d+)", words)
    if chapter:
        return (0.4, 1.0, 1.9, 3.2, 4.5)[min(5, max(1, int(chapter[1]))) - 1], 1.5
    if trophy["tier"] == "platinum" or "100% completion" in words:
        return 9, 2.2
    if words.strip(". ") == "complete the final mission":
        return 4.5, 1.6
    if re.search(r"\b(all|every|100|250|50)\b", words):
        return 4.2, 1.55
    if re.search(r"\b(complete|win|earn|purchase|register)\b", words):
        return 1.7, 1.15
    return 0.9, 1.0


def epochs(history):
    result = []
    last_read = None
    for row in history:
        time = day(row["at"])
        snapshot = max(1, row["players_tracked"]), row["rates"]
        if not result or result[-1][1:] != snapshot:
            update = time if last_read is None else (time + last_read) / 2
            result.append((update, *snapshot))
        last_read = time
    return result


def unlock(age, scale, shape):
    return -math.expm1(-(max(0, age) / scale) ** shape)


def cohort_mass(cohorts, time, scale, shape):
    return sum(size * unlock(time - start, scale, shape)
               for start, size in cohorts if start < time)


def player_paths(rows, checkpoint, target):
    end, size, _ = rows[-1]
    gaps = [b[0] - a[0] for a, b in zip(rows, rows[1:]) if b[0] - a[0] > 0.025]
    period = min(1.2, max(0.07, median(gaps[-12:]))) if gaps else 0.32
    slopes = [math.log(size / old_size) / (end - time)
              for time, old_size, _ in rows[:-1] if 0.12 <= end - time <= 1.1]
    if not slopes and len(rows) > 1:
        slopes = [math.log(size / rows[0][1]) / max(0.1, end - rows[0][0])]
    growth = min(2.8, max(0, median(slopes))) if slopes else 0
    rng = random.Random(462991)
    paths = []
    for _ in range(384):
        cadence = period * math.exp(0.65 * rng.gauss(0, 1))
        lag = max(0.012, cadence - (checkpoint - end))
        first = checkpoint + lag * rng.uniform(0.45, 1.55)
        refresh = end if first > target else first + cadence * int((target - first) / cadence)
        days = refresh - end
        intensity = max(0, growth + (0.36 + 0.28 * growth) * rng.gauss(0, 1))
        expansion = intensity * 1.45 * math.log1p(days / 1.45)
        if len(rows) == 1:
            expansion += min(1.7, 2 * days) * rng.expovariate(1)
        paths.append((days, math.expm1(min(4.2, expansion)), rng.random(),
                      rng.gauss(0, 1), rng.random()))
    return paths


def fit(rows, index, mass_at, scale, shape):
    observations = [(time, n * rates[index] / 100) for time, n, rates in rows
                    if rates[index] is not None][-24:]
    end = rows[-1][0]
    models = []
    cumulative = 0
    for factor in (0.42, 0.75, 1.25, 2.2):
        for power in (0.75 * shape, shape, 1.4 * shape):
            for seed_age in (0.7, 3.5, 14):
                duration = scale * factor
                values = []
                for time, count in observations:
                    mass = mass_at(time, duration, power, seed_age)
                    weight = (0.4 + 0.6 * count / (count + 4)) * math.exp(
                        -min(30, (end - time) / 0.8))
                    values.append((weight, math.log((count + 0.25) / (mass + 0.25))))
                weight_sum = sum(weight for weight, _ in values)
                log_limit = min(0, sum(w * level for w, level in values) / weight_sum)
                cost = sum(w * min(5, (level - log_limit) ** 2)
                           for w, level in values) / weight_sum
                cumulative += math.exp(-cost * min(10, len(values) * 1.1))
                models.append((cumulative, duration, power, seed_age, math.exp(log_limit)))
    return models


def count_trend(rows, index, end, count):
    """Estimate a damped elasticity from the recent growth in unlock counts."""
    first = rows[0][0]
    slopes = []
    for time, size, rates in rows[:-1]:
        if rates[index] is None or not 0.35 <= end - time <= 1.35:
            continue
        earlier = size * rates[index] / 100
        age_ratio = math.log((end - first + 0.35) / (time - first + 0.35))
        slopes.append(math.log((count + 0.5) / (earlier + 0.5)) / age_ratio)
    if not slopes or count < 3:
        return None
    return min(3.5, max(-0.25, median(slopes))), end - first + 0.35


def sample_trophy(rows, mass_at, index, trophy, paths):
    observed = next(((time, n, rates[index]) for time, n, rates in reversed(rows)
                     if rates[index] is not None), None)
    if observed is None:
        return [0, 0, 0, 100, 100]
    last_seen, n, rate = observed
    end, size, _ = rows[-1]
    anchor = (n * rate / 100 + 0.18) / (n + 0.36)
    models = fit(rows, index, mass_at, *progression(trophy))
    trend = count_trend(rows, index, end, n * rate / 100) if last_seen == end else None
    ceiling_sizes = [size for _, size, rates in rows if rates[index] == 100]
    always_ceiling = rate == 100 and all(
        rates[index] in (None, 100) for _, _, rates in rows)
    # A ceiling that survives substantial inflow can be a tracking prerequisite.
    ceiling_weight = 0.0
    if always_ceiling:
        expansion_evidence = math.log(max(ceiling_sizes) / min(ceiling_sizes))
        ceiling_weight = min(0.94, 0.50 + 0.23 * expansion_evidence)
    total = models[-1][0]
    samples = []
    for days, expansion, selector, shock, mix in paths:
        if days == 0 and last_seen == end:
            samples.append(rate)
            continue
        if mix < ceiling_weight:
            samples.append(100.0)
            continue
        _, scale, shape, seed_age, limit = next(m for m in models if m[0] >= selector * total)
        current = limit * mass_at(last_seen, scale, shape, seed_age) / n
        existing = mass_at(end + days, scale, shape, seed_age)
        new = sum(unlock(days * (1 - (i + 0.5) / 8), scale, shape)
                  for i in range(8)) / 8
        future = limit * (existing / size + expansion * new) / (1 + expansion)
        retain = math.exp(-(days + end - last_seen) / (0.85 + 3 * mix))
        center = logit(future) + retain * (logit(anchor) - logit(current))
        if rate == 100:
            # Preserve an observed ceiling without magnifying tiny model misses
            # in failure odds when the fitted cohort is already saturated.
            adjusted = anchor * future / max(anchor, current)
            center = logit(retain * adjusted + (1 - retain) * future)
        if trend is not None and 0 < rate < 100:
            elasticity, maturity = trend
            expected = n * anchor * math.exp(elasticity * math.log1p(days / maturity))
            empirical = expected / (size * (1 + expansion))
            weight = 0.38 * mix
            center += weight * (logit(min(0.995, empirical)) - center)
        noise = (0.22 + 0.35 * mix) * math.sqrt(days + end - last_seen) * shock
        samples.append(round(100 / (1 + math.exp(-max(-60, center + noise))), 2))
    samples.sort()
    return [samples[round(level * (len(samples) - 1))] for level in LEVELS]


def forecast(case):
    rows = epochs(case["history"])
    if rows:
        cohorts = [(rows[0][0], rows[0][1])]
        for (start, old_size, _), (end, size, _) in zip(rows, rows[1:]):
            if size > old_size:
                cohorts.append(((start + end) / 2, size - old_size))
        initial_time, initial_size = cohorts[0]
        arrivals = cohorts[1:]

        @lru_cache(maxsize=65536)
        def mass_at(time, scale, shape, seed_age):
            initial = initial_size * unlock(time - initial_time + seed_age, scale, shape)
            return initial + cohort_mass(arrivals, time, scale, shape)

        paths = player_paths(rows, day(case["at"]), day(case["target"]))
    return {"trophies": [
        {"id": trophy["id"], "q": sample_trophy(rows, mass_at, i, trophy, paths)
         if rows else [0, 0, 0, 100, 100]}
        for i, trophy in enumerate(case["trophies"])
    ]}


def main():
    inputs = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
    outputs = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
    outputs.mkdir(parents=True, exist_ok=True)
    for source in sorted(inputs.glob("*.in")):
        case = json.loads(source.read_text(encoding="utf-8"))
        payload = json.dumps(forecast(case), separators=(",", ":"), allow_nan=False)
        (outputs / (source.stem + ".out")).write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
