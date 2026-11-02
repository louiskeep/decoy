"""Seeded: span call without record_exception=False, set_status_on_exception=False."""


def f(tracer):
    return tracer.start_span("decoy.run", record_exception=False)
