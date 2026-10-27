# Journal des modifications

Chaque version publiée de Hivey Browser, ce qui change pour vous. Les versions
suivent Chromium : `156.0.8078.4701` = Chromium 156.0.8078.47, révision Hivey 1.

## 156.0.8078.4704 — 27 octobre 2026

### Barre Hivey
- Nouvelle **barre Hivey** au bord de la fenêtre : les espaces de **Hivey
  Tools** (chat, chats web, agent, traduction, amélioration de texte, images,
  PDF, sécurité, Wisebase, benchmark, MCP) s'ouvrent directement dans le
  panneau latéral, plus **Hivey Cyber**, **Hivey Shield**, **Ressources** et
  **Hivey Studio**.
- À droite par défaut, **à gauche avec les onglets verticaux** ; clic droit
  pour la déplacer ou la masquer (elle revient par le clic droit sur la barre
  d'onglets ou dans Hivey Studio).
- La sidebar Hivey AI est **intégrée au navigateur** : ses onglets sont les
  boutons de la barre Hivey, qui ouvrent et referment le panneau sur
  l'onglet choisi, sans en-tête ni logo en double.
- Barre Hivey masquée : la sidebar (**Hivey Tools**) et Hivey Cyber
  reviennent en haut avec les extensions, et y repartent quand la barre
  revient.

### Onglets verticaux
- **Une seule surface** avec la barre de navigation : même couleur, plus de
  séparation ; la page a un coin arrondi en haut et un coin droit en bas.
- **À gauche ou à droite**, au choix (clic droit sur la barre d'onglets ou
  Hivey Studio).

### Thèmes
- Choisir un thème **remplace vraiment toutes les couleurs**, y compris
  celles que vous aviez changées à la main ; le thème actif est mis en
  évidence.
- Quatre nouveaux thèmes : **Minuit** (noir pur pour écrans OLED),
  **Océan**, **Forêt** et **Rose**.
- Les thèmes colorent aussi la page Nouvel onglet, les survols d'onglets,
  les séparateurs, les barres d'information, la recherche dans la page, les
  suggestions de la barre d'adresse, les boutons, les champs et les
  interrupteurs.
- **Material** : un clic sur sa carte ouvre le sélecteur de couleur, sa
  palette est générée à partir de la couleur choisie.
- L'**icône de la barre des tâches** (Windows) et du dock ou du menu (Linux)
  prend la couleur du thème.

### Barre d'adresse
- Le **logo Hivey**, centré, devant « Hivey Browser » sur les pages internes.
- **Pays du serveur** de chaque site (drapeau et code) ; un clic donne son
  adresse IP, le pays et la connexion (HTTP/2, TLS…), avec des liens WHOIS et
  détails IP. La base de données est livrée avec le navigateur : **aucune
  requête** n'est faite pour cela.

## 156.0.8078.4702 — 26 octobre 2026

### Téléchargement
- **Liens permanents** vers la dernière version, qui ne changent plus d'une
  version à l'autre :
  [Windows](https://github.com/FlorianMartins/hivey-browser/releases/latest/download/hivey-browser-windows-x64-installer.exe),
  [Linux](https://github.com/FlorianMartins/hivey-browser/releases/latest/download/hivey-browser-linux-x64.tar.xz).

### Hivey AI intégré
- La **sidebar Hivey AI** (version 2.201.298) est livrée avec le navigateur
  (son icône dans la barre d'outils) : votre clé API ou un modèle local,
  aucun serveur Hivey entre vous et le fournisseur.
- Ses **mises à jour arrivent automatiquement** : chaque nouvelle version
  validée de la sidebar est intégrée, testée et publiée dans le navigateur
  dans la foulée.
- **Pas une passoire** : elle ne lit une page que si vous l'ouvrez sur cet
  onglet. Une page piégée ne peut pas la piloter (injection de prompt).

### Outils de cybersécurité
- Nouvelle extension intégrée **Hivey Cyber** (icône bouclier-loupe, et clic
  droit sur une page, un lien ou un texte) :
  - WHOIS, géolocalisation IP, DNS et certificats ;
  - VirusTotal, urlscan.io, Shodan ;
  - SSL Labs, en-têtes de sécurité, Observatory, Wayback Machine ;
  - recherche dans Have I Been Pwned.

### Sécurité
- **USB, série, HID et Bluetooth bloqués** : les sites ne peuvent même plus
  les demander. Autorisable site par site.
- **Mode durci** en option (Hivey Studio > Confidentialité) : plus
  d'optimiseur JavaScript (JIT), la cible de la plupart des failles des
  navigateurs.

### Apparence
- **Thèmes Aura, Ambre nuit et Jour**, appliqués à tout le navigateur : barre
  d'onglets, barre d'outils, menus clic droit, panneaux, Paramètres et Hivey
  Studio. L'aperçu correspond exactement au résultat.
- **Une couleur pour chaque partie du navigateur**, avec une **pipette** qui
  prend une couleur n'importe où sur l'écran, même hors du navigateur.
- L'**icône de la fenêtre** (barre des tâches) prend la couleur du thème. Le
  logo est le même partout.
- **Onglets verticaux** de la couleur de la barre d'outils. Ils ne se
  déploient plus au survol par défaut (option dans Hivey Studio).
- Le **mode compact** réduit aussi la barre de navigation.

### Hivey Studio
- Bouton **Ressources** dans la barre d'outils : jauges en direct, onglets
  gourmands et limiteurs dans une fenêtre déroulante.
- Hivey Studio **se met à jour en direct** : une option changée ailleurs
  (clic droit sur les onglets, Paramètres) y apparaît aussitôt.

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
