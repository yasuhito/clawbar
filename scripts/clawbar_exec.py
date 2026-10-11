"""Set parent-death termination before exec, without thread-unsafe preexec_fn."""

from __future__ import annotations

import ctypes
import os
import signal
import sys

PR_SET_PDEATHSIG = 1


def main() -> None:
    expected_parent = int(sys.argv[1])
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))
    # The parent might have exited before prctl; do not leave an orphan behind.
    if os.getppid() != expected_parent:
        os.kill(os.getpid(), signal.SIGTERM)
    # exec preserves PDEATHSIG and the process group used for deadline cleanup.
    os.execvp(sys.argv[2], sys.argv[2:])


if __name__ == "__main__":
    main()
