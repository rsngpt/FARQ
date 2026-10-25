const path = require('path');
require('dotenv').config();

module.exports = {
    port: process.env.PORT || 3000,
    paths: {
        storageDir: path.resolve(__dirname, '../media_storage'),
        jobsFile: path.resolve(__dirname, '../media_storage/jobs.json'),
        authDir: path.resolve(__dirname, '../baileys_auth')
    },
    backend: {
        baseUrl: process.env.FARQ_API_BASE_URL || process.env.DEEPFAKE_BACKEND_URL || 'http://localhost:5001',
        apiKey: process.env.FARQ_API_KEY || 'farq_secret_key_2026',
        timeoutMs: parseInt(process.env.BACKEND_TIMEOUT_MS, 10) || 60000
    },
    security: {
        userHashPepper: process.env.USER_HASH_PEPPER || 'farq_pepper_secret_2026',
        callbackSecret: process.env.FARQ_CALLBACK_SECRET || 'farq_callback_secret_2026'
    }
};
