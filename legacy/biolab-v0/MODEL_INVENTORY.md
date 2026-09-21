# Legacy Model Inventory

Pickle files were inventoried by filename, size, hash, and adjacent metadata only. No pickle was loaded or executed.
All declared metrics are classified as `SELF_REPORTED_PROJECT_METRIC` pending split, leakage, and independent-validation audit.

| File | SHA-256 | Algorithm | Training rows | Declared metric | Value |
| --- | --- | --- | ---: | --- | ---: |
| `formolecular/modelos_ia/oraculo_aero.pkl` | `51c79ce5c01a655f8cdfb8c16efb34b08b9649520ecf77afc9316d785e3aea46` | RandomForestRegressor (source-script declaration) | 2706120 | AERO/OB_Pct | 0.2297 |
| `formolecular/modelos_ia/oraculo_aero_isp.pkl` | `ff1c9683aa31e511728a42570dc33b04e2e6067b3a13e7ec969e61ff30cb921c` | RandomForestRegressor (source-script declaration) | 2944555 | ISP | 0.7951 |
| `formolecular/modelos_ia/oraculo_agro.pkl` | `08b5df0ec071bcddba9a7807b5fef7b70dfcb99c45900bc4e5c55f9c77596c3a` | RandomForestRegressor (source-script declaration) | 2706120 | AGRO/Eficiencia_Nutricional | 0.9488 |
| `formolecular/modelos_ia/oraculo_food.pkl` | `b3e20eb07d2a61f6b88dc9a0339c7b56fd6fa21a9c0a16ddb5da7b97e400e52f` | RandomForestRegressor (source-script declaration) | 2706120 | FOOD/Peso_Molar | 0.8456 |
| `formolecular/modelos_ia/oraculo_mat.pkl` | `ade37ecddc389a43a3b0d06a2130a543d8f6cb564c071ed2e9be9b931acf327a` | RandomForestRegressor (source-script declaration) | 2706120 | MATERIAIS/TPSA_Superficie | 0.9304 |
| `formolecular/modelos_ia/oraculo_qed.pkl` | `20ec45d0e5d81ef3babbebc4aa2b971ada0f95e263b64250fde11177145c1b6f` | RandomForestRegressor (source-script declaration) | 2706120 | QED | 0.7969 |
| `formolecular/modelos_ia_farma/oraculo_farma_admet_qed.pkl` | `b47832ea61649fa96e6281074d801ef61400ec0f7db852025dfbeee0db2ca66f` | RandomForestRegressor (source-script declaration) | 3000000 | FARMA QED | 0.8958 |

The aero metric with R² 0.2297 is explicitly `LEGACY_MODEL_PERFORMANCE_WEAK` and is not used for new conclusions.
QED can be calculated directly with RDKit; an ML QED surrogate is not automatically superior or necessary.
