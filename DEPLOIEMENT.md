# FORGE — Questionnaire en ligne + CRM privé

Mettre le questionnaire sur un site et recevoir les données dans une interface
privée réservée à l'équipe.

## Ce que contient le dossier

| Fichier | Rôle |
|---|---|
| `forge-quiz-v8.html` | Le questionnaire public (envoie ses données à `/api/submit`) |
| `app.py` | Le serveur : sert le questionnaire, enregistre les soumissions, interface équipe |
| `requirements.txt` | Dépendances Python (Flask + gunicorn) |
| `Procfile` | Commande de démarrage pour l'hébergeur |
| `forge_questionnaire.py` | Le moteur en Python (optionnel, pour calculs côté serveur / analyses) |

Quand c'est lancé :
- **`/`** → le questionnaire (lien public à mettre sur le site)
- **`/admin`** → l'espace équipe (connexion par identifiant + mot de passe)
- **`/admin/export.csv`** → export de toutes les soumissions (Excel-compatible)

---

## 1. Tester en local (sur ton ordinateur)

```bash
pip install -r requirements.txt

# Réglages (obligatoires en vrai, un défaut existe pour tester) :
export FORGE_ADMIN_USER="forge"
export FORGE_ADMIN_PASSWORD="choisis-un-mot-de-passe-solide"
export FORGE_SECRET_KEY="une-longue-chaine-aleatoire-32-caracteres-min"

python app.py
```

Ouvre http://127.0.0.1:8000 (questionnaire) et http://127.0.0.1:8000/admin (équipe).

Sur Windows (PowerShell), remplace `export X="y"` par `$env:X="y"`.

---

## 2. Mettre en ligne — option simple : Render.com (gratuit pour démarrer)

1. Crée un compte sur https://render.com
2. Mets ces fichiers dans un dépôt GitHub (ou glisse-les — Render accepte un repo).
3. Render → **New → Web Service** → connecte le dépôt.
4. Réglages :
   - **Build command** : `pip install -r requirements.txt`
   - **Start command** : `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Region** : Frankfurt (UE, pour le RGPD).
5. **Environment → Add Environment Variable** (très important) :
   | Clé | Valeur |
   |---|---|
   | `FORGE_ADMIN_USER` | l'identifiant de connexion de l'équipe |
   | `FORGE_ADMIN_PASSWORD` | un mot de passe solide |
   | `FORGE_SECRET_KEY` | une longue chaîne aléatoire |
   | `FORGE_HTTPS` | `1` |
   | `FORGE_DB_PATH` | `/var/data/forge_crm.db` (voir ci-dessous) |
6. **Disk** : ajoute un disque persistant (Render → Disks), point de montage
   `/var/data`, 1 Go. **Indispensable** : sinon la base SQLite est effacée à
   chaque redéploiement.
7. Déploie. Render te donne une URL `https://forge-xxxx.onrender.com`.
   - Public : `https://forge-xxxx.onrender.com/`
   - Équipe : `https://forge-xxxx.onrender.com/admin`

**Railway.app** et **Fly.io** marchent pareil (mêmes commandes, même besoin d'un
volume persistant pour la base).

---

## 3. Mettre le questionnaire sur TON site existant

Deux façons :

**A. Lien / bouton** (le plus simple) : un bouton « Faire le bilan » qui pointe
vers l'URL publique du service (`https://forge-xxxx.onrender.com/`).

**B. Intégration (iframe)** dans une page de ton site :
```html
<iframe src="https://forge-xxxx.onrender.com/"
        style="width:100%;height:900px;border:0" title="Bilan Forge"></iframe>
```

Dans les deux cas, les données partent automatiquement vers le CRM : rien à faire
de plus. (Tu peux aussi héberger tout le site sur ce même service si tu veux.)

---

## 4. Brancher l'email / la newsletter (optionnel)

Le serveur enregistre déjà prénom + email + consentement newsletter. Pour pousser
l'email vers **Brevo / Mailchimp**, ajoute un appel dans `api_submit()` (dans
`app.py`, juste après l'`INSERT`). Exemple Brevo :

```python
import urllib.request, json as _json
if row["newsletter"] and row["email"]:
    req = urllib.request.Request(
        "https://api.brevo.com/v3/contacts",
        data=_json.dumps({"email": row["email"],
                          "attributes": {"PRENOM": row["prenom"]},
                          "listIds": [TON_ID_DE_LISTE], "updateEnabled": True}).encode(),
        headers={"api-key": "TA_CLE_BREVO", "Content-Type": "application/json"})
    try: urllib.request.urlopen(req, timeout=5)
    except Exception: pass
```

---

## 5. RGPD — à respecter (données de santé déclaratives)

- **Héberger en UE** (région Frankfurt/Paris) et **en HTTPS** (`FORGE_HTTPS=1`).
- La case **« publication scientifique »** est distincte de la newsletter :
  le CRM est rempli dans tous les cas, mais les **scores** ne doivent être
  exploités de façon publiable que si `consent_recherche = 1` (colonne présente
  dans l'export et le tableau).
- **Droit à l'effacement** : bouton « Supprimer » sur chaque fiche de l'admin.
- Ajoute une courte **mention RGPD** sous le formulaire de contact (finalité,
  responsable, droit d'accès/suppression, durée de conservation).
- Idéalement, fais valider le dispositif par ton DPO / un juriste avant diffusion
  large, surtout pour la partie « données de santé ».

---

## 6. Sécurité — bonnes pratiques

- Mets un **mot de passe long** et une **`FORGE_SECRET_KEY`** aléatoire (jamais
  les valeurs par défaut).
- Pour plusieurs personnes dans l'équipe avec des comptes séparés, on peut
  passer à une vraie table `users` (mots de passe hachés) — dis-le-moi et je
  l'ajoute.
- Sauvegarde régulière du fichier `forge_crm.db` (ou de l'export CSV).

---

## Rappel honnête

La pondération des scores est calibrée sur la littérature mais reste une
**heuristique à valider** sur tes vraies données. Les réponses brutes sont
stockées (`answers_json`) précisément pour permettre cette calibration plus tard.
Et certaines **références citées dans les conseils sont à revérifier** avant toute
communication publique.
