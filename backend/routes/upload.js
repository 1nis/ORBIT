const express = require('express');
const multer = require('multer');
const path = require('path');
const parser = require('../services/parser');
const analyzer = require('../services/analyzer');

const router = express.Router();

const storage = multer.memoryStorage();
const upload = multer({
  storage: storage,
  limits: { fileSize: 10 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    if (ext === '.csv' || ext === '.pdf') {
      cb(null, true);
    } else {
      cb(new Error('Format non supporté. Utilisez CSV ou PDF.'));
    }
  }
});

router.post('/upload', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'Aucun fichier fourni' });
    }

    const months = parseInt(req.body.months) || 3;
    const fileExtension = path.extname(req.file.originalname).toLowerCase();
    
    let transactions = [];

    if (fileExtension === '.csv') {
      transactions = await parser.parseCSV(req.file.buffer);
    } else if (fileExtension === '.pdf') {
      transactions = await parser.parsePDF(req.file.buffer);
    }

    const subscriptions = analyzer.detectSubscriptions(transactions, months);
    const statistics = analyzer.calculateStatistics(subscriptions);

    global.subscriptionsData = {
      subscriptions,
      statistics,
      transactions,
      uploadDate: new Date()
    };

    res.json({
      success: true,
      subscriptions,
      statistics,
      transactionCount: transactions.length
    });

  } catch (error) {
    console.error('Erreur upload:', error);
    res.status(500).json({ 
      error: 'Erreur lors du traitement du fichier', 
      message: error.message 
    });
  }
});

module.exports = router;
