# MOLDISC-015 — C-2545 source-provenance and stereochemistry resolution

Status: **CLOSED_FIRST_RESULT_PRESERVED**

## Scientific question

Can the experimental identity associated with AqSolDB `C-2545 / phenyl-kni-727 /
logS -3.62` be traced to a sufficiently specific source to resolve its
stereochemistry, or must the available evidence remain explicitly
non-stereodefined?

MOLDISC-015 is exclusively a provenance and identity program. It does not
generate molecules, execute docking or ESOL, select candidates, use Vina,
modify AqSolDB, or import biological properties.

## Frozen parent and AqSolDB record

The parent is MOLDISC-014 with program scientific hash
`f940d95189616131829a22f9e68a53a960eddf8fd05f5fd7ebac43ece85481ed`.
The frozen measured record is AqSolDB `C-2545`, named `phenyl-kni-727`, with
raw SMILES:

```text
CC(C)(C)NC(=O)C1N(CSC1(C)C)C(=O)C(O)C(CC2=CC=CC=C2)NC(=O)C3=CC=CC=C3
```

Its preserved InChI is:

```text
InChI=1S/C27H35N3O4S/c1-26(2,3)29-24(33)22-27(4,5)35-17-30(22)25(34)21(31)20(16-18-12-8-6-9-13-18)28-23(32)19-14-10-7-11-15-19/h6-15,20-22,31H,16-17H2,1-5H3,(H,28,32)(H,29,33)
```

The formula is `C27H35N3O4S`, the full InChIKey is
`URHJIBSBOJFXDI-UHFFFAOYSA-N`, the connectivity block is
`URHJIBSBOJFXDI`, and the measured logS is `-3.62` from one observation. The
InChI contains no `/t`, `/m`, or `/s` stereochemical layers; the source record
is therefore frozen as `stereochemistry_specified=false`.

The immutable AqSolDB lineage is commit
`98cdd10a372058743e4f3fb950a1c9974ec9603a`, blob
`67016e030cf0a741e250ba0267bd84461041db5f`, and parsed-source hash
`2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4`.

## Dataset-C provenance

The AqSolDB README mapping `3. dataset-C.csv [3]` (README line 56) is frozen before
external source research. Reference [3] is:

> Raevsky OA, Grigor'ev VY, Polianczyk DE, Raevskaja OE, Dearden JC.
> Calculation of aqueous solubility of crystalline un-ionized organic
> chemicals and drugs based on structural similarity and physicochemical
> descriptors. J Chem Inf Model. 2014;54:683-691.
> DOI: `10.1021/ci400692n`.

Supporting information is accepted only from ACS, an attributable publisher
mirror, or an immutable public archival copy with a verifiable hash. Raw
records are preserved before normalization, with URL, publisher, filename,
transport SHA256, byte size, retrieval date, and DOI.

## Identity and transfer boundary

`phenyl-kni-727` is not treated as `KNI-727` by name alone. A generic public
`KNI-727` record with formula `C30H41N3O5S` is identity-incompatible with
`C-2545` unless another attributable source proves otherwise. Name-only or
substring matches are preserved as rejected identity candidates.

The four allowed resolution states are:

- `RESOLVED_EXACT_STEREOCHEMICAL_IDENTITY`;
- `UNRESOLVED_SOURCE_STEREOCHEMISTRY`;
- `CONFLICTING_SOURCE_IDENTITIES`;
- `SOURCE_RECORD_NOT_RECOVERABLE`.

The initial transfer decision remains false. The `SOURCE-DELTA-BOTH` product
has InChIKey `URHJIBSBOJFXDI-FDFHNCONSA-N`: it shares the connectivity block
with C-2545 but does not share the full InChIKey. Tanimoto 1.0, formula,
connectivity, or a compound-family name cannot authorize measurement transfer.
Transfer requires exact canonical isomeric identity, full InChIKey equality,
and attribution of `-3.62` specifically to that resolved structure.

No stereochemistry is borrowed retrospectively from the JE2 lineage, and no
stereoisomer is chosen using docking or biological evidence.

## First result preserved

The first source-resolution execution recovered the publisher's supporting
information workbook from the ACS Publications locator via its publisher-hosted
Figshare transport mirror. The artifact is `ci400692n_si_001.xls`, 778752 bytes,
with transport SHA256
`4E3DD0EB7170CDB580A1D73E1CB7BA44D6D02E512D3D9C50365C1F8E47E7658E`.

The workbook contains an exact row match at `Support_info` row 2567:
`PHENYL-KNI-727`, the frozen raw SMILES, and `logSexp=-3.62`. It has no
compound number, CAS number, InChI, InChIKey, original-source locator, or
stereochemical representation. Therefore the record is source-recoverable but
the original experimental stereochemistry remains unresolved:
`UNRESOLVED_SOURCE_STEREOCHEMISTRY`.

The generic public `KNI-727` identity remains preserved as a rejected candidate
because its formula is `C30H41N3O5S` and its InChIKey connectivity block is
`CSWRAOHDICNMPU`, both incompatible with C-2545. The C-2545/source-delta
connectivity block matches (`URHJIBSBOJFXDI`), but the full InChIKey does not,
so measurement transfer remains `false`.

The canonical first-run validation record is
[`validation/moldisc-015-first-run-v1.json`](../validation/moldisc-015-first-run-v1.json);
the raw supporting-information manifest is
[`validation/moldisc-015-supporting-information-v1.json`](../validation/moldisc-015-supporting-information-v1.json),
and the complete generated run bundle is in
[`validation/moldisc-015-first-run-v1/`](../validation/moldisc-015-first-run-v1/).
The preserved scientific hashes are:

- source trace: `7e10824b6ef60006da23e3b26f63737cb8717476d05ca3371022164d94f78599`;
- identity resolution: `984e0deb92949dd6953c6641b8ad469b35d442012ba331536ae73bde260a0693`;
- program: `8e22c0565f2d78dc16468c8edb8f8f0b90a4007e50ced99e00e3d7a0b0f63e5d`.

MOLDISC-015 executes no molecule generation, docking, ESOL, candidate
selection, Vina use, biological-property import, or AqSolDB mutation. It does
not open MOLDISC-016.
