"""Coordinate module startup and shutdown."""

from __future__ import annotations

import logging

from midijuggler.modules.base import Module, ModuleCategory

LOGGER = logging.getLogger(__name__)


class ModuleRegistry:
    """Own all runtime modules and start them in category order."""

    def __init__(self) -> None:
        self._modules: list[Module] = []

    def add(self, module: Module) -> None:
        self._modules.append(module)

    def extend(self, modules: list[Module]) -> None:
        self._modules.extend(modules)

    def modules(self) -> tuple[Module, ...]:
        return tuple(self._modules)

    def by_category(self, category: ModuleCategory) -> list[Module]:
        return [module for module in self._modules if module.category == category]

    async def start_all(self) -> None:
        order = (
            ModuleCategory.IO,
            ModuleCategory.GENERATOR,
            ModuleCategory.MODIFIER,
            ModuleCategory.INTERFACE,
        )
        for category in order:
            for module in self.by_category(category):
                LOGGER.info("starting %s module %s", category.value, module.name)
                await module.start()

    async def stop_all(self) -> None:
        for module in reversed(self._modules):
            if module.running:
                LOGGER.info("stopping %s module %s", module.category.value, module.name)
                await module.stop()
