# Recette n°3 — planning difficile RH + DER

## Objet

Cette recette mesure la V1.2.0 **telle quelle**, avant toute nouvelle règle, sur un cas pseudonymisé reproduisant les symptômes métier suivants :

- double orientation RH + DER ;
- vague RH 07:45 ;
- douche générale impossible à positionner dans la fenêtre RH certains jours faute de capacité ;
- lit vapeur indisponible dans cette fenêtre, reporté manuellement en fin de cure ;
- retour RH après un passage en DER ;
- ajouts manuels nécessaires dans la référence Nymphéa.

La pièce image fournie avec la demande montre un écran GitHub et non les lignes du planning source. Le cas encode donc les défauts explicitement décrits et les règles déjà présentes dans le référentiel V1.2.0 ; il ne prétend pas copier un planning nominatif.

## Principe : baseline avant correction

Aucune modification n'est apportée à :

- `src/fumades_solver/model.py` ;
- `config/solver.json` ;
- la branche `main` ;
- le tag `v1.2.0`.

Le cas est ajouté sur la branche dédiée `feature/acceptance-003-rh-der`. La baseline Nymphéa est un CSV **inerte** servant uniquement à la comparaison. Le solveur travaille sur la prescription complète et les charges pseudonymisées, avec les règles V1.2.0 existantes.

## Données synthétiques et configurables

`data/acceptance/rh_der_reference_003/scenario.json` contient tous les paramètres :

- date synthétique et 18 jours du lundi au samedi ;
- identifiants pseudonymes ;
- prescription cible de 72 soins ;
- 6 jours chargés ;
- fenêtre RH 07:45–09:00 ;
- créneaux de douche générale de 5 minutes ;
- créneaux vapeur de 15 minutes ;
- jours de report manuel en fin de cure ;
- seuil de respect horaire et secteur de départ attendu.

La charge comporte 20 séjours pseudonymisés : 15 occupent successivement `DER_GENERAL` et 5 occupent successivement `VAP` sur les jours configurés. Elle matérialise la capacité sans créer de dépassement artificiel.

### Prescription cible

| Code | Secteur | Quantité |
|---|---|---:|
| `0408` | RH | 18 |
| `0301` | DER | 18 |
| `0324` | DER | 18 |
| `0513` | RH | 12 |
| `0519` | RH | 6 |
| **Total** | | **72** |

## Défauts mesurés dans la baseline

Après génération déterministe :

| Indicateur | Baseline |
|---|---:|
| Soins prescrits | 72 |
| Soins positionnés | 66 |
| Soins non positionnés | 6 |
| Douches générales non positionnées | 6 |
| Ajouts manuels vapeur | 6 |
| Reports vapeur en fin de cure | 6 |
| Retours RH → DER → RH | 6 |
| Retours inter-secteurs tous sens | 6 |
| Respect du début à 07:45 (tolérance 5 min) | 100 % |
| Départ dans le secteur RH | 100 % |
| Couverture de prescription | 91,67 % |
| Respect du jour prescrit | 83,33 % |
| Attente totale | 330 min |
| Durée moyenne du parcours | 56,67 min |
| Dépassement de capacité | 0 min |

Les valeurs sont recalculées par `tools/generate_rh_der_reference_003.py` et stockées dans `nymphea_baseline_metrics.json`.

## Indicateurs de comparaison

`src/fumades_solver/acceptance_metrics.py` calcule, pour la baseline et le solveur :

- soins prescrits, positionnés et non positionnés ;
- ajouts manuels et reports de jour ;
- retours RH → DER → RH et tout motif secteur A → B → A ;
- nombre total de déplacements inter-secteurs ;
- respect horaire et respect du secteur RH au premier soin ;
- attente et durée du parcours ;
- couverture et respect journalier de la prescription ;
- doublons et soins supplémentaires ;
- occupation, concurrence maximale et surcharge de chaque poste.

Le comparateur n'affirme pas qu'un retour a disparu simplement parce que son sens s'est inversé. `avoidable_sector_returns` détecte également DER → RH → DER.

## Génération et contrôle de la baseline

```bash
python tools/generate_rh_der_reference_003.py

python -m fumades_solver.cli validate \
  --input-dir data/acceptance/rh_der_reference_003 \
  --parameter-dir config/parameters \
  --config config/solver.json
```

Attendu : `VALID`, 21 séjours pseudonymisés, 192 demandes au total, 72 demandes cibles.

## Exécution obligatoire de la V1.2.0 avec CP-SAT

```bash
rm -rf outputs/rh_der_reference_003_v1_2_0_cp_sat

python -m fumades_solver.cli solve \
  --input-dir data/acceptance/rh_der_reference_003 \
  --parameter-dir config/parameters \
  --config config/solver.json \
  --output-dir outputs/rh_der_reference_003_v1_2_0_cp_sat \
  --engine cp-sat
```

Puis :

```bash
rm -rf outputs/rh_der_reference_003_comparison

python tools/compare_rh_der_reference_003.py \
  --solver-output outputs/rh_der_reference_003_v1_2_0_cp_sat \
  --output-dir outputs/rh_der_reference_003_comparison
```

Fichiers produits :

- `comparison.json` : résultats complets et deltas ;
- `comparison.csv` : tableau exploitable ;
- `comparison.md` : synthèse ;
- `solver_resource_occupation.csv` et `baseline_resource_occupation.csv`.

### Contrat CP-SAT obligatoire

- statut `OPTIMAL` ou `FEASIBLE` ;
- moteur `cp-sat` ;
- 192 lignes de planning, dont 72 pour le séjour cible ;
- 72/72 soins cibles positionnés sur leur jour prescrit ;
- aucune surcharge de poste ;
- aucune écriture Nymphéa ;
- les retours de secteur, le respect du départ RH, l'attente et la durée sont **mesurés et non forcés**.

## Validation automatisée complète

Dans un environnement où OR-Tools est installé :

```bash
python tools/verify_rh_der_reference_003.py --skip-install --clean-output
```

Ou, après activation du `.venv` :

```bash
python tools/verify_rh_der_reference_003.py --skip-install --clean-output
```

Le script exécute le générateur, toute la suite `pytest`, la validation, le calcul CP-SAT, la comparaison, les contrôles de capacité, la sécurité Nymphéa, `git diff --check` et l'absence de modification du modèle/configuration stable.

## Vérification locale sans OR-Tools

Le moteur `fallback` vérifie le pipeline, mais **ne vaut pas recette CP-SAT** :

```bash
rm -rf outputs/rh_der_reference_003_v1_2_0_fallback
PYTHONPATH=src python -m fumades_solver.cli solve \
  --input-dir data/acceptance/rh_der_reference_003 \
  --parameter-dir config/parameters \
  --config config/solver.json \
  --output-dir outputs/rh_der_reference_003_v1_2_0_fallback \
  --engine fallback
```

Sur la reconstruction locale, le fallback place 72/72 soins sans ajout manuel ni surcharge, mais conserve 6 retours inter-secteurs dans le sens DER → RH → DER, ne commence aucun des 18 jours dans le secteur RH, et augmente l'attente et la durée du parcours. Cela confirme l'intérêt de mesurer avant d'ajouter une règle.

## Sécurité et gouvernance

- aucune donnée nominative dans les fichiers ajoutés ;
- aucune modification de prescription par le solveur ;
- `write_to_nymphea: false` contrôlé par les tests et le validateur ;
- aucune API d'écriture ajoutée ;
- statut produit `PROPOSE` ;
- validation humaine obligatoire.

## Commit et push sur branche dédiée

```bash
git switch --detach v1.2.0
git switch -c feature/acceptance-003-rh-der

# appliquer le patch livré, puis :
python tools/verify_rh_der_reference_003.py --skip-install --clean-output

git diff --check
git diff --quiet v1.2.0 -- src/fumades_solver/model.py config/solver.json

git add docs/ACCEPTANCE_RH_DER_003.md \
  data/acceptance/rh_der_reference_003 \
  src/fumades_solver/acceptance_metrics.py \
  tools/generate_rh_der_reference_003.py \
  tools/compare_rh_der_reference_003.py \
  tools/verify_rh_der_reference_003.py \
  tests/test_rh_der_reference_003.py

git diff --cached --check
git commit -m "Add RH DER acceptance case 003 baseline and metrics"
git push -u origin feature/acceptance-003-rh-der
```

Ne jamais ajouter `outputs/` au commit et ne pas créer de tag avant revue de la recette.
