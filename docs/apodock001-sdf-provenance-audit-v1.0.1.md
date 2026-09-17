# APODOCK-001 SDF provenance audit

Status: **v1.0.1 is `FROZEN_BUT_UNEXECUTABLE`; all nine current inputs are scientifically equivalent and support the separately versioned v1.0.2 bundle.**

Audit branch: `audit/apodock001-sdf-provenance`<br>
Base: `research-os-v1.3` at `b62248fd69cc1ded88596cfa0b7125c5d50ae30b`<br>
Frozen protocol audited: `research-os.apodock001.protocol.v1.0.1+9e293289c9729603`<br>
Frozen protocol hash: `9e293289c972960333cdd442324c0c6c2485d0b3e90471f9882abfa3312a8f13`

The machine-readable record is [`apodock001-sdf-provenance-audit-v1.0.1.json`](apodock001-sdf-provenance-audit-v1.0.1.json). It records every response timestamp, HTTP status, content type, content length when supplied, ETag/Last-Modified when supplied, and SHA-256.

## Historical artifact

The audited artifact was workflow `34642755042`, head `fa0a737eaa1989856474068f330c3c2c52d74344`, artifact `apodock001-preflight-v1.0`, ID `10280154166`. GitHub declared ZIP SHA-256:

`2026a042818c4ec021fea672d4ceba72a31734c61da4ce8c97413dcb3bfcace8`

The independently downloaded ZIP matched that digest. It contained exactly one file, `apodock001-preflight-v1.0.json`, and contained no SDF, MOL, or ligand input bytes. The JSON preserved the nine filenames and structural identities, but not the frozen SDF hashes or the historical payload bytes. The historical code and URL provenance were sufficient to reconstruct requests, but not to recover the original serialization.

## Reconstructed historical requests

The historical implementation used the following exact template and User-Agent:

`https://models.rcsb.org/v1/{pdb_id}/ligand?auth_asym_id={chain}&auth_seq_id={auth_seq_id}&encoding=sdf`<br>
`Research-OS/5.1 REDOCK-001`

| Case | PDB | CCD | Chain | auth_seq_id | URL |
|---|---|---|---|---:|---|
| APD-001 | 1FTM | AMQ | A | 428 | `https://models.rcsb.org/v1/1ftm/ligand?auth_asym_id=A&auth_seq_id=428&encoding=sdf` |
| APD-002 | 1JG6 | UDP | A | 400 | `https://models.rcsb.org/v1/1jg6/ligand?auth_asym_id=A&auth_seq_id=400&encoding=sdf` |
| APD-003 | 1RPJ | ALL | A | 291 | `https://models.rcsb.org/v1/1rpj/ligand?auth_asym_id=A&auth_seq_id=291&encoding=sdf` |
| APD-004 | 2DRI | RIP | A | 272 | `https://models.rcsb.org/v1/2dri/ligand?auth_asym_id=A&auth_seq_id=272&encoding=sdf` |
| APD-005 | 1USI | PHE | A | 1346 | `https://models.rcsb.org/v1/1usi/ligand?auth_asym_id=A&auth_seq_id=1346&encoding=sdf` |
| APD-006 | 1RF4 | SPQ | A | 1451 | `https://models.rcsb.org/v1/1rf4/ligand?auth_asym_id=A&auth_seq_id=1451&encoding=sdf` |
| APD-007 | 1SW2 | BET | A | 301 | `https://models.rcsb.org/v1/1sw2/ligand?auth_asym_id=A&auth_seq_id=301&encoding=sdf` |
| APD-008 | 1EX7 | 5GP | A | 187 | `https://models.rcsb.org/v1/1ex7/ligand?auth_asym_id=A&auth_seq_id=187&encoding=sdf` |
| APD-009 | 2E2O | BGC | A | 400 | `https://models.rcsb.org/v1/2e2o/ligand?auth_asym_id=A&auth_seq_id=400&encoding=sdf` |

## Three-download audit and scientific comparison

All 27 instance-SDF responses returned HTTP 200. No case had three identical payload hashes, so the endpoint is not byte-stable. The current payloads were compared against the corresponding CCD ideal graph and the named holo-PDB instance using graph-derived atom correspondence, with no rigid-body fit. All nine coordinate RMSDs are direct same-frame values and all are exactly `0.0 Å` at the recorded precision; the coordinate identity hash equals the frozen holo-reference coordinate hash in every case.

| Case | Frozen SHA-256 | Three current SHA-256 values | Heavy atoms | Formula | Canonical isomeric identity | Coordinate identity | Direct RMSD Å | Classification |
|---|---|---|---:|---|---|---|---:|---|
| APD-001 | `2f39cdd28b98dc8b43b11d4dae25707030ebabd1c8516f82063e0e130f0d19d8` | `a893e515f7ba97c50b504e756e02e336c3b382f588d8eb7bb21cab0d9e3b6ba2` / `655e65b853829a33c846a848d5d27b897689d71e5390b697a5b5b8540cc4bb35` / `bfc59112de608e3954d08bac0b3a4c304c9d7495930f03f0c3818a7d13110368` | 13 | `C7H10N2O4` | `Cc1onc(O)c1C[C@H](N)C(=O)O` | `5352f4a8b0add589f6b952173f4fe4cb684098d64b76cd64633d076b4db963fd` | 0.0 | REPRESENTATION_DRIFT |
| APD-002 | `a682e91ad95000725b01d2b4009bf33e2d074628dd0aabcbe1fb97a5aca2f839` | `b4584cc9658b6147db694e6582aedda0151321848b1813b6bbce3b6e35aa4830` / `87aaecc7a84995bddb496b6264b46f0d20c210beecdc0842f6cd1e1bed7c6f0c` / `57724b22c7d32dad8bb067845c5af3ba29d2efc59e18a297b3263e04bc119f38` | 25 | `C9H14N2O12P2` | `O=c1ccn([C@@H]2O[C@H](CO[P@@](=O)(O)OP(=O)(O)O)[C@@H](O)[C@H]2O)c(=O)[nH]1` | `5b0878987f0c9e7f7fe66ce95b70d97b6602417b8b00fdd2d7b3618a8c752609` | 0.0 | REPRESENTATION_DRIFT |
| APD-003 | `988255475de09e1ad1e92a7f82da5e39fad1b0fdc32ef42356491e69c981b9f2` | `8039ffe1369ec42b47d82cd286772a1e66fe4103f733615a18df531588ff18a3` / `a448cd32f33d8dab695875b01614aedb14db1d0194fbc580fee46ea4277e2b46` / `8025fcae93c5a2c662946fac58ce0e948c8a6ba2458037353da89a149d2ce8cf` | 12 | `C6H12O6` | `OC[C@H]1O[C@@H](O)[C@H](O)[C@H](O)[C@@H]1O` | `b63b2365c278ec0074cca7b9ad7a51e0ced6840c2af346d2923f17d36dad5d1c` | 0.0 | REPRESENTATION_DRIFT |
| APD-004 | `627c77aa18e9b7bbb7756c035a29a7f08a3a1ff2ab2bd76f06d755190a80e0a6` | `5457e8146f22b30b9eb57c13220edd77a3972a0cbe507fe3245766aedc8330b3` / `b8aa807f141b4988bbdb4e73e5c380e765903a764bba6d3a48ed1dbe483910e1` / `a608c46e86880829397afeea9c9b1556a90a0c6f7c0093d4330767af66d94121` | 10 | `C5H10O5` | `O[C@@H]1[C@H](O)[C@H](O)CO[C@H]1O` | `8c6158195559d2f1d82366e31cbe7666f4b0a01edc8d5c872e49fa4eadb411ba` | 0.0 | REPRESENTATION_DRIFT |
| APD-005 | `8f7e5bec593c54cfa85d55fbca86e97d51a8dc4888f93f33f98db1e92bfe9062` | `31a3fce7a28ca150a3e30f669bd6cb5ca8a074e44d70b949e77bdbd2ff28de20` / `6639a5dc6e5d585ebd72928a780b477aad6cdf597116421f1fcc061f93c8bd37` / `c952b67e7344f0bcfc52ffb3133ff49a97f63e8397fa27efadc308bc1e315d88` | 12 | `C9H11NO2` | `N[C@@H](Cc1ccccc1)C(=O)O` | `e51188114c9aa3f6c7468f6d58dea703542ff95f4e19b17b0f173ddffd90e4e2` | 0.0 | REPRESENTATION_DRIFT |
| APD-006 | `e90e52934bf9bb8c0cc0da441714430385662af14b2fba320a2128cbfa6627a2` | `4758b41bb282af21d8b65b67027ce5845a69611a175e7ae6d13f75e8c1cced99` / `c5c7456874782fe0048a5b101c0edaf8538a29e78a153fc9a554ac60dcae253a` / `1a6a2d009766ab893cfd4f3a945eb8d951c64d2b7bf840a9029984cd813140a6` | 27 | `C10H15FO14P2` | `O=C(O)C1=C[C@@H](OP(=O)(O)O)[C@@H](O)[C@H](O[C@@](CF)(OP(=O)(O)O)C(=O)O)C1` | `0d12d168ffba95b309fcebdde9cf791f64fecdf73d9c3b1c4f3b19e63011c397` | 0.0 | REPRESENTATION_DRIFT |
| APD-007 | `fccf596bede93d055ff037eea0c3d4895d0bf276dd8c6b395c69dd2af566548a` | `640e93624d0537a86fea8985b9165af9d78700b09164c70e9c901e19654671c4` / `5b76d00cd9015b97e91a29b17abbedbbb742fb0df0eda4aed7bb88d37af9bcd0` / `3ac37ce9b045beae910f154007dc8c0f83e8ea1720427c174c037ace902a80ed` | 8 | `C5H12NO2+` | `C[N+](C)(C)CC(=O)O` | `d8bd23ca3f24a1d98bda4298351d36f2e3a8fb3224de5c1d639a535005da6f00` | 0.0 | REPRESENTATION_DRIFT |
| APD-008 | `a9e1d894b39b39b6173587929a1c6e2dc22a200794ca73b554e085d118591d52` | `a87d64b1867409ad808068e545c3e680441222f17424baafa9c99c13147ef5e3` / `14fa02f2c910db3b8b56e7aeda52e99b9da649f7613cc514954743cf1753181a` / `c3ed31828841321c26ef3d217482e9c2d45c18572501c7aada4603dce96a8474` | 24 | `C10H14N5O8P` | `Nc1nc2c(ncn2[C@@H]2O[C@H](COP(=O)(O)O)[C@@H](O)[C@H]2O)c(=O)[nH]1` | `02500fcb1d6a9f3d5b409ffa698f45440e22c3fe08b59404e7b27c8e828ead1b` | 0.0 | REPRESENTATION_DRIFT |
| APD-009 | `98bb6e838039037c4dc4653600850d8474f951208e63c2f52be1f85be60a7376` | `62077e92a402efe5355472e65b14bd0a2840336a98295be2040506dc808ef2b4` / `fe4e6f7afc0b58a33b9ca9d178afadc430db420543200222f59d630cd18ed6b2` / `0dd5d27e1ccf88d17cfa36719d5bb0c59b4265f433f29b8d931758ac9697953c` | 12 | `C6H12O6` | `OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@@H]1O` | `bcb8b22fb9bf71e4f07d8beefb5b3f525c9d1797dd45823f605b9c8c368adad3` | 0.0 | REPRESENTATION_DRIFT |

For every row, the element multiset, bond graph, bond orders, aromaticity, formal charge, formula, canonical SMILES, canonical isomeric SMILES, stereochemistry, fragment count, ligand ID/chain/sequence mapping, and same-frame coordinate identity passed. The current payload SHA changes because the endpoint serialization includes changing operational metadata; this is exactly why v1.0.2 archives selected bytes locally.

## Decision

- Historical frozen SDF bytes recovered: **0/9**.
- v1.0.1: **preserved and not executable**; its byte hashes remain unchanged and it produced no results.
- Current endpoint: **not byte-stable**; a fresh HTTP download is not an acceptable reproducible input source.
- Current scientific equivalence: **9/9 proven**; all cases are `REPRESENTATION_DRIFT`.
- Methodological action: create a separately versioned v1.0.2 with an immutable local input bundle. No v1.0.1 hash was replaced.

No Vina command was started, no receptor or ligand was passed to Vina, and no prospective score or pose was observed.
