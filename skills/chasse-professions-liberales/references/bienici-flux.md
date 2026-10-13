# Flux Bien'ici — endpoints, champs, pagination, adresse

## Endpoints (JSON public, non bloque, robots permissif)
- suggest : `https://res.bienici.com/suggest.json?q=<texte>&type=city,delegated-city,department,postalCode,region,arrondissement`
- search  : `https://www.bienici.com/realEstateAds.json?filters=<json>`

`filters` (JSON compact) : `size`, `from`, `filterType` (`buy`|`rent`), `onTheMarket:[true]`,
`zoneIdsByTypes:{zoneIds:[<zone_id>]}`, `propertyType:[...]`, `minArea`, `maxArea`,
`minPrice`, `maxPrice`, `minRooms`.

## Pagination
La reponse porte `total` (toutes les annonces correspondantes) et `realEstateAds` (une page
de `size`). Boucler `from` = 0, 40, 80, ... jusqu'a ce que le cumul atteigne `total`
(petit `sleep` entre appels). Le CLI `bienici.py annonces` ne fait **qu'une** page.

## Champs bruts utiles (`realEstateAds[i]`)
- `id`, `title`, `propertyType` (`flat`/`house`/`premises`/`shop`/`office`/`programme`/...),
  `adType` ; **`programme`** = programme neuf multi-lots (prix/surfaces en listes), a ecarter
  quand on cherche un bien unique
- `price` (nombre **ou liste**), `surfaceArea`, `pricePerSquareMeter`
- `city`, `postalCode`, `district` `{libelle, name, cp, code_insee}`
- `floor` (**0 = RDC ; absent pour certaines annonces**) : le champ peut **contredire le
  texte** (annonce a `floor == 0` dont la description dit « 1er etage ») -> croiser avec
  titre/description avant de trancher, ne jamais conclure sur le seul champ
- `roomsQuantity`
- `hasElevator` (**souvent absent** pour locaux/bureaux), `hasCellar`,
  `energyClassification`, `greenhouseGazClassification`
- `accountDisplayName` (agence — **souvent absent**, notamment pour les locaux/bureaux)
- `photos[]` `{url_photo, url}` : le chemin de `url_photo` contient le **slug de l'agence**
  (`office8/eraagence_982/...`, `office8/rez_de_chaussee/...`) -> sert a attribuer l'annonce
  quand `accountDisplayName` manque, et d'indice pour la recherche multi-source
- `lifeAnnuityAgeOfMan` / `lifeAnnuityAgeOfWoman` / `lifeAnnuityMonthlyAllowance` : presents
  => **viager** (pas une vente de murs) ; ne pas le compter dans les « bonnes affaires »
- `publicationDate`, `modificationDate`, `priceHasDecreased`
- `addressKnown` (bool), `blurInfo` `{radius, origin, position:{lat,lon}, bbox}` : `radius`
  **varie selon l'annonce** (50 / 100 / 250 m courants ; `1000` = centroide quand
  `addressKnown == false`)
- **Aucun champ adresse rue.**

## Lien d'annonce
`https://www.bienici.com/annonce/<vente|location>/<slug-ville>/<id>`
(slug = ville en minuscules, espaces -> `-`, `e`/`e` accentues -> `e`).

## Adresse approximative (reverse BAN)
`https://api-adresse.data.gouv.fr/reverse/?lat=<lat>&lon=<lon>&limit=1`
-> `features[0].properties.label` / `street` / `postcode` / `distance`.
- Marquer **approximatif** : l'ecart possible vaut `blurInfo.radius` (50 a 250 m).
- `addressKnown == false` -> point = centroide d'arrondissement, voie **factice** : ne pas
  l'afficher, dire « adresse non communiquee ».
- Plusieurs annonces peuvent partager exactement le meme point (centroide, ou bien
  rediffuse) : detecter les positions identiques.

## Position exacte pour un calcul de proximite (flux BRUT, pas la fiche normalisee)
La fiche normalisee de `bienici.py` **omet** les coordonnees. Pour trier par distance a un
repere (metro, place, gare), rejouer la MEME requete que l'outil et lire le brut — ne jamais
reconstruire `filters` a la main (la zone serait ignoree) :
```python
import sys, json; sys.path.insert(0, "/opt/tools")
import bienici
zid = bienici._premier_zone_id("Lyon 7")
filtres = {"size":40, "from":0, "filterType":"buy", "onTheMarket":[True],
           "zoneIdsByTypes":{"zoneIds":[zid]}, "minArea":30, "maxArea":200}
data = bienici.http_get_json(bienici.BIENICI_SEARCH,
        params={"filters": json.dumps(filtres, separators=(",",":"))}, timeout=30)
# data["realEstateAds"] -> blurInfo.position{lat,lon}, addressKnown ; boucler "from" += 40
```
- **Depuis `execute_code`** : piloter les CLI par `subprocess.run(cmd, shell=True,
  capture_output=True, text=True, timeout=...)` ; en bibliotheque, ajouter `/opt/tools` au
  `sys.path` puis `import bienici`.
- `price` ET `surfaceArea` peuvent etre des **listes** dans le brut (programmes neufs :
  `[53,70]` m2, `[324000,388000]` EUR) -> normaliser chaque valeur avec un helper qui prend
  l'element 0, sinon `30 <= surf <= 60` plante sur un `TypeError`.
- Une zone d'arrondissement renvoie parfois des annonces d'un **autre CP** (limites
  partagees : zone Lyon 7 -> quelques 69003/69002) : **filtrer sur `postalCode`**.
- Qualifier RDC / RDC surelev / destination en comparant sur le **texte** (titre +
  `description`) : ces mentions n'existent PAS dans les champs structures.
- **Distance NON exploitable si `blurInfo.radius == 1000` ou `addressKnown == false`** : le
  point est alors le centroide (arrondissement/quartier) et l'ecart atteint plusieurs centaines
  de metres (mesure : 594 m calcules vs 279 m reels pour un bien dont la rue etait citee dans
  le texte). Dans ce cas, geocoder la rue citee et retenir CETTE distance ; ne classer par
  proximite d'un repere qu'apres, et le dire au client.

## Repere de proximite (metro, gare) — prendre le NOEUD, pas le centroide BAN
Le point BAN d'une grande place peut etre a ~300 m du noeud de station : BAN « Place Jean
Jaures » = 45,7399 / 4,8397 alors que la station (OSM `type=station`, ou article Wikipedia)
= 45,7375 / 4,8374. Prendre la **coordonnee du noeud de station**, sinon la distance
annoncee est fausse de plusieurs centaines de metres. Attention aux **noms TCL != noms
usuels du client** (« metro Jean Jaures » = station **Place Jean Jaures**, ligne B, 7e).
Distance = haversine a vol d'oiseau, **a annoncer approximative** (position floutee) ;
~80 m/min a pied (3-4 min ≈ 330 m, 5 min ≈ 450 m, 8 min ≈ 660 m).

### Valider une ancre de transport — ordre de preference
Pour une station NOMMEE, dans cet ordre :
1. **Wikipedia `prop=coordinates`, titre exact** `<Nom> (métro de Lyon)` — le plus rapide et
   fiable (ex. `titles=Brotteaux (métro de Lyon)` -> 45.767025 / 4.859412). Si `coordinates`
   est absent, c'est que le titre differe -> essayer le suffixe `(métro de Lyon)` AVANT de
   conclure a l'absence de station.
2. **Nominatim** `https://nominatim.openstreetmap.org/search?format=json&q=station%20<Nom>%20Lyon&limit=3`
   -> renvoie le `node` OSM de la station (`lat`/`lon`). Deux sources concordantes valent
   validation.
3. **Overpass** en repli — utile pour cartographier TOUS les arrets d'un secteur, pas seulement
   une station.
- **Nom officiel de la station** : le libelle du client n'est pas fiable. Lister les stations
  du reseau via l'API Wikipedia :
  `https://fr.wikipedia.org/w/api.php?action=parse&page=Liste%20des%20stations%20du%20m%C3%A9tro%20de%20Lyon&prop=wikitext&format=json`
  (nom officiel, ligne, arrondissement, date d'ouverture). `prop=coordinates&titles=<station>`
  renvoie `missing` des que le titre exact n'existe pas -> ne PAS en conclure qu'il n'y a pas
  de station.
- **Coordonnees + arrets du secteur (repli)** : Overpass — **header `User-Agent`
  obligatoire** (sans lui : HTTP 406) —
  `https://overpass-api.de/api/interpreter?data=<url-encode>`, avec une **bbox explicite**
  (une requete par `area["name"="Lyon"]` peut ne rien renvoyer) et en interrogeant **`node`
  ET `way`** : certaines stations sont des `way` (Place Jean Jaures) et une requete sur les
  seuls `node` les manque ; `out center tags` fournit `center.lat/lon` des `way`. Chercher
  `station=subway`, `railway=tram_stop`, `highway=bus_stop` : le client veut « les
  transports », pas seulement le metro.
- Reperes verifies : **Place Jean Jaures (ligne B) = 45,73758 / 4,83733**, 69007 ; **Brotteaux
  (ligne B) = 45,7670 / 4,8594**, place Jules Ferry, 69006 (Wikipedia et OSM concordants) ;
  Debourg (ligne B + tram T1) a ~735 m de Place Jean Jaures. Attention, « Jean Jaures /
  Guillotiere » renvoye par OSM est une station de velos en libre-service, pas un metro. Une
  annonce peut ecrire « gare » pour une station de metro (« gare des Brotteaux » = metro
  Brotteaux).

## Zone (exemple Lyon 6e)
`zone "Lyon 6e"` -> type `arrondissement`, INSEE `69386`, CP `69006`, zoneId `-10679`.
Preferer l'arrondissement a la ville quand le texte contient un numero.
