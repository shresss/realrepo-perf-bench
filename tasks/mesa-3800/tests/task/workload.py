"""Public EventList lifecycle, without private heap/counter inspection."""
import argparse
import json


class Recorder:
    def __init__(self):
        self.executed = []

    def record(self, identity, generation):
        self.executed.append([identity, generation])


def run(case, size, seed):
    from mesa.time import Event, EventList, Priority

    if case not in {"reschedule", "repeat-cancel", "clear-reuse", "cancel-popped", "compact", "priority"} or size < 1:
        raise ValueError("unsupported case")
    queue, recorder = EventList(), Recorder()
    priorities = [Priority.HIGH, Priority.DEFAULT, Priority.LOW]
    observed_counts, peeks = [], []

    def add(identity, generation):
        event = Event((identity * 17 + seed) % 19 + generation * 32,
                      recorder.record, priority=priorities[(identity + generation) % 3],
                      function_args=[identity, generation])
        queue.add_event(event)
        return event

    live = [add(i, 0) for i in range(size)]
    observed_counts.append(len(queue))
    generations = 8 if case in {"reschedule", "repeat-cancel", "compact"} else 0
    for generation in range(1, generations + 1):
        for i in range(size):
            live[i].cancel()
            if case == "repeat-cancel":
                live[i].cancel()
            if i % 32 == 0:
                observed_counts.append(len(queue))
            live[i] = add(i, generation)
            if i % 32 == 0:
                observed_counts.append(len(queue))
        if case == "compact":
            queue.compact()
        peeks.append([list(event.function_args) for event in queue.peek_ahead(3)])
    if case == "clear-reuse":
        old = live
        queue.clear()
        observed_counts.append(len(queue))
        live = [add(i, 1) for i in range(size)]
        old[0].cancel()
        observed_counts.append(len(queue))
    elif case == "cancel-popped":
        first = queue.pop_event()
        first.execute()
        first.cancel()
        observed_counts.append(len(queue))
    elif case == "priority":
        peeks.append([list(event.function_args) for event in queue.peek_ahead(min(5, size))])
    while not queue.is_empty():
        queue.pop_event().execute()
    observed_counts.append(len(queue))
    try:
        queue.pop_event()
    except IndexError:
        empty_exception = "IndexError"
    else:
        empty_exception = "no_error"
    return {"executed": recorder.executed, "counts": observed_counts,
            "peeks": peeks, "empty_pop_exception": empty_exception}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
