// web/static/games/game24/js/script.js
class Game24 {
    constructor() {
        this.currentPuzzle = null;
        this.score = 0;
        this.init();
    }

    async init() {
        await this.checkAuthentication();
        this.setupEventListeners();
        await this.loadNewPuzzle();
        this.loadScore();
    }

    async checkAuthentication() {
        try {
            const response = await fetch('/auth/check');
            const data = await response.json();
            
            if (!data.authenticated) {
                window.location.href = '/?login_required=true';
                return;
            }
        } catch (error) {
            console.error('Auth check failed:', error);
            window.location.href = '/?login_required=true';
        }
    }

    setupEventListeners() {
        document.getElementById('new-puzzle').addEventListener('click', () => this.loadNewPuzzle());
        document.getElementById('check-solution').addEventListener('click', () => this.checkSolution());
        document.getElementById('difficulty').addEventListener('change', () => this.loadNewPuzzle());
    }

    async loadNewPuzzle() {
        try {
            const difficulty = document.getElementById('difficulty').value;
            const response = await fetch(`/api/game24/get_puzzle?difficulty=${difficulty}`);
            
            if (!response.ok) {
                throw new Error('Failed to load puzzle');
            }
            
            this.currentPuzzle = await response.json();
            this.displayCards(this.currentPuzzle.cards);
            this.clearResult();
            
        } catch (error) {
            console.error('Error loading puzzle:', error);
            this.showError('Failed to load puzzle. Please try again.');
        }
    }

    displayCards(cards) {
        const container = document.getElementById('cards-container');
        container.innerHTML = cards.map(card => 
            `<div class="card">${card}</div>`
        ).join('');
    }

    async checkSolution() {
        const solution = document.getElementById('solution-input').value.trim();
        
        if (!solution) {
            this.showError('Please enter a solution');
            return;
        }

        try {
            const response = await fetch('/api/game24/check_solution', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    puzzle_id: this.currentPuzzle.puzzle_id,
                    solution: solution
                })
            });

            const result = await response.json();
            
            if (result.correct) {
                this.showSuccess('Correct! 🎉');
            } else {
                this.showError('Incorrect. Try again! ❌');
            }
            
        } catch (error) {
            console.error('Error checking solution:', error);
            this.showError('Failed to check solution. Please try again.');
        }
    }

    showSuccess(message) {
        const resultDiv = document.getElementById('result');
        resultDiv.textContent = message;
        resultDiv.className = 'result success';
    }

    showError(message) {
        const resultDiv = document.getElementById('result');
        resultDiv.textContent = message;
        resultDiv.className = 'result error';
    }

    clearResult() {
        const resultDiv = document.getElementById('result');
        resultDiv.textContent = '';
        resultDiv.className = 'result';
    }

    async checkSolution() {
        const solution = document.getElementById('solution-input').value.trim();
        
        if (!solution) {
            this.showError('Please enter a solution');
            return;
        }

        try {
            const response = await fetch('/api/game24/check_solution', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    puzzle_id: this.currentPuzzle.puzzle_id,
                    solution: solution
                })
            });

            const result = await response.json();
            
            if (result.correct) {
                this.showSuccess('Correct! 🎉');
                this.updateScore(1);
                setTimeout(() => this.loadNewPuzzle(), 1500); // Auto-load new puzzle after success
            } else {
                this.showError('Incorrect. Try again! ❌');
            }
            
        } catch (error) {
            console.error('Error checking solution:', error);
            this.showError('Failed to check solution. Please try again.');
        }
    }

    updateScore(points) {
        this.score += points;
        this.saveScore();
        this.displayScore();
    }

    displayScore() {
        // Create or update score display
        let scoreDisplay = document.getElementById('score-display');
        if (!scoreDisplay) {
            scoreDisplay = document.createElement('div');
            scoreDisplay.id = 'score-display';
            scoreDisplay.className = 'score-display';
            document.querySelector('.game-container').prepend(scoreDisplay);
        }
        scoreDisplay.textContent = `Score: ${this.score}`;
    }

    saveScore() {
        localStorage.setItem('game24_score', this.score);
    }

    loadScore() {
        const savedScore = localStorage.getItem('game24_score');
        if (savedScore) {
            this.score = parseInt(savedScore);
            this.displayScore();
        }
    }

    async showLeaderboard() {
        try {
            const response = await fetch('/leaderboard/game24');
            const data = await response.json();
            
            // Display leaderboard in a modal or separate section
            console.log('Leaderboard:', data.leaderboard);
        } catch (error) {
            console.error('Error loading leaderboard:', error);
        }
    }
    
    async showMyStats() {
        try {
            const response = await fetch('/leaderboard/my-stats');
            const data = await response.json();
            
            // Display user stats
            console.log('My Stats:', data);
        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }

}

// Initialize game when page loads
document.addEventListener('DOMContentLoaded', () => {
    new Game24();
});
