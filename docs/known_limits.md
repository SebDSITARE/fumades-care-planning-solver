# Limites connues V1.1.1

- Les durées non multiples de cinq minutes sont arrondies au créneau supérieur. C'est volontaire pour ne jamais sous-estimer une occupation.
- La préférence térébenthine est faible : elle cède devant l'ancrage horaire, les verrouillages et la faisabilité des ressources.
- Sans colonne de classification des soins secs dans `care_types.csv`, seul le code `0408` est reconnu comme soin sec de repli.
- L'overlay ne modifie pas les paramètres métier V1.1. Les capacités, compatibilités et paramètres provisoires restent donc sous responsabilité de leur référentiel source.
- `FEASIBLE` signifie qu'une solution a été trouvée sans preuve d'optimalité. `diagnostics.json` expose la borne et le gap pour quantifier cette limite.
