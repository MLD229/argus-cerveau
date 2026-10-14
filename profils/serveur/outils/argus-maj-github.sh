#!/usr/bin/env bash
# ============================================================================
#  argus-maj-github.sh — surveille le dépôt GitHub du cerveau Argus.
#
#  Lancé par cron. SILENCIEUX s'il n'y a rien de nouveau. Sinon, affiche les
#  commits apparus depuis le dernier passage — c'est ce texte qui est envoyé.
#
#  POURQUOI : le cerveau (profils, skills, outils) évolue sur GitHub. Sans
#  veille, la machine pourrait rester des semaines en arrière sans qu'on le
#  sache. Ici on SIGNALE ; on n'applique PAS automatiquement (une mise à jour
#  des profils touche à la mémoire de l'agent : ça se décide, pas à l'aveugle).
# ============================================================================
set -uo pipefail

REPO_DIR=/home/momo/projects/argus-cerveau
ETAT=/home/momo/.hermes/scripts/.argus-maj-github.dernier
BRANCHE=main

[ -d "$REPO_DIR/.git" ] || { echo "⚠️  ARGUS — dépôt introuvable : $REPO_DIR"; exit 1; }

# --- Récupérer l'état distant (sans toucher au travail local) ---------------
cd "$REPO_DIR" || exit 1
if ! git fetch --quiet origin "$BRANCHE" 2>/dev/null; then
  # Échec réseau : on ne crie pas (fréquent hors ligne) — on sort en silence.
  exit 0
fi

DISTANT=$(git rev-parse --short "origin/$BRANCHE" 2>/dev/null || echo "")

# --- Premier passage : on mémorise, sans rien dire --------------------------
if [ ! -f "$ETAT" ]; then
  echo "$DISTANT" > "$ETAT"
  exit 0
fi

DERNIER=$(cat "$ETAT" 2>/dev/null || echo "")
[ "$DISTANT" = "$DERNIER" ] && exit 0      # rien de neuf -> silence

# --- Il y a du nouveau : on prépare le résumé -------------------------------
NOUVEAUX=$(git log --oneline --no-decorate "$DERNIER..origin/$BRANCHE" 2>/dev/null | head -15)
NB=$(git rev-list --count "$DERNIER..origin/$BRANCHE" 2>/dev/null || echo "?")

echo "📦 ARGUS — mise à jour disponible sur GitHub ($NB commit(s))"
echo
echo "$NOUVEAUX"
echo
echo "Dernier vu : $DERNIER   →   maintenant : $DISTANT"
echo
echo "Pour appliquer :"
echo "  cd $REPO_DIR && git pull && ./installer-tout.sh"
echo
echo "(Rien n'est appliqué automatiquement : une mise à jour des profils"
echo " touche à la mémoire de l'agent.)"

# Mémoriser le nouvel état pour ne pas répéter l'alerte.
echo "$DISTANT" > "$ETAT"
