import pprint

import requests

from countdown_core.ruter.ruter_client import RuterClient


def test_ruter_client():
    client = RuterClient(
        ["NSR:StopPlace:59872"],
        session=requests.Session(),
    )
    next = client.get_next_departures(1)
    pprint.pp(next)
