#!/usr/bin/env python3
"""Retry durable CoolMRI camera upload records without taking new pictures."""

from __future__ import annotations

import fcntl
import sys

from scheduled_capture import LOCK_PATH, logger, process_failed_sessions


def main() -> int:
    with LOCK_PATH.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        recovered, attempted = process_failed_sessions()
        if attempted:
            logger.info("retry_recovered=%s retry_attempted=%s", recovered, attempted)
        return 0 if recovered == attempted else 1


if __name__ == "__main__":
    sys.exit(main())
