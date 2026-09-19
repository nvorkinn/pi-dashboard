import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT = 10


def build_retrying_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """A requests.Session that automatically retries transient failures (connection
    errors, 502/503/504) with exponential backoff, so a flaky network doesn't need to
    be handled by hand at every call site."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[502, 503, 504],
        allowed_methods=None,  # retry on every method, including the POST used for auth
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
