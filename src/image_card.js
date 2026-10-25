const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');

/**
 * Generate a visual verdict PNG card image for WhatsApp
 * @param {Object} analysis - The verdict data from Mana's backend
 * @returns {Promise<string|null>} - Absolute path to generated PNG image file
 */
function generateCardImage(analysis) {
    return new Promise((resolve) => {
        const outPath = path.resolve(__dirname, `../media_storage/card_${Date.now()}_${Math.random().toString(36).slice(2, 6)}.png`);
        const scriptPath = path.resolve(__dirname, 'generate_card.py');
        const dataJson = JSON.stringify(analysis || {});

        execFile('python3', [scriptPath, dataJson, outPath], (err) => {
            if (err || !fs.existsSync(outPath)) {
                console.error('[CARD IMAGE ERROR]', err ? err.message : 'File not created');
                return resolve(null);
            }
            resolve(outPath);
        });
    });
}

module.exports = { generateCardImage };
