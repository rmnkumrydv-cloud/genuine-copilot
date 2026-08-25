"""Original fixture: a small, self-contained inventory module.

Used as the baseline for the clone-similarity ordering assertions:
original vs. renamed-copy vs. rewritten vs. unrelated.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Product:
    sku: str
    name: str
    price: float
    quantity: int = 0

    def total_value(self) -> float:
        return self.price * self.quantity


@dataclass
class Inventory:
    products: dict = field(default_factory=dict)

    def add(self, product: Product) -> None:
        if product.sku in self.products:
            self.products[product.sku].quantity += product.quantity
        else:
            self.products[product.sku] = product

    def remove(self, sku: str, quantity: int) -> bool:
        if sku not in self.products:
            return False
        item = self.products[sku]
        if item.quantity < quantity:
            return False
        item.quantity -= quantity
        return True

    def total_worth(self) -> float:
        return sum(p.total_value() for p in self.products.values())

    def low_stock(self, threshold: int = 5) -> list:
        return [p.sku for p in self.products.values() if p.quantity < threshold]
