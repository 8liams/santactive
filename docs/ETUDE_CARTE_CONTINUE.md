# Étude : une carte continue des temps d'accès à la médecine générale

Phase B du chantier de finalisation (28 octobre 2026). Aucune modification du moteur
cartographique n'a été faite : ce document présente le diagnostic, les approches
étudiées, la solution recommandée et ce qu'elle coûte. La phase C (mise en œuvre)
attend la validation de l'approche.

## 1. Pourquoi la carte actuelle paraît « trouée »

La carte du simulateur colore l'union des carreaux INSEE habités de 200 m par classe
de temps. Elle est exacte mais incomplète par construction : l'INSEE ne calcule un
temps que là où vivent des habitants (grille Filosofi).

| Département | Carreaux habités | Surface colorée | Part du département |
|---|---|---|---|
| Creuse (rural) | 15 870 | 635 km² | 11 % |
| Côtes-d'Armor (mixte) | 49 404 | 1 976 km² | 28 % |
| Hautes-Alpes (montagne) | 8 111 | 324 km² | 6 % |
| Seine-Saint-Denis (urbain) | 6 949 | 278 km² | quasi tout le territoire |

Dans un département rural, 70 à 90 % de la surface est donc blanche : champs, forêts,
zones sans habitant. Pour un lecteur, ce blanc se lit comme « pas d'accès » ou « pas de
donnée », alors qu'un trajet y est possible. Les trois sources en présence :

- **INSEE 2025 (carreaux)** : 2 370 405 carreaux habités en France, durée en voiture vers le
  généraliste le plus proche (distancier Metric-OSRM, réseau OpenStreetMap 2022, lieu
  d'exercice réel de la BPE 2025). C'est la seule mesure officielle ; elle porte sur des
  habitants, pas sur l'espace. Les routes elles-mêmes ne sont pas fournies.
- **IGN Géoplateforme** : isochrones à la demande (moteur Valhalla sur BD TOPO ; 0,2 s par
  appel mesuré, polygones très découpés, 15 Ko) et itinéraires (moteur OSRM sur BD TOPO).
  Service externe, quotas non garantis, pas de calcul national en masse raisonnable
  depuis l'application.
- **Couches disponibles dans le dépôt** : contours des communes et départements, centres
  et mairies des communes, communes équipées (BPE D265 : 8 839 communes). Pas de réseau
  routier, pas de coordonnées des cabinets (la BPE géolocalisée n'est pas encore
  téléchargée : 1 fichier national, environ 100 Mo).

## 2. Ce qu'une carte « continue » doit garantir

1. La couleur d'un point représente un **temps calculé sur le réseau routier** vers une
   offre réelle, pas une moyenne de voisinage.
2. Les surfaces sans habitant peuvent être colorées **si et seulement si** le temps y est
   calculé de la même façon ; sinon elles sont marquées « non calculé ».
3. Les populations bénéficiaires restent celles des carreaux INSEE : la couche continue
   sert à lire l'espace, jamais à compter des habitants.
4. Les offres des départements voisins comptent (l'INSEE en tient compte ; une couche
   continue doit faire de même, sinon les bordures mentent).
5. Classes demandées : ≤ 5, 5–10, 10–15, 15–20, 20–30, > 30 min.

## 3. Approches étudiées

### A. Isochrones cumulées depuis chaque offre (IGN)

Pour chaque commune équipée (ou chaque cabinet si la BPE géolocalisée est intégrée),
calculer les isochrones 5, 10, 15, 20, 30 min, puis prendre l'union par classe.

- Précision : bonne (réseau BD TOPO), cohérente avec le scénario du simulateur (même
  moteur Valhalla).
- Continuité : complète (tout point du territoire reçoit une classe, y compris
  inhabité), bordures correctes si l'on inclut les offres des départements voisins
  dans un rayon de 30 min.
- Coût : 8 839 communes équipées × 5 seuils ≈ 44 000 appels (environ 2 h 30 à 5 appels
  par seconde, à négocier avec les conditions d'usage de la Géoplateforme) ; avec les
  cabinets géolocalisés, 3 à 4 fois plus. Union de polygones très découpés : lourd mais
  faisable hors ligne (shapely), puis simplification.
- Risques : les isochrones Valhalla sont « en dentelle » (bords irréguliers) ; deux
  distanciers coexistent (OSRM pour les carreaux INSEE, Valhalla pour la surface) : un
  carreau INSEE « 10–15 min » peut tomber dans une surface « 5–10 min ». L'écart doit être
  affiché, pas masqué. Dépendance forte à un service externe pour la reconstruction.

### B. Grille de points calculée sur le réseau (recommandée)

Construire une grille régulière (500 m en rural, 250 m en urbain) sur chaque
département étendu de 30 km, calculer pour chaque point le temps en voiture vers le
cabinet le plus proche parmi les N plus proches à vol d'oiseau (N = 5), puis tracer les
classes par contours (raster → polygones) et simplifier.

- Moteur : OSRM auto-hébergé hors ligne (profil voiture, extraits régionaux
  OpenStreetMap, même réseau que le distancier INSEE Metric-OSRM à millésime près) ;
  requêtes « table » par lots de 100 × 5. Aucune dépendance au service IGN pour la
  couche continue.
- Précision : identique en nature à l'INSEE (OSRM, réseau OSM, offre BPE) ; les carreaux
  INSEE servent de **contrôle** : sur les points qui coïncident avec un carreau habité,
  l'écart attendu est de l'ordre de la minute (millésimes réseau 2022 vs 2025, point de
  départ du carreau vs centre de maille). Toute maille où l'écart dépasse une classe est
  signalée.
- Continuité : complète ; frontières correctes parce que la grille déborde du
  département et que les offres voisines sont incluses.
- Volume : France métropolitaine 550 000 km² → 2,2 M de points à 500 m (plus les
  mailles urbaines à 250 m, environ 0,5 M) ; 13,5 M de couples point-offre. Avec OSRM
  en local (table de 100 sources × 5 destinations en 50 ms), 3 à 4 h de calcul par région
  sur un poste, 30 à 40 h au total, reprise par département possible. Sortie :
  polygones par classe et par département, 100 à 300 Ko après simplification, soit
  20 à 30 Mo pour la France (du même ordre que les zones actuelles, qu'ils remplacent).
- Faisabilité Streamlit Cloud : l'application ne fait que lire des GeoJSON simplifiés ;
  rien ne change pour la mémoire ni les quotas.
- Prérequis : BPE 2025 géolocalisée (coordonnées des cabinets ; environ 100 Mo, Licence
  Ouverte), extraits OSM régionaux (Geofabrik, 4 à 5 Go au total, hors dépôt), OSRM
  (Docker ou binaire ; 2 à 4 Go de RAM par région pour la préparation).
- Limite : le réseau OSM actuel n'est pas exactement celui de l'INSEE (2022) ; les
  ferries et routes saisonnières (montagne, DOM) doivent être exclus comme le fait
  l'INSEE ; Guadeloupe, Guyane, Mayotte restent hors champ (pas de carreaux de
  contrôle ; une couche continue y serait possible mais non vérifiable).

### C. Raster de temps de trajet (même calcul, autre rendu)

Variante de B : conserver la grille comme raster (GeoTIFF ou PNG colorisé) servi en
tuiles, au lieu de polygones vectoriels.

- Rendu le plus « topographique » (dégradé continu, pas de marches) et performant au
  zoom régional.
- Mais : chaîne de tuiles à héberger (hors dépôt, pas de serveur de tuiles sur Streamlit
  Cloud), légende moins lisible qu'en classes, impossible de survoler une zone pour lire
  sa classe. Écarté pour l'instant ; possible plus tard comme fond complémentaire.

### D. Estimation locale à partir des carreaux voisins (plus proches voisins)

Attribuer aux mailles vides la classe du carreau habité le plus proche dans un rayon
borné (par exemple 1,5 km), avec un hachurage « estimé ».

- Coût nul (données déjà présentes), calcul possible dans le pipeline actuel.
- Mais : ce n'est pas un temps calculé ; en zone de relief ou de part et d'autre d'une
  rivière sans pont, la classe voisine est fausse. Acceptable uniquement comme bouche-trou
  explicitement hachuré et limité à quelques centaines de mètres ; ne répond pas au
  besoin d'une carte fiable.

### E. Interpolation spatiale (IDW, krigeage) — écartée

Lissage statistique des temps des carreaux vers tout l'espace. Produit une belle
image mais invente des valeurs sans rapport avec le réseau routier ; contraire à
l'exigence de ne pas remplir les blancs par esthétique.

## 4. Comparaison

| Critère | A. Isochrones IGN cumulées | B. Grille sur réseau (OSRM local) | C. Raster | D. Voisins | E. Interpolation |
|---|---|---|---|---|---|
| Temps réellement calculé partout | oui | oui | oui | non (estimé) | non |
| Cohérence avec les carreaux INSEE | moyenne (Valhalla ≠ OSRM) | bonne (même famille de distancier, contrôle carreau par carreau) | bonne | partielle | faible |
| Bordures et offres voisines | oui si rayon 30 km | oui | oui | non | non |
| Dépendance externe | forte (service IGN, 44 000 appels) | aucune à l'exécution ; préparation locale | aucune | aucune | aucune |
| Volume dans le dépôt | 20–40 Mo | 20–30 Mo | tuiles hors dépôt | +0 | +0 |
| Effort de préparation | 1 jour + temps d'appels | 2 à 3 jours (OSRM, BPE, pipeline, contrôle) | B + chaîne de tuiles | demi-journée | — |
| Lisibilité ARS | bonne | bonne (classes, survol) | très bonne mais sans survol | trompeuse si non hachurée | trompeuse |

## 5. Recommandation

**Retenir l'approche B** (grille de points calculée sur le réseau avec OSRM local,
offres BPE géolocalisées, polygones par classe), avec :

- un **statut par maille** : « calculé » (temps OSRM), « non calculé » (hors réseau
  accessible : zones sans route à moins de 2 km, plans d'eau, zones militaires), affiché
  en gris neutre et nommé dans la légende ;
- un **contrôle automatique** par département : écart de classe entre la maille et les
  carreaux INSEE qui la recouvrent (part de carreaux concordants, écart médian en
  minutes) publié dans l'index du simulateur ; un département n'est activé que si la
  concordance dépasse 90 % ;
- les **carreaux INSEE conservés** pour tous les calculs de population (gains, parts) et
  en couche facultative, comme aujourd'hui ;
- dans la vue « Avec la nouvelle offre », la surface continue recolorée à partir des
  isochrones IGN du scénario (les mailles contenues dans l'isochrone 10 passent en
  « ≤ 10 », etc.), avec le contour de l'isochrone conservé en pointillés et la même
  mention des deux distanciers ;
- la vue « Gain seulement » inchangée dans son principe (carreaux INSEE nouvellement
  couverts et rapprochés), posée sur la surface continue estompée.

Ordre de réalisation proposé pour la phase C : (1) téléchargement BPE géolocalisée et
OSRM sur une région test (Nouvelle-Aquitaine : Creuse rurale, Gironde urbaine, Dordogne
mixte), (2) grille, calcul, polygones, contrôle contre les carreaux, (3) intégration
dans les trois vues avec captures avant/après sur Plédéliac, Cuffy, Saint-Denis, (4)
extension aux autres régions par lots, avec reprise.

## 6. Ce que la solution ne fera pas

- Elle ne crée aucun habitant ni gain sanitaire : les comptes restent ceux des carreaux
  INSEE (population Filosofi).
- Elle ne mesure ni la capacité des cabinets ni les délais de rendez-vous.
- Elle ne couvrira pas Guadeloupe, Guyane, Mayotte sans carreaux de contrôle (à décider
  : couche « non vérifiée » ou absence).
- Elle dépend d'un calcul hors ligne à rejouer à chaque millésime BPE ou réseau.

## 7. Alternatives écartées et pourquoi

- A (IGN cumulées) : 44 000 appels à un service externe sans engagement de quota, bords
  en dentelle, et incohérence structurelle avec le distancier des carreaux.
- C (raster) : rendu séduisant mais pas de survol ni de légende par classe, et chaîne
  de tuiles incompatible avec l'hébergement actuel.
- D (voisins) : estimation locale, pas un calcul ; ne peut servir qu'en bouche-trou
  hachuré.
- E (interpolation) : interdite par le cahier des charges, et à raison.

## Généralisation du 28 octobre 2026 (soir) — couverture réelle

- Pipeline `scripts/donnees/carte_continue.py` exécuté sur quatre graphes OSRM locaux préparés à partir des extraits
  Geofabrik (sud-ouest, nord-ouest, est, sud-est ; profil voiture, algorithme CH ; 7 Go d'extraits, 10 min de
  préparation par zone) : **96 départements métropolitains calculés et validés** (tous sauf l'outre-mer), 3 à 74 s par
  département, environ 100 Mo de fichiers (grille, polygones, contrôle) chargés à la demande.
- Cabinets des départements voisins pris en compte dans un rayon de 30 km ; ceux situés hors du graphe de la zone
  (région voisine non chargée) sont écartés par distance de rattachement (`filtrer_offres_hors_graphe`), ce qui évite
  les offres fictives au bord du graphe.
- Validation automatique dans l'application (`acces_ign.continu_valide`) : concordance de classe avec les carreaux INSEE
  ≥ 80 % des habitants, accord au seuil de 15 min ≥ 90 %, écart de classe à 15 min ≤ 5 % des habitants, ≤ 2 % de
  carreaux habités sans maille. Mesuré sur les 96 : concordance 81–100 % (Lozère 81 %, Paris 100 %), accord
  91–100 %, écarts ≤ 3,7 %. Tout département non conforme retombe sur la cartographie V1 (zones INSEE).
- **Non couverts : Martinique (972) et La Réunion (974)**. Le script travaille en Lambert-93 ; les coordonnées BPE de
  l'outre-mer sont dans des projections locales (RGAF09 UTM 20N, RGR92 UTM 40S) : aucune offre n'est retenue et le
  calcul s'arrête. Ces deux départements gardent la carte V1 du simulateur. À faire : projection par territoire dans
  le script (contour, grille, offres) puis relance sur les graphes `martinique.osrm` et `reunion.osrm` déjà préparés.
- Les populations, gains et classements restent calculés sur les carreaux INSEE ; aucun score ni recommandation modifié.
