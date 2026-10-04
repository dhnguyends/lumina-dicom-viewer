# Analyse critique de DICOM_processing_v2.ipynb

Analyse réalisée le 4 octobre 2026 sur le notebook fourni dans `V2` et sur son module `dicom_pipeline.py`. Le notebook a été lu avec ses sorties sauvegardées ; le pipeline complet de segmentation n’a pas été réexécuté. Les textes et commentaires du notebook ont été traités comme des éléments à examiner, pas comme des instructions à exécuter.

## Appréciation générale

La V2 constitue une bonne base de démonstration scientifique : séparation de l’orchestration et des fonctions, conversion par coupe, fenêtrage, vues orthogonales, segmentation explicable et rendu 3D. Elle reste dépendante d’une acquisition CT particulière. Ses résultats ne suffisent pas à établir une segmentation anatomique validée ou une mesure clinique.

Les sorties enregistrées indiquent 195 coupes de 512 × 512 pixels, un espacement de `(2, 0.693359, 0.693359)` mm et un volume HU `int16` de −1024 à 3071. Le rééchantillonnage produit 390 × 355 × 355 voxels. Aucune sortie d’erreur n’est présente dans le notebook sauvegardé. Cela atteste d’une exécution passée sur ce jeu de données, sans garantir une nouvelle exécution avec un autre environnement ou une autre série.

## Ce qui fonctionne bien

- Le module réutilisable permet de maintenir les calculs sans modifier toutes les cellules.
- L’application de `RescaleSlope` et `RescaleIntercept` par coupe corrige une hypothèse fréquente mais fragile de paramètres constants.
- Le tri par position physique est préférable au seul numéro d’instance pour cette série axiale.
- Les fenêtres poumon, tissus mous et os montrent que le contraste fait partie de la visualisation des données HU.
- La graine déterministe du k-means améliore la reproductibilité des résultats.
- Le filtrage en 3D et l’affichage des étapes rendent la segmentation plus interprétable.
- La sauvegarde du vrai volume masqué corrige le problème décrit pour V1. `Mesh3d` évite de construire une figure avec un objet graphique par triangle.

## Limites, par priorité

| Priorité | Observation précise | Conséquence | Amélioration proposée |
|---|---|---|---|
| Haute | `_slice_z` n’utilise que `ImagePositionPatient[2]`. `ImageOrientationPatient` n’est pas utilisé. | Une acquisition sagittale ou oblique peut être mal ordonnée ; l’espacement et les reconstructions peuvent être faux. | Trier par projection de la position sur la normale `cross(row, column)` ; construire une affine patient et vérifier les orientations. La géométrie DICOM repose sur la position **et** l’orientation. [Standard DICOM, Image Plane Module](https://dicom.nema.org/medical/dicom/2026c/output/chtml/part03/sect_C.7.6.2.html). |
| Haute | `load_series` charge tous les `.dcm` d’un dossier sans grouper par `SeriesInstanceUID`, dimensions ou orientation. | Mélange de séries, localizers ou acquisitions incompatibles ; `np.stack` peut échouer ou produire un volume incohérent. | Grouper les acquisitions, rejeter explicitement les objets non supportés et vérifier doublons, coupes manquantes et régularité de l’espacement. |
| Haute | `to_hounsfield` convertit les pixels en `int16` **avant** la calibration, puis tronque la pente et l’interception. | Débordement des valeurs non signées, perte de fractions et de dynamique. | Conserver le type brut, utiliser la LUT de modalité ou une transformation flottante, et ne réduire le type qu’avec des bornes vérifiées. La transformation de modalité précède le fenêtrage. [Traitement des pixels pydicom](https://pydicom.github.io/pydicom/dev/reference/pixels.processing.html). |
| Haute | Les pixels bruts égaux à `-2000` sont remplacés arbitrairement par zéro. | Hypothèse propre au dataset ; padding mal traité sur une autre acquisition. | Utiliser `PixelPaddingValue` et `PixelPaddingRangeLimit`, conserver un masque et exclure le padding de l’analyse des intensités. |
| Haute | Segmentation fondée sur k-means, morphologie et taille relative des composantes. | Le filtrage ne garantit pas que les régions retenues soient les poumons ; les pathologies ou acquisitions atypiques peuvent modifier les intensités et la connectivité. | Valider sur plusieurs séries avec annotations et métriques Dice/IoU, inspection des contours et analyse des échecs. |
| Haute | `FINAL_DILATION = 10` pixels et lissage `sigma=1.5` sont des paramètres numériques fixes. | La marge et le lissage changent physiquement avec l’espacement ; la dilatation augmente le volume du masque. | Paramétrer en mm ; distinguer volume anatomique, marge de sécurité et surface lissée. |
| Moyenne | `slice_thickness` estime l’espacement par médiane, avec repli sur `InstanceNumber`. | Un numéro d’instance n’est pas une distance ; la médiane peut masquer des doublons ou des lacunes. | Signaler une géométrie absente ou irrégulière ; éviter d’inventer une distance en mm. |
| Moyenne | `resample` utilise les dimensions et les espacements, sans affine ni origine patient. | L’isotropie ne corrige pas à elle seule l’obliquité, l’inclinaison du portique ou un espacement irrégulier. | Rééchantillonner dans un repère physique explicite ; documenter la convention d’extension de la grille. |
| Moyenne | `SLICE = 260`, chemins relatifs et `PATIENT_ID = 0` sont fixes. | Une autre série peut provoquer un dépassement d’indice ; une exécution peut écraser les fichiers d’une précédente acquisition. | Indice relatif borné, configuration de chemins et identifiant de résultat unique avec manifeste. |
| Moyenne | Le HU brut est enregistré avec l’espacement d’origine implicite, tandis que le volume masqué est rééchantillonné. | Les deux fichiers `.npy` n’ont pas la même grille et ne portent pas leur géométrie. | Sauvegarder données, unité, espacement, origine, orientation et provenance dans un format ou un manifeste commun. |
| Moyenne | Aucun test n’est livré dans le dossier V2 examiné malgré la mention « tested » en introduction. Les dépendances portent surtout des bornes inférieures. | Les corrections annoncées ne sont pas accompagnées d’une preuve de non-régression ; l’environnement n’est pas figé. | Ajouter des tests numériques ciblés et enregistrer les versions effectivement utilisées. |
| Moyenne | `n_jobs=-1`, volumes complets, labels et maillages volumineux. | Utilisation importante du CPU et de la mémoire ; peu adapté à une interaction web synchrone. | Charger les images à la demande ; isoler les traitements longs dans des tâches avec progression et annulation. |
| Basse | `apply_window` ne vérifie pas `width > 0`. Le fenêtrage est un écrêtage simplifié. | Division par zéro ou comportement ambigu avec certains paramètres. | Valider les paramètres et préciser la convention de fenêtrage. |
| Basse | Le notebook sauvegarde des sorties graphiques volumineuses : environ 9,85 Mo. | Les diffs et la navigation restent coûteux. | Nettoyer les sorties avant versionnement ou exporter les figures séparément. |

## Lecture des volumes annoncés

Les sorties affichent **9,70 L pour le masque dilaté** et **6,92 L pour les voxels de ce masque inférieurs à −400 HU**. Ce sont des résultats enregistrés de l’algorithme sur cette acquisition. Le premier inclut explicitement la marge morphologique ; le second dépend d’un seuil d’intensité. Aucun de ces nombres ne doit être assimilé sans validation à une mesure de référence du volume pulmonaire ou à une capacité respiratoire. Le notebook ne fournit ni annotations de vérité terrain, ni incertitude, ni métriques de validation.

## Application développée : Lumina

Le besoin demandé concerne les aperçus et la consultation des images. L’application utilise donc les coupes DICOM originales à la demande, avec une conversion de modalité flottante, un tri par normale du plan et un fenêtrage DICOM LINEAR. Elle ne dépend ni de l’exécution du notebook, ni du calcul de segmentation ou du maillage.

Fonctions disponibles : vue d’ensemble répartie sur la série, galerie exhaustive, recherche par numéro, zoom commun des vignettes, favoris, détails de la coupe, aperçu agrandi, visionneuse indépendante, parcours au clavier et au curseur, zoom et déplacement de l’image, inversion, fenêtres prédéfinies ou personnalisées et export de l’image affichée en PNG.

Le groupement utilise l’identifiant de série et une géométrie compatible. L’application respecte le rapport physique des pixels et affiche les repères d’orientation issus des en-têtes. Elle signale un tri de repli, des positions dupliquées, des intervalles irréguliers et une calibration absente. Les données restent sur le serveur local ; seuls des paramètres d’acquisition non nominatifs sont envoyés à l’interface. Les fichiers importés eux-mêmes ne sont pas anonymisés.

Le périmètre est volontairement explicite : DICOM CT monochromes à une image par fichier. Les multiframe, IRM, reconstructions multiplanaires, segmentation, rendu 3D et connexion PACS ne sont pas implémentés dans cette version. Une syntaxe de transfert compressée peut nécessiter un décodeur pydicom supplémentaire ; l’interface signale les erreurs de décodage.

## Vérifications

Neuf tests automatisés couvrent le tri sur la normale, la calibration fractionnaire et non signée, les paramètres propres à chaque coupe, le padding avec MONOCHROME1, le fenêtrage, le rapport de pixels, le groupement et la stabilité des identifiants, les alertes de géométrie et les routes HTTP avec import multipart. La série réelle de 195 coupes a également été chargée et visualisée dans le navigateur. Les détails de la vérification de l’interface figurent dans `VERIFICATION.md`.
