"""Curated, source-backed research problem catalog for Research OS 3.3.

The records below are discovery inputs, not claims that the problems are
solved. URLs point to primary papers, official standards, official databases,
or official software documentation. The live Codex may rank these records but
cannot add sources, evidence levels, or scientific results.
"""

from __future__ import annotations

from typing import Any, Iterable

from research_os.core.types import EvidenceLevel
from research_os.knowledge import KnowledgeRetriever, ReviewStatus, SourceLocator, SourceRecord, SourceRegistry, SourceType, Zettel, ZettelType
from research_os.oracle.provider import LiveCodexProtocolError

from research_os.campaigns.models import ProblemCandidate, ProblemDiscoveryResult


REAL_SOURCE_CATALOG: tuple[SourceRecord, ...] = (
    SourceRecord("SRC-AQSOLDB-PAPER", "AqSolDB: A curated reference set of aqueous solubility and 2D descriptors", authors=("Sorkun et al.",), year=2019, doi="10.1038/s41597-019-0151-1", url="https://doi.org/10.1038/s41597-019-0151-1", source_type=SourceType.PAPER, metadata={"quality": "PRIMARY", "role": "dataset paper", "retrieval": "bibliographic citation only"}),
    SourceRecord("SRC-AQSOLDB-DATA", "AqSolDB pinned dataset-G release", organization="AqSolDB project", year=2019, url="https://raw.githubusercontent.com/mcsorkun/AqSolDB/8e02b548fd9a78778ff89a5aa9a460d1a289cc3a/data/dataset-G.csv", license="CC0-1.0 as declared by the pinned release", source_type=SourceType.DATASET, metadata={"quality": "DATASET_DOCUMENTATION", "commit": "8e02b548fd9a78778ff89a5aa9a460d1a289cc3a", "sha256": "e3b80a24edb5528fe3a7c4a808b26045804c73680183f43c21afbec905158071"}),
    SourceRecord("SRC-ESOL-PAPER", "ESOL: Estimating Aqueous Solubility Directly from Molecular Structure", authors=("John S. Delaney",), year=2004, doi="10.1021/ci034243x", url="https://doi.org/10.1021/ci034243x", source_type=SourceType.PAPER, metadata={"quality": "PRIMARY", "role": "published baseline method"}),
    SourceRecord("SRC-CANTERA-COMBUSTOR", "Cantera combustor residence-time example", organization="Cantera developers", year=2026, url="https://www.cantera.org/stable/examples/python/reactors/combustor.html", source_type=SourceType.MANUAL, metadata={"quality": "OFFICIAL_DOCUMENTATION", "role": "executable reference protocol", "mechanism": "gri30.yaml"}),
    SourceRecord("SRC-CANTERA-GRI30", "Cantera input and mechanism documentation", organization="Cantera developers", year=2026, url="https://www.cantera.org/dev/examples/input/index.html", source_type=SourceType.MANUAL, metadata={"quality": "OFFICIAL_DOCUMENTATION", "role": "mechanism scope and caveat"}),
    SourceRecord("SRC-NASA-HE-REPORT", "Hydrogen Embrittlement: A Review of the Literature", organization="NASA Technical Reports Server", year=2016, url="https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/20160005654.pdf", source_type=SourceType.REPORT, metadata={"quality": "PRIMARY", "role": "technical review/report"}),
    SourceRecord("SRC-NASA-STD-6016C", "NASA-STD-6016C: Standard Materials and Processes Requirements for Spacecraft", organization="NASA", year=2021, url="https://standards.nasa.gov/sites/default/files/standards/NASA/C/2021-09-30-NASA-STD-6016C-Approved.pdf", source_type=SourceType.STANDARD, metadata={"quality": "OFFICIAL_DOCUMENT", "role": "materials/process requirements"}),
    SourceRecord("SRC-NASA-MAPTIS", "Materials And Processes Technical Information System features", organization="NASA", year=2026, url="https://maptis.nasa.gov/Features", source_type=SourceType.DATABASE, metadata={"quality": "OFFICIAL_DATABASE", "role": "materials compatibility and failure data"}),
    SourceRecord("SRC-DOE-BATTERY-DATA-HUB", "DOE Battery Data Hub", organization="U.S. Department of Energy", year=2026, url="https://batterydata.energy.gov/", source_type=SourceType.DATASET, metadata={"quality": "OFFICIAL_DATABASE", "role": "battery data discovery and life prediction"}),
    SourceRecord("SRC-NASA-PCOE-RW3", "NASA PCoE RW3 room-temperature random-walk battery artifact", organization="NASA Prognostics Center of Excellence", year=2015, url="https://data.nasa.gov/dataset/randomized-battery-usage-3-room-temperature-variable-recharge-random-walk", license="https://www.usa.gov/government-works", source_type=SourceType.DATASET, metadata={"quality": "OFFICIAL_PUBLIC_ARTIFACT", "role": "raw battery degradation measurements", "artifact_url": "https://data.nasa.gov/docs/legacy/ames/3.Battery_Uniform_Distribution_Variable_Charge_Room_Temp_DataSet_2Post.zip", "artifact_sha256": "4e757b8b4e574202c32702000e1002f7a235d1c83a5729cef584ce528f3a4859", "artifact_size_bytes": 140923718, "schema": "MATLAB data.step fields documented by the archive README", "retrieval_date": "2026-09-04"}),
    SourceRecord("SRC-RCSB-1PXX", "RCSB PDB 1PXX: diclofenac bound to the cyclooxygenase active site of COX-2", organization="RCSB Protein Data Bank", year=2003, url="https://www.rcsb.org/structure/1PXX", source_type=SourceType.DATABASE, metadata={"quality": "OFFICIAL_DATABASE", "role": "experimental structure", "species": "Mus musculus", "structure_id": "1PXX", "pdb_doi": "10.2210/pdb1PXX/pdb"}),
    SourceRecord("SRC-NIST-WEBBOOK", "NIST Chemistry WebBook, SRD 69", organization="National Institute of Standards and Technology", year=2025, url="https://webbook.nist.gov/chemistry/", source_type=SourceType.DATABASE, metadata={"quality": "OFFICIAL_DATABASE", "role": "thermochemical and thermophysical reference data"}),
    SourceRecord("SRC-NIST-FLUID", "NIST Chemistry WebBook: Thermophysical Properties of Fluid Systems", organization="National Institute of Standards and Technology", year=2025, url="https://webbook.nist.gov/chemistry/fluid/", source_type=SourceType.DATABASE, metadata={"quality": "OFFICIAL_DATABASE", "role": "thermal transport reference data"}),
    SourceRecord("SRC-NASEM-REPRO", "Reproducibility and Replicability in Science", organization="National Academies of Sciences, Engineering, and Medicine", year=2019, url="https://nap.nationalacademies.org/collection/89/reproducibility", source_type=SourceType.REPORT, metadata={"quality": "CONSENSUS_REPORT", "role": "reproducibility definitions and practice"}),
)


def _p(problem_id: str, title: str, domain: str, context: str, question: str, matters: str, sources: tuple[str, ...], datasets: tuple[str, ...], capabilities: tuple[str, ...], engines: tuple[str, ...], level: EvidenceLevel, blockers: tuple[str, ...], safety: tuple[str, ...], *, executable: bool = False, quality: tuple[str, ...] = ()) -> ProblemCandidate:
    return ProblemCandidate(problem_id, title, domain, context, question, matters, sources, datasets, capabilities, engines, level, blockers, safety, quality or ("SOURCE_METADATA_VERIFIED",), executable)


REAL_PROBLEM_CATALOG: tuple[ProblemCandidate, ...] = (
    _p("P-MOL-01", "Scaffold OOD and uncertainty for aqueous solubility", "molecular", "Solubility models can be over-trusted when scaffold families shift.", "How does a real AqSolDB scaffold split expose applicability-domain failures and residual-interval coverage?", "Reliable early-stage property screening needs explicit failure modes and OOD exclusion.", ("SRC-AQSOLDB-PAPER", "SRC-AQSOLDB-DATA", "SRC-ESOL-PAPER"), ("aqsoldb-g-real-sample", "aqsoldb-g"), ("Morgan fingerprints", "scaffold split", "residual calibration"), ("numpy-ridge",), EvidenceLevel.E1_ML, ("the checked-in sample is not the full release", "no independent external test is bundled"), ("analysis-only; do not claim clinical or deployment efficacy",), executable=True),
    _p("P-MOL-02", "Published ESOL baseline versus scaffold generalization", "molecular", "A published linear solubility baseline is a useful incumbent but does not remove dataset shift.", "Does a published ESOL-style baseline retain error stability across scaffold and molecular-size segments?", "A transparent baseline makes model improvement and regression visible.", ("SRC-ESOL-PAPER", "SRC-AQSOLDB-PAPER"), ("AqSolDB-G"), ("descriptor audit", "segment analysis"), ("numpy-ridge",), EvidenceLevel.E1_ML, ("descriptor implementation parity must be demonstrated",), ("no molecule ranking without OOD and uncertainty checks",)),
    _p("P-COMB-01", "Hydrogen versus methane equilibrium under declared conditions", "combustion/energy", "Hydrogen and methane comparisons are meaningful only when the mechanism, mixture, temperature and pressure are recorded.", "Under the same Cantera equilibrium protocol, how do H2 and CH4 adiabatic HP outputs differ at selected equivalence ratios?", "Fuel and thermal system comparisons require traceable conditions and mechanism provenance.", ("SRC-CANTERA-COMBUSTOR", "SRC-CANTERA-GRI30"), ("none; engine mechanism is the computational input"), ("equilibrium request normalization", "condition capture"), ("cantera/gri30.yaml",), EvidenceLevel.E3_PHYSICS, ("GRI30 is an illustrative mechanism and not universal validation",), ("safe simulated equilibrium only; no hardware/control instruction",), executable=True),
    _p("P-COMB-02", "Mechanism and condition sensitivity in combustion comparisons", "combustion/energy", "The same fuel statement can produce different outputs when initial state or mechanism changes.", "Which recorded condition changes dominate the comparison, and which conclusions fail when the protocol changes?", "Sensitivity and reproducibility are prerequisites for engineering interpretation.", ("SRC-CANTERA-GRI30", "SRC-NIST-WEBBOOK"), ("none"), ("protocol comparison", "Ledger reproducibility"), ("cantera/gri30.yaml",), EvidenceLevel.E3_PHYSICS, ("only the registered mechanism is executable now",), ("simulation-only; no operational safety claim",), executable=True),
    _p("P-MAT-01", "Condition-specific hydrogen embrittlement evidence gap", "materials/degradation", "Hydrogen embrittlement depends on material, stress, environment and temperature; generic statements are unsafe.", "Can the available sources support a condition-matched conclusion for a named alloy, or do they only define the missing test matrix?", "Material compatibility decisions need material- and condition-specific evidence.", ("SRC-NASA-HE-REPORT", "SRC-NASA-STD-6016C", "SRC-NASA-MAPTIS"), ("MAPTIS records require access/review"), ("source synthesis", "condition matrix"), ("none configured",), EvidenceLevel.E4_CURATED_EXPERIMENTAL, ("no condition-matched alloy test is locally available", "MAPTIS access may be restricted"), ("do not provide a material approval or flight-safety recommendation",)),
    _p("P-MAT-02", "Alloy fluid compatibility and corrosion ranking reproducibility", "materials/degradation", "NASA materials databases expose tests across alloys and environments, but records are not interchangeable.", "Can compatibility rankings be reproduced after matching alloy, environment, stress, temperature and test method?", "Comparability controls prevent false transfer of a rating between conditions.", ("SRC-NASA-MAPTIS", "SRC-NASA-STD-6016C"), ("MAPTIS materials selection records"), ("source reconciliation", "condition matching"), ("none configured",), EvidenceLevel.E4_CURATED_EXPERIMENTAL, ("database access and test-condition coverage",), ("no procurement or qualification advice",)),
    _p("P-MAT-03", "Long-term outgassing and thermal-vacuum degradation evidence map", "materials/degradation", "Non-metallic materials can change under thermal-vacuum and long-duration exposure.", "Which material, exposure and measurement fields are required before a degradation claim can be supported?", "A structured evidence map makes missing aging tests explicit.", ("SRC-NASA-MAPTIS", "SRC-NASA-STD-6016C"), ("MAPTIS outgassing and MISSE records"), ("evidence schema", "gap analysis"), ("none configured",), EvidenceLevel.E4_CURATED_EXPERIMENTAL, ("no local long-duration exposure dataset",), ("do not certify material suitability",)),
    _p("P-BATT-01", "Battery degradation trajectory reproducibility from public records", "battery/electrochemistry", "Battery life datasets are heterogeneous in protocol, cell identity and environmental conditions.", "Can a public battery record be normalized into a condition-complete degradation experiment without inventing missing fields?", "Life prediction is only actionable when cycle, temperature, current and cell metadata are traceable.", ("SRC-NASA-PCOE-RW3", "SRC-DOE-BATTERY-DATA-HUB", "SRC-NASEM-REPRO"), ("battery-nasa-pcoe-rw3",), ("dataset schema audit", "uncertainty and missingness"), ("scipy optional MATLAB parser",), EvidenceLevel.E4_CURATED_EXPERIMENTAL, ("capacity and uncertainty fields may be absent from the public step schema", "license/access terms must remain recorded"), ("no battery control or safety recommendation",)),
    _p("P-PHARMA-01", "Species-disciplined COX-2 docking reproducibility", "pharma computational", "RCSB 1PXX is an experimental murine COX-2 structure with diclofenac; docking is not efficacy.", "Can a target-preparation and docking workflow be reproduced while preserving the source species and structural identity?", "Target identity and preparation affect every downstream computational interpretation.", ("SRC-RCSB-1PXX", "SRC-NASEM-REPRO"), ("RCSB PDB 1PXX"), ("target identity validation", "docking protocol audit"), ("vina (not configured)",), EvidenceLevel.E2_COMPUTATIONAL, ("no Vina executable/configured receptor in the current runtime",), ("no clinical, binding-affinity or therapeutic claim",)),
    _p("P-THERM-01", "Thermal-transport condition coverage for fluid estimates", "transport/thermal", "NIST SRD 69 provides thermophysical properties for selected fluids under declared state conventions.", "Which temperature/pressure states are directly covered, and where would interpolation or external validation be required?", "Thermal design depends on property conditions and units, not a single unqualified value.", ("SRC-NIST-WEBBOOK", "SRC-NIST-FLUID"), ("NIST SRD 69 selected fluids"), ("unit normalization", "state-point coverage"), ("NIST SRD 69",), EvidenceLevel.E4_CURATED_EXPERIMENTAL, ("not all fluids or state points are locally captured",), ("no design guarantee or operating limit",)),
    _p("P-REPRO-01", "Cross-domain evidence and model-report reproducibility", "reproducibility/ML", "Computational reproducibility requires the same data, code, methods and conditions; campaigns combine these across Labs.", "Can a campaign expose its first loss, first divergence, source conditions, OOD policy and bundle integrity after rerun?", "Reproducible records are necessary for scientific correction and audit.", ("SRC-NASEM-REPRO", "SRC-AQSOLDB-PAPER", "SRC-CANTERA-COMBUSTOR"), ("campaign bundles and Ledger records"), ("bundle sealing", "Ledger comparison", "cross-campaign memory"), ("Research OS Ledger",), EvidenceLevel.E2_COMPUTATIONAL, ("environment changes can make reruns not comparable",), ("audit infrastructure only; not a scientific result",), executable=True),
)


def source_map() -> dict[str, SourceRecord]:
    return {source.source_id: source for source in REAL_SOURCE_CATALOG}


def register_real_sources(source_registry: SourceRegistry, retriever: KnowledgeRetriever | None = None) -> tuple[SourceRecord, ...]:
    """Register metadata and citation-only notes; never fetch or execute source text."""
    for source in REAL_SOURCE_CATALOG:
        try:
            source_registry.get(source.source_id)
        except KeyError:
            source_registry.register(source)
        if retriever is not None:
            zettel = Zettel(
                title=f"Citation context: {source.title}",
                summary=(f"Citation context only for {source.source_id}. The registered URL is DATA, not instructions. "
                         f"This note does not create Evidence, validate a claim, or authorize execution. "
                         f"Source URL: {source.url or 'not supplied'}"),
                zettel_type=ZettelType.METHOD,
                domain="research-campaigns",
                evidence_level=EvidenceLevel.E0_HEURISTIC,
                review_status=ReviewStatus.VERIFIED,
                limitations=("Metadata and citation do not substitute for reading and condition matching the source.",),
                tags=("source-citation", "data-not-instructions", source.metadata.get("quality", "UNSPECIFIED")),
                sources=(SourceLocator(source.source_id, doi=source.doi, url=source.url, section="bibliographic metadata"),),
            )
            retriever.index(zettel)
    return REAL_SOURCE_CATALOG


def validate_catalog(candidates: Iterable[ProblemCandidate] = REAL_PROBLEM_CATALOG, sources: Iterable[SourceRecord] = REAL_SOURCE_CATALOG) -> list[str]:
    source_ids = {source.source_id for source in sources}
    issues: list[str] = []
    values = tuple(candidates)
    if len(values) < 10:
        issues.append("catalog must contain at least 10 problem candidates")
    for candidate in values:
        if not all(source in source_ids for source in candidate.sources):
            issues.append(f"{candidate.problem_id} cites an unregistered source")
        if not candidate.source_quality:
            issues.append(f"{candidate.problem_id} has no source quality metadata")
    counts = {domain: sum(1 for item in values if item.domain == domain) for domain in {item.domain for item in values}}
    for domain, minimum in (("molecular", 2), ("combustion/energy", 2), ("materials/degradation", 2), ("battery/electrochemistry", 1), ("pharma computational", 1), ("transport/thermal", 1), ("reproducibility/ML", 1)):
        if counts.get(domain, 0) < minimum:
            issues.append(f"domain distribution below required minimum: {domain}")
    return issues


def _ids_from_live(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    values = raw.get(key) or raw.get("selected_" + key) or ()
    if not isinstance(values, list):
        raise LiveCodexProtocolError(f"{key} must be a JSON list")
    return tuple(str(item.get("problem_id") if isinstance(item, dict) else item) for item in values)


def discover_and_select(provider: Any, *, context: dict[str, Any] | None = None, candidates: tuple[ProblemCandidate, ...] = REAL_PROBLEM_CATALOG, sources: tuple[SourceRecord, ...] = REAL_SOURCE_CATALOG) -> ProblemDiscoveryResult:
    """Ask the live boundary to rank registered problems, then validate IDs."""
    issues = validate_catalog(candidates, sources)
    if issues:
        raise ValueError("invalid real problem catalog: " + "; ".join(issues))
    payload = {"candidates": [item.to_dict() for item in candidates], "sources": [item.to_dict() for item in sources], "selection_criteria": {"primary_count": 3, "secondary_count": 2, "cover_domains": True, "prefer_executable": True, "required_primary_problem_ids": ["P-MOL-01", "P-COMB-01", "P-MAT-01"], "required_secondary_problem_ids": ["P-BATT-01", "P-PHARMA-01"], "mission_note": "These five records are the named 3.3 campaign gates; rank and justify them from the supplied catalog, then preserve this exact coverage."}}
    discovery_raw = provider.discover_problems({**payload, **(context or {})})
    # Discovery and final selection are separate live operations. The second
    # call makes the named milestone gates explicit without allowing the model
    # to invent or replace a source-backed problem.
    raw = provider.select_campaigns([item.to_dict() for item in candidates], payload["selection_criteria"])
    primary = _ids_from_live(raw, "primary_problem_ids")
    secondary = _ids_from_live(raw, "secondary_problem_ids")
    known = {item.problem_id: item for item in candidates}
    if len(primary) != 3 or len(secondary) != 2 or set(primary) & set(secondary):
        raise LiveCodexProtocolError("live selection must contain 3 distinct primary and 2 distinct secondary problem IDs")
    if any(item not in known for item in (*primary, *secondary)):
        raise LiveCodexProtocolError("live selection referenced an unknown problem ID")
    returned_ids = {str(item.get("problem_id")) for item in raw.get("candidates") or () if isinstance(item, dict) and item.get("problem_id")}
    if returned_ids and not returned_ids.issubset(set(known)):
        raise LiveCodexProtocolError("live discovery returned an unknown problem ID")
    required_primary = ("P-MOL-01", "P-COMB-01", "P-MAT-01")
    required_secondary = ("P-BATT-01", "P-PHARMA-01")
    if set(primary) != set(required_primary) or set(secondary) != set(required_secondary):
        raise LiveCodexProtocolError("campaign selection did not preserve the required 3.3 primary/secondary coverage")
    ranking = tuple({"problem_id": str(item.get("problem_id")), "priority": item.get("priority"), "reason": str(item.get("reason") or item.get("justification") or "")[:500]} for item in discovery_raw.get("candidates") or () if isinstance(item, dict) and item.get("problem_id") in known)
    return ProblemDiscoveryResult(candidates, primary, secondary, str(raw.get("reasoning_summary") or raw.get("summary") or discovery_raw.get("reasoning_summary") or "Live Codex ranked the registered source-backed catalog."), {"provider": getattr(provider, "provider_id", type(provider).__name__), "candidate_count": len(candidates), "source_count": len(sources), "discovery_raw_keys": sorted(discovery_raw), "selection_raw_keys": sorted(raw), "discovery_reasoning_summary": str(discovery_raw.get("reasoning_summary") or discovery_raw.get("summary") or ""), "discovery_candidate_ranking": list(ranking), "required_primary_problem_ids": list(required_primary), "required_secondary_problem_ids": list(required_secondary)})
