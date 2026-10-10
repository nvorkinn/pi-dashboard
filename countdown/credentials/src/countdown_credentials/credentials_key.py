"""The key that keeps the device credentials file encrypted at rest. It never lives next to the file:
systemd hands it to the service as a credential (LoadCredential=, see countdown.service), and a container
gets it as a Docker secret. Without one (a dev machine) the file stays plain JSON, as it always was."""

import os
from pathlib import Path

from cryptography.fernet import Fernet

KEY_NAME = "credentials-key"
# Where Docker mounts a Compose secret.
DOCKER_SECRETS_DIR = Path("/run/secrets")


def credentials_key() -> Fernet | None:
    """The cipher for the credentials file, or None if this device wasn't given a key."""
    directories = [Path(d) for d in (os.environ.get("CREDENTIALS_DIRECTORY"),) if d]
    for directory in (*directories, DOCKER_SECRETS_DIR):
        path = directory / KEY_NAME
        if path.is_file():
            return Fernet(path.read_bytes().strip())
    return None
