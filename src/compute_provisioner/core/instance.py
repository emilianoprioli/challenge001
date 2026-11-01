import os
import socket


def instance_id() -> str:
    """Return Railway's stable replica id, falling back to the local hostname."""
    return os.getenv("RAILWAY_REPLICA_ID") or socket.gethostname()


def public_instance_id(value: str | None) -> str | None:
    if not value:
        return None
    return f"replica-{value[:8]}"
