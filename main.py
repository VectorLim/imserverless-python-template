"""IMServerless entry point; keep platform dispatch separate from business logic."""

import logging
import os
import sys

from pipeline.example import process

logger = logging.getLogger(__name__)


def handle(job_id=None, context=None, header=None, body=None) -> tuple[bool, str, str]:
    """Run the configured pipeline and return the platform's status tuple."""
    script = os.environ.get("SCRIPT_NAME", "example")
    if script != "example":
        raise ValueError(f"Unknown SCRIPT_NAME: {script!r}")
    message = process(os.environ.get("ENV_MODE", "test"))
    logger.info("Pipeline completed: script=%s job_id=%s", script, job_id)
    return True, message, message


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print(handle())
