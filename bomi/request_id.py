"""X-Request-Id generation.

The spec asks for a new UUID on every request, so there is nothing to derive:
each call gets its own uuid4. Retries deliberately replay the id of the attempt
they are retrying - see BomiClient._send - so a request that reached the server
but lost its response is deduplicated rather than charged twice.
"""

import uuid


def new_id():
    """A fresh X-Request-Id. Every request gets its own."""
    return str(uuid.uuid4())
