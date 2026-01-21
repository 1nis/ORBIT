# 🎯 Guide d'Utilisation - SubManager

## 📦 Installation Rapide

### Windows

1. **Double-cliquez** sur `install.bat` pour installer les dépendances
2. **Double-cliquez** sur `start.bat` pour démarrer le serveur
3. Ouvrez votre navigateur sur **http://localhost:3000**

### Manuel

```bash
cd backend
npm install
node server.js
```

## 🚀 Démarrage Rapide

1. **Accédez à l'application** : `http://localhost:3000`
2. Cliquez sur **"Analyser"** dans le menu
3. Sélectionnez la période (1, 2 ou 3 mois)
4. Uploadez votre fichier CSV ou PDF
5. Consultez vos abonnements dans le Dashboard !

## 📝 Préparer votre Relevé Bancaire

### Format CSV Recommandé

Créez un fichier `.csv` avec ces colonnes :

```csv
date,description,montant
01/12/2023,NETFLIX ABONNEMENT,-15.99
05/12/2023,SPOTIFY PREMIUM,-9.99
```

### Colonnes Acceptées

| Type | Noms acceptés |
|------|---------------|
| **Date** | `date`, `date_operation`, `transaction_date`, `dateop` |
| **Description** | `description`, `libelle`, `beneficiaire`, `label` |
| **Montant** | `montant`, `amount`, `debit`, `credit`, `somme` |

### Exporter depuis votre Banque

**Banques principales :**

- **BNP Paribas** : Mes comptes > Télécharger mes opérations > Format CSV
- **Crédit Agricole** : Mes comptes > Exporter > CSV
- **Société Générale** : Mes comptes > Export > Format Excel/CSV
- **LCL** : Mes comptes > Télécharger > CSV
- **Boursorama** : Comptes > Historique > Exporter en CSV

## 🎨 Fonctionnalités de l'Interface

### Dashboard

- **Statistiques en temps réel** : Total mensuel, annuel, nombre d'abonnements
- **Filtres par catégorie** : Streaming, Logiciels, Fitness, etc.
- **Vue détaillée** : Cliquez sur l'icône info pour voir les détails
- **Annulation** : Marquez un abonnement pour annulation

### Analyse

- **Drag & Drop** : Glissez votre fichier directement
- **Sélection de période** : 1, 2 ou 3 mois d'analyse
- **Progression** : Indicateur de chargement pendant l'analyse

## 🧪 Tester avec les Données d'Exemple

Un fichier **`example-data.csv`** est fourni avec :
- 9 abonnements récurrents
- 3 mois de données
- Différentes catégories (Streaming, Fitness, Utilities, etc.)

**Pour tester :**
1. Allez dans "Analyser"
2. Uploadez `example-data.csv`
3. Observez les résultats !

## 🔍 Comment Fonctionne la Détection ?

### Algorithme de Détection

1. **Groupement** : Regroupe les transactions par bénéficiaire
2. **Analyse de récurrence** : Vérifie les montants similaires (±2%)
3. **Calcul de fréquence** : Détecte mensuel, trimestriel, annuel
4. **Score de confiance** : Évalue la régularité (0-100%)
5. **Catégorisation** : Assigne une catégorie automatiquement

### Fréquences Détectées

| Fréquence | Intervalle |
|-----------|-----------|
| Hebdomadaire | 6-8 jours |
| Bimensuel | 12-16 jours |
| Mensuel | 25-35 jours |
| Trimestriel | 85-95 jours |
| Annuel | 355-375 jours |

## 📊 Interpréter les Résultats

### Cartes d'Abonnement

Chaque carte affiche :
- **Icône** : Selon la catégorie
- **Nom** : Extrait de la description
- **Montant** : Par période de facturation
- **Badge de fréquence** : Mensuel, Annuel, etc.
- **Prochaine date** : Estimation du prochain paiement

### Code Couleur

- 🎬 **Rouge** : Streaming
- 💻 **Bleu** : Logiciels
- 💪 **Vert** : Fitness
- 🚗 **Orange** : Transport
- ⚡ **Bleu clair** : Utilities
- 🛡️ **Violet** : Assurance
- 📦 **Gris** : Autres

### Score de Confiance

- **90-100%** : Très fiable (3+ occurrences régulières)
- **70-89%** : Fiable (2 occurrences)
- **50-69%** : Possible (irrégularité détectée)
- **<50%** : Incertain (données insuffisantes)

## ⚙️ Personnalisation

### Ajouter des Catégories

Éditez `backend/services/parser.js` :

```javascript
const categories = {
    streaming: ['netflix', 'spotify', 'disney', 'prime'],
    // Ajoutez vos mots-clés ici
    gaming: ['steam', 'playstation', 'xbox', 'nintendo'],
};
```

### Modifier les Seuils de Détection

Éditez `backend/services/analyzer.js` :

```javascript
// Tolérance de variance (actuellement 5%)
if (amountVariance / avgAmount > 0.05) continue;

// Intervalles de fréquence
if (avgInterval >= 25 && avgInterval <= 35) {
    return { type: 'monthly', days: 30 };
}
```

## 🐛 Résolution de Problèmes

### Aucun abonnement détecté

**Solutions :**
- Vérifiez que votre CSV contient au moins 2 occurrences du même service
- Assurez-vous que les dates sont sur 2-3 mois
- Vérifiez le format des colonnes (date, description, montant)

### Erreur lors de l'upload

**Vérifications :**
- Le serveur est-il démarré ? (`start.bat`)
- Le fichier est-il bien en `.csv` ou `.pdf` ?
- Le fichier fait-il moins de 10 Mo ?

### Le serveur ne démarre pas

```bash
# Vérifier Node.js
node --version  # Doit être 14+

# Réinstaller les dépendances
cd backend
rm -rf node_modules
npm install
```

### Erreur "Cannot GET /"

Le serveur n'est pas démarré. Lancez `start.bat` ou `node server.js` dans le dossier backend.

## 💡 Astuces

### Optimiser la Détection

1. **Utilisez 3 mois de données** pour une meilleure précision
2. **Nettoyez vos données** : Retirez les transactions non pertinentes
3. **Vérifiez les montants** : Les variations doivent être < 2%

### Exporter vos Résultats

Actuellement en développement. Prochainement :
- Export PDF
- Export Excel
- Envoi par email

### Sauvegarder vos Données

Les données sont stockées en mémoire. Pour persistance :
- Ajoutez une base de données (MongoDB, PostgreSQL)
- Implémentez l'authentification utilisateur
- Activez le stockage local (localStorage)

## 📱 Utilisation Mobile

L'interface est **responsive** et fonctionne sur mobile :
- Navigation adaptée
- Cartes empilées verticalement
- Drag & drop remplacé par sélection de fichier

## 🔐 Confidentialité

- **Pas de stockage permanent** : Les données sont en mémoire
- **Aucun envoi externe** : Tout est traité localement
- **Pas de tracking** : Aucune analyse ou publicité

## 📈 Fonctionnalités à Venir

- [ ] Export PDF des abonnements
- [ ] Alertes de renouvellement
- [ ] Graphiques de tendance
- [ ] Comparaison mois par mois
- [ ] Suggestions d'économies
- [ ] Multi-utilisateurs avec authentification

## 🆘 Support

Pour toute question :
1. Consultez la section **Dépannage** du README.md
2. Vérifiez les logs du serveur (dans le terminal)
3. Ouvrez une issue sur GitHub

## 📚 Ressources

- [Documentation Express.js](https://expressjs.com/)
- [Guide CSV](https://fr.wikipedia.org/wiki/Comma-separated_values)
- [Node.js Best Practices](https://github.com/goldbergyoni/nodebestpractices)

---

**Bon usage ! 🎉**

Si vous trouvez cette application utile, n'hésitez pas à la partager !
