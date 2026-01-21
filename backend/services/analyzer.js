const crypto = require('crypto');

class SubscriptionAnalyzer {
  detectSubscriptions(transactions, months = 3) {
    const cutoffDate = new Date();
    cutoffDate.setMonth(cutoffDate.getMonth() - months);
    
    const recentTransactions = transactions.filter(t => t.date >= cutoffDate);
    
    const groupedByDescription = this.groupTransactions(recentTransactions);
    
    const subscriptions = [];

    for (const [description, txs] of Object.entries(groupedByDescription)) {
      if (txs.length < 2) continue;

      const avgAmount = txs.reduce((sum, t) => sum + t.amount, 0) / txs.length;
      const amountVariance = this.calculateVariance(txs.map(t => t.amount));
      
      if (amountVariance / avgAmount > 0.05) continue;

      const frequency = this.detectFrequency(txs);
      
      if (frequency) {
        const subscription = {
          id: this.generateId(description),
          name: this.cleanDescription(description),
          amount: parseFloat(avgAmount.toFixed(2)),
          frequency: frequency.type,
          category: txs[0].category,
          lastPaymentDate: txs[0].date,
          nextPaymentDate: this.estimateNextPayment(txs[0].date, frequency.type),
          transactionCount: txs.length,
          totalSpent: parseFloat(txs.reduce((sum, t) => sum + t.amount, 0).toFixed(2)),
          confidence: this.calculateConfidence(txs, frequency),
          markedForCancellation: false
        };

        subscriptions.push(subscription);
      }
    }

    return subscriptions.sort((a, b) => b.amount - a.amount);
  }

  groupTransactions(transactions) {
    const groups = {};

    transactions.forEach(tx => {
      const normalized = this.normalizeDescription(tx.description);
      
      if (!groups[normalized]) {
        groups[normalized] = [];
      }
      groups[normalized].push(tx);
    });

    return groups;
  }

  normalizeDescription(desc) {
    return desc
      .toLowerCase()
      .replace(/\d{2}\/\d{2}/g, '')
      .replace(/\d+/g, '')
      .replace(/[^\w\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .substring(0, 50);
  }

  cleanDescription(desc) {
    return desc
      .split(' ')
      .filter(word => word.length > 2)
      .slice(0, 4)
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  detectFrequency(transactions) {
    if (transactions.length < 2) return null;

    const sortedTxs = [...transactions].sort((a, b) => a.date - b.date);
    const intervals = [];

    for (let i = 1; i < sortedTxs.length; i++) {
      const daysDiff = (sortedTxs[i].date - sortedTxs[i - 1].date) / (1000 * 60 * 60 * 24);
      intervals.push(daysDiff);
    }

    const avgInterval = intervals.reduce((sum, val) => sum + val, 0) / intervals.length;

    if (avgInterval >= 25 && avgInterval <= 35) {
      return { type: 'monthly', days: 30 };
    } else if (avgInterval >= 85 && avgInterval <= 95) {
      return { type: 'quarterly', days: 90 };
    } else if (avgInterval >= 355 && avgInterval <= 375) {
      return { type: 'yearly', days: 365 };
    } else if (avgInterval >= 12 && avgInterval <= 16) {
      return { type: 'biweekly', days: 14 };
    } else if (avgInterval >= 6 && avgInterval <= 8) {
      return { type: 'weekly', days: 7 };
    }

    return null;
  }

  calculateVariance(numbers) {
    const mean = numbers.reduce((sum, val) => sum + val, 0) / numbers.length;
    const squareDiffs = numbers.map(val => Math.pow(val - mean, 2));
    return squareDiffs.reduce((sum, val) => sum + val, 0) / numbers.length;
  }

  estimateNextPayment(lastDate, frequency) {
    const next = new Date(lastDate);
    
    switch (frequency) {
      case 'weekly':
        next.setDate(next.getDate() + 7);
        break;
      case 'biweekly':
        next.setDate(next.getDate() + 14);
        break;
      case 'monthly':
        next.setMonth(next.getMonth() + 1);
        break;
      case 'quarterly':
        next.setMonth(next.getMonth() + 3);
        break;
      case 'yearly':
        next.setFullYear(next.getFullYear() + 1);
        break;
    }

    return next;
  }

  calculateConfidence(transactions, frequency) {
    let score = 0;

    score += Math.min(transactions.length * 10, 40);

    const amounts = transactions.map(t => t.amount);
    const avgAmount = amounts.reduce((sum, val) => sum + val, 0) / amounts.length;
    const variance = this.calculateVariance(amounts);
    const consistencyScore = Math.max(0, 30 - (variance / avgAmount * 100));
    score += consistencyScore;

    if (frequency.type === 'monthly') score += 30;
    else if (frequency.type === 'yearly') score += 20;
    else if (frequency.type === 'quarterly') score += 25;

    return Math.min(Math.round(score), 100);
  }

  calculateStatistics(subscriptions) {
    const total = subscriptions.reduce((sum, sub) => {
      let monthlyAmount = sub.amount;
      
      if (sub.frequency === 'yearly') {
        monthlyAmount = sub.amount / 12;
      } else if (sub.frequency === 'quarterly') {
        monthlyAmount = sub.amount / 3;
      } else if (sub.frequency === 'weekly') {
        monthlyAmount = sub.amount * 4.33;
      } else if (sub.frequency === 'biweekly') {
        monthlyAmount = sub.amount * 2.16;
      }

      return sum + monthlyAmount;
    }, 0);

    const byCategory = subscriptions.reduce((acc, sub) => {
      if (!acc[sub.category]) {
        acc[sub.category] = { count: 0, total: 0 };
      }
      acc[sub.category].count++;
      acc[sub.category].total += sub.amount;
      return acc;
    }, {});

    return {
      totalMonthly: parseFloat(total.toFixed(2)),
      totalYearly: parseFloat((total * 12).toFixed(2)),
      subscriptionCount: subscriptions.length,
      averageSubscription: parseFloat((total / subscriptions.length || 0).toFixed(2)),
      byCategory,
      mostExpensive: subscriptions[0] || null,
      upcomingPayments: this.getUpcomingPayments(subscriptions)
    };
  }

  getUpcomingPayments(subscriptions) {
    const upcoming = subscriptions
      .map(sub => ({
        name: sub.name,
        amount: sub.amount,
        date: sub.nextPaymentDate
      }))
      .sort((a, b) => a.date - b.date)
      .slice(0, 5);

    return upcoming;
  }

  generateId(text) {
    return crypto.createHash('md5').update(text).digest('hex').substring(0, 8);
  }
}

module.exports = new SubscriptionAnalyzer();
