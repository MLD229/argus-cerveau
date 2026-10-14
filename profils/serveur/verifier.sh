#!/usr/bin/env bash
# ============================================================================
#  verifier.sh — contrôle du profil 'serveur' et de sa publication.
#
#  Vérification ad-hoc (il n'existe pas de suite de tests pour ce dépôt) :
#  elle contrôle les comportements modifiés, pas l'ensemble du cerveau.
#
#      ./verifier.sh          # tout
#      ./verifier.sh canal    # seulement le canal de commandement
# ============================================================================
set -uo pipefail

S="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CER="$(cd "$S/../.." && pwd)"
CMD="$S/outils/argus-commandement.sh"

ok=0; ko=0
R() { if [ "$2" = "$3" ]; then echo "  OK   $1"; ok=$((ok+1)); else echo "  FAIL $1 (attendu '$3', obtenu '$2')"; ko=$((ko+1)); fi; }

echo "== 1. Structure =="
R "SOUL.md"                "$([ -f "$S/SOUL.md" ] && echo oui)" "oui"
R "distribution.yaml"      "$([ -f "$S/distribution.yaml" ] && echo oui)" "oui"
R "config.yaml"            "$([ -f "$S/config.yaml" ] && echo oui)" "oui"
R "4 skills"               "$(ls "$S/skills" | wc -l | tr -d ' ')" "4"
R "3 scripts"              "$(ls "$S"/outils/*.sh | wc -l | tr -d ' ')" "3"

echo "== 2. Contrat du profil =="
R "name = argus-serveur"   "$(grep -c '^name: argus-serveur' "$S/distribution.yaml")" "1"
R "cle API declaree"       "$(grep -c 'DEEPSEEK_API_KEY' "$S/distribution.yaml")" "1"

echo "== 3. Intégration à l'installation =="
R "ALL contient serveur"   "$(grep -c 'ALL=(chef veille client serveur)' "$CER/installer-tout.sh")" "1"
R "selecteur accepte"      "$(grep -c 'chef|veille|client|serveur)' "$CER/installer-tout.sh")" "1"

echo "== 4. Syntaxe des scripts =="
for f in "$S"/outils/*.sh; do
  if bash -n "$f" 2>/dev/null; then echo "  OK   $(basename "$f")"; ok=$((ok+1))
  else echo "  FAIL syntaxe $f"; ko=$((ko+1)); fi
done

# --- Le canal de commandement -----------------------------------------------
# Le point sensible : une boîte vide (ou un simple gabarit) NE DOIT RIEN
# déclencher. Sans ce contrôle, la machine rejouerait l'exemple du gabarit.
boite() {
  local t; t=$(mktemp -d)
  ( cd "$t" && git init -q . && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m i )
  echo "$t"
}

echo "== 5. Canal : rien à faire =="
T=$(boite)
printf '# Demande a executer\n\n<!--\nexemple : relance le serveur\n-->\n' > "$T/demande.md"
out=$(ARGUS_CMD_REPO="$T" bash "$CMD" lire 2>/dev/null); rc=$?
R "gabarit -> code 0"      "$rc" "0"
R "gabarit -> silence"     "${out:-vide}" "vide"
printf '' > "$T/demande.md"
ARGUS_CMD_REPO="$T" bash "$CMD" etat >/dev/null 2>&1
R "fichier vide -> code 0" "$?" "0"
rm -rf "$T"

echo "== 6. Canal : demande réelle =="
T=$(boite)
printf '# Demande\nRelance le serveur.\n' > "$T/demande.md"
out=$(ARGUS_CMD_REPO="$T" bash "$CMD" lire 2>/dev/null); rc=$?
R "demande -> code 10"     "$rc" "10"
R "demande -> lue"         "$(echo "$out" | grep -c 'Relance le serveur')" "1"

echo "== 7. Canal : traitement =="
ARGUS_CMD_REPO="$T" bash "$CMD" traiter >/dev/null 2>&1
ARGUS_CMD_REPO="$T" bash "$CMD" etat >/dev/null 2>&1
R "boite vidée -> code 0"  "$?" "0"
R "archive créée"          "$([ -n "$(ls "$T"/historique 2>/dev/null)" ] && echo oui)" "oui"
rm -rf "$T"

echo "== 8. Canal : refus d'un dépôt public =="
T=$(boite); printf '# D\nTest.\n' > "$T/demande.md"
ARGUS_CMD_SLUG=MLD229/argus-ui ARGUS_CMD_REPO="$T" bash "$CMD" etat >/dev/null 2>&1
R "dépôt public -> refus"  "$?" "3"
rm -rf "$T"

echo "== 9. Publication =="
if command -v gh >/dev/null 2>&1; then
  R "argus-ui public"        "$(gh repo view MLD229/argus-ui --json isPrivate -q .isPrivate 2>/dev/null)" "false"
  R "commandement privé"     "$(gh repo view MLD229/argus-commandement --json isPrivate -q .isPrivate 2>/dev/null)" "true"
  R "aucun .etat en ligne"   "$(gh api repos/MLD229/argus-ui/contents -q '.[].name' 2>/dev/null | grep -c '^\.etat$')" "0"
else
  echo "  (gh absent — contrôles de publication ignorés)"
fi

echo
echo "===== $ok OK, $ko échec(s) ====="
[ "$ko" -eq 0 ] || exit 1
