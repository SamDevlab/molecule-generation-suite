from research_os.ledger.regression import detect_regressions
from research_os.ledger.registry import RunRegistry


def list_workflows(registry: RunRegistry, **kwargs):
    return registry.list_workflows(**kwargs)


def show_workflow(registry: RunRegistry, workflow_id: str):
    return registry.get_workflow(workflow_id)


def rerun_workflow(registry: RunRegistry, workflow_id: str, **kwargs):
    return registry.rerun_workflow(workflow_id, **kwargs)


def compare_workflows(registry: RunRegistry, original: str, rerun: str):
    return registry.compare_workflows(original, rerun)


def workflow_regressions(registry: RunRegistry, original: str, rerun: str):
    return detect_regressions(registry.compare_workflows(original, rerun))


__all__ = ["compare_workflows", "list_workflows", "rerun_workflow", "show_workflow", "workflow_regressions"]
