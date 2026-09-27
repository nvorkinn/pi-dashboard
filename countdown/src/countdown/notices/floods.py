from datetime import datetime, timedelta

from countdown.core.abstract_client import DEFAULT_TIMEOUT
from countdown.core.models import FloodWarningsResponse, Postcode
from countdown.notices.notice import Notice, NoticeSource, Severity

FLOODS_URL = "https://environment.data.gov.uk/flood-monitoring/id/floods"
RADIUS_KM = 5

# severityLevel 4 is "warning no longer in force", which isn't worth showing.
SEVERITY_BY_LEVEL = {
    1: (Severity.SEVERE, "Severe flood warning"),
    2: (Severity.WARNING, "Flood warning"),
    3: (Severity.INFO, "Flood alert"),
}


class FloodWarningsSource(NoticeSource):
    """Environment Agency flood alerts and warnings near the postcode. England only:
    elsewhere the feed just has nothing to report."""

    name = "Flood warnings"
    refresh_interval = timedelta(minutes=15)

    def __init__(self, session, location: Postcode):
        super().__init__(session)
        self.params = {"lat": location.latitude, "long": location.longitude, "dist": RADIUS_KM}

    def fetch(self, now: datetime) -> list[Notice]:
        response = self.session.get(FLOODS_URL, params=self.params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        notices = []
        for warning in FloodWarningsResponse.model_validate_json(response.content).items:
            if warning.severity_level in SEVERITY_BY_LEVEL:
                severity, label = SEVERITY_BY_LEVEL[warning.severity_level]
                notices.append(Notice("Floods", severity, f"{label}: {warning.description}"))
        return notices
