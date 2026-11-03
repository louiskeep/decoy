"""Seeded: record_exception writes the exception text as an event."""


def f(span, exc):
    span.record_exception(exc)
