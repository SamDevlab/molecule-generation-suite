from __future__ import annotations

from typing import Final


# Portable structural freeze captured before any CROSSDOCK-001 Vina execution.
PREFLIGHT_RUN_ID: Final = 34607126629
PREFLIGHT_ARTIFACT_ID: Final = 10266663459
PREFLIGHT_ARTIFACT_ZIP_SHA256: Final = "1c2a1f62e4290b3c21cfc918579c6f34e362c82c63a943bc2d8d4e1ee9cdcb5d"
PREFLIGHT_SELECTION_MANIFEST_HASH: Final = "852f027bdc55ba8c2def9d3fde0a80e70cf6a4ffc375b4eb8a696e436b681215"
PREFLIGHT_FREEZE_HEAD_SHA: Final = "4192379f4a88262a20e2e64a46b486cd2047aa18"

# The first no-Vina preflight was scientifically identical but its manifest
# included raw floating-point SVD/grid values and was therefore not portable
# across BLAS/LAPACK runners. It is retained only as audit provenance and must
# not be used as the CROSSDOCK-001 structural identity.
NONPORTABLE_PREFLIGHT_RUN_ID: Final = 34605661949
NONPORTABLE_PREFLIGHT_ARTIFACT_ID: Final = 10266555733
NONPORTABLE_PREFLIGHT_RAW_MANIFEST_HASH: Final = (
    "9631023f89b2971a503cab193989e0ac8d3eb53642d27fdcbf5572e5e04e4a26"
)


# Structural identities frozen from the successful canonical no-Vina preflight.
# These values are outcome-independent and must not be changed in response to
# later Vina poses or RMSDs without a new CROSSDOCK protocol version.
FROZEN_DIRECTED_STRUCTURAL_IDENTITIES: Final = {
    "XDK-01-1": {
        "source_pdb_sha256": "90a8967dff4cb0cc7a7dc8fc94c4179a021ddc02d9489b3c742b44c1d7b5c75f",
        "target_pdb_sha256": "6149c1b553d3017cd0e809989cd2d08275f715ca36b6fbcf78319aa056f342f5",
        "transformed_source_reference_coordinate_hash": "b835ca7aa3f3416ab9d4b124911368e265c31eae0bb8ae4d6740b9a94c9cc2e6",
        "target_reference_coordinate_hash": "971794381887a06bd2dc3b77028bc1512554cc7c947d651ea2ef31930cfaa9a1",
        "grid_hash": "3fd0e6e4e66d984c66a0f19e257f89cf6231bf67b0ab5f9264bb808ddca41540",
        "matched_identical_pocket_ca_pairs": 73,
    },
    "XDK-01-2": {
        "source_pdb_sha256": "6149c1b553d3017cd0e809989cd2d08275f715ca36b6fbcf78319aa056f342f5",
        "target_pdb_sha256": "90a8967dff4cb0cc7a7dc8fc94c4179a021ddc02d9489b3c742b44c1d7b5c75f",
        "transformed_source_reference_coordinate_hash": "28ba3cb70fabf117948e16652499cb729d9ec549d3ab39206de5975d88a62565",
        "target_reference_coordinate_hash": "c0a108d90da325eef4fc591760d7ccff2ee6b43fcbdfe8d1027ad9e9eb8f49e8",
        "grid_hash": "c3a3838741c7d6f08940ea71f7cb1a09b4a185e4027449750eda5f2625c0aac4",
        "matched_identical_pocket_ca_pairs": 82,
    },
    "XDK-02-1": {
        "source_pdb_sha256": "6ef163ddcf3e3298b6c0982dc8c06e89c61b9d6705fb34ced7e142a0313d764d",
        "target_pdb_sha256": "6c26e0fa11bb312260fcdda1a0d9dd8ca2aa3c0284e2a56ffa8a3570e2b71cee",
        "transformed_source_reference_coordinate_hash": "a38120b95cf6ec5fc2d9812cd29f84ed8145f0c5f1edfba4cc3c78f11aa9b797",
        "target_reference_coordinate_hash": "542593630ee2dbc8dfbb021b4aaa2321a6070cf087a9e80b8e0a5ed527241e7e",
        "grid_hash": "8eb6174016d8ee1d2f37b69d450b5a410d77a2b7184278b70df9569663382f7b",
        "matched_identical_pocket_ca_pairs": 58,
    },
    "XDK-02-2": {
        "source_pdb_sha256": "6c26e0fa11bb312260fcdda1a0d9dd8ca2aa3c0284e2a56ffa8a3570e2b71cee",
        "target_pdb_sha256": "6ef163ddcf3e3298b6c0982dc8c06e89c61b9d6705fb34ced7e142a0313d764d",
        "transformed_source_reference_coordinate_hash": "258c22d3dfdd73bcb1331ecbb568217f243f09110c285c12437bb96c9e56cfc2",
        "target_reference_coordinate_hash": "985d0d600bd2c7065b6b26d35e5818c2e13d61ad7b84714422380214cabfd087",
        "grid_hash": "0fac4d1e516f9f150304e185553b91044f76f2ece42df9c5df013cd61a7886d2",
        "matched_identical_pocket_ca_pairs": 61,
    },
    "XDK-03-1": {
        "source_pdb_sha256": "c6131f20e2c0134b1716f46a6733cf3b2478ec9aded7a4a988327d87f6b94328",
        "target_pdb_sha256": "6a436d9e222c4f5bbfa20495a2f77113201adb2fc7a168297abb19192b80d326",
        "transformed_source_reference_coordinate_hash": "8570e133f177ce3bf4302c19fe32ec2b7af6d6fbe9c568ef8ae4a4ea71f20383",
        "target_reference_coordinate_hash": "f5a881c1d853f64a9f448d9bb7a0929c12bea49410900409dc83883764b542b1",
        "grid_hash": "a71622c4ca27e3b047074e6446c3e6c591e846ba3326757687deaa6535a7f3af",
        "matched_identical_pocket_ca_pairs": 105,
    },
    "XDK-03-2": {
        "source_pdb_sha256": "6a436d9e222c4f5bbfa20495a2f77113201adb2fc7a168297abb19192b80d326",
        "target_pdb_sha256": "c6131f20e2c0134b1716f46a6733cf3b2478ec9aded7a4a988327d87f6b94328",
        "transformed_source_reference_coordinate_hash": "dc12e097f5de00ba6b1c7e58d5df00a195f2c24d4beac2964e14584c758d388c",
        "target_reference_coordinate_hash": "e71fdce9e2d09dd759a725d0b44dba6e57bf8583b9871d3bb9c7a2be30194b69",
        "grid_hash": "3548e44f2796802757c4a6ce85173b176373223d1c8ec273413d7d4f93b6154f",
        "matched_identical_pocket_ca_pairs": 92,
    },
    "XDK-04-1": {
        "source_pdb_sha256": "452e2ef0df640d032c98c7f3b127fe0b04aa3d418d4da965028007fae612e018",
        "target_pdb_sha256": "5be35938659cacd3a683a44f9a2482f6eeb538b303f0d0463bdd48d2c6481b7b",
        "transformed_source_reference_coordinate_hash": "3f2f31aecb60734c2a27c3242239445d5d09ddc3bedf0470888228bea29f2e51",
        "target_reference_coordinate_hash": "e603f0cfa32f8a36e9a09a1f4ca8ea17b6bd995aa7b5497fe36df070e6894f8f",
        "grid_hash": "dc18fa62afe52216852a707433a2bafe2302a90c1a713296346cb9338bca4723",
        "matched_identical_pocket_ca_pairs": 73,
    },
    "XDK-04-2": {
        "source_pdb_sha256": "5be35938659cacd3a683a44f9a2482f6eeb538b303f0d0463bdd48d2c6481b7b",
        "target_pdb_sha256": "452e2ef0df640d032c98c7f3b127fe0b04aa3d418d4da965028007fae612e018",
        "transformed_source_reference_coordinate_hash": "f4aff4666d5b3f650733e71154b466b88055282b8c20cfe01fa53c7922d54804",
        "target_reference_coordinate_hash": "40a513fc1c56b0ddcda8c4ea5d33a152d50f949914ddab957a62040095013b3c",
        "grid_hash": "cf122ff2a57d49a529865d59fb4a64748946fcbb6f64e9b5b4ded9ecf7e0ff27",
        "matched_identical_pocket_ca_pairs": 84,
    },
    "XDK-05-1": {
        "source_pdb_sha256": "bd29e8407047a2c8863a5039823d74978ba615e01b06bfe501e4827e833ae48d",
        "target_pdb_sha256": "5255e85c4fc9d24087390c76d1dc7a43921ba3208904aec9ea335c3699fe60c3",
        "transformed_source_reference_coordinate_hash": "9c17ec4b6548c04554c96f7dcfa16acbc19ff6aef4cc367c3334093e7b8e99f0",
        "target_reference_coordinate_hash": "860b86b7e318f01ec6c4f0107cd24ffe9e88ef7760e31a36e34305286efa111c",
        "grid_hash": "7ec4ecf8fb0692051e0015a1191345cc2dda2c289c579234d0707da291c511b8",
        "matched_identical_pocket_ca_pairs": 73,
    },
    "XDK-05-2": {
        "source_pdb_sha256": "5255e85c4fc9d24087390c76d1dc7a43921ba3208904aec9ea335c3699fe60c3",
        "target_pdb_sha256": "bd29e8407047a2c8863a5039823d74978ba615e01b06bfe501e4827e833ae48d",
        "transformed_source_reference_coordinate_hash": "fa7c84d284198ddbd8faaa6f648723f4a06ad7922bbb5e731131f1ef3e250ea4",
        "target_reference_coordinate_hash": "ca4e7c655c7340e4a934f83c2fcce67c29ebb981fe909db123ca07d36bb2b47b",
        "grid_hash": "79613819225216ddc84a00f4ddf5112d548da636dc446c75c0e4c7713f8e355e",
        "matched_identical_pocket_ca_pairs": 73,
    },
}
