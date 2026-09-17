from __future__ import annotations

from typing import Any

from research_os.docking.crossdock_identity import stable_hash


PREFLIGHT_RUN_ID = 34642755042
PREFLIGHT_HEAD_SHA = "fa0a737eaa1989856474068f330c3c2c52d74344"
PREFLIGHT_ARTIFACT_ID = 10280154166
PREFLIGHT_ARTIFACT_ZIP_SHA256 = "2026a042818c4ec021fea672d4ceba72a31734c61da4ce8c97413dcb3bfcace8"
SELECTION_MANIFEST_HASH = "c5fae682ecf6b7e8884de8b4d02fd052d306ea3b5d421b6ad44814289afae805"
STRUCTURALLY_ELIGIBLE_COUNT = 10
CHEMISTRY_READY_FOR_VINA_COUNT = 9


FROZEN_STRUCTURAL_IDENTITIES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "APD-001", "apo_pdb_id": "1FTO", "holo_pdb_id": "1FTM",
        "ligand_components": ["AMQ"], "ligand_representation": "single_ccd",
        "apo_pdb_sha256": "0ce7725547277e0f5099cfdf8ab160f10565aca56f2673576b029e6b9a8ff5c5",
        "holo_pdb_sha256": "ed3e80b20042c83ce90e2722878210e0ac46905472980bdeaea4c49a9d200ee0",
        "matched_identical_global_ca_pairs": 257,
        "holo_reference_coordinate_hash": "5352f4a8b0add589f6b952173f4fe4cb684098d64b76cd64633d076b4db963fd",
        "transformed_holo_reference_coordinate_hash": "ccf67ec008dc4a63f21b0263c745b16dcbebfe18b21eb32fb9d90dfccf5b8f4d",
        "grid_hash": "32a48e733ed5811a5b6ee605ca40da9db4ec46e09b56f7210091fd9b3f5d8273",
        "chemistry_ready_for_vina": True, "status": "STRUCTURALLY_ELIGIBLE", "reason": None,
    },
    {
        "case_id": "APD-002", "apo_pdb_id": "1JEJ", "holo_pdb_id": "1JG6",
        "ligand_components": ["UDP"], "ligand_representation": "single_ccd",
        "apo_pdb_sha256": "acb4491398d6c9314df4f86c23bef6173673c8198911759c46473ff91b8cede0",
        "holo_pdb_sha256": "a8dd05039e3aa3ebcfc0e9d7a7ab3e6c1adbe42a5ba8cefc195bcd8ff25d4540",
        "matched_identical_global_ca_pairs": 351,
        "holo_reference_coordinate_hash": "5b0878987f0c9e7f7fe66ce95b70d97b6602417b8b00fdd2d7b3618a8c752609",
        "transformed_holo_reference_coordinate_hash": "ba2d66ac1b2df5eb501971cad24d1f62dcbff40b482de67c31c35809be262fd5",
        "grid_hash": "89262a32a1b65b3d87fb18b4eff60fc06dcde87981b2cfefa5c2988726411620",
        "chemistry_ready_for_vina": True, "status": "STRUCTURALLY_ELIGIBLE", "reason": None,
    },
    {
        "case_id": "APD-003", "apo_pdb_id": "1GUD", "holo_pdb_id": "1RPJ",
        "ligand_components": ["ALL"], "ligand_representation": "single_ccd",
        "apo_pdb_sha256": "39690cc3b27d863ce7f0c2501098ad7865df4b0cae3033a0088233f00e7632cd",
        "holo_pdb_sha256": "a92c80a7c9335c70f602bc93fa8b90a1d39136a07cfe9595bad7e6bbfc3951e5",
        "matched_identical_global_ca_pairs": 288,
        "holo_reference_coordinate_hash": "b63b2365c278ec0074cca7b9ad7a51e0ced6840c2af346d2923f17d36dad5d1c",
        "transformed_holo_reference_coordinate_hash": "c4abe58e6a046c1de40eb1c0dd45fd7bc4f63b8e2ab1949510c9ec7bc51132cf",
        "grid_hash": "3bd54009275f7a78a27adeedc143561744b0e20f39fb890105801eacaf486ad0",
        "chemistry_ready_for_vina": True, "status": "STRUCTURALLY_ELIGIBLE", "reason": None,
    },
    {
        "case_id": "APD-004", "apo_pdb_id": "1URP", "holo_pdb_id": "2DRI",
        "ligand_components": ["RIP"], "ligand_representation": "single_ccd",
        "apo_pdb_sha256": "bec62c4708fb02bfff5c8688edc209878dadad4f24a3941e800e946d3f470594",
        "holo_pdb_sha256": "4bb0398e05a34fcba530e1afd2696e0f5822c190787fc78d29fdcd5b06c16b35",
        "matched_identical_global_ca_pairs": 271,
        "holo_reference_coordinate_hash": "8c6158195559d2f1d82366e31cbe7666f4b0a01edc8d5c872e49fa4eadb411ba",
        "transformed_holo_reference_coordinate_hash": "2840d4781616d3900dcbdf3230462df12d880d5b215c8afbbc9ec7d2efe43c96",
        "grid_hash": "6fbdfb979fc4eae2d9ca41b14f677262efd9270864b6f03803405fb61c0b73d4",
        "chemistry_ready_for_vina": True, "status": "STRUCTURALLY_ELIGIBLE", "reason": None,
    },
    {
        "case_id": "APD-005", "apo_pdb_id": "1USG", "holo_pdb_id": "1USI",
        "ligand_components": ["PHE"], "ligand_representation": "single_ccd",
        "apo_pdb_sha256": "f996b2dd2d9e2104acb659dd4d6841859cbf26e8630a4c0b1297c3f9840433b8",
        "holo_pdb_sha256": "a736ec7553dfcfdf33345c8eaeeb75bc8cfcea533bc5335f9c0e938e361a3cf8",
        "matched_identical_global_ca_pairs": 345,
        "holo_reference_coordinate_hash": "e51188114c9aa3f6c7468f6d58dea703542ff95f4e19b17b0f173ddffd90e4e2",
        "transformed_holo_reference_coordinate_hash": "682566809a5273fb4b4467d31b0b3d3afeef30cf372a268f89002c536225489b",
        "grid_hash": "245337e0e3d586a6695186239d72d3a0df8a41d7e8e03cf1d2383d5f2c0ece3d",
        "chemistry_ready_for_vina": True, "status": "STRUCTURALLY_ELIGIBLE", "reason": None,
    },
    {
        "case_id": "APD-006", "apo_pdb_id": "1RF5", "holo_pdb_id": "1RF4",
        "ligand_components": ["SPQ"], "ligand_representation": "single_ccd",
        "apo_pdb_sha256": "3e327ed733fece4c37d56fa1c337d9d22a1956e99bc203c13fca2bf2146e575f",
        "holo_pdb_sha256": "4179442c7fa29744fba08ef57528c96bba2ac8760c3faff4c6b76de32440d109",
        "matched_identical_global_ca_pairs": 427,
        "holo_reference_coordinate_hash": "0d12d168ffba95b309fcebdde9cf791f64fecdf73d9c3b1c4f3b19e63011c397",
        "transformed_holo_reference_coordinate_hash": "7f8abb711910d00e1e28aa1e0891406bbdb25fe625ff9039174dc5c201d40b1e",
        "grid_hash": "8a401471d60de42da2d6bd5d9b66f9b80bcc7a14f221363fd1cba412517bb0d4",
        "chemistry_ready_for_vina": True, "status": "STRUCTURALLY_ELIGIBLE", "reason": None,
    },
    {
        "case_id": "APD-007", "apo_pdb_id": "1SW5", "holo_pdb_id": "1SW2",
        "ligand_components": ["BET"], "ligand_representation": "single_ccd",
        "apo_pdb_sha256": "06b2712fe25ddad5b69171a3ff80b9cc9efec2983cdc981b3f0cee2698773355",
        "holo_pdb_sha256": "1f40b28ab62214959ef1cfb0c07a375e9deb6e5674aa1599ee6f91853710996c",
        "matched_identical_global_ca_pairs": 270,
        "holo_reference_coordinate_hash": "d8bd23ca3f24a1d98bda4298351d36f2e3a8fb3224de5c1d639a535005da6f00",
        "transformed_holo_reference_coordinate_hash": "602d52a1355b258ec5867d9eb71ee6ea6054a64f3e05f589b6216c31fb707ef9",
        "grid_hash": "67d617706586b0ffce9741d6791daddba6629cdff597341daf3fb9640a2873b3",
        "chemistry_ready_for_vina": True, "status": "STRUCTURALLY_ELIGIBLE", "reason": None,
    },
    {
        "case_id": "APD-008", "apo_pdb_id": "1EX6", "holo_pdb_id": "1EX7",
        "ligand_components": ["5GP"], "ligand_representation": "single_ccd",
        "apo_pdb_sha256": "546afe6d3517db719edbf0b31f7fe0a9731a31e2d61b750c5dc318921ee2aeb0",
        "holo_pdb_sha256": "545bb8efeea0d3c1629502ceb240b4278b18e8fba7ffae320b921d05046798ee",
        "matched_identical_global_ca_pairs": 186,
        "holo_reference_coordinate_hash": "02500fcb1d6a9f3d5b409ffa698f45440e22c3fe08b59404e7b27c8e828ead1b",
        "transformed_holo_reference_coordinate_hash": "02cfec87655f2be9d56d7eeaafcb505051916ddec6f2122c8e4b39c57795dd0b",
        "grid_hash": "c8ceadfc3b453b64873d83edf6970ea9494d7f35cc628554de67bfc6aeaac368",
        "chemistry_ready_for_vina": True, "status": "STRUCTURALLY_ELIGIBLE", "reason": None,
    },
    {
        "case_id": "APD-009", "apo_pdb_id": "2E2N", "holo_pdb_id": "2E2O",
        "ligand_components": ["BGC"], "ligand_representation": "single_ccd",
        "apo_pdb_sha256": "5feb770ff43215aa327509ba9174e4076a3962393493a49074e822dc624e57b2",
        "holo_pdb_sha256": "978d8d59c2fb03c6691b6e51ffd8098786334c13363c6ebaf04707708adb3a8e",
        "matched_identical_global_ca_pairs": 298,
        "holo_reference_coordinate_hash": "bcb8b22fb9bf71e4f07d8beefb5b3f525c9d1797dd45823f605b9c8c368adad3",
        "transformed_holo_reference_coordinate_hash": "9b9530b6789cbba566b8f8b5ab37580a377d50585086c1b981bc33cc881745d0",
        "grid_hash": "2829a1e8129d8e73b8db45dbd5d003aeb96eec85d642f93c1c06a661cd8a51cb",
        "chemistry_ready_for_vina": True, "status": "STRUCTURALLY_ELIGIBLE", "reason": None,
    },
    {
        "case_id": "APD-010", "apo_pdb_id": "1Y3Q", "holo_pdb_id": "1Y3N",
        "ligand_components": ["BEM", "MAV"], "ligand_representation": "branched_glycan",
        "apo_pdb_sha256": "47a531a5430f585f133bce3069a952d29d591610d8442de522e9b37b7348efbe",
        "holo_pdb_sha256": "d524b4932316fdaf7fbea162aae79285639010f51bfb4a09c169127aa0248c8f",
        "matched_identical_global_ca_pairs": 490,
        "holo_reference_coordinate_hash": "77f9f08b253ad978dba2f931b69039cb029191b296139111caca65a1294ae419",
        "transformed_holo_reference_coordinate_hash": "2f6132da1553abbca2b5acfb31065299e0e3bfc7d3006e31778ad22dffdc8641",
        "grid_hash": "57cc2739e03c6d55f835d035b0011ca90687793d1e0d5db029d242c0deb55399",
        "chemistry_ready_for_vina": False, "status": "STRUCTURALLY_ELIGIBLE", "reason": None,
    },
)


def portable_manifest_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": record["case"]["case_id"],
            "apo_pdb_id": record["case"]["apo_pdb_id"],
            "holo_pdb_id": record["case"]["holo_pdb_id"],
            "ligand_components": record["case"]["holo_ligand_components"],
            "ligand_representation": record["case"]["ligand_representation"],
            "apo_pdb_sha256": record.get("apo_pdb_sha256"),
            "holo_pdb_sha256": record.get("holo_pdb_sha256"),
            "matched_identical_global_ca_pairs": record.get("matched_identical_global_ca_pairs"),
            "holo_reference_coordinate_hash": record.get("holo_reference_coordinate_hash"),
            "transformed_holo_reference_coordinate_hash": record.get("transformed_holo_reference_coordinate_hash"),
            "grid_hash": (record.get("grid") or {}).get("grid_hash"),
            "chemistry_ready_for_vina": record["chemistry_ready_for_vina"],
            "status": record["status"],
            "reason": record.get("reason"),
        }
        for record in report["records"]
    ]


def validate_frozen_preflight(report: dict[str, Any]) -> None:
    if report.get("docking_executed") is not False:
        raise ValueError("frozen APODOCK preflight must not execute docking")
    if report.get("vina_imported_or_invoked") is not False:
        raise ValueError("frozen APODOCK preflight must not import or invoke Vina")
    if report.get("structurally_eligible_count") != STRUCTURALLY_ELIGIBLE_COUNT:
        raise ValueError("APODOCK structural eligibility count changed")
    if report.get("chemistry_ready_for_vina_count") != CHEMISTRY_READY_FOR_VINA_COUNT:
        raise ValueError("APODOCK chemistry-readiness count changed")
    observed = portable_manifest_from_report(report)
    if observed != list(FROZEN_STRUCTURAL_IDENTITIES):
        raise ValueError("APODOCK portable structural identities changed")
    observed_hash = stable_hash(observed)
    if observed_hash != SELECTION_MANIFEST_HASH:
        raise ValueError(
            f"APODOCK selection manifest hash changed: {observed_hash} != {SELECTION_MANIFEST_HASH}"
        )
    if report.get("selection_manifest_hash") != SELECTION_MANIFEST_HASH:
        raise ValueError("reported APODOCK selection manifest hash changed")
