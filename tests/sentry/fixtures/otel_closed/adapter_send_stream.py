"""Seeded: adapter send without stream=True."""


def f(adapter, prepared):
    return adapter.send(prepared, timeout=(2, 5), verify=True, cert=None, proxies={})
