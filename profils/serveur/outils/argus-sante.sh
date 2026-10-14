#!/usr/bin/env bash
# ============================================================================
#  argus-sante.sh — surveillance du serveur Argus (watchdog).
#
#  Lancé par cron. SILENCIEUX quand tout va bien : n'affiche RIEN si le
#  serveur répond. Sinon, sort le diagnostic — c'est ce texte qui est envoyé.
#
#  POURQUOI SILENCIEUX : un watchdog qui parle à chaque tick devient du bruit
#  qu'on finit par ignorer. On ne parle QUE si quelque chose ne va pas.
#
#  CE QUI EST VÉRIFIÉ
#    1. le conteneur de l'agent (argus-confine) tourne ;
#    2. le serveur de l'interface répond en local (127.0.0.1:8080) ;
#    3. l'accès fixe (Tailscale serve) répond ;
#    4. le magasin de notifications est lisible.
#  Et si un point est en panne, on TENTE de réparer (relance), puis on
#  re-vérifie avant de conclure.
# ============================================================================
set -uo pipefail

PORT="${ARGUS_UI_PORT:-8080}"
UI_DIR=/home/momo/Documents/ui-web
URL_FIXE="https://argus-pc-1.tail49b6d2.ts.net"
DOCKER_OK=0

D() { docker "$@"; }
if ! docker info >/dev/null 2>&1; then
  if command -v newgrp >/dev/null 2>&1; then
    D() { newgrp docker -c "docker $(printf '%q ' "$@")"; }
  fi
fi

problemes=()

# --- 1. Le conteneur de l'agent ---------------------------------------------
if [ -z "$(D ps --filter 'name=^argus-confine$' --format '{{.Names}}' 2>/dev/null)" ]; then
  # Tentative de réparation : le wrapper sait démarrer proprement.
  [ -x /home/momo/projects/argus-deploy/argus ] && \
    /home/momo/projects/argus-deploy/argus --start >/dev/null 2>&1
  sleep 5
  if [ -z "$(D ps --filter 'name=^argus-confine$' --format '{{.Names}}' 2>/dev/null)" ]; then
    problemes+=("le conteneur 'argus-confine' (l'agent) est ARRÊTÉ et n'a pas redémarré")
  fi
fi

# --- 2. Le serveur de l'interface -------------------------------------------
code_local=$(curl -s -m 8 -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/sante" 2>/dev/null); code_local=${code_local:-000}
if [ "$code_local" != "200" ]; then
  # Tentative de réparation : relancer via le script du projet.
  if [ -x "$UI_DIR/argus-ui" ]; then
    ( cd "$UI_DIR" && ./argus-ui --local >/dev/null 2>&1 )
    sleep 4
    code_local=$(curl -s -m 8 -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/sante" 2>/dev/null); code_local=${code_local:-000}
  fi
  [ "$code_local" != "200" ] && problemes+=("l'interface ne répond pas en local (code $code_local, port $PORT)")
fi

# --- 3. L'accès fixe (Tailscale) --------------------------------------------
code_fixe=$(curl -s -m 12 -o /dev/null -w "%{http_code}" "$URL_FIXE/api/sante" 2>/dev/null); code_fixe=${code_fixe:-000}
if [ "$code_fixe" != "200" ]; then
  # Réparation : re-pointer serve (idempotent).
  if [ -x /usr/bin/tailscale ]; then
    /usr/bin/tailscale serve --bg --https=443 "http://127.0.0.1:$PORT" >/dev/null 2>&1
    sleep 3
    code_fixe=$(curl -s -m 12 -o /dev/null -w "%{http_code}" "$URL_FIXE/api/sante" 2>/dev/null); code_fixe=${code_fixe:-000}
  fi
  [ "$code_fixe" != "200" ] && problemes+=("l'accès fixe $URL_FIXE ne répond pas (code $code_fixe)")
fi

# --- 4. Le magasin de notifications -----------------------------------------
MAGASIN=/home/momo/projects/argus-deploy/notifs/notifications.json
if [ -f "$MAGASIN" ]; then
  if ! python3 -c "import json;json.load(open('$MAGASIN'))" 2>/dev/null; then
    problemes+=("le magasin de notifications est illisible (JSON corrompu) : $MAGASIN")
  fi
fi

# --- Verdict : on ne parle QUE s'il y a un problème -------------------------
if [ ${#problemes[@]} -eq 0 ]; then
  exit 0        # silence total = tout va bien
fi

echo "⚠️  ARGUS — problème détecté ($(date '+%d/%m %H:%M'))"
echo
for p in "${problemes[@]}"; do echo "  - $p"; done
echo
echo "État :"
echo "  conteneur : $(D ps --filter 'name=^argus-confine$' --format '{{.Status}}' 2>/dev/null || echo 'absent')"
echo "  local     : $code_local"
echo "  url fixe  : $code_fixe"
echo
echo "Pour relancer à la main : cd $UI_DIR && ./argus-ui"
exit 1
