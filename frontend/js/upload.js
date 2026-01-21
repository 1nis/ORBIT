const API_URL = 'http://localhost:3000/api';

let selectedMonths = 2;

document.addEventListener('DOMContentLoaded', () => {
    initMonthSelector();
    initDropzone();
});

function initMonthSelector() {
    const monthButtons = document.querySelectorAll('.month-btn');
    monthButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            monthButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedMonths = parseInt(btn.dataset.months);
        });
    });
}

function initDropzone() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    
    dropzone.addEventListener('click', () => {
        fileInput.click();
    });
    
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragging');
    });
    
    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragging');
    });
    
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragging');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0]);
        }
    });
}

async function handleFile(file) {
    const allowedTypes = ['text/csv', 'application/pdf', 'application/vnd.ms-excel'];
    const allowedExtensions = ['.csv', '.pdf'];
    
    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    
    if (!allowedExtensions.includes(fileExtension) && !allowedTypes.includes(file.type)) {
        alert('Format de fichier non supporté. Utilisez CSV ou PDF.');
        return;
    }
    
    if (file.size > 10 * 1024 * 1024) {
        alert('Le fichier est trop volumineux (max 10 Mo).');
        return;
    }
    
    showLoading();
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('months', selectedMonths);
    
    try {
        const response = await fetch(`${API_URL}/upload`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        hideLoading();
        
        if (result.success) {
            showResult(result);
        } else {
            alert(`Erreur: ${result.error || 'Une erreur est survenue'}`);
        }
    } catch (error) {
        hideLoading();
        console.error('Erreur upload:', error);
        alert('Erreur lors de l\'envoi du fichier. Vérifiez que le serveur est démarré.');
    }
}

function showLoading() {
    document.querySelector('.dropzone-content').style.display = 'none';
    document.querySelector('.dropzone-loading').style.display = 'flex';
}

function hideLoading() {
    document.querySelector('.dropzone-content').style.display = 'block';
    document.querySelector('.dropzone-loading').style.display = 'none';
}

function showResult(result) {
    const resultContainer = document.getElementById('upload-result');
    const resultMessage = document.getElementById('result-message');
    
    const message = `
        ${result.subscriptions.length} abonnement(s) détecté(s)
        sur ${result.transactionCount} transactions analysées.
        Total mensuel estimé: ${result.statistics.totalMonthly}€
    `;
    
    resultMessage.textContent = message;
    resultContainer.style.display = 'block';
    
    document.getElementById('dropzone').style.display = 'none';
}

window.addEventListener('load', () => {
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(style);
});
