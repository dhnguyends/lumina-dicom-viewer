# Vérification de Lumina — 4 octobre 2026

## Vérifications automatisées

- `python -m unittest discover -s tests -v` : **9 tests passent**.
- `node --check static/app.js` : syntaxe JavaScript valide.
- `python -m py_compile server.py` : syntaxe Python valide.
- Le test HTTP couvre les routes JSON et PNG, les bornes des paramètres, le rejet d’une origine externe, les chemins de fichiers non autorisés et un import multipart de DICOM synthétique.

## Vérifications dans le navigateur

La série réelle du notebook a été indexée : **195 coupes, 512 × 512 pixels, intervalle mesuré 2 mm**. Les 24 aperçus de la vue d’ensemble se chargent correctement.

| Interaction | Observation |
|---|---|
| Zoom des aperçus | Le bouton + passe de 100 % à 110 % ; la largeur cible commune passe à 198 px et les cartes affichées ont la même largeur. |
| Aperçu agrandi | La boîte de dialogue affiche une coupe réelle, ses repères patient, la fenêtre de contraste et le curseur de parcours. |
| Parcours de la série | Le bouton suivant passe de la coupe 27 à la coupe 28 et met à jour image, titre et curseur. |
| Contraste, inversion et zoom | Les paramètres de la visionneuse passent à centre 40, largeur 400, inversion active et zoom 110 %. |
| Recherche | « 98 » renvoie uniquement la coupe 98 sur la série de 195 images. |
| Favoris | Ajouter un favori donne un compteur de 1 et une galerie filtrée avec une carte ; le retrait remet le compteur à zéro. |
| Galerie exhaustive | « Toutes les coupes » produit 195 cartes avec chargement paresseux des images. |
| Fenêtre os | Le contrôle affiche « Os » et toutes les URLs d’aperçu utilisent une largeur de 1800 HU. |
| Visionneuse indépendante | Une page indépendante affiche correctement la coupe 98 avec le fenêtrage poumon, sans bibliothèque latérale. |
| Console | Aucun message d’erreur ou avertissement relevé au moment de l’inspection. |

## Limites de cette vérification

Le navigateur intégré de Codex ignore les demandes de popup observées lors de l’essai. La page indépendante a été ouverte directement et vérifiée. La demande `window.open` est implémentée mais son ouverture effective dans Chrome/Edge reste à vérifier par l’utilisateur dans son navigateur habituel. Selon les réglages du navigateur, une nouvelle fenêtre peut être présentée comme un onglet ou être bloquée.

Les règles CSS pour téléphone et tablette sont présentes. La commande de redimensionnement disponible dans le navigateur intégré n’a pas modifié la largeur de mise en page mesurée ; la vue téléphone n’est donc pas déclarée vérifiée. Le réglage temporaire du navigateur a été réinitialisé.

Les tests numériques utilisent de petits DICOM synthétiques, sans données nominatives. La segmentation et les calculs 3D du notebook n’ont pas été réexécutés. Il ne s’agit pas d’une validation clinique.

## Édition GitHub

Les observations ci-dessus concernent le développement local original. Les illustrations publiées sur GitHub sont remplacées par un fantôme synthétique sans données patient. Le notebook et les séries réelles ne sont pas distribués. Les tests ont également été exécutés dans le checkout de publication.
