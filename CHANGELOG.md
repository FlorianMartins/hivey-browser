# Journal des modifications

Chaque version publiée de Hivey Browser, ce qui change pour vous. Les versions
suivent Chromium : `156.0.8078.4701` = Chromium 156.0.8078.47, révision Hivey 1.

## 156.0.8078.4701 — 26 octobre 2026

Première version publique, pour **Windows** (installeur) et **Linux** (archive
portable).

### Sécurité et mises à jour
- Basé sur **Chromium 156** (ungoogled-chromium) : les derniers correctifs de
  sécurité.
- **Mises à jour automatiques** : le navigateur vérifie les nouvelles versions
  10 minutes après son lancement puis deux fois par jour, refuse tout ce qui
  n'est pas signé par Hivey, et s'installe en arrière-plan sous Windows
  (« Relancer pour mettre à jour »). Sous Linux, la nouvelle version est
  signalée dans Hivey Studio. Désactivable dans *Hivey Studio > À propos*.
- **Aucune requête au démarrage** : vérifié à chaque version sur Windows et
  Linux (seule la sonde du DNS chiffré Quad9, et sous Windows la détection
  automatique de proxy du système, sur le réseau local).

### Confidentialité
- **Hivey Shield** (uBlock Origin Lite intégré) : bloque publicités, traqueurs,
  bannières cookies, paramètres de suivi dans les liens (`fbclid`, `utm_…`) et
  sites malveillants ; l'icône dans la barre d'outils compte ce qui est bloqué.
- Les autres sites ne reçoivent plus que **l'origine** de la page d'où vous
  venez, jamais l'adresse complète.
- **Anti-empreinte renforcé** : bruit dans l'audio, nombre de processeurs
  plafonné, **polices installées invisibles** des sites, en plus du bruit
  Canvas/texte et du GPU masqué.
- Pas de Topics, d'Attribution Reporting ni de *fenced frames* (publicité
  ciblée de Google).

### Personnalisation : Hivey Studio
- Nouvelle page **Hivey Studio** (menu ⋮ > *Hivey Studio*, ou
  `chrome://hivey`), ouverte au premier lancement, en français et en anglais.
- **N'importe quelle couleur** pour tout le navigateur, préréglages (Ambre
  Hivey, Aura, Violet, Océan…), style de palette, clair/sombre, niveaux de gris.
- **Onglets verticaux**, **mode compact**, panneau latéral à gauche ou à
  droite, boutons de la barre d'outils, **page Nouvel onglet au choix**.
- Comportement des onglets : molette sur la barre d'onglets, Ctrl+Tab dans
  l'ordre d'utilisation, garder la fenêtre ouverte après le dernier onglet,
  pop-ups en onglets, et d'autres options auparavant cachées.

### Ressources, comme un navigateur gaming
- **Jauges en direct** (processeur, mémoire, réseau) et **onglets gourmands**,
  avec *Afficher* et *Fermer*.
- **Limiteur de RAM**, **limiteur de processeur** par onglet (Windows) et
  **limiteur de réseau** pour tout le navigateur, appliqués sans redémarrer.
