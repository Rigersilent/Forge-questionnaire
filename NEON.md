# Brancher une base Neon (Postgres gratuit) — pour ne plus perdre les données

Avec Neon, vos données **ne sont plus effacées** quand vous mettez le site à jour.
C'est gratuit, hébergé en Europe, et le code est déjà prêt : il suffit d'ajouter
une variable `DATABASE_URL` sur Render.

## Étapes (≈ 15 min)

### 1. Créer la base Neon
1. Allez sur **https://neon.tech** → **Sign up** (gratuit, connexion possible avec GitHub).
2. **Create a project**.
   - Name : `forge`
   - **Region : Europe (Frankfurt)** — important pour le RGPD.
   - Postgres version : laissez par défaut.
3. Une fois le projet créé, Neon affiche une **Connection string** (bouton
   « Connect » / « Connection Details »). Elle ressemble à :
   ```
   postgresql://forge_owner:XXXXXXXX@ep-cool-name-123456.eu-central-1.aws.neon.tech/forge?sslmode=require
   ```
   **Copiez-la en entier** (choisissez l'affichage « psql » ou « URI », pas « pooled » si le choix est proposé — les deux marchent, l'URI simple suffit).

### 2. Donner cette adresse à Render
1. Sur **Render** → votre service → menu **Environment**.
2. **Add Environment Variable** :
   - **Key** : `DATABASE_URL`
   - **Value** : collez la connection string copiée à l'étape 1.
3. **Save Changes**.
4. (Si vous aviez encore la variable `FORGE_DB_PATH`, supprimez-la — elle ne sert plus.)

### 3. Redéployer
- Render → **Manual Deploy → Clear build cache & deploy**.

C'est tout. Au démarrage, le code détecte `DATABASE_URL` et crée automatiquement
la table dans Neon. Les prochaines soumissions sont stockées **durablement**.

## Comment vérifier que ça marche
- Render → onglet **Logs** : vous devez voir la ligne
  **`[FORGE] Base : PostgreSQL (DATABASE_URL détecté)`**.
  (Si vous voyez « SQLite », c'est que la variable n'est pas prise en compte.)
- Faites un bilan test sur le site, puis allez sur `/admin` : il doit apparaître.
- Refaites un **Manual Deploy** : cette fois, le bilan test **doit toujours être là**.

## Bon à savoir
- Les données déjà présentes en SQLite **ne sont pas transférées** automatiquement
  (SQLite était de toute façon effacé à chaque déploiement). On repart donc propre
  avec Neon — à faire **avant** d'avoir de vrais clients, c'est le bon moment.
- Offre gratuite Neon : largement suffisante pour une bêta (plusieurs milliers de
  soumissions). Pas de carte bancaire.
- Sauvegarde : vous pouvez toujours exporter l'Excel / le CSV depuis `/admin`.
