"""Seeded: set_status with a description."""


def f(span, StatusCode):
    span.set_status(StatusCode.ERROR, "boom")
