#!/usr/bin/env bash
# ============================================================================
#  argus-commandement.sh — boîte aux lettres à distance via un dépôt Git privé.
#
#  USAGE (appelé par l'agent ou par la tâche automatique)
#      argus-commandement.sh lire        # affiche la demande en attente (vide si aucune)
#      argus-commandement.sh repondre "texte"   # écrit la réponse dans le dépôt
#      argus-commandement.sh traiter     # archive la demande et vide la boîte
#      argus-commandement.sh etat        # rien à faire ? / demande en attente ?
#
#  PRINCIPE
#      Un dépôt Git PRIVÉ sert de boîte aux lettres. La machine va LIRE le
#      dépôt (elle ne l'expose jamais). demande.md vide = rien à faire.
#      Le script NE DÉCIDE RIEN : il lit et écrit. C'est l'agent qui juge si
#      la demande est exécutable ou dangereuse (voir la skill canal-commandement).
#
#  SÉCURITÉ
#      Le dépôt DOIT être privé. Le script le vérifie (si `gh` est disponible)
#      et REFUSE de fonctionner sur un dépôt public : sinon n'importe qui
#      pourrait commander la machine.
# ============================================================================
set -uo pipefail

REPO="${ARGUS_CMD_REPO:-$HOME/argus-commandement}"
DEPOT_SLUG="${ARGUS_CMD_SLUG:-MLD229/argus-commandement}"
DEMANDE="$REPO/demande.md"
REPONSE="$REPO/reponse.md"
HISTO="$REPO/historique"

die() { echo "ERREUR: $*" >&2; exit 2; }

# --- Vérifier que le dépôt existe -------------------------------------------
[ -d "$REPO/.git" ] || die "dépôt du canal introuvable : $REPO (cloner d'abord)"

# --- Vérifier qu'il est PRIVÉ (garde-fou) -----------------------------------
verifier_prive() {
  command -v gh >/dev/null 2>&1 || return 0   # sans gh, on ne peut pas vérifier
  local priv
  priv=$(gh repo view "$DEPOT_SLUG" --json isPrivate -q .isPrivate 2>/dev/null || echo "?")
  if [ "$priv" = "false" ]; then
    echo "REFUS : le dépôt $DEPOT_SLUG est PUBLIC." >&2
    echo "Un dépôt public permettrait à n'importe qui de commander cette machine." >&2
    echo "Rendez-le privé, ou changez ARGUS_CMD_SLUG." >&2
    exit 3
  fi
}

# --- Mettre à jour le dépôt local -------------------------------------------
# On récupère les éventuelles demandes déposées depuis un autre appareil.
maj() {
  git -C "$REPO" fetch --quiet origin 2>/dev/null || return 0
  local br
  br=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)
  git -C "$REPO" merge --ff-only "origin/$br" --quiet 2>/dev/null || true
}

# --- Le contenu d'une demande est-il vide ? ---------------------------------
# Une demande « vide » = fichier absent, ou uniquement : des blancs, des titres
# markdown, des cases à cocher vides, ou un GABARIT (blocs <!-- ... -->).
# PIÈGE RÉSOLU : un gabarit d'aide contient un EXEMPLE de demande ; s'il n'était
# pas retiré, la machine rejouerait l'exemple à chaque passage. On supprime donc
# tout bloc de commentaire HTML, même sur plusieurs lignes, avant de juger.
est_vide() {
  local f="$1"
  [ -f "$f" ] || return 0
  local utile
  utile=$(sed -e ':a' -e '/<!--/!b' -e 'N' -e '/-->/!ba' -e 's/<!--.*-->//g' "$f" 2>/dev/null \
          | grep -vE '^\s*$|^\s*#|^\s*-\s*\[\s*\]\s*$' \
          | tr -d '[:space:]')
  [ -z "$utile" ]
}

case "${1:-lire}" in
  --help|-h)
    sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
    exit 0 ;;

  etat)
    verifier_prive
    maj
    if est_vide "$DEMANDE"; then
      echo "aucune demande en attente"
      exit 0
    fi
    echo "demande en attente"
    exit 10 ;;

  lire)
    verifier_prive
    maj
    if est_vide "$DEMANDE"; then
      exit 0                      # rien : sortie vide, l'agent ne dit rien
    fi
    cat "$DEMANDE"
    exit 10 ;;

  repondre)
    verifier_prive
    shift
    [ $# -gt 0 ] || die "usage : argus-commandement.sh repondre \"texte\""
    mkdir -p "$REPO"
    {
      echo "# Réponse d'Argus — $(date '+%d/%m/%Y %H:%M')"
      echo
      printf '%s\n' "$*"
    } > "$REPONSE"
    git -C "$REPO" add reponse.md 2>/dev/null || true
    git -C "$REPO" -c user.name=argus -c user.email=argus@local \
      commit -q -m "réponse : $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || true
    git -C "$REPO" push --quiet 2>/dev/null || \
      echo "(la réponse est écrite localement ; publication impossible hors ligne)" >&2
    exit 0 ;;

  traiter)
    verifier_prive
    [ -f "$DEMANDE" ] || { echo "aucune demande"; exit 0; }
    mkdir -p "$HISTO"
    stamp=$(date '+%Y-%m-%d_%H%M%S')
    cp "$DEMANDE" "$HISTO/demande-$stamp.md" 2>/dev/null || true
    # vider la boîte : on laisse le gabarit, jamais de contenu résiduel
    cat > "$DEMANDE" <<'GABARIT'
# Demande à exécuter

<!--
Écrivez votre demande ci-dessous, en français.
Laissez ce fichier vide (ou comme ceci) s'il n'y a rien à faire.

Exemple :
Redémarre l'interface, elle ne répond plus sur mon téléphone.
-->
GABARIT
    git -C "$REPO" add -A 2>/dev/null || true
    git -C "$REPO" -c user.name=argus -c user.email=argus@local \
      commit -q -m "demande traitée ($stamp)" 2>/dev/null || true
    git -C "$REPO" push --quiet 2>/dev/null || \
      echo "(archivage local effectué ; publication impossible hors ligne)" >&2
    exit 0 ;;

  *)
    die "commande inconnue : $1 (attendu : lire | repondre | traiter | etat)" ;;
esac
