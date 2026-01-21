# SubManager - Gestionnaire d'Abonnements SaaS

Application web complète pour analyser vos relevés bancaires et détecter automatiquement vos abonnements récurrents.

## 🚀 Fonctionnalités

- **Upload de relevés bancaires** : Support CSV et PDF
- **Détection automatique** : Algorithme intelligent pour identifier les abonnements récurrents
- **Dashboard complet** : Statistiques en temps réel (total mensuel, annuel, nombre d'abonnements)
- **Filtrage par catégorie** : Streaming, Logiciels, Fitness, Transport, etc.
- **Gestion d'abonnements** : Marquer pour annulation, voir les détails
- **Interface moderne** : Design dark mode, animations fluides, responsive

## 📋 Prérequis

- Node.js 14+ et npm
- Navigateur moderne (Chrome, Firefox, Edge, Safari)

## 🛠️ Installation

### 1. Cloner le projet

```bash
git clone <repo-url>
cd subscription-manager-saas
```

### 2. Installer les dépendances

```bash
npm install
```

### 3. Démarrer le serveur

```bash
npm start
```

Le serveur démarre sur `http://localhost:3000`

### Mode développement (avec auto-reload)

```bash
npm run dev
```

## 📁 Structure du Projet

```
/
├── backend/
│   ├── server.js               # Serveur Express principal
│   ├── routes/
│   │   ├── upload.js           # Route d'upload de fichiers
│   │   └── subscriptions.js    # Routes gestion abonnements
│   ├── services/
│   │   ├── parser.js           # Parser CSV/PDF
│   │   └── analyzer.js         # Détection abonnements
│   └── package.json
├── frontend/
│   ├── index.html              # Page principale
│   ├── css/
│   │   └── style.css           # Styles
│   ├── js/
│   │   ├── app.js              # Logique principale
│   │   └── upload.js           # Gestion upload
│   └── assets/
├── example-data.csv            # Fichier CSV d'exemple
├── README.md
└── package.json
```

## 🎯 Utilisation

### 1. Préparer votre relevé bancaire

Formats supportés :
- **CSV** : Colonnes `date`, `description`, `montant`
- **PDF** : Relevés bancaires standard

### 2. Upload du fichier

1. Accédez à l'onglet **Analyser**
2. Sélectionnez la période d'analyse (1, 2 ou 3 mois)
3. Glissez-déposez votre fichier ou cliquez pour sélectionner
4. Attendez l'analyse (quelques secondes)

### 3. Consulter les résultats

- **Dashboard** : Vue d'ensemble avec statistiques
- **Filtres** : Par catégorie (Streaming, Software, etc.)
- **Actions** : Voir détails, marquer pour annulation

## 📊 Format CSV Attendu

Exemple de fichier CSV compatible :

```csv
date,description,montant
01/12/2023,NETFLIX ABONNEMENT,-15.99
05/12/2023,SPOTIFY PREMIUM,-9.99
15/12/2023,SALLE DE SPORT BASIC FIT,-29.99
01/01/2024,NETFLIX ABONNEMENT,-15.99
05/01/2024,SPOTIFY PREMIUM,-9.99
```

**Colonnes acceptées** :
- Date : `date`, `date_operation`, `transaction_date`
- Description : `description`, `libelle`, `beneficiaire`
- Montant : `montant`, `amount`, `debit`

## 🔧 API Endpoints

### POST /api/upload
Upload et analyse d'un relevé bancaire

**Body** : FormData avec `file` et `months`

**Response** :
```json
{
  "success": true,
  "subscriptions": [...],
  "statistics": {...},
  "transactionCount": 45
}
```

### GET /api/subscriptions
Récupère tous les abonnements détectés

**Response** :
```json
{
  "success": true,
  "data": {
    "subscriptions": [...],
    "statistics": {...}
  }
}
```

### POST /api/subscriptions/:id/cancel
Marque un abonnement pour annulation

**Response** :
```json
{
  "success": true,
  "message": "Abonnement marqué pour annulation"
}
```

## 🧠 Algorithme de Détection

L'algorithme détecte les abonnements en analysant :

1. **Récurrence** : Transactions avec même bénéficiaire et montant similaire (±2%)
2. **Fréquence** : Mensuelle, trimestrielle, annuelle, hebdomadaire
3. **Confiance** : Score basé sur nombre d'occurrences et régularité
4. **Catégorisation** : Automatique selon mots-clés

## 🎨 Personnalisation

### Couleurs (dans `style.css`)

```css
:root {
    --bg-primary: #0f0f1a;
    --accent-primary: #6366F1;
    /* ... */
}
```

### Catégories (dans `parser.js`)

Ajouter des mots-clés pour améliorer la détection :

```javascript
const categories = {
    streaming: ['netflix', 'spotify', 'disney+', ...],
    // ...
};
```

## 🐛 Dépannage

### Le serveur ne démarre pas

```bash
# Vérifier Node.js
node --version

# Réinstaller les dépendances
rm -rf node_modules package-lock.json
npm install
```

### Erreur CORS

Vérifiez que le frontend accède bien à `http://localhost:3000`

### Fichier non reconnu

Assurez-vous que le CSV :
- Utilise `;` ou `,` comme séparateur
- Contient les colonnes date, description, montant
- Est encodé en UTF-8

## 📦 Dépendances Principales

- **express** : Framework web
- **multer** : Upload de fichiers
- **csv-parser** : Parsing CSV
- **pdf-parse** : Parsing PDF
- **cors** : Cross-Origin Resource Sharing

## 🔐 Sécurité

- Validation des types de fichiers
- Limite de taille (10 Mo)
- Stockage temporaire en mémoire
- Pas de persistance des données sensibles

## 📝 Fichier d'Exemple

Un fichier `example-data.csv` est fourni pour tester l'application.

## 🚀 Déploiement

### Production

1. Configurer les variables d'environnement
2. Utiliser un reverse proxy (nginx)
3. Ajouter HTTPS
4. Utiliser une base de données (MongoDB, PostgreSQL)

### Variables d'environnement

```bash
PORT=3000
NODE_ENV=production
```

## 📄 Licence

MIT

## 🤝 Contribution

Les contributions sont les bienvenues ! Ouvrez une issue ou PR.

---

**Bon usage ! 🎉**
