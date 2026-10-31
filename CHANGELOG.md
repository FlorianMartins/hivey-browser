# Journal des modifications

Chaque version publiée de Hivey Browser, ce qui change pour vous. Les versions
suivent Chromium : `156.0.8078.4701` = Chromium 156.0.8078.47, révision Hivey 1.

## 156.0.8078.4716 — 31 octobre 2026

### Installation (Windows)
- L'assistant est **sombre de bout en bout**, aux couleurs du navigateur :
  plus de zones blanches, licence lisible (texte clair), liste des
  composants, dossier, installation et fin d'installation sombres.

### Barre Hivey
- **Icônes modernes nettes** : plus d'effet de flou ; en « couleur du
  thème », exactement la couleur des icônes du thème.
- Les onglets de la barre passent **en icônes modernes colorées** par
  défaut (modifiable dans Paramètres > Disposition).
- **Tor** a une nouvelle icône (un oignon).

### Barre de navigation
- **Bouton Tor** à droite, comme Brave : une fenêtre privée avec Tor en un
  clic (masquable ou déplaçable dans Paramètres > Disposition > Barre
  d'outils).
- **Recherche d'onglets** dans la barre de navigation (la flèche à droite,
  comme « Lister tous les onglets » de Firefox) au lieu de la bande
  d'onglets ; on peut la remettre dans la bande (Paramètres > Onglets).
- Plus de bandeau « indicateur de ligne de commande non pris en charge
  (--translate-security-origin) » au démarrage.

## 156.0.8078.4715 — 30 octobre 2026

### Confidentialité
- **Ponts Tor** : là où le réseau Tor est bloqué (certains réseaux
  d'entreprise, d'école, certains pays), la fenêtre Tor passe quand même.
  En mode automatique, elle essaie la connexion directe, puis Snowflake,
  puis meek ; vous pouvez aussi choisir le pont (Paramètres >
  Confidentialité > Ponts Tor).

### Barre d'adresse
- Une adresse tapée comme telle (« kamaraderie.fr », sans « www. ») ouvre
  toujours le site ; la recherche Google n'apparaît qu'en suggestion
  en-dessous, même si vous l'aviez déjà recherchée.

## 156.0.8078.4714 — 30 octobre 2026

### Confidentialité
- **Fenêtre privée avec Tor**, comme Brave : gratuit et sans compte. Votre
  trafic passe par le réseau Tor (les sites ne voient pas votre adresse IP,
  les noms de domaine sont résolus par Tor) et rien n'est gardé à la
  fermeture. Bouton dans la barre Hivey, dans Paramètres > Confidentialité,
  et « Ouvrir le lien dans une fenêtre Tor » au clic droit. Tor démarre à la
  demande et s'arrête avec la dernière fenêtre Tor.

## 156.0.8078.4713 — 30 octobre 2026

### Confidentialité
- **Copier le lien sans pistage**, comme Firefox : clic droit sur un lien
  (ou sur la page : « Copier l'adresse de la page sans pistage ») ; les
  balises qui vous suivent (utm_*, fbclid, gclid, msclkid, igshid, si de
  YouTube…) sont retirées avant la copie.
- **VPN au choix** : Proton VPN (gratuit avec un compte Proton, Suisse,
  sans journaux, open source) se propose pendant l'installation, ou dans
  Paramètres > Confidentialité > VPN. Rien n'est installé si vous ne le
  choisissez pas.

### Profils
- **Nouvelles images de profil Hivey**, en trois styles : des mascottes
  rigolotes (abeille, robot, fantôme, renard, astronaute…), des emblèmes
  sérieux et des motifs sobres.

### Barre d'adresse
- Le bouton Traduire de Hivey disparaît (il faisait doublon avec celui de
  Chromium) ; « Traduire cette page » dans la bulle du drapeau et le clic
  droit traduisent toujours la page directement.

## 156.0.8078.4712 — 30 octobre 2026

### Barre Hivey
- **Icônes modernes « néon »** : une nouvelle image pour chaque onglet et
  outil, le pictogramme plein dans un dégradé de deux teintes, avec un halo
  lumineux ; bien distinctes des icônes classiques.
- Clic droit sur **Favoris** : « Importer les favoris d'un autre
  navigateur… ».

### Barre d'adresse
- Le bouton **Traduire** traduit la page directement (Google Traduction),
  sans ouvrir la sidebar. Rien n'est envoyé à Google tant que vous ne
  cliquez pas.
- Bouton **Incrustation vidéo** (image dans l'image) quand une vidéo joue ;
  et la vidéo vous suit automatiquement dans une petite fenêtre quand vous
  changez d'onglet (réglable dans Paramètres > Onglets).
- La bulle du serveur affiche l'**IPv4 et l'IPv6** du site, et le
  **drapeau** s'affiche correctement sur la ligne Pays.

### Personnalisation
- **Barre d'outils personnalisable** (Paramètres > Disposition) : déplacez
  les boutons et la barre d'adresse où vous voulez, masquez-en, ajoutez-en
  (impression, téléchargements, historique…).
- **Importer** a sa propre section dans les Paramètres : favoris de Chrome,
  Edge, Brave, Vivaldi, Opera, Chromium (aussi en Flatpak et Snap sous
  Linux) et Firefox.

### Confidentialité
- **uBlock Origin complet** intégré, en plus d'uBlock Origin Lite : bloque
  les pubs YouTube et Twitch (Twitch insère certaines pubs dans la vidéo
  elle-même : aucun bloqueur n'en vient à bout à 100 %).

### Installation (Windows)
- L'assistant prend les couleurs du navigateur et **coche toutes les
  options** par défaut (modules, mode confidentialité, raccourcis).

## 156.0.8078.4711 — 29 octobre 2026

### Barre Hivey
- **Icônes modernes plus sobres** : plus de cadre, le pictogramme seul, à la
  taille des icônes classiques, rempli d'un dégradé (couleurs de l'outil ou du
  thème), comme une favicon.

### Barre d'adresse
- Nouveaux boutons à côté du drapeau : **Traduire** la page (Hivey Tools) et
  **Ouvrir comme application** (le site dans sa propre fenêtre, avec son
  icône dans la barre des tâches).
- Même espace entre le drapeau, les boutons et les icônes de la page
  (favoris, cookies).

### Performances
- **Mode Gaming** (bouton Performances de la barre Hivey) : bride le
  navigateur pendant que vous jouez (RAM, processeur par onglet, réseau) et
  met les onglets inactifs en veille plus tôt ; vidéos et musique continuent
  en fond. Vos réglages reviennent quand vous le coupez.

### Installation (Windows)
- **Un vrai assistant d'installation** : choix du dossier d'installation,
  des modules intégrés (bloqueur de publicités, Hivey AI, Hivey Cyber),
  d'un **mode confidentialité** (JavaScript sans JIT, cookies tiers bloqués,
  WebRTC sans fuite d'IP, pas de suggestions de recherche, Do Not Track) et
  des raccourcis (bureau, barre des tâches), en français ou en anglais.
- Les mises à jour automatiques restent silencieuses et gardent le dossier
  choisi.

### Apparence
- Les **séparateurs entre les onglets** prennent la couleur du thème.
- Le **logo** de l'application a un vrai dégradé de couleur (barre des
  tâches, bureau, menu).

## 156.0.8078.4710 — 29 octobre 2026

### Barre Hivey
- **Icônes modernes repensées** : des tuiles en dégradé plus grandes, avec
  le pictogramme **découpé en transparence** ; multicolores ou couleur du
  thème.
- **Hivey Cyber quitte la barre Hivey** : il est dans la bulle du drapeau de
  la barre d'adresse (« Analyser avec Hivey Cyber »).
- Le **survol** a la même forme arrondie que le bouton ouvert.
- La barre **garde sa largeur** quand un onglet de la sidebar s'ouvre (plus
  de marge du côté de la barre).
- La **barre de navigation passe au-dessus** de la barre Hivey : Retour,
  Avancer et Actualiser restent à leur place, Retour au-dessus de la barre,
  sans vide à gauche.

### Barre d'adresse
- Le bouton du serveur affiche le **vrai drapeau** du pays (image, aussi sous
  Windows), sans texte ni barre de séparation.
- Un site servi par un **réseau de diffusion** (Cloudflare, Fastly…) affiche
  un globe : son pays n'était pas le vrai (souvent « CA »), le serveur du site
  étant masqué derrière ce réseau ; la bulle le dit.
- La bulle est plus large et commence par l'**adresse IP** (bouton
  « Copier l'IP ») ; nouveaux liens **Shodan** et **SSL Labs**.

### Application
- Le **logo Hivey est plus grand** dans la barre des tâches, sur le bureau
  et dans les menus.

## 156.0.8078.4709 — 28 octobre 2026

### Barre Hivey
- **Chaque bouton peut aller en haut, au centre ou en bas** de la barre :
  glissez-le où vous voulez (Paramètres compris).
- **Icônes modernes plus lisibles** : une tuile translucide et le
  pictogramme en couleur pleine. Elles existent en **multicolore** ou en
  **couleur du thème**, pour les onglets de la sidebar IA comme pour les
  boutons du bas (clic droit > Icônes / Boutons du bas).
- Par défaut, **Hivey Cyber est en haut**, au niveau de la barre de
  navigation, et le bas suit l'ordre **Performances, Favoris, Historique,
  Paramètres**.
- Les icônes sont **bien centrées**.
- **L'historique s'ouvre dans le panneau latéral**, comme les favoris ; un
  clic sur une entrée l'ouvre dans l'onglet courant.
- Un **second clic referme** ce que le bouton a ouvert (historique,
  favoris, Performances, Hivey Cyber).

### Panneau latéral
- Il s'ouvre **toujours du côté de la barre Hivey** et **glisse depuis
  elle** sans passer par-dessus ; son contenu apparaît en fondu.
- Plus de **bordure** entre la barre et le panneau.
- Les **coins arrondis** de la page sont remplis de la couleur de la barre
  (on ne voit plus le site derrière).

### Hivey Tools
- **Chats web** : ils s'affichent dès la première ouverture, même juste
  après le démarrage (avant, il fallait attendre une erreur et changer de
  fournisseur).

### Favoris
- **Importer des favoris** (Paramètres > Disposition) depuis **Chrome, Edge,
  Brave, Vivaldi, Opera ou Chromium** installés sur l'ordinateur ; Firefox et
  les fichiers HTML passent par la page d'import du navigateur.

## 156.0.8078.4708 — 28 octobre 2026

### Barre Hivey
- **Nouvelles icônes modernes**, dessinées pour Hivey : tuiles en dégradé
  de la couleur de chaque onglet, reflet léger, pictogramme blanc (fini les
  emojis). Elles s'appliquent par défaut aux **onglets de la sidebar IA**.
- Les **boutons du bas** (Hivey Cyber, Performances, Historique, Favoris,
  Paramètres) ont **leur propre style** : couleur du thème par défaut, ou
  modernes (clic droit > Boutons du bas, ou Paramètres > Disposition).
- **Retour, Avancer, Actualiser** reviennent dans la barre de navigation,
  avec leurs icônes habituelles.

### Navigateur
- Le bouton **Rechercher dans les onglets** (et les autres boutons plats de
  la bande d'onglets) prend la **couleur du thème** au lieu du gris.
- Le **premier démarrage après l'installation** ouvre directement les
  **Paramètres**.
- Un **nouvel onglet** ouvre la page d'accueil de votre **moteur de
  recherche** (Google par défaut) ; une adresse de votre choix reste
  possible dans Paramètres > Disposition.
- Les profils restés sur **DuckDuckGo** passent sur **Google**, le moteur
  par défaut (une seule fois ; le choix reste dans Paramètres > Disposition).

## 156.0.8078.4707 — 28 octobre 2026

### Barre Hivey, entièrement personnalisable depuis la barre
- **Glissez un bouton** pour le déplacer (une ligne montre où il arrive).
- **Clic droit** : masquer ce bouton, **réafficher les boutons masqués**,
  style des **icônes**, côté gauche/droite, masquer la barre.
- **Icônes modernes** (images en couleur, style emoji) ou **classiques**
  (multicolores ou couleur du thème) ; en classique, les couleurs restent
  réservées aux onglets de la sidebar IA.
- **Retour, Avancer, Actualiser** passent en haut de la barre Hivey : la
  barre d'adresse commence au bord.
- Le bouton **Paramètres referme** l'onglet Paramètres s'il est ouvert.
- La zone du site a un **coin arrondi** du côté de la barre Hivey.

### Barre d'adresse
- Le **drapeau du serveur** est tout à droite, comme dans Firefox ; sa
  bulle propose **Analyser avec Hivey Cyber** et **Traduire cette page**.
- **Google** devient le moteur de recherche par défaut ; le choix du moteur
  est dans Paramètres > Disposition.

### Fenêtre
- Le **menu du clic droit sur la barre de titre** (Windows) prend les
  couleurs du thème et contient « Afficher la barre Hivey ».
- **Icône de l'application** : le logo Hivey (aux couleurs du thème)
  remplace enfin l'ancien dans la barre des tâches, sur le bureau et dans le
  menu Démarrer ; sous Linux, la fenêtre est reconnue comme « Hivey
  Browser » et son icône s'affiche dans le dock.

### Sidebar sans la barre Hivey
- Barre Hivey masquée, la sidebar redevient l'**extension complète** (son
  menu d'onglets, son côté gauche/droite) et son logo n'a plus de **fond
  blanc**.

## 156.0.8078.4706 — 27 octobre 2026

### Barre Hivey personnalisable
- **Paramètres > Disposition > Barre Hivey** : changez l'**ordre** des
  boutons (flèches ou glisser-déposer), **masquez** ceux que vous n'utilisez
  pas (aussi par clic droit sur un bouton : « Masquer ce bouton ») et
  **ajoutez vos propres sites** (WhatsApp, Notion, Spotify…) : ils s'ouvrent
  dans le panneau latéral, connectés comme dans un onglet ; un second clic
  les referme.
- **Icônes** : couleur du thème ou **multicolore**, chaque bouton avec une
  couleur qui a du sens (vert pour la sécurité, rouge pour le PDF, ambre pour
  la traduction…), adaptée aux thèmes clairs et sombres.
- **MCP** passe entre Agent et Traduction.
- Clic droit sur la barre : « Personnaliser la barre Hivey… ».

### Correctifs
- **Les chats web fonctionnent aussi sur les profils existants** (l'accès
  aux sites des chats n'était donné qu'aux nouvelles installations).
- Plus de **bordure claire sous la barre de navigation** : la barre et la
  page forment une seule surface.

### Apparence
- Nouvelle couleur **« Onglets verticaux »** dans Paramètres > Apparence :
  le fond des onglets verticaux (et du bouton « + ») n'est plus gris fixe.
- **Nouveau logo** : celui de la sidebar Hivey AI (quatre barres, violet vers
  indigo), pour la fenêtre, la barre des tâches, l'installateur, la barre
  d'adresse et les Paramètres.

## 156.0.8078.4705 — 27 octobre 2026

### Barre Hivey
- Les onglets de la sidebar s'affichent **dès l'ouverture** de la fenêtre.
- **Nouvelles icônes** plus modernes (style duotone), dans la **couleur du
  thème en plus clair** (violet clair avec Aura).
- Les onglets de la sidebar sont **centrés verticalement** ; en bas :
  **Hivey Cyber, Performances, Historique, Favoris et Paramètres**.
- La **molette** sur la barre passe à l'onglet suivant ou précédent quand le
  panneau est ouvert.
- Hivey Shield (uBlock Origin Lite) n'est plus dans la barre : il reste dans
  la barre d'outils, avec son compteur.
- Ouverture et fermeture du panneau **plus vives et plus douces**.

### Hivey Tools
- **Les chats web fonctionnent** (Gemini, Claude, ChatGPT, Copilot, Mistral,
  DeepSeek…) : la sidebar a accès à ces sites, et seulement à eux, en plus
  des API des fournisseurs.

### Paramètres
- **Hivey Studio devient « Paramètres »** (menu ⋮ : « Paramètres Hivey »),
  avec une icône d'engrenage dans la barre Hivey.

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
