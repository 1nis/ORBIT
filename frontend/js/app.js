const API_URL = 'http://localhost:3000/api';

let currentFilter = 'all';
let subscriptionsData = [];
let selectedSubscriptionId = null;

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initFilters();
    loadSubscriptions();
});

function initNavigation() {
    const navButtons = document.querySelectorAll('.nav-btn');
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const page = btn.dataset.page;
            switchPage(page);
        });
    });
}

function switchPage(pageName) {
    document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    
    document.getElementById(`${pageName}-page`).classList.add('active');
    document.querySelector(`[data-page="${pageName}"]`).classList.add('active');
    
    if (pageName === 'dashboard') {
        loadSubscriptions();
    }
}

function initFilters() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            renderSubscriptions();
        });
    });
}

async function loadSubscriptions() {
    try {
        const response = await fetch(`${API_URL}/subscriptions`);
        const result = await response.json();
        
        if (result.success) {
            subscriptionsData = result.data.subscriptions || [];
            updateStatistics(result.data.statistics);
            renderSubscriptions();
        }
    } catch (error) {
        console.error('Erreur chargement:', error);
    }
}

function updateStatistics(stats) {
    if (!stats) return;
    
    document.getElementById('stat-monthly').textContent = `${stats.totalMonthly || 0}€`;
    document.getElementById('stat-yearly').textContent = `${stats.totalYearly || 0}€`;
    document.getElementById('stat-count').textContent = stats.subscriptionCount || 0;
    document.getElementById('stat-average').textContent = `${stats.averageSubscription || 0}€`;
}

function renderSubscriptions() {
    const container = document.getElementById('subscriptions-list');
    
    const filtered = subscriptionsData.filter(sub => {
        if (currentFilter === 'all') return true;
        return sub.category === currentFilter;
    });
    
    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
                    <circle cx="32" cy="32" r="30" stroke="currentColor" stroke-width="2" opacity="0.2"/>
                    <path d="M32 20v24M20 32h24" stroke="currentColor" stroke-width="2"/>
                </svg>
                <h3>Aucun abonnement</h3>
                <p>Aucun abonnement trouvé dans cette catégorie</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = filtered.map(sub => createSubscriptionCard(sub)).join('');
}

function createSubscriptionCard(sub) {
    const icon = getCategoryIcon(sub.category);
    const badge = getFrequencyBadge(sub.frequency);
    const cancelledClass = sub.markedForCancellation ? 'cancelled' : '';
    const nextPayment = new Date(sub.nextPaymentDate).toLocaleDateString('fr-FR');
    
    return `
        <div class="subscription-card ${cancelledClass}" data-id="${sub.id}">
            <div class="subscription-icon" style="background: ${getCategoryColor(sub.category)}">
                ${icon}
            </div>
            <div class="subscription-info">
                <div class="subscription-name">${sub.name}</div>
                <div class="subscription-meta">
                    <span class="meta-item">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                            <circle cx="8" cy="8" r="6" stroke-width="1.5"/>
                            <path d="M8 5v3l2 2" stroke-width="1.5"/>
                        </svg>
                        ${nextPayment}
                    </span>
                    <span class="subscription-badge badge-${sub.frequency}">${badge}</span>
                    ${sub.markedForCancellation ? '<span class="meta-item" style="color: var(--danger)">À annuler</span>' : ''}
                </div>
            </div>
            <div class="subscription-amount">${sub.amount}€</div>
            <div class="subscription-actions">
                <button class="btn-icon" onclick="viewDetails('${sub.id}')" title="Détails">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor">
                        <circle cx="10" cy="10" r="8" stroke-width="1.5"/>
                        <path d="M10 10h.01" stroke-width="2"/>
                    </svg>
                </button>
                <button class="btn-icon danger" onclick="cancelSubscription('${sub.id}')" title="Annuler">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor">
                        <path d="M5 5l10 10M15 5l-10 10" stroke-width="2"/>
                    </svg>
                </button>
            </div>
        </div>
    `;
}

function getCategoryIcon(category) {
    const icons = {
        streaming: '🎬',
        software: '💻',
        fitness: '💪',
        transport: '🚗',
        utilities: '⚡',
        insurance: '🛡️',
        other: '📦'
    };
    return icons[category] || icons.other;
}

function getCategoryColor(category) {
    const colors = {
        streaming: '#EF4444',
        software: '#6366F1',
        fitness: '#10B981',
        transport: '#F59E0B',
        utilities: '#3B82F6',
        insurance: '#8B5CF6',
        other: '#6B7280'
    };
    return colors[category] || colors.other;
}

function getFrequencyBadge(frequency) {
    const badges = {
        monthly: 'Mensuel',
        yearly: 'Annuel',
        quarterly: 'Trimestriel',
        weekly: 'Hebdo',
        biweekly: 'Bimensuel'
    };
    return badges[frequency] || frequency;
}

function cancelSubscription(id) {
    selectedSubscriptionId = id;
    document.getElementById('cancel-modal').classList.add('active');
}

function closeCancelModal() {
    document.getElementById('cancel-modal').classList.remove('active');
    selectedSubscriptionId = null;
}

async function confirmCancel() {
    if (!selectedSubscriptionId) return;
    
    try {
        const response = await fetch(`${API_URL}/subscriptions/${selectedSubscriptionId}/cancel`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (result.success) {
            closeCancelModal();
            await loadSubscriptions();
            showNotification('Abonnement marqué pour annulation', 'success');
        }
    } catch (error) {
        console.error('Erreur annulation:', error);
        showNotification('Erreur lors de l\'annulation', 'error');
    }
}

function viewDetails(id) {
    const sub = subscriptionsData.find(s => s.id === id);
    if (!sub) return;
    
    alert(`
Détails de l'abonnement:
------------------------
Nom: ${sub.name}
Montant: ${sub.amount}€
Fréquence: ${getFrequencyBadge(sub.frequency)}
Catégorie: ${sub.category}
Confiance: ${sub.confidence}%
Transactions: ${sub.transactionCount}
Total dépensé: ${sub.totalSpent}€
Prochain paiement: ${new Date(sub.nextPaymentDate).toLocaleDateString('fr-FR')}
    `);
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 2rem;
        right: 2rem;
        padding: 1rem 2rem;
        background: ${type === 'success' ? 'var(--success)' : 'var(--danger)'};
        color: white;
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        z-index: 9999;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

window.switchPage = switchPage;
window.cancelSubscription = cancelSubscription;
window.closeCancelModal = closeCancelModal;
window.confirmCancel = confirmCancel;
window.viewDetails = viewDetails;
