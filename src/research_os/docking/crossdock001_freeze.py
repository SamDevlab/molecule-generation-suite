from __future__ import annotations

from typing import Final


PREFLIGHT_RUN_ID: Final = 34605661949
PREFLIGHT_ARTIFACT_ID: Final = 10266555733
PREFLIGHT_ARTIFACT_ZIP_SHA256: Final = "de539ce3c3f08d892ae967bb09f7aaac0fd4cec6fadfe5407ad3ff0cd650eff4"
PREFLIGHT_SELECTION_MANIFEST_HASH: Final = "9631023f89b2971a503cab193989e0ac8d3eb53642d27fdcbf5572e5e04e4a26"
PREFLIGHT_FREEZE_HEAD_SHA: Final = "34780d629b800578becd72ad1280b36c1b90f252"


# Structural identities frozen from the successful no-Vina preflight. These
# values are outcome-independent and must not be changed in response to later
# Vina poses or RMSDs without a new CROSSDOCK protocol version.
FROZEN_DIRECTED_STRUCTURAL_IDENTITIES: Final = {
    "XDK-01-1": {
        "source_pdb_sha256": "90a8967dff4cb0cc7a7dc8fc94c4179a021ddc02d9489b3c742b44c1d7b5c75f",
        "target_pdb_sha256": "6149c1b553d3017cd0e809989cd2d08275f715ca36b6fbcf78319aa056f342f5",
        "transformed_source_reference_coordinate_hash": "b835ca7aa3f3416ab9d4b124911368e265c31eae0bb8ae4d6740b9a94c9cc2e6",
        "target_reference_coordinate_hash": "971794381887a06bd2dc3b77028bc1512554cc7c947d651ea2ef31930cfaa9a1",
        "grid_hash": "24b5cbbe9f293d36a7082a61bc6e71984cb4a0a3a3aa6fe703ecb39cc2a14ca3",
        "matched_identical_pocket_ca_pairs": 73,
    },
    "XDK-01-2": {
        "source_pdb_sha256": "6149c1b553d3017cd0e809989cd2d08275f715ca36b6fbcf78319aa056f342f5",
        "target_pdb_sha256": "90a8967dff4cb0cc7a7dc8fc94c4179a021ddc02d9489b3c742b44c1d7b5c75f",
        "transformed_source_reference_coordinate_hash": "28ba3cb70fabf117948e16652499cb729d9ec549d3ab39206de5975d88a62565",
        "target_reference_coordinate_hash": "c0a108d90da325eef4fc591760d7ccff2ee6b43fcbdfe8d1027ad9e9eb8f49e8",
        "grid_hash": "d07a95db50941bf2fd80bbc199aec2bf541813895c1132f34b819c55abdaa2d8",
        "matched_identical_pocket_ca_pairs": 82,
    },
    "XDK-02-1": {
        "source_pdb_sha256": "6ef163ddcf3e3298b6c0982dc8c06e89c61b9d6705fb34ced7e142a0313d764d",
        "target_pdb_sha256": "6c26e0fa11bb312260fcdda1a0d9dd8ca2aa3c0284e2a56ffa8a3570e2b71cee",
        "transformed_source_reference_coordinate_hash": "a38120b95cf6ec5fc2d9812cd29f84ed8145f0c5f1edfba4cc3c78f11aa9b797",
        "target_reference_coordinate_hash": "542593630ee2dbc8dfbb021b4aaa2321a6070cf087a9e80b8e0a5ed527241e7e",
        "grid_hash": "a639295dcb20687f3e4dc64e1e09f8dab9cf47157c9f3dbd0c1e3833869d9967",
        "matched_identical_pocket_ca_pairs": 58,
    },
    "XDK-02-2": {
        "source_pdb_sha256": "6c26e0fa11bb312260fcdda1a0d9dd8ca2aa3c0284e2a56ffa8a3570e2b71cee",
        "target_pdb_sha256": "6ef163ddcf3e3298b6c0982dc8c06e89c61b9d6705fb34ced7e142a0313d764d",
        "transformed_source_reference_coordinate_hash": "258c22d3dfdd73bcb1331ecbb568217f243f09110c285c12437bb96c9e56cfc2",
        "target_reference_coordinate_hash": "985d0d600bd2c7065b6b26d35e5818c2e13d61ad7b84714422380214cabfd087",
        "grid_hash": "8bf29f005a41f49fd7637a086d0adcfa88633198a22845ac0f534aef3a7bacd4",
        "matched_identical_pocket_ca_pairs": 61,
    },
    "XDK-03-1": {
        "source_pdb_sha256": "c6131f20e2c0134b1716f46a6733cf3b2478ec9aded7a4a988327d87f6b94328",
        "target_pdb_sha256": "6a436d9e222c4f5bbfa20495a2f77113201adb2fc7a168297abb19192b80d326",
        "transformed_source_reference_coordinate_hash": "8570e133f177ce3bf4302c19fe32ec2b7af6d6fbe9c568ef8ae4a4ea71f20383",
        "target_reference_coordinate_hash": "f5a881c1d853f64a9f448d9bb7a0929c12bea49410900409dc83883764b542b1",
        "grid_hash": "53677f6dfc471f5393475325428df73f099fa317e490ca0a308caa88b8965db8",
        "matched_identical_pocket_ca_pairs": 105,
    },
    "XDK-03-2": {
        "source_pdb_sha256": "6a436d9e222c4f5bbfa20495a2f77113201adb2fc7a168297abb19192b80d326",
        "target_pdb_sha256": "c6131f20e2c0134b1716f46a6733cf3b2478ec9aded7a4a988327d87f6b94328",
        "transformed_source_reference_coordinate_hash": "dc12e097f5de00ba6b1c7e58d5df00a195f2c24d4beac2964e14584c758d388c",
        "target_reference_coordinate_hash": "e71fdce9e2d09dd759a725d0b44dba6e57bf8583b9871d3bb9c7a2be30194b69",
        "grid_hash": "84ced58efb1032533877c0a4fcc87bd5ed28d660c535581ca20ed360ebeb6c34",
        "matched_identical_pocket_ca_pairs": 92,
    },
    "XDK-04-1": {
        "source_pdb_sha256": "452e2ef0df640d032c98c7f3b127fe0b04aa3d418d4da965028007fae612e018",
        "target_pdb_sha256": "5be35938659cacd3a683a44f9a2482f6eeb538b303f0d0463bdd48d2c6481b7b",
        "transformed_source_reference_coordinate_hash": "3f2f31aecb60734c2a27c3242239445d5d09ddc3bedf0470888228bea29f2e51",
        "target_reference_coordinate_hash": "e603f0cfa32f8a36e9a09a1f4ca8ea17b6bd995aa7b5497fe36df070e6894f8f",
        "grid_hash": "ba4a1be2a0604c9ee0142586f1e7c0cf5c6b12e2d7bc9693422120ef39894954",
        "matched_identical_pocket_ca_pairs": 73,
    },
    "XDK-04-2": {
        "source_pdb_sha256": "5be35938659cacd3a683a44f9a2482f6eeb538b303f0d0463bdd48d2c6481b7b",
        "target_pdb_sha256": "452e2ef0df640d032c98c7f3b127fe0b04aa3d418d4da965028007fae612e018",
        "transformed_source_reference_coordinate_hash": "f4aff4666d5b3f650733e71154b466b88055282b8c20cfe01fa53c7922d54804",
        "target_reference_coordinate_hash": "40a513fc1c56b0ddcda8c4ea5d33a152d50f949914ddab957a62040095013b3c",
        "grid_hash": "f3381f4b7cfdca5586f6957eee0ccfe49fcd8cacb972068a50b4e3ce903a9c77",
        "matched_identical_pocket_ca_pairs": 84,
    },
    "XDK-05-1": {
        "source_pdb_sha256": "bd29e8407047a2c8863a5039823d74978ba615e01b06bfe501e4827e833ae48d",
        "target_pdb_sha256": "5255e85c4fc9d24087390c76d1dc7a43921ba3208904aec9ea335c3699fe60c3",
        "transformed_source_reference_coordinate_hash": "9c17ec4b6548c04554c96f7dcfa16acbc19ff6aef4cc367c3334093e7b8e99f0",
        "target_reference_coordinate_hash": "860b86b7e318f01ec6c4f0107cd24ffe9e88ef7760e31a36e34305286efa111c",
        "grid_hash": "d5b938f4e966a1e4ec080a0752fb0a9c10982f93e35be19bea58e1105a23e552",
        "matched_identical_pocket_ca_pairs": 73,
    },
    "XDK-05-2": {
        "source_pdb_sha256": "5255e85c4fc9d24087390c76d1dc7a43921ba3208904aec9ea335c3699fe60c3",
        "target_pdb_sha256": "bd29e8407047a2c8863a5039823d74978ba615e01b06bfe501e4827e833ae48d",
        "transformed_source_reference_coordinate_hash": "fa7c84d284198ddbd8faaa6f648723f4a06ad7922bbb5e731131f1ef3e250ea4",
        "target_reference_coordinate_hash": "ca4e7c655c7340e4a934f83c2fcce67c29ebb981fe909db123ca07d36bb2b47b",
        "grid_hash": "e3f8d999fcdda8eeecaec0cbf35082a09be174bdaaa7a2e45a2bc6371ec65a23",
        "matched_identical_pocket_ca_pairs": 73,
    },
}
