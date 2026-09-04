from research_os.core.types import GateStatus
from research_os.labs import BatteryLab, ElectrochemistryLab


def test_domain_foundation_requires_conditions():
    result = BatteryLab().run({"property": "capacity", "value": 1.0, "unit": "Ah", "method": "registered-method"})
    assert result.first_loss.status is GateStatus.INSUFFICIENT_EVIDENCE


def test_domain_foundation_does_not_fake_engine_evidence():
    result = ElectrochemistryLab().run({"property": "potential", "value": 1.2, "unit": "V", "conditions": {"temperature_k": 298}, "method": "registered-method"})
    assert result.status == "INDETERMINATE"
    assert not result.evidence

