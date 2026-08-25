"""Renamed-copy fixture: the original with identifiers renamed and comments
added, but identical logic and structure. A classic Type-2 clone — this is what
"copy-paste with cosmetic renames" produces, and it must score HIGH on logic
similarity despite every variable name being different.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Item:  # renamed from Product
    code: str  # was sku
    title: str  # was name
    cost: float  # was price
    count: int = 0  # was quantity

    def total_value(self) -> float:
        # same body, renamed fields
        return self.cost * self.count


@dataclass
class Store:  # renamed from Inventory
    items: dict = field(default_factory=dict)

    def add(self, item: Item) -> None:
        if item.code in self.items:
            self.items[item.code].count += item.count
        else:
            self.items[item.code] = item

    def remove(self, code: str, count: int) -> bool:
        if code not in self.items:
            return False
        entry = self.items[code]
        if entry.count < count:
            return False
        entry.count -= count
        return True

    def total_worth(self) -> float:
        return sum(p.total_value() for p in self.items.values())

    def low_stock(self, limit: int = 5) -> list:
        return [p.code for p in self.items.values() if p.count < limit]
