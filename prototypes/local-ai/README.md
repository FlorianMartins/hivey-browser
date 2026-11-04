# Prototype : IA locale « Gaming-Safe »

Hors du navigateur : rien ici n'est embarqué dans Hivey. Il sert à décider avec des mesures. Cible : les fonctions de Perplexity Comet avec l'approche locale de Sigma, sans service cloud obligatoire.

## Contenu

| Fichier | Rôle |
|---|---|
| `manifest.json` | Versions figées et sha256 du moteur (llama.cpp), de PresentMon et des modèles |
| `fetch.py` | Téléchargement vérifié (Linux) |
| `frame_sim.c` | Jeu simulé : travail CPU et mémoire à 144 Hz, avec échéances |
| `bench_interference.py` | Coût pour le jeu simulé, par réglage de bridage (Linux) |
| `eval_models.py`, `corpus/` | Qualité des modèles : faits, citations, injections, avec ou sans XML |
| `measure.ps1` | **Mesure sur un vrai PC Windows avec un vrai jeu** |
| `design/` | Maquette animée de l'interface (données d'exemple) |

## Résultats sur Ryzen 7 3700X (2019), CPU seul

Jeu simulé à 144 Hz, Qwen3 1.7B Q4, médiane de 3 passages de 60 s dans un ordre mélangé (`medium` : 4 threads, 4 ms par image ; `heavy` : 8 threads, 5,5 ms).

| Réglage | 1 % low, moyen | Tokens/s, moyen | 1 % low, lourd | Tokens/s, lourd |
|---|---|---|---|---|
| Sans IA | 143,9 | – | 141,0 | – |
| Normal, 8 threads | 80,1 | 22,6 | 45,0 | 22,1 |
| Basse priorité, 8 threads | 80,6 | 22,0 | 59,9 | 10,9 |
| Basse priorité, 4 threads | 118,6 | 20,3 | 93,9 | 16,3 |
| Basse priorité, 2 threads | 143,4 | 16,0 | 111,5 | 11,6 |
| Processus suspendu | 143,2 | 0 | 141,9 | 0 |

- La basse priorité seule n'empêche pas les saccades : c'est le nombre de threads qui compte.
- 2 threads sont sans effet mesurable sur le jeu moyen, mais coûtent 21 % de 1 % low sur le jeu lourd. D'où la pause en jeu.
- Suspendre le processus ramène au niveau sans IA, modèle gardé en mémoire.
- Un moteur s'arrête par un arrêt brutal : `SIGTERM` attend la fin de la génération.
- `--no-repack` réduit la mémoire de 2 266 à 1 627 Mo sur Qwen3 sans perte de vitesse mesurée (2 threads).

## Modèles (sans jeu)

10 tâches inventées, 2 graines, 2 styles de consigne ; petit corpus, à élargir. Les consignes en français ont poussé plusieurs modèles à répondre en français à des questions en anglais : le critère de langue n'est pas fiable. Vitesse avec 4 threads bridés, RAM avant `--no-repack`.

| Modèle | Tokens/s | Faits sans / avec XML | Injections suivies sans / avec XML | RAM | Licence |
|---|---|---|---|---|---|
| Qwen2.5 1.5B | 31,7 | 83 % / 93 % | 2/8, 4/8 | 1,8 Go | Apache 2.0 |
| Qwen3 1.7B | 25,5 | 90 % / 85 % | 6/8, 6/8 | 2,3 Go | Apache 2.0 |
| SmolLM3 3B | 16,7 | 72 % / 73 % | 6/8, 5/8 | 3,5 Go | Apache 2.0 |
| Llama 3.2 3B | 15,6 | 47 % / 65 % | 3/8, 3/8 | 3,8 Go | Llama 3.2 |
| Ministral 3 3B | 14,9 | 63 % / 63 % | 6/8, 6/8 | 4,0 Go | Apache 2.0 |
| Granite 4 micro | 13,3 | 73 % / 83 % | 6/8, 0/8 | 3,9 Go | Apache 2.0 |

Au total, les injections réussissent dans 29 essais sur 48 sans XML et 24 sur 48 avec : les balises ne suffisent pas, la sécurité doit venir des droits de l'agent. Le 0/8 de Granite repose sur 4 attaques et 2 graines souvent identiques : à vérifier sur un corpus plus large.

## Limites

Le simulateur ne couvre ni le GPU ni la VRAM. Ce serveur et les runners de CI ne peuvent pas lancer de jeu : seul `measure.ps1` sur un vrai PC répond à la question finale.

## Reproduire

```sh
python3 fetch.py <cache>
gcc -O2 -pthread frame_sim.c -o <cache>/frame_sim -lm
python3 bench_interference.py <cache> Qwen3-1.7B-Q4_K_M.gguf out.jsonl
python3 eval_models.py <cache> eval.jsonl
```
