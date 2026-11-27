# État d'implémentation V1.1.1

Implémenté et couvert par tests :

- grille de cinq minutes ;
- `earliest_start`, `preferred_day_start`, `latest_start` ;
- interdiction dure de commencer avant `earliest_start` ;
- optimisation du premier soin quotidien ;
- conservation de `locked_start` et `locked_resource` ;
- préférence faible `0307` en fin de séance ou avant un soin sec ;
- avertissements provisoires limités aux soins utilisés ;
- diagnostics avec borne, gap absolu/relatif, branches et conflits ;
- indicateurs quotidiens ;
- générateur et recette `rh_reference_001` (18 jours, 72 soins) ;
- compatibilité ascendante de lecture des séjours V1.1.

La V1.1 reste accessible dans l'historique Git. Le script d'application crée une branche dédiée avant toute copie.
