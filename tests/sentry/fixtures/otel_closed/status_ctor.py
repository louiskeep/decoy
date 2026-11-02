"""Seeded: a Status object (carries a description)."""


def f(span, trace):
    span.set_status(trace.Status(trace.StatusCode.ERROR))
