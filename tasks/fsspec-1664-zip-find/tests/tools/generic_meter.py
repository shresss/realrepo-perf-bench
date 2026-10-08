"""Verifier-authored, same-process diagnostics; NOT a security boundary.

No candidate callable is replaced. Pandas dispatch wrappers register Python code
objects while an API call is active, and monitoring observes actual entries.
Native callables without a Python code object are reported as unobserved.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
import functools
from pathlib import Path
import sys
import threading
import types


class GenericMeter:
    TOOL_ID = 4
    TOOL_NAME = "afterquery-probe-v1"

    def __init__(self, source, target_paths, package_paths=("janitor",), pandas_udf=True):
        if not hasattr(sys, "monitoring"):
            raise RuntimeError("sys.monitoring requires Python >=3.12")
        self.source = Path(source).resolve()
        self.targets = self._paths(target_paths)
        self.packages = self._paths(package_paths)
        self.pandas_udf = pandas_udf
        self.counts = Counter()
        self.dispatches = Counter()
        self.callback_entries = Counter()
        self.unobservable_callables = Counter()
        self.by_function = Counter()
        self._code_scope = {}
        self._code_labels = {}
        self._tls = threading.local()
        self._patches = []
        self._callbacks = {}
        self._started = False
        self._events = sys.monitoring.events.PY_START | sys.monitoring.events.CALL

    def _paths(self, paths):
        if not paths:
            raise ValueError("empty measurement scope")
        result = []
        for raw in paths:
            relative = Path(raw)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("meter scopes must be repository-relative")
            path = (self.source / relative).resolve()
            if not path.is_relative_to(self.source):
                raise ValueError("meter scope escaped source")
            result.append(path)
        return tuple(result)

    def _scope(self, code):
        if code not in self._code_scope:
            filename = Path(code.co_filename)
            if filename.is_absolute():
                resolved = filename.resolve()
                target = any(resolved == p or resolved.is_relative_to(p) for p in self.targets)
                package = any(resolved == p or resolved.is_relative_to(p) for p in self.packages)
                if target:
                    self._code_labels[code] = f"{resolved.relative_to(self.source)}:{code.co_name}"
            else:
                target = package = False
            self._code_scope[code] = (target, package)
        return self._code_scope[code]

    def _entry(self, code, offset):
        target, package = self._scope(code)
        if target:
            self.counts["target_py_start"] += 1
            self.by_function[self._code_labels[code]] += 1
        if package:
            self.counts["package_py_start"] += 1
        for api, depth in getattr(self._tls, "active", {}).get(code, {}).items():
            if depth:
                self.callback_entries[api] += 1

    def _call(self, code, offset, callable_object, arg0):
        target, package = self._scope(code)
        if target:
            self.counts["target_call"] += 1
        if package:
            self.counts["package_call"] += 1

    @staticmethod
    def _callables(value):
        if isinstance(value, dict):
            for child in value.values():
                yield from GenericMeter._callables(child)
        elif isinstance(value, (tuple, list)):
            for child in value:
                yield from GenericMeter._callables(child)
        elif callable(value):
            yield value

    @staticmethod
    def _code(value):
        while isinstance(value, functools.partial):
            value = value.func
        if isinstance(value, types.MethodType):
            value = value.__func__
        code = getattr(value, "__code__", None)
        if isinstance(code, types.CodeType):
            return code
        method = getattr(type(value), "__call__", None)
        code = getattr(method, "__code__", None)
        return code if isinstance(code, types.CodeType) else None

    @contextmanager
    def _dispatch(self, api, function):
        self.dispatches[api] += 1
        if not hasattr(self._tls, "active"):
            self._tls.active = defaultdict(Counter)
        codes = set()
        for fn in self._callables(function):
            code = self._code(fn)
            if code is None:
                self.unobservable_callables[api] += 1
            else:
                codes.add(code)
        for code in codes:
            self._tls.active[code][api] += 1
        try:
            yield
        finally:
            for code in codes:
                self._tls.active[code][api] -= 1

    def _patch(self, cls, name):
        original = getattr(cls, name)
        api = f"{cls.__name__}.{name}"
        owned = name in cls.__dict__

        @functools.wraps(original)
        def dispatch(obj, *args, **kwargs):
            function = args[0] if args else kwargs.get("func", kwargs.get("arg"))
            with self._dispatch(api, function):
                return original(obj, *args, **kwargs)

        setattr(cls, name, dispatch)
        self._patches.append((cls, name, original, dispatch, owned))

    def start(self):
        if self._started:
            raise RuntimeError("meter already started")
        mon = sys.monitoring
        if mon.get_tool(self.TOOL_ID) is not None:
            raise RuntimeError("monitoring tool id already occupied")
        # Pandas imports happen before event collection and before workload code.
        if self.pandas_udf:
            import pandas as pd
            from pandas.core.groupby.generic import DataFrameGroupBy, SeriesGroupBy
            for cls, names in (
                (pd.DataFrame, ("apply", "agg", "aggregate")),
                (pd.Series, ("apply", "map", "agg", "aggregate")),
                (DataFrameGroupBy, ("apply", "agg", "aggregate")),
                (SeriesGroupBy, ("apply", "agg", "aggregate")),
            ):
                for name in names:
                    self._patch(cls, name)
        mon.use_tool_id(self.TOOL_ID, self.TOOL_NAME)
        self._callbacks = {mon.events.PY_START: self._entry, mon.events.CALL: self._call}
        for event, callback in self._callbacks.items():
            mon.register_callback(self.TOOL_ID, event, callback)
        mon.set_events(self.TOOL_ID, self._events)
        self._started = True
        return self

    def finish(self):
        if not self._started:
            raise RuntimeError("meter not started")
        mon = sys.monitoring
        issues = []
        if mon.get_tool(self.TOOL_ID) != self.TOOL_NAME:
            issues.append("monitoring_tool_identity_changed")
        if mon.get_events(self.TOOL_ID) != self._events:
            issues.append("monitoring_event_mask_changed")
        # Register_callback returns the previous object; checking then restoring
        # detects an end-state change, not a temporary change during execution.
        for event, callback in self._callbacks.items():
            previous = mon.register_callback(self.TOOL_ID, event, callback)
            if previous is not callback:
                issues.append(f"monitoring_callback_changed:{event}")
        for cls, name, _, wrapper, _ in self._patches:
            if getattr(cls, name) is not wrapper:
                issues.append(f"pandas_dispatch_changed:{cls.__name__}.{name}")
        mon.set_events(self.TOOL_ID, 0)
        for event in self._callbacks:
            mon.register_callback(self.TOOL_ID, event, None)
        mon.free_tool_id(self.TOOL_ID)
        for cls, name, original, _, owned in reversed(self._patches):
            if owned:
                setattr(cls, name, original)
            else:
                delattr(cls, name)
        self._started = False
        counts = {name: self.counts[name] for name in (
            "target_py_start", "target_call", "package_py_start", "package_call")}
        return {
            "schema_version": 1, "provenance": "same_process_diagnostic",
            "integrity_checked": not issues, "integrity_issues": issues,
            "counts": counts, "pandas_dispatches": dict(self.dispatches),
            "pandas_python_callback_entries": dict(self.callback_entries),
            "pandas_native_callable_dispatches_unobserved": dict(self.unobservable_callables),
            "target_function_entries": dict(self.by_function),
            "target_paths": [str(p.relative_to(self.source)) for p in self.targets],
            "package_paths": [str(p.relative_to(self.source)) for p in self.packages],
            "limitations": [
                "Endpoint checks do not establish uninterrupted measurement or prevent same-process interference.",
                "Python events do not count native array work; native callable invocations are not observed.",
                "Nested pandas API counts overlap; do not sum them as unique operations.",
            ],
        }
