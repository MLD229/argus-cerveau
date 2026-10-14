#!/usr/bin/env bash
# ============================================================================
#  installer-tout.sh — installe l'ÉCOSYSTÈME ARGUS complet (3 profils).
#
#  Hermes installe UN profil par dépôt (`hermes profile install`). Ce script
#  fait la boucle sur les 3 profils du dépôt et enchaîne l'étape que Hermes ne
#  fait pas : rendre les outils Python accessibles à l'agent.
#
#  LES 3 PROFILS
#    chef   — parle au client, route, agrège (outils système complets)
#    veille — recherche lourde en arrière-plan, ne parle pas au client
#    client — « Signature Libérale » : cherche des biens pour un particulier
#
#  USAGE
#      ./installer-tout.sh                 # installe les 3 profils
#      ./installer-tout.sh chef client     # seulement certains profils
#      TOOLS_DIR=~/argus-tools ./installer-tout.sh
#      ./installer-tout.sh --check         # vérifie l'état, n'installe rien
#
#  IDEMPOTENT : un profil déjà installé est mis à jour (`hermes profile
#  update`), jamais dupliqué. Les données utilisateur (memories, sessions,
#  .env) ne sont JAMAIS écrasées.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${TOOLS_DIR:-/opt/tools}"
ALL=(chef veille client serveur)
SELECTED=()
CHECK=0
# Préfixe des profils installés. NOM court (chef/veille/client) COLLISIONNE avec
# des profils locaux qui peuvent déjà exister — d'où le préfixe par défaut.
PREFIX="${ARGUS_PROFILE_PREFIX:-argus-}"

say() { echo "[argus] $*"; }
die() { echo "ERREUR: $*" >&2; exit 1; }

for a in "$@"; do
  case "$a" in
    --check) CHECK=1 ;;
    chef|veille|client|serveur) SELECTED+=("$a") ;;
    *) die "profil inconnu : $a (attendu : chef, veille, client, serveur)" ;;
  esac
done
[ ${#SELECTED[@]} -eq 0 ] && SELECTED=("${ALL[@]}")

command -v hermes >/dev/null 2>&1 || die "'hermes' introuvable dans le PATH."

# Le nom réellement installé, préfixé.
pname() { echo "${PREFIX}$1"; }

# --- 1. Les profils sont-ils présents dans le dépôt ? -----------------------
for p in "${SELECTED[@]}"; do
  [ -f "$HERE/profils/$p/distribution.yaml" ] \
    || die "profils/$p/distribution.yaml absent — dépôt incomplet ?"
done

# --- Mode --check -----------------------------------------------------------
if [ "$CHECK" -eq 1 ]; then
  for p in "${SELECTED[@]}"; do
    if hermes profile info "$(pname "$p")" >/dev/null 2>&1; then
      say "OK       profil '$(pname "$p")' installé"
    else
      say "MANQUANT profil '$(pname "$p")'"
    fi
  done
  if [ -f "$TOOLS_DIR/bienici.py" ]; then
    say "OK       outils présents dans $TOOLS_DIR"
  else
    say "MANQUANT outils dans $TOOLS_DIR (lancer ./installer.sh)"
  fi
  exit 0
fi

# --- 2. Installer (ou mettre à jour) chaque profil --------------------------
for p in "${SELECTED[@]}"; do
  NAME="$(pname "$p")"
  if hermes profile info "$NAME" >/dev/null 2>&1; then
    say "mise à jour du profil '$NAME'…"
    hermes profile update "$NAME" --yes 2>&1 | sed 's/^/    /'
  else
    say "installation du profil '$NAME'…"
    hermes profile install "$HERE/profils/$p" --name "$NAME" --yes 2>&1 | sed 's/^/    /'
  fi
done

# --- 3. Clé API : dire quoi faire si elle manque -----------------------------
for p in "${SELECTED[@]}"; do
  PE="$HOME/.hermes/profiles/$(pname "$p")"
  if [ ! -f "$PE/.env" ]; then
    say "clé API manquante pour '$(pname "$p")' — à créer :"
    say "    cp $PE/.env.EXAMPLE $PE/.env && \$EDITOR $PE/.env"
  fi
done

# --- 4. Les outils Python (indispensables au profil client) ------------------
if printf '%s\n' "${SELECTED[@]}" | grep -qx client; then
  say "installation des outils Python…"
  TOOLS_DIR="$TOOLS_DIR" "$HERE/installer.sh"
else
  say "profil 'client' non sélectionné — outils Python non installés."
fi

echo
say "Écosystème installé (préfixe '${PREFIX}'). Essais :"
say "    hermes -p $(pname chef)   chat"
say "    hermes -p $(pname client) -z \"un local pour mon cabinet à Lyon 6e\""
say "    hermes -p $(pname veille) -z \"prépare une fiche marché sur Lyon 6e\""
