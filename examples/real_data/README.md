# AqSolDB-G real-data fixture

`aqsoldb_g_sample.csv` is a 46-row subset of the official AqSolDB `data/dataset-G.csv` file. It retains the empirical `Solubility` target and SMILES, and is used only as a small CI/golden-run fixture. The complete source has 1,144 rows and can be fetched explicitly by the v1.6 downloader using its pinned commit and SHA-256.

The upstream data directory publishes a CC0-1.0 license. The upstream license also disclaims clearance of third-party rights, so Research OS records the source, citation, license URL, commit, and observed hash and does not silently download data during tests.

Source: Sorkun et al., “AqSolDB, a curated reference set of aqueous solubility and 2D descriptors for a diverse set of compounds,” *Scientific Data* (2019), DOI [10.1038/s41597-019-0151-1](https://doi.org/10.1038/s41597-019-0151-1).
