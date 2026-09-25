import requests

from countdown.http import DEFAULT_TIMEOUT
from countdown.models import Postcode, PostcodeResponse

POSTCODES_URL = "https://api.postcodes.io/postcodes"


def lookup_postcode(session: requests.Session, postcode: str) -> Postcode | None:
    """Where a UK postcode is: coordinates, country, English region and local authority.
    None if postcodes.io doesn't know it (a typo, or a terminated postcode); raises if
    postcodes.io can't be reached, so the caller can try again later."""
    response = session.get(f"{POSTCODES_URL}/{postcode.strip()}", timeout=DEFAULT_TIMEOUT)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return PostcodeResponse.model_validate_json(response.content).result
