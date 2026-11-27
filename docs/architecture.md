# Architecture V1.1

```text
Export Nymphea en lecture seule
        |
        v
stays.csv + care_requests.csv + locked_appointments.csv
        |
        v
Validation structurelle et metier
        |-- erreurs bloquantes -> rapport de coherence
        v
Modele de faisabilite OR-Tools CP-SAT
        |-- soins avec ressource: intervalles optionnels par poste compatible
        |-- actes SANS_CRENEAU: rattachement a la journee sans intervalle
        |-- capacites: NoOverlap/Cumulative
        |-- parcours: non-chevauchement + transitions inter-secteurs
        |-- VR: irrigation nasale avant les autres actes VR a creneau
        |-- rendez-vous verrouilles: heure/poste imposes
        v
planning.csv + diagnostics.json + rapport_infeasibilite.txt
        |
        v
Validation humaine; aucune ecriture Nymphea
```

## Composants

- `config/parameters`: referentiels configurables, jamais codes en dur dans le moteur.
- `schemas`: contrat d'entree JSON Schema pour les exports Nymphea normalises.
- `src/fumades_solver/validation.py`: controles avant calcul.
- `src/fumades_solver/model.py`: modele CP-SAT avec hypotheses d'exigence pour extraire un noyau d'infaisabilite.
- `src/fumades_solver/fallback.py`: ordonnanceur de secours deterministe, uniquement pour tests locaux sans OR-Tools.
- `src/fumades_solver/export.py`: CSV/JSON/rapport texte, avec refus d'ecraser un dossier existant.

## Perimetre

Le modele est transversal RH, DER et VR. Les doubles orientations ne sont pas des forfaits codes en dur: elles sont representees par plusieurs secteurs dans un meme sejour et par des temps de transition configurables.
