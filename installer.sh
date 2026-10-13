#!/usr/bin/env bash
# ============================================================================
#  installer.sh — prépare l'hôte pour le cerveau ARGUS.
#
#  Le cerveau lui-même s'installe avec `hermes profile install` (il copie
#  SOUL.md, config.yaml, skills/, outils/). Ce script fait ce que cette
#  commande ne peut pas faire : rendre les OUTILS PYTHON accessibles à
#  l'agent.
#
#  POURQUOI : les skills appellent `python3 /opt/tools/bienici.py` etc. Ce
#  chemin doit exister, sinon l'agent « réinvente » l'appel à la main et
#  échoue (piège documenté : la zone est ignorée, on récupère 950 000
#  annonces de France entière).
#
#  USAGE :
#      ./installer.sh                 # installe dans /opt/tools (défaut)
#      TOOLS_DIR=~/.argus-tools ./installer.sh
#      ./installer.sh --check         # vérifie seulement, ne copie rien
#
#  IDEMPOTENT : relançable sans risque. Utilise sudo seulement si /opt/tools
#  n'est pas accessible en écriture.
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${TOOLS_DIR:-/opt/tools}"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

# Les outils vivent sous profils/client/outils/ (le dépôt porte 3 profils).
SRC_TOOLS="$HERE/profils/client/outils"
[ -d "$SRC_TOOLS" ] || SRC_TOOLS="$HERE/outils"

die() { echo "ERREUR: $*" >&2; exit 1; }
say() { echo "[cerveau] $*"; }

# --- 1. Les outils sont-ils présents dans le dépôt ? ------------------------
[ -d "$SRC_TOOLS" ] || die "dossier 'outils/' absent — le dépôt est-il complet ?"
count=$(find "$SRC_TOOLS" -maxdepth 1 -name '*.py' | wc -l)
[ "$count" -gt 0 ] || die "aucun script .py dans outils/"
say "$count script(s) Python trouvés dans $SRC_TOOLS"

# --- 2. Où poser les outils ? ----------------------------------------------
if [ "$CHECK" -eq 1 ]; then
  if [ -d "$TOOLS_DIR" ] && [ -f "$TOOLS_DIR/bienici.py" ]; then
    say "OK — outils déjà installés dans $TOOLS_DIR"
  else
    say "MANQUANT — $TOOLS_DIR/bienici.py absent. Lancer ./installer.sh"
    exit 1
  fi
  exit 0
fi

SUDO=""
if [ ! -w "$(dirname "$TOOLS_DIR")" ] 2>/dev/null && [ ! -w "$TOOLS_DIR" ] 2>/dev/null; then
  command -v sudo >/dev/null 2>&1 || die "$TOOLS_DIR non inscriptible et sudo absent. Utiliser TOOLS_DIR=~/argus-tools ./installer.sh"
  SUDO="sudo"
  say "élévation sudo nécessaire pour écrire dans $TOOLS_DIR"
fi

$SUDO mkdir -p "$TOOLS_DIR"
# On copie les .py + le README, sans les caches.
$SUDO cp -f "$SRC_TOOLS"/*.py "$TOOLS_DIR"/
[ -f "$SRC_TOOLS/README.md" ] && $SUDO cp -f "$SRC_TOOLS/README.md" "$TOOLS_DIR"/ 2>/dev/null || true
$SUDO find "$TOOLS_DIR" -maxdepth 1 -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
say "outils installés dans $TOOLS_DIR"

# --- 3. Test de vie (le vrai critère de réussite) --------------------------
say "test de vie : résolution de zone ('Lyon 6')..."
if out=$(python3 "$TOOLS_DIR/bienici.py" zone "Lyon 6" 2>&1); then
  if printf '%s' "$out" | grep -q -- '-10679'; then
    say "OK — l'outil répond et résout Lyon 6e (zoneId -10679)"
  else
    say "ATTENTION — l'outil répond mais la zone attendue n'apparaît pas."
    say "Réponse : $(printf '%s' "$out" | head -c 200)"
  fi
else
  say "ÉCHEC — bienici.py n'a pas répondu correctement :"
  say "$(printf '%s' "$out" | head -c 300)"
  exit 2
fi

echo
say "Terminé. Le cerveau est prêt."
say "  Terminal  : hermes -p argus chat"
say "  Une fois   : hermes -p argus -z \"trouve un local à Lyon 6e\""
say "  UI web     : l'hôte doit monter $TOOLS_DIR en lecture seule"
