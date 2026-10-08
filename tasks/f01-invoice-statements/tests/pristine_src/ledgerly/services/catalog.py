"""Product names for statements and exports."""
from ..config import Settings
from ..db.repositories import ProductRepository


class ProductCatalog:
    """Resolves product ids to the names printed on statements.

    Names are cached, so an invoice that lists the same product on several lines
    looks it up once. A product that has been removed from the catalog resolves
    to Settings.unknown_product_label. Callers reset() per invoice to bound memory
    on large exports; the cache is also capped at Settings.product_cache_max.
    """

    def __init__(self, repo: ProductRepository, settings: Settings):
        self._repo = repo
        self._settings = settings
        self._names: dict[int, str] = {}

    def describe(self, product_id: int) -> str:
        name = self._names.get(product_id)
        if name is None:
            product = self._repo.get(product_id)
            name = product.name if product is not None else self._settings.unknown_product_label
            if len(self._names) >= self._settings.product_cache_max:
                # Evict the oldest entry; dicts keep insertion order.
                del self._names[next(iter(self._names))]
            self._names[product_id] = name
        return name

    def reset(self) -> None:
        """Forget every cached name."""
        self._names.clear()
