"""Lineage query functions; temporal order is intentionally not an edge."""

from research_os.ledger.registry import RunRegistry


def ancestors(registry: RunRegistry, run_id: str):
    return registry.get_ancestors(run_id)


def descendants(registry: RunRegistry, run_id: str):
    return registry.get_descendants(run_id)


def lineage(registry: RunRegistry, run_id: str):
    return registry.get_lineage(run_id)


def add_dependency(registry: RunRegistry, dependency):
    return registry.add_dependency(dependency)
