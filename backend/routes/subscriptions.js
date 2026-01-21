const express = require('express');
const router = express.Router();

global.subscriptionsData = {
  subscriptions: [],
  statistics: {},
  transactions: [],
  uploadDate: null
};

router.get('/subscriptions', (req, res) => {
  try {
    res.json({
      success: true,
      data: global.subscriptionsData
    });
  } catch (error) {
    res.status(500).json({ error: 'Erreur lors de la récupération des abonnements' });
  }
});

router.post('/subscriptions/:id/cancel', (req, res) => {
  try {
    const { id } = req.params;
    const subscription = global.subscriptionsData.subscriptions.find(s => s.id === id);
    
    if (!subscription) {
      return res.status(404).json({ error: 'Abonnement non trouvé' });
    }

    subscription.markedForCancellation = true;
    subscription.cancellationDate = new Date();

    res.json({
      success: true,
      message: 'Abonnement marqué pour annulation',
      subscription
    });

  } catch (error) {
    res.status(500).json({ error: 'Erreur lors de l\'annulation' });
  }
});

router.delete('/subscriptions/:id', (req, res) => {
  try {
    const { id } = req.params;
    const index = global.subscriptionsData.subscriptions.findIndex(s => s.id === id);
    
    if (index === -1) {
      return res.status(404).json({ error: 'Abonnement non trouvé' });
    }

    global.subscriptionsData.subscriptions.splice(index, 1);

    res.json({
      success: true,
      message: 'Abonnement supprimé'
    });

  } catch (error) {
    res.status(500).json({ error: 'Erreur lors de la suppression' });
  }
});

module.exports = router;
