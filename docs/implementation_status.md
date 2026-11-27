# Etat de la V1.1

## Pret a utiliser

- 104 regles effectives et 25 corrections de Thierry tracees;
- 34 types d'actes, 46 ressources et 63 compatibilites configurables;
- schema d'entree normalise;
- validation structurelle et metier;
- modele OR-Tools CP-SAT de faisabilite;
- moteur local de secours pour verifier le pipeline hors connexion;
- demonstration pseudonymisee RH, DER, VR et trois doubles orientations;
- export CSV/JSON/XLSX et rapport d'infaisabilite;
- refus d'ecraser un dossier de sortie existant;
- aucune ecriture Nymphea.

## Verification realisee dans le pack

Le scenario de demonstration contient 24 occurrences sur 6 sejours synthetiques et produit un planning faisable. Le scenario negatif force 5 baignoires RH a 07:30 pour 4 postes et produit l'erreur explicite `LOCKED_CAPACITY_OVERLOAD`.

Le moteur CP-SAT est le moteur cible. Le calcul de demonstration fourni a ete execute avec le moteur de secours, car le paquet OR-Tools doit etre installe dans l'environnement cible avec `python -m pip install -e .`.

## Parametres a completer avant recette terrain

- horaires exacts DER/VR/kiné par jour;
- effectifs reels par secteur et tranche;
- compatibilite PMR par poste;
- confirmation de la douche penetrante a 6 min;
- capacite et regle de partage exactes de la piscine;
- calendrier mardi/samedi des kines;
- liste active des postes en debut de saison.
