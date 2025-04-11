// Game constants
const CANVAS_WIDTH = 600;
const CANVAS_HEIGHT = 400;
const GRID_SIZE = 20;
const GRID_WIDTH = CANVAS_WIDTH / GRID_SIZE;
const GRID_HEIGHT = CANVAS_HEIGHT / GRID_SIZE;
const INITIAL_SNAKE_SPEED = 150; // milliseconds between moves
const GRAVITY = 0.5;
const JUMP_FORCE = -10;
const PIPE_SPEED = 2;
const PIPE_SPAWN_INTERVAL = 2000; // milliseconds
const PIPE_GAP = 150;
const PIPE_WIDTH = 50;

// Game variables
let canvas = document.getElementById('game-canvas');
let ctx = canvas.getContext('2d');
let snake = [];
let food = {};
let direction = 'right';
let nextDirection = 'right';
let score = 0;
let gameRunning = false;
let gameMode = 'snake'; // 'snake', 'flappy', or 'hybrid'
let lastRenderTime = 0;
let pipes = [];
let lastPipeTime = 0;

// Flappy bird variables
let birdY = CANVAS_HEIGHT / 2;
let birdVelocity = 0;
let birdSize = 20;
let birdX = CANVAS_WIDTH / 4;

// Game mode buttons
const snakeModeBtn = document.getElementById('snake-mode');
const flappyModeBtn = document.getElementById('flappy-mode');
const hybridModeBtn = document.getElementById('hybrid-mode');
const instructionsText = document.getElementById('current-instructions');

// Set game mode
function setGameMode(mode) {
    gameMode = mode;
    
    // Update active button
    snakeModeBtn.classList.remove('active-mode');
    flappyModeBtn.classList.remove('active-mode');
    hybridModeBtn.classList.remove('active-mode');
    
    if (mode === 'snake') {
        snakeModeBtn.classList.add('active-mode');
        instructionsText.textContent = 'Use arrow keys to control the snake. Eat the food to grow longer!';
    } else if (mode === 'flappy') {
        flappyModeBtn.classList.add('active-mode');
        instructionsText.textContent = 'Press SPACE to make the bird jump. Avoid the pipes!';
    } else {
        hybridModeBtn.classList.add('active-mode');
        instructionsText.textContent = 'Control the snake with arrow keys and press SPACE to jump. Collect food and avoid pipes!';
    }
    
    // Restart game with new mode
    initGame();
}

// Event listeners for game mode buttons
snakeModeBtn.addEventListener('click', () => setGameMode('snake'));
flappyModeBtn.addEventListener('click', () => setGameMode('flappy'));
hybridModeBtn.addEventListener('click', () => setGameMode('hybrid'));

// Initialize the game
function initGame() {
    // Reset variables
    snake = [
        {x: 5, y: 10},
        {x: 4, y: 10},
        {x: 3, y: 10}
    ];
    direction = 'right';
    nextDirection = 'right';
    score = 0;
    updateScore(0);
    pipes = [];
    lastPipeTime = 0;
    birdY = CANVAS_HEIGHT / 2;
    birdVelocity = 0;
    
    // Place initial food
    placeFood();
    
    // Hide game over screen
    document.getElementById('game-over').style.display = 'none';
    
    // Start game loop
    gameRunning = true;
    window.requestAnimationFrame(gameStep);
}

// Game step function (called by requestAnimationFrame)
function gameStep(currentTime) {
    if (!gameRunning) return;
    
    window.requestAnimationFrame(gameStep);
    
    // Calculate time since last frame
    const deltaTime = currentTime - lastRenderTime;
    
    // Control game speed based on mode
    if (gameMode === 'snake' || gameMode === 'hybrid') {
        if (deltaTime < INITIAL_SNAKE_SPEED) return;
    }
    
    lastRenderTime = currentTime;
    
    // Spawn pipes in flappy and hybrid modes
    if ((gameMode === 'flappy' || gameMode === 'hybrid') && 
        currentTime - lastPipeTime > PIPE_SPAWN_INTERVAL) {
        spawnPipe();
        lastPipeTime = currentTime;
    }
    
    update(deltaTime);
    draw();
}

// Update game state
function update(deltaTime) {
    if (gameMode === 'snake' || gameMode === 'hybrid') {
        updateSnake();
    }
    
    if (gameMode === 'flappy' || gameMode === 'hybrid') {
        updateFlappyBird(deltaTime);
        updatePipes();
    }
}

// Update snake movement
function updateSnake() {
    // Update direction
    direction = nextDirection;
    
    // Calculate new head position
    const head = {x: snake[0].x, y: snake[0].y};
    
    switch (direction) {
        case 'up':
            head.y -= 1;
            break;
        case 'down':
            head.y += 1;
            break;
        case 'left':
            head.x -= 1;
            break;
        case 'right':
            head.x += 1;
            break;
    }
    
    // Check for collisions
    if (isSnakeCollision(head)) {
        gameOver();
        return;
    }
    
    // Add new head
    snake.unshift(head);
    
    // Check if food is eaten
    if (head.x === food.x && head.y === food.y) {
        // Increase score
        updateScore(score + 1);
        
        // Place new food
        placeFood();
    } else {
        // Remove tail if no food eaten
        snake.pop();
    }
}

// Update flappy bird physics
function updateFlappyBird(deltaTime) {
    // Apply gravity
    birdVelocity += GRAVITY;
    birdY += birdVelocity;
    
    // Check for collisions with ceiling and floor
    if (birdY <= 0) {
        birdY = 0;
        birdVelocity = 0;
    }
    
    if (birdY >= CANVAS_HEIGHT - birdSize) {
        birdY = CANVAS_HEIGHT - birdSize;
        gameOver();
        return;
    }
    
    // Check for collisions with pipes
    if (checkPipeCollisions()) {
        gameOver();
        return;
    }
    
    // In hybrid mode, check if bird position overlaps with food
    if (gameMode === 'hybrid') {
        const birdGridX = Math.floor(birdX / GRID_SIZE);
        const birdGridY = Math.floor(birdY / GRID_SIZE);
        
        if (birdGridX === food.x && birdGridY === food.y) {
            updateScore(score + 1);
            placeFood();
        }
    }
}

// Update pipes movement
function updatePipes() {
    // Move pipes
    for (let i = 0; i < pipes.length; i++) {
        pipes[i].x -= PIPE_SPEED;
    }
    
    // Remove pipes that are off screen
    pipes = pipes.filter(pipe => pipe.x + PIPE_WIDTH > 0);
    
    // Add score when passing pipes in flappy mode
    for (let i = 0; i < pipes.length; i++) {
        if (!pipes[i].passed && pipes[i].x + PIPE_WIDTH < birdX) {
            pipes[i].passed = true;
            if (gameMode === 'flappy') {
                updateScore(score + 1);
            }
        }
    }
}

// Draw game elements
function draw() {
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw sky background
    ctx.fillStyle = '#87CEEB';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Draw ground
    ctx.fillStyle = '#8B4513'; // Brown
    ctx.fillRect(0, CANVAS_HEIGHT - 20, CANVAS_WIDTH, 20);
    ctx.fillStyle = '#7CFC00'; // Lawn green
    ctx.fillRect(0, CANVAS_HEIGHT - 20, CANVAS_WIDTH, 5);
    
    // Draw grid (optional)
    if (gameMode === 'snake' || gameMode === 'hybrid') {
        drawGrid();
    }
    
    // Draw pipes in flappy and hybrid modes
    if (gameMode === 'flappy' || gameMode === 'hybrid') {
        drawPipes();
    }
    
    // Draw food in snake and hybrid modes
    if (gameMode === 'snake' || gameMode === 'hybrid') {
        drawCell(food.x, food.y, '#FF5722');
    }
    
    // Draw snake in snake and hybrid modes
    if (gameMode === 'snake' || gameMode === 'hybrid') {
        snake.forEach((segment, index) => {
            const color = index === 0 ? '#4CAF50' : '#8BC34A'; // Head is darker green
            drawCell(segment.x, segment.y, color);
        });
    }
    
    // Draw bird in flappy and hybrid modes
    if (gameMode === 'flappy' || gameMode === 'hybrid') {
        drawBird();
    }
}

// Draw a single cell
function drawCell(x, y, color) {
    ctx.fillStyle = color;
    ctx.fillRect(x * GRID_SIZE, y * GRID_SIZE, GRID_SIZE, GRID_SIZE);
    
    // Add cell border
    ctx.strokeStyle = '#111';
    ctx.lineWidth = 1;
    ctx.strokeRect(x * GRID_SIZE, y * GRID_SIZE, GRID_SIZE, GRID_SIZE);
}

// Draw grid lines
function drawGrid() {
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.1)';
    ctx.lineWidth = 0.5;
    
    // Vertical lines
    for (let x = 0; x <= canvas.width; x += GRID_SIZE) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
    }
    
    // Horizontal lines
    for (let y = 0; y <= canvas.height; y += GRID_SIZE) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
    }
}

// Draw the flappy bird
function drawBird() {
    // Bird body
    ctx.fillStyle = '#FFEB3B'; // Yellow
    ctx.beginPath();
    ctx.arc(birdX + birdSize/2, birdY + birdSize/2, birdSize/2, 0, Math.PI * 2);
    ctx.fill();
    
    // Bird eye
    ctx.fillStyle = 'white';
    ctx.beginPath();
    ctx.arc(birdX + birdSize * 0.7, birdY + birdSize * 0.3, birdSize/6, 0, Math.PI * 2);
    ctx.fill();
    
    // Bird pupil
    ctx.fillStyle = 'black';
    ctx.beginPath();
    ctx.arc(birdX + birdSize * 0.75, birdY + birdSize * 0.3, birdSize/12, 0, Math.PI * 2);
    ctx.fill();
    
    // Bird beak
    ctx.fillStyle = '#FF9800'; // Orange
    ctx.beginPath();
    ctx.moveTo(birdX + birdSize, birdY + birdSize/2);
    ctx.lineTo(birdX + birdSize * 1.3, birdY + birdSize * 0.4);
    ctx.lineTo(birdX + birdSize * 1.3, birdY + birdSize * 0.6);
    ctx.closePath();
    ctx.fill();
}

// Draw pipes
function drawPipes() {
    ctx.fillStyle = '#4CAF50'; // Green
    
    for (let i = 0; i < pipes.length; i++) {
        const pipe = pipes[i];
        
        // Top pipe
        ctx.fillRect(pipe.x, 0, PIPE_WIDTH, pipe.topHeight);
        
        // Bottom pipe
        ctx.fillRect(pipe.x, pipe.topHeight + PIPE_GAP, PIPE_WIDTH, CANVAS_HEIGHT - (pipe.topHeight + PIPE_GAP));
        
        // Pipe caps
        ctx.fillStyle = '#388E3C'; // Darker green
        ctx.fillRect(pipe.x - 5, pipe.topHeight - 10, PIPE_WIDTH + 10, 10);
        ctx.fillRect(pipe.x - 5, pipe.topHeight + PIPE_GAP, PIPE_WIDTH + 10, 10);
        ctx.fillStyle = '#4CAF50'; // Reset to original green
    }
}

// Spawn a new pipe
function spawnPipe() {
    const topHeight = Math.floor(Math.random() * (CANVAS_HEIGHT - PIPE_GAP - 100)) + 50;
    
    pipes.push({
        x: CANVAS_WIDTH,
        topHeight: topHeight,
        passed: false
    });
}

// Check for pipe collisions
function checkPipeCollisions() {
    for (let i = 0; i < pipes.length; i++) {
        const pipe = pipes[i];
        
        // Check if bird is within pipe's x-range
        if (birdX + birdSize > pipe.x && birdX < pipe.x + PIPE_WIDTH) {
            // Check if bird is hitting top or bottom pipe
            if (birdY < pipe.topHeight || birdY + birdSize > pipe.topHeight + PIPE_GAP) {
                return true;
            }
        }
    }
    
    return false;
}

// Place food at random position
function placeFood() {
    // Generate random position
    let newFood;
    do {
        newFood = {
            x: Math.floor(Math.random() * GRID_WIDTH),
            y: Math.floor(Math.random() * (GRID_HEIGHT - 1)) // Keep food above ground
        };
    } while (isFoodOnSnake(newFood));
    
    food = newFood;
}

// Check if food is on snake
function isFoodOnSnake(pos) {
    return snake.some(segment => segment.x === pos.x && segment.y === pos.y);
}

// Check for snake collisions
function isSnakeCollision(pos) {
    // Wall collision
    if (pos.x < 0 || pos.x >= GRID_WIDTH || pos.y < 0 || pos.y >= GRID_HEIGHT - 1) { // Keep snake above ground
        return true;
    }
    
    // Self collision (skip head)
    for (let i = 1; i < snake.length; i++) {
        if (pos.x === snake[i].x && pos.y === snake[i].y) {
            return true;
        }
    }
    
    // In hybrid mode, check for pipe collisions
    if (gameMode === 'hybrid') {
        for (let i = 0; i < pipes.length; i++) {
            const pipe = pipes[i];
            const snakeX = pos.x * GRID_SIZE;
            const snakeY = pos.y * GRID_SIZE;
            
            // Check if snake head is within pipe's x-range
            if (snakeX + GRID_SIZE > pipe.x && snakeX < pipe.x + PIPE_WIDTH) {
                // Check if snake head is hitting top or bottom pipe
                if (snakeY < pipe.topHeight || snakeY + GRID_SIZE > pipe.topHeight + PIPE_GAP) {
                    return true;
                }
            }
        }
    }
    
    return false;
}

// Update score display
function updateScore(newScore) {
    score = newScore;
    document.getElementById('score').textContent = `Score: ${score}`;
}

// Game over
function gameOver() {
    gameRunning = false;
    document.getElementById('final-score').textContent = score;
    document.getElementById('game-over').style.display = 'block';
}

// Handle keyboard input
document.addEventListener('keydown', (event) => {
    if (gameMode === 'snake' || gameMode === 'hybrid') {
        switch (event.key) {
            case 'ArrowUp':
                if (direction !== 'down') nextDirection = 'up';
                event.preventDefault();
                break;
            case 'ArrowDown':
                if (direction !== 'up') nextDirection = 'down';
                event.preventDefault();
                break;
            case 'ArrowLeft':
                if (direction !== 'right') nextDirection = 'left';
                event.preventDefault();
                break;
            case 'ArrowRight':
                if (direction !== 'left') nextDirection = 'right';
                event.preventDefault();
                break;
        }
    }
    
    if ((gameMode === 'flappy' || gameMode === 'hybrid') && event.code === 'Space') {
        // Bird jump
        birdVelocity = JUMP_FORCE;
        event.preventDefault();
    }
});

// Restart button
document.getElementById('restart-button').addEventListener('click', initGame);

// Start the game
initGame();