"""Replace this harmless example with your application logic."""


def process(env_mode: str) -> str:
    """Return a result without external services, credentials or file writes."""
    if env_mode != "test":
        raise ValueError("The example pipeline only supports ENV_MODE=test")
    return "Example pipeline completed"
