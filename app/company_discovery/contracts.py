"""Controller-only capabilities and errors. Never deserialize identity from browser JSON."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import time
from typing import Callable, ContextManager


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class DiscoveryError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True)
class TrustedImportIdentity:
    generation: int
    instance_id: str
    principal: str
    expires_at: float
    fence: Callable[[], ContextManager]

    @property
    def owner(self):
        return digest([self.generation, self.instance_id, self.principal])

    @contextmanager
    def guard(self, validator):
        validator(self)
        if time.time() >= self.expires_at:
            raise DiscoveryError("lease_expired", 401)
        with self.fence():
            validator(self)
            if time.time() >= self.expires_at:
                raise DiscoveryError("lease_expired", 401)
            yield
