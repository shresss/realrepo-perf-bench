"""Independent stdlib oracle: Decimal event accounting and variance formula."""
from collections import defaultdict
from decimal import Decimal, localcontext
import math
from statistics import NormalDist


def expected(case, size, seed):
    if size < 2 or case not in {"ordinary", "weighted", "same-event-ties", "terminal-event", "no-interest"}:
        raise ValueError("at least two subjects and a declared case required")
    duration, event, weights = [], [], []
    groups = [(i // 2 if case == "same-event-ties" else i) for i in range(size)]
    for i, g in enumerate(groups):
        duration.append(g + 1)
        code = 0 if (g + seed) % 5 == 0 else 1 + g % 2
        if g == groups[-1]:
            code = 1 if case == "terminal-event" else 0
        elif case == "no-interest" and code:
            code = 2
        event.append(code)
        weights.append(1 + (i + seed) % 3 if case == "weighted" else 1)
    grouped = defaultdict(lambda: [0, 0, 0])
    for time, code, weight in zip(duration, event, weights):
        grouped[time][0] += weight
        grouped[time][1] += weight * bool(code)
        grouped[time][2] += weight * (code == 1)
    population = sum(weights)
    timeline = [0.0] + [float(time) for time in sorted(grouped)]
    table = [[0, 0, 0, 0, population, population]]
    risk = population
    for time in sorted(grouped):
        removed, deaths, interest = grouped[time]
        table.append([removed, deaths, interest, removed - deaths, 0, risk])
        risk -= removed
    with localcontext() as context:
        context.prec = 50
        D = Decimal
        survival, cumulative = D(1), D(0)
        density, terms = [], []
        for removed, deaths, interest, _, _, at_risk in table:
            n, d, j = D(at_risk), D(deaths), D(interest)
            lag = survival
            cumulative += lag * j / n
            survival *= (n - d) / n
            density.append(cumulative)
            # At the final exhausted risk set the (F_t-F_i)^2 factor is zero;
            # the baseline's pandas reduction omits that undefined contribution.
            a = d / n / (n - d) if n != d else D(0)
            b = lag * lag * j * (n - j) / (n * n * n)
            c = lag * j / (n * n)
            terms.append((a, b, c, cumulative))
        variance = []
        if size <= 64:
            for stop, f in enumerate(density, 1):
                variance.append(sum((a * (f - fi) ** 2 + b - 2 * c * (f - fi)
                                     for a, b, c, fi in terms[:stop]), D(0)))
        else:
            a0 = a1 = a2 = b0 = c0 = c1 = D(0)
            for a, b, c, f in terms:
                a0 += a
                a1 += a * f
                a2 += a * f * f
                b0 += b
                c0 += c
                c1 += c * f
                variance.append(a0 * f * f - 2 * a1 * f + a2 + b0 - 2 * (c0 * f - c1))
    density, variance = [float(x) for x in density], [float(x) for x in variance]
    critical = NormalDist().inv_cdf(.975)
    confidence = []
    for f, v in zip(density, variance):
        if f <= 0 or f >= 1 or v < 0:
            confidence.append([None, None])
        else:
            transform = math.log(-math.log(f))
            uncertainty = math.sqrt(v) / (f * abs(math.log(f)))
            confidence.append([math.exp(-math.exp(transform + critical * uncertainty)),
                               math.exp(-math.exp(transform - critical * uncertainty))])
    input_weights = weights if case == "weighted" else None
    return {"timeline": timeline, "incidence_columns": ["CIF_1"], "incidence": density,
            "variance": variance,
            "confidence_columns": ["AJ_estimate_upper_0.95", "AJ_estimate_lower_0.95"],
            "confidence": confidence,
            "event_columns": ["removed", "observed", "observed_1", "censored", "entrance", "at_risk"],
            "event_table": table, "inputs_before": [duration, event, input_weights],
            "inputs_after": [duration, event, input_weights]}


def equivalent(actual, wanted):
    if not isinstance(actual, dict) or set(actual) != set(wanted):
        return False
    numeric = {"incidence", "variance", "confidence"}
    if any(actual[key] != wanted[key] for key in wanted if key not in numeric):
        return False

    def compare(a, b, atol):
        if isinstance(b, list):
            return isinstance(a, list) and len(a) == len(b) and all(compare(x, y, atol) for x, y in zip(a, b))
        if b is None:
            return a is None
        return type(a) in (int, float) and math.isfinite(a) and math.isclose(a, b, rel_tol=1e-8, abs_tol=atol)

    return all(compare(actual[key], wanted[key], 2e-7 if key == "confidence" else 1e-10) for key in numeric)
