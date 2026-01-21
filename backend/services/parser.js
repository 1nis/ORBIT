const csv = require('csv-parser');
const { Readable } = require('stream');
const pdfParse = require('pdf-parse');

class Parser {
  async parseCSV(buffer) {
    return new Promise((resolve, reject) => {
      const transactions = [];
      const stream = Readable.from(buffer);

      stream
        .pipe(csv({
          separator: [',', ';'],
          mapHeaders: ({ header }) => header.trim().toLowerCase()
        }))
        .on('data', (row) => {
          const transaction = this.normalizeTransaction(row);
          if (transaction) {
            transactions.push(transaction);
          }
        })
        .on('end', () => {
          resolve(transactions.sort((a, b) => b.date - a.date));
        })
        .on('error', reject);
    });
  }

  async parsePDF(buffer) {
    try {
      const data = await pdfParse(buffer);
      const text = data.text;
      
      const transactions = [];
      const lines = text.split('\n');
      
      const dateRegex = /(\d{2}[\/\-\.]\d{2}[\/\-\.]\d{2,4})/;
      const amountRegex = /(-?\d+[,\.]\d{2})/;
      
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        const dateMatch = line.match(dateRegex);
        const amountMatch = line.match(amountRegex);

        if (dateMatch && amountMatch) {
          const description = line.replace(dateMatch[0], '').replace(amountMatch[0], '').trim();
          
          transactions.push({
            date: this.parseDate(dateMatch[0]),
            description: description || 'Transaction',
            amount: parseFloat(amountMatch[0].replace(',', '.')),
            category: this.guessCategory(description)
          });
        }
      }

      return transactions.sort((a, b) => b.date - a.date);
    } catch (error) {
      console.error('Erreur parsing PDF:', error);
      return [];
    }
  }

  normalizeTransaction(row) {
    const possibleDateFields = ['date', 'date operation', 'date_operation', 'transaction_date', 'dateop'];
    const possibleDescriptionFields = ['description', 'libelle', 'libellé', 'label', 'beneficiaire', 'beneficiary'];
    const possibleAmountFields = ['amount', 'montant', 'debit', 'credit', 'somme'];

    let date = null;
    let description = '';
    let amount = 0;

    for (const field of possibleDateFields) {
      if (row[field]) {
        date = this.parseDate(row[field]);
        break;
      }
    }

    for (const field of possibleDescriptionFields) {
      if (row[field]) {
        description = row[field];
        break;
      }
    }

    for (const field of possibleAmountFields) {
      if (row[field]) {
        const value = String(row[field]).replace(',', '.').replace(/\s/g, '');
        amount = parseFloat(value);
        if (!isNaN(amount)) break;
      }
    }

    if (!date || !description) {
      return null;
    }

    return {
      date,
      description: description.trim(),
      amount: Math.abs(amount),
      category: this.guessCategory(description)
    };
  }

  parseDate(dateString) {
    const cleaned = dateString.replace(/[\/\-\.]/g, '/');
    const parts = cleaned.split('/');
    
    if (parts.length === 3) {
      let day = parseInt(parts[0]);
      let month = parseInt(parts[1]) - 1;
      let year = parseInt(parts[2]);

      if (year < 100) {
        year += 2000;
      }

      return new Date(year, month, day);
    }

    return new Date(dateString);
  }

  guessCategory(description) {
    const desc = description.toLowerCase();
    
    const categories = {
      streaming: ['netflix', 'spotify', 'disney', 'prime video', 'youtube', 'deezer', 'apple music', 'hulu', 'canal+'],
      software: ['adobe', 'microsoft', 'office', 'google', 'dropbox', 'github', 'notion', 'slack', 'zoom', 'figma'],
      fitness: ['salle sport', 'gym', 'fitness', 'yoga', 'basic fit', 'keep cool', 'orange bleue'],
      transport: ['uber', 'bolt', 'lime', 'sncf', 'ratp', 'velib', 'autolib'],
      utilities: ['edf', 'engie', 'eau', 'gaz', 'électricité', 'internet', 'orange', 'free', 'sfr', 'bouygues'],
      insurance: ['assurance', 'mutuelle', 'axa', 'allianz', 'maif', 'macif'],
      other: []
    };

    for (const [category, keywords] of Object.entries(categories)) {
      if (keywords.some(keyword => desc.includes(keyword))) {
        return category;
      }
    }

    return 'other';
  }
}

module.exports = new Parser();
