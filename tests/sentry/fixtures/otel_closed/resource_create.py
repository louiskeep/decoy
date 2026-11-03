"""Seeded: Resource.create reads OTEL_RESOURCE_ATTRIBUTES and detectors."""


def f(Resource):
    return Resource.create({})
