"""A genuine full public estimator fit; no timing or expected values."""
import argparse
import json
import math


def run(case, size, seed):
    from lifelines import AalenJohansenFitter

    if size < 2 or case not in {"ordinary", "weighted", "same-event-ties", "terminal-event", "no-interest"}:
        raise ValueError("unsupported case")
    groups = [i // 2 if case == "same-event-ties" else i for i in range(size)]
    durations = [g + 1 for g in groups]
    events = [0 if (g + seed) % 5 == 0 else 1 + g % 2 for g in groups]
    # Censor the final time group except in the declared terminal-event case.
    for i, g in enumerate(groups):
        if g == groups[-1]:
            events[i] = 1 if case == "terminal-event" else 0
        elif case == "no-interest" and events[i]:
            events[i] = 2
    weights = [1 + (i + seed) % 3 for i in range(size)] if case == "weighted" else None
    before = [list(durations), list(events), None if weights is None else list(weights)]
    fit = AalenJohansenFitter(calculate_variance=True, seed=seed)
    fit.fit(durations, events, event_of_interest=1, weights=weights)

    def finite(value):
        value = float(value)
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "+infinity" if value > 0 else "-infinity"
        return value

    return {"timeline": [float(x) for x in fit.cumulative_density_.index],
            "incidence_columns": list(fit.cumulative_density_.columns),
            "incidence": [finite(x) for x in fit.cumulative_density_.iloc[:, 0]],
            "variance": [finite(x) for x in fit.variance_],
            "confidence_columns": list(fit.confidence_interval_.columns),
            "confidence": [[finite(a), finite(b)] for a, b in fit.confidence_interval_.itertuples(index=False, name=None)],
            "event_columns": list(fit.event_table.columns),
            "event_table": [[int(x) for x in row] for row in fit.event_table.itertuples(index=False, name=None)],
            "inputs_before": before, "inputs_after": [durations, events, weights]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument("--seed", required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
