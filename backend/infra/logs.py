"""Console logging setup for the process (master-plan ticket 16).

One place decides the level and line format, so a job run reads as a single
story on stdout. Called from the API lifespan — the only entrypoint today.
Stdlib logging only; JSON formatting is deferred to Phase 3.

Job-pipeline lines lead with `job=<id>` so one grep follows a whole run.
"""
import logging

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"


def configure():
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
