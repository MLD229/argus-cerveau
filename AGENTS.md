# AGENTS.md — instructions pour un agent IA

> Destiné à un agent IA qui aide un utilisateur **non technique** à installer
> Argus. Lisez tout avant d'agir.

## Votre rôle

L'utilisateur ne connaît pas le terminal. Vous faites le travail ; il ne fait
que répondre à vos questions (sa clé d'API, autoriser une installation).

- Pas de sortie brute, pas de log, pas de commande affichée.
- Français simple, une étape à la fois, résultat d'abord.
- Échec → arrêtez-vous, expliquez, proposez. N'enchaînez pas.

## Ce dépôt

`argus-cerveau` contient les **savoir-faisirs** de l'agent sous forme de
profils Hermes (format natif `distribution.yaml`). Ce n'est pas une
application : ça s'installe dans Hermes.

Quatre profils :

| Profil | Rôle |
|---|---|
| `argus-chef` | l'agent d'agence : comprend la demande, route, répond |
| `argus-veille` | recherche lourde en arrière-plan |
| `argus-client` | « Signature Libérale » : cherche des biens pour un particulier |
| `argus-serveur` | installe et surveille l'installation, porte le canal de commandement |

## Installation

**Prérequis** : Hermes Agent installé (`hermes --version` doit répondre), git,
et une clé d'API DeepSeek fournie par l'utilisateur.

```bash
git clone https://github.com/MLD229/argus-cerveau.git
cd argus-cerveau
./installer-tout.sh
```

**Vérifier** : `./installer-tout.sh --check` → aucun `MANQUANT`.

### La clé d'API (indispensable)

```bash
echo 'DEEPSEEK_API_KEY=sk-LA-CLE' > ~/.hermes/.env
chmod 600 ~/.hermes/.env
for p in argus-chef argus-veille argus-client argus-serveur; do
  cp ~/.hermes/.env ~/.hermes/profiles/$p/.env 2>/dev/null || true
done
```

**Vérifier** : `hermes -p argus-chef -z "dis juste: pret"` répond.

**Piège vécu** : la clé doit être dans le `.env` du profil **et** à la racine de
`~/.hermes/`. Hermes lit celui du profil quand on utilise `-p`. Si seule la
racine est remplie, l'agent répond « pas d'identifiants ».

### Les outils Python

Le profil `client` appelle des outils Python installés sur la machine :

```bash
./installer.sh              # installe les outils (dans /opt/tools par défaut)
```

## Ensuite : l'interface

```bash
git clone https://github.com/MLD229/argus-ui.git
cd argus-ui && ./argus-ui
```

Guide complet (adresse permanente, application téléphone, dépannage) :
`https://github.com/MLD229/argus-ui/blob/master/INSTALLATION.md`

## Règles de sécurité

- **Demandez la clé d'API**, ne la devinez jamais, ne l'écrivez jamais dans un dépôt.
- Ne supprimez aucune donnée de l'utilisateur sans demande explicite.
- Ne touchez pas aux tâches automatiques ou aux profils existants sans le dire.
- Si l'utilisateur veut changer une adresse ou un port déjà en service :
  prévenez que cela casse une application déjà installée.

## Vérifications de fin

1. `hermes -p argus-chef -z "dis juste: pret"` → répond.
2. `hermes -p argus-client -z "un local pour mon cabinet à Lyon 6e"` → répond.
3. `./installer-tout.sh --check` (dans argus-cerveau) → aucun `MANQUANT`.

Rapportez : étapes réussies, toute étape en échec avec le message exact.
