# Solveur de planification des soins des Thermes des Fumades - V1.1

Prototype de faisabilite global RH, DER, VR et doubles orientations, construit a partir du referentiel qualite valide le 18/11/2026 et de ses 25 annotations de Thierry.

## Ce que contient le pack

- tables de parametres CSV et classeur de lecture `Fumades_Parametres_Solveur_V1_1_20261127.xlsx`;
- contrat d'entree Nymphea normalise (`schemas/nymphea_input.schema.json`);
- modele OR-Tools CP-SAT de faisabilite;
- jeu de demonstration pseudonymise couvrant RH, DER, VR, RH+VR, RH+DER et DER+VR;
- controles de coherence;
- export `planning.csv` et `diagnostics.json`;
- rapport d'infaisabilite avec precontroles et noyau d'hypotheses CP-SAT lorsque disponible;
- aucun connecteur d'ecriture Nymphea.

## Installation recommandee

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

OR-Tools doit etre installe depuis un index Python ayant acces au paquet `ortools`. Le projet demande Python 3.11 ou 3.12.

## Verification des donnees

```bash
fumades-solver validate \
  --input-dir data/demo \
  --parameter-dir config/parameters
```

## Calcul CP-SAT

```bash
fumades-solver solve \
  --input-dir data/demo \
  --parameter-dir config/parameters \
  --config config/solver.json \
  --output-dir outputs/run_demo
```

Le dossier de sortie doit ne pas exister. Ce comportement evite tout ecrasement. Pour une nouvelle execution, utiliser un nouveau nom de dossier.

## Scenario infaisable

```bash
fumades-solver solve \
  --input-dir data/demo_infeasible \
  --parameter-dir config/parameters \
  --config config/solver.json \
  --output-dir outputs/run_infeasible
```

Le rapport explique notamment les surcharges de rendez-vous verrouilles, les soins sans poste compatible, les durees manquantes et les incoherences de dates.

## Mode local sans OR-Tools

Pour permettre le test du pipeline dans un environnement prive sans depot de paquets, le CLI propose explicitement `--engine fallback`. Ce moteur deterministe n'est pas le moteur cible. En recette et production, utiliser le moteur par defaut `cp-sat` apres installation d'OR-Tools.

```bash
PYTHONPATH=src python -m fumades_solver.cli solve \
  --engine fallback \
  --input-dir data/demo \
  --parameter-dir config/parameters \
  --config config/solver.json \
  --output-dir outputs/test_local
```

## Regles de securite

- lecture seule des exports Nymphea;
- aucune modification automatique de prescription;
- planning genere en etat `PROPOSE`;
- validation humaine obligatoire avant communication;
- rendez-vous communiques geles par defaut, deblocables seulement avec motif d'incident;
- modifications de nature de soin soumises a validation medicale;
- tous les parametres sont externalises dans `config/parameters`.

## Ordre de travail conseille

1. Charger un export pseudonymise Nymphea dans le contrat normalise.
2. Completer horaires DER/VR, roulements reels, postes actifs et PMR.
3. Executer `validate` jusqu'a zero erreur bloquante.
4. Lancer la faisabilite CP-SAT.
5. Faire valider le planning par Marie-Laure/qualite.
6. Comparer au planning Nymphea sans ecrire dans Nymphea.
7. Seulement ensuite ajouter l'optimisation multi-objectifs et une API de recette.
