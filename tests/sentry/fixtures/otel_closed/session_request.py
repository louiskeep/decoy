"""Seeded: a requests.Session send resolves redirects and reads the body."""


def f(requests, url, body):
    return requests.Session().post(url, data=body, stream=True, allow_redirects=False)
