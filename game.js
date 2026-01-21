// Configuration du jeu
const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

const GRID_SIZE = 20;
const TILE_COUNT = canvas.width / GRID_SIZE;

// Variables du jeu
let snake = [];
let snakeLength = 5;
let foodX = 0;
let foodY = 0;
let velocityX = 0;
let velocityY = 0;
let score = 0;
let bestScore = 0;
let gameSpeed = 100;
let gameLoop = null;
let currentDifficulty = '';

// Initialisation
document.addEventListener('DOMContentLoaded', function() {
    loadBestScore();
    updateBestScoreDisplay();
});

// Charger le meilleur score depuis localStorage
function loadBestScore() {
    const saved = localStorage.getItem('snakeBestScore');
    bestScore = saved ? parseInt(saved) : 0;
}

// Sauvegarder le meilleur score dans localStorage
function saveBestScore() {
    if (score > bestScore) {
        bestScore = score;
        localStorage.setItem('snakeBestScore', bestScore.toString());
    }
}

// Mettre à jour l'affichage du meilleur score
function updateBestScoreDisplay() {
    document.getElementById('bestScoreMenu').textContent = bestScore;
    document.getElementById('bestScore').textContent = bestScore;
    document.getElementById('bestScoreFinal').textContent = bestScore;
}

// Démarrer le jeu avec la difficulté choisie
function startGame(difficulty) {
    currentDifficulty = difficulty;
    
    // Définir la vitesse selon la difficulté
    switch(difficulty) {
        case 'easy':
            gameSpeed = 150;
            break;
        case 'medium':
            gameSpeed = 100;
            break;
        case 'hard':
            gameSpeed = 50;
            break;
    }
    
    // Afficher le nom de la difficulté
    const difficultyNames = {
        'easy': 'Facile',
        'medium': 'Moyen',
        'hard': 'Difficile'
    };
    document.getElementById('difficulty').textContent = difficultyNames[difficulty];
    
    // Cacher le menu et afficher le jeu
    document.getElementById('menu').classList.add('hidden');
    document.getElementById('gameOver').classList.add('hidden');
    document.getElementById('gameArea').classList.remove('hidden');
    
    // Initialiser le jeu
    initGame();
}

// Initialiser le jeu
function initGame() {
    // Réinitialiser le serpent au centre
    snake = [];
    snakeLength = 5;
    
    const centerX = Math.floor(TILE_COUNT / 2);
    const centerY = Math.floor(TILE_COUNT / 2);
    
    for (let i = 0; i < snakeLength; i++) {
        snake.push({ x: centerX - i, y: centerY });
    }
    
    // Direction initiale vers la droite
    velocityX = 1;
    velocityY = 0;
    
    // Score à zéro
    score = 0;
    updateScore();
    
    // Placer la nourriture
    placeFood();
    
    // Démarrer la boucle de jeu
    if (gameLoop) {
        clearInterval(gameLoop);
    }
    gameLoop = setInterval(update, gameSpeed);
    
    // Ajouter les contrôles clavier
    document.addEventListener('keydown', handleKeyPress);
}

// Placer la nourriture aléatoirement
function placeFood() {
    let validPosition = false;
    
    while (!validPosition) {
        foodX = Math.floor(Math.random() * TILE_COUNT);
        foodY = Math.floor(Math.random() * TILE_COUNT);
        
        // Vérifier que la nourriture n'est pas sur le serpent
        validPosition = true;
        for (let segment of snake) {
            if (segment.x === foodX && segment.y === foodY) {
                validPosition = false;
                break;
            }
        }
    }
}

// Gérer les touches du clavier
function handleKeyPress(event) {
    // Empêcher le scroll de la page
    if ([37, 38, 39, 40].includes(event.keyCode)) {
        event.preventDefault();
    }
    
    switch(event.keyCode) {
        case 37: // Flèche gauche
            if (velocityX !== 1) {
                velocityX = -1;
                velocityY = 0;
            }
            break;
        case 38: // Flèche haut
            if (velocityY !== 1) {
                velocityX = 0;
                velocityY = -1;
            }
            break;
        case 39: // Flèche droite
            if (velocityX !== -1) {
                velocityX = 1;
                velocityY = 0;
            }
            break;
        case 40: // Flèche bas
            if (velocityY !== -1) {
                velocityX = 0;
                velocityY = 1;
            }
            break;
    }
}

// Boucle principale du jeu
function update() {
    // Calculer la nouvelle position de la tête
    const head = { x: snake[0].x + velocityX, y: snake[0].y + velocityY };
    
    // Vérifier collision avec les murs
    if (head.x < 0 || head.x >= TILE_COUNT || head.y < 0 || head.y >= TILE_COUNT) {
        gameOver();
        return;
    }
    
    // Vérifier collision avec le corps
    for (let segment of snake) {
        if (segment.x === head.x && segment.y === head.y) {
            gameOver();
            return;
        }
    }
    
    // Ajouter la nouvelle tête
    snake.unshift(head);
    
    // Vérifier si le serpent mange la nourriture
    if (head.x === foodX && head.y === foodY) {
        score += 10;
        snakeLength++;
        updateScore();
        placeFood();
    } else {
        // Enlever la queue si pas de nourriture mangée
        while (snake.length > snakeLength) {
            snake.pop();
        }
    }
    
    // Dessiner le jeu
    draw();
}

// Dessiner le jeu
function draw() {
    // Fond du canvas
    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Grille (optionnel, pour un meilleur visuel)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= TILE_COUNT; i++) {
        ctx.beginPath();
        ctx.moveTo(i * GRID_SIZE, 0);
        ctx.lineTo(i * GRID_SIZE, canvas.height);
        ctx.stroke();
        
        ctx.beginPath();
        ctx.moveTo(0, i * GRID_SIZE);
        ctx.lineTo(canvas.width, i * GRID_SIZE);
        ctx.stroke();
    }
    
    // Dessiner la nourriture avec animation
    const foodGradient = ctx.createRadialGradient(
        foodX * GRID_SIZE + GRID_SIZE / 2,
        foodY * GRID_SIZE + GRID_SIZE / 2,
        0,
        foodX * GRID_SIZE + GRID_SIZE / 2,
        foodY * GRID_SIZE + GRID_SIZE / 2,
        GRID_SIZE / 2
    );
    foodGradient.addColorStop(0, '#ff6b6b');
    foodGradient.addColorStop(1, '#ee5a6f');
    
    ctx.fillStyle = foodGradient;
    ctx.beginPath();
    ctx.arc(
        foodX * GRID_SIZE + GRID_SIZE / 2,
        foodY * GRID_SIZE + GRID_SIZE / 2,
        GRID_SIZE / 2 - 2,
        0,
        2 * Math.PI
    );
    ctx.fill();
    
    // Dessiner le serpent
    snake.forEach((segment, index) => {
        // Gradient pour chaque segment
        const gradient = ctx.createLinearGradient(
            segment.x * GRID_SIZE,
            segment.y * GRID_SIZE,
            (segment.x + 1) * GRID_SIZE,
            (segment.y + 1) * GRID_SIZE
        );
        
        if (index === 0) {
            // Tête du serpent (plus claire)
            gradient.addColorStop(0, '#4ade80');
            gradient.addColorStop(1, '#22c55e');
        } else {
            // Corps du serpent (gradient progressif)
            const intensity = 1 - (index / snake.length) * 0.5;
            gradient.addColorStop(0, `rgba(74, 222, 128, ${intensity})`);
            gradient.addColorStop(1, `rgba(34, 197, 94, ${intensity})`);
        }
        
        ctx.fillStyle = gradient;
        ctx.fillRect(
            segment.x * GRID_SIZE + 1,
            segment.y * GRID_SIZE + 1,
            GRID_SIZE - 2,
            GRID_SIZE - 2
        );
        
        // Yeux pour la tête
        if (index === 0) {
            ctx.fillStyle = '#1a1a2e';
            const eyeSize = 3;
            const eyeOffset = 6;
            
            if (velocityX !== 0) {
                // Yeux horizontaux
                ctx.fillRect(segment.x * GRID_SIZE + eyeOffset, segment.y * GRID_SIZE + 5, eyeSize, eyeSize);
                ctx.fillRect(segment.x * GRID_SIZE + eyeOffset, segment.y * GRID_SIZE + 12, eyeSize, eyeSize);
            } else {
                // Yeux verticaux
                ctx.fillRect(segment.x * GRID_SIZE + 5, segment.y * GRID_SIZE + eyeOffset, eyeSize, eyeSize);
                ctx.fillRect(segment.x * GRID_SIZE + 12, segment.y * GRID_SIZE + eyeOffset, eyeSize, eyeSize);
            }
        }
    });
}

// Mettre à jour le score
function updateScore() {
    document.getElementById('currentScore').textContent = score;
}

// Game Over
function gameOver() {
    // Arrêter la boucle de jeu
    clearInterval(gameLoop);
    gameLoop = null;
    
    // Retirer les contrôles
    document.removeEventListener('keydown', handleKeyPress);
    
    // Sauvegarder le meilleur score
    saveBestScore();
    updateBestScoreDisplay();
    
    // Afficher l'écran Game Over
    document.getElementById('gameArea').classList.add('hidden');
    document.getElementById('gameOver').classList.remove('hidden');
    document.getElementById('finalScore').textContent = score;
}

// Rejouer avec la même difficulté
function restartGame() {
    startGame(currentDifficulty);
}

// Retour au menu
function backToMenu() {
    // Arrêter le jeu si en cours
    if (gameLoop) {
        clearInterval(gameLoop);
        gameLoop = null;
    }
    
    // Retirer les contrôles
    document.removeEventListener('keydown', handleKeyPress);
    
    // Afficher le menu
    document.getElementById('gameOver').classList.add('hidden');
    document.getElementById('gameArea').classList.add('hidden');
    document.getElementById('menu').classList.remove('hidden');
    
    updateBestScoreDisplay();
}
