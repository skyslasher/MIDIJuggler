"""Module base classes and categories."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import DataPointSpec


class ModuleCategory(str, Enum):
    IO = "io"
    MODIFIER = "modifier"
    GENERATOR = "generator"
    INTERFACE = "interface"


class Module(ABC):
    """Lifecycle boundary for a data-point-aware module."""

    def __init__(self, name: str, store: DataPointStore) -> None:
        self.name = name
        self.store = store
        self.running = False

    @property
    @abstractmethod
    def category(self) -> ModuleCategory:
        raise NotImplementedError

    @abstractmethod
    def datapoints(self) -> list[DataPointSpec]:
        raise NotImplementedError

    async def start(self) -> None:
        self.running = True
        self.store.register_many(self.datapoints())

    async def stop(self) -> None:
        self.running = False


class IOModule(Module):
    category = ModuleCategory.IO


class ModifierModule(Module):
    category = ModuleCategory.MODIFIER


class GeneratorModule(Module):
    category = ModuleCategory.GENERATOR


class InterfaceModule(Module):
    category = ModuleCategory.INTERFACE
