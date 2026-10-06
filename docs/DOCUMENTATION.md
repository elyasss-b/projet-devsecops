# Projet DevSecOps : plateforme de delivery sécurisée

> Binôme : Chayma Kalmani et Elyas Boutahar

## 1. Objectif

Mettre en place une chaîne de livraison qui récupère le code depuis Git, vérifie sa qualité et sa sécurité, construit et analyse une image conteneurisée, la publie dans un registry et la déploie automatiquement sur Kubernetes. La livraison est bloquée dès qu'un contrôle de sécurité critique échoue, et chaque étape laisse une trace.

## 2. Application

Application web de prise de notes développée en Python avec Flask : création, consultation et suppression de notes via une API JSON, page HTML de consultation, endpoint `/health` utilisé par Kubernetes.

Mesures de sécurité intégrées au code : validation des entrées (titre obligatoire, 100 caractères maximum), échappement HTML automatique par Jinja (testé), en-têtes de sécurité HTTP (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy), configuration sensible lue depuis l'environnement et jamais écrite dans le code.

Limite assumée : les notes sont stockées en mémoire, chaque pod a ses propres données et elles sont perdues au redémarrage. Le projet porte sur la chaîne de livraison, pas sur la persistance.

## 3. Architecture

![Architecture](architecture.png)

| Composant | Choix | Justification |
|---|---|---|
| Gestion du code et CI/CD | GitHub, GitHub Actions | |
| Registry | GitHub Container Registry | intégré à GitHub, authentification par le jeton du pipeline |
| Cluster | K3s sur une VM Debian OVH | Kubernetes léger, adapté à une seule VM |
| Déploiement | runner GitHub auto-hébergé sur la VM | l'API Kubernetes (port 6443) n'est jamais exposée sur internet, la VM n'ouvre que les ports 22 et 80 |
| Exposition | Ingress Traefik (fourni par K3s) | |

[Compléter la colonne Justification avec vos propres mots]

## 4. Chaîne CI/CD

[Capture : vue d'ensemble d'un pipeline réussi dans l'onglet Actions]

| Étape | Outil | Ce qui est contrôlé |
|---|---|---|
| Lint | Ruff | erreurs et style du code Python |
| Tests | Pytest | comportement de l'application (10 tests, couverture mesurée) |
| Secrets | Gitleaks | secrets présents dans tout l'historique Git |
| SAST | Semgrep | failles dans le code (injection SQL, injection de commande, debug activé...) |
| Dépendances | Trivy fs | CVE connues dans les bibliothèques Python |
| IaC | Trivy config | mauvaises configurations du Dockerfile et des manifests Kubernetes |
| Image | Trivy image | CVE du système et des paquets de l'image construite, génération du SBOM |
| Cluster | Trivy k8s | posture de sécurité du cluster après déploiement |

## 5. Security gate

Les scanners ne bloquent pas eux-mêmes : ils produisent un rapport JSON. Le script `scripts/security_gate.py` lit tous les rapports, classe chaque problème par sévérité et applique la politique :

| Sévérité | Décision |
|---|---|
| CRITICAL | pipeline bloqué |
| HIGH | pipeline bloqué |
| MEDIUM | avertissement |
| LOW | information |

Correspondances : tout secret détecté par Gitleaks est classé CRITICAL. Pour Semgrep, ERROR devient HIGH, WARNING devient MEDIUM, INFO devient LOW.

Le gate est appliqué deux fois : après les scans du code (avant toute construction d'image) et après le scan de l'image (avant le push). Si un rapport est absent ou illisible, le gate échoue : on ne livre pas ce qu'on n'a pas pu contrôler.

Les exceptions éventuelles sont déclarées dans `.trivyignore`, une ligne par CVE, avec justification et date de revue.

[Capture : résumé du security gate dans l'onglet Summary du pipeline]

## 6. Durcissement

### Image Docker

| Mesure | Effet |
|---|---|
| build multi-stage | les outils de build ne sont pas dans l'image finale |
| image de base `python:3.12-slim` | moins de paquets, donc moins de CVE |
| suppression de pip | surface d'attaque réduite |
| utilisateur non-root (UID 10001) | un attaquant n'obtient pas root dans le conteneur |
| fichiers de l'application appartenant à root | le code ne peut pas être modifié à l'exécution |
| copie explicite des fichiers nécessaires | ni tests, ni `.git`, ni secrets dans l'image |
| HEALTHCHECK | état de l'application vérifiable |

[Tableau à compléter : nombre de CVE de l'image avant / après durcissement]

### Kubernetes

| Mesure | Effet |
|---|---|
| namespace en Pod Security `restricted` | Kubernetes refuse tout pod non conforme |
| `runAsNonRoot`, `allowPrivilegeEscalation: false`, capabilities supprimées | pas d'élévation de privilèges |
| `readOnlyRootFilesystem` | système de fichiers en lecture seule (sauf `/tmp`) |
| limites CPU et mémoire | un pod ne peut pas saturer le nœud |
| NetworkPolicy | seul Traefik peut joindre les pods |
| `automountServiceAccountToken: false` | pas de jeton Kubernetes dans les pods |
| Secret Kubernetes créé par le pipeline | `SECRET_KEY` stockée dans les secrets GitHub, jamais dans Git |

## 7. Traçabilité

Chaque image est taguée avec le SHA du commit et porte les labels OCI `source` et `revision`. La version déployée est visible sur `/health`. Chaque exécution du pipeline conserve en artefacts les rapports de tests, les rapports JSON de chaque scanner, le SBOM et le résumé du scan du cluster. L'environnement GitHub `production` garde l'historique des déploiements.

## 8. Démonstration

[Décrire le commit utilisé pour la démo et coller les captures de chaque étape : commit, pipeline, scans, gate, image dans GHCR, déploiement, application dans le navigateur avec la nouvelle version]

## 9. Challenge final

La branche `challenge` contient cinq problèmes volontaires.

| Problème introduit | Fichier | Détecté par | Sévérité | Décision |
|---|---|---|---|---|
| clé AWS fictive | `settings.py` | Gitleaks | | |
| Flask 2.2.2 et Werkzeug 2.2.2 | `requirements.txt` | Trivy fs | | |
| conteneur root, ADD, port 22 exposé | `Dockerfile` | Trivy config | | |
| conteneur privilégié, root, montage de `/` de l'hôte | `k8s/deployment.yaml` | Trivy config | | |
| injection SQL, debug Flask activé | `app.py` | Semgrep | | |

[Remplir les colonnes Sévérité et Décision à partir du résumé du security gate de votre pipeline, et ajouter les captures]

Les quatre exigences sont démontrées : la plateforme détecte les problèmes, produit des rapports, bloque ceux définis comme critiques, et autorise la livraison quand les contrôles passent (pipeline vert sur `main`).

## 10. Limites et améliorations possibles

[À compléter. Pistes : signature des images avec Cosign et vérification à l'admission avec Kyverno, compte de service Kubernetes à privilèges limités pour le runner, base de données persistante, environnement de staging avant la production]
