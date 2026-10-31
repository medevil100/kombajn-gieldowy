"""Cooperative Linux provider/restart lease. No providers or database writes.

Installed /run file belongs to root; application operations take shared leases.
The independent guardian takes an exclusive lease before a controlled restart.
Without an installed guardian, existing Windows/Linux behavior is unchanged.
"""
from contextlib import contextmanager
from functools import wraps
import os
from pathlib import Path

LOCK_PATH = Path('/run/ki2-guardian/provider.lock')


class MaintenanceBusy(RuntimeError):
    pass


class MaintenanceUnavailable(RuntimeError):
    pass


@contextmanager
def provider_lease(path=None):
    path = Path(path) if path is not None else LOCK_PATH
    if os.name != 'posix' or not path.exists():
        yield True
        return
    import fcntl
    # Never create/replace the root-owned coordination file from application code.
    try:
        handle=path.open('rb')
    except (PermissionError, FileNotFoundError) as exc:
        raise MaintenanceUnavailable from exc
    with handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def guard_operation(*, defer=False, error=MaintenanceBusy):
    def decorate(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            try:
                with provider_lease() as acquired:
                    if not acquired:
                        if defer:
                            return False
                        raise error('KI: krótka przerwa techniczna nadzoru. Nie rozpoczęto zapytania ani wysyłki.')
                    return function(*args, **kwargs)
            except MaintenanceUnavailable as exc:
                # A broken installed lease must never silently permit a paid call.
                raise error('KI: blokada nadzoru niedostępna; operacja nie została rozpoczęta.') from exc
        return guarded
    return decorate
