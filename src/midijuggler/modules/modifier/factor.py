"""Simple multiplicative factor transform."""

from __future__ import annotations

from dataclasses import dataclass

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind


@dataclass(frozen=True)
class FactorTransform:
    factor: float = 1.0

    @classmethod
    def from_connection(cls, connection: ConnectionSpec) -> FactorTransform:
        if connection.modifier != ModifierKind.FACTOR:
            raise ValueError(f"unsupported modifier: {connection.modifier}")
        if connection.factor == 0.0:
            raise ValueError("factor must not be zero")
        return cls(factor=connection.factor)


def apply_factor(value: float, transform: FactorTransform) -> float:
    return value * transform.factor
