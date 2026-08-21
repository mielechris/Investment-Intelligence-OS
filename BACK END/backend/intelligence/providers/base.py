from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    kind: str
    configured: bool
    live: bool
    detail: str


class EvidenceProvider(ABC):
    name: str
    kind: str

    @abstractmethod
    def status(self) -> ProviderStatus:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, **kwargs: Any):
        raise NotImplementedError
