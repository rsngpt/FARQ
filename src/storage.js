const fs = require('fs');
const path = require('path');
const mime = require('mime-types');
const config = require('./config');

// Ensure media storage directory exists
if (!fs.existsSync(config.paths.storageDir)) {
    fs.mkdirSync(config.paths.storageDir, { recursive: true });
}

/**
 * Save incoming media buffer to disk
 * @param {Buffer} buffer - Raw media buffer
 * @param {string} id - WhatsApp message ID
 * @param {string} rawMime - Mime type from message
 * @param {string} typeHint - 'image' | 'video' | 'audio'
 * @returns {{ name: string, path: string, mimetype: string, sizeBytes: number }}
 */
function saveMedia(buffer, id, rawMime, typeHint) {
    const ext = mime.extension(rawMime) || (typeHint === 'audio' ? 'ogg' : 'bin');
    const fileName = `${Date.now()}_${id}.${ext}`;
    const filePath = path.join(config.paths.storageDir, fileName);

    fs.writeFileSync(filePath, buffer);
    console.log(`[MEDIA STORED] ${fileName} (${(buffer.length / 1024).toFixed(1)} KB)`);

    return {
        name: fileName,
        path: filePath,
        mimetype: rawMime,
        sizeBytes: buffer.length
    };
}

/**
 * Append or update a job in jobs.json for the deepfake backend
 * @param {Object} job
 */
function recordJob(job) {
    let jobs = [];
    try {
        if (fs.existsSync(config.paths.jobsFile)) {
            jobs = JSON.parse(fs.readFileSync(config.paths.jobsFile, 'utf8') || '[]');
        }
    } catch {
        jobs = [];
    }

    jobs.unshift(job);
    if (jobs.length > 50) jobs = jobs.slice(0, 50);

    fs.writeFileSync(config.paths.jobsFile, JSON.stringify(jobs, null, 2));
    console.log(`[JOB RECORDED] Staged job ${job.jobId} in jobs.json`);
}

/**
 * Read all currently queued jobs
 */
function getJobs() {
    try {
        if (fs.existsSync(config.paths.jobsFile)) {
            return JSON.parse(fs.readFileSync(config.paths.jobsFile, 'utf8') || '[]');
        }
    } catch {}
    return [];
}

function getRecentJobForUser(userRef) {
    const jobs = getJobs();
    return jobs.find(j => j.userRef === userRef);
}

module.exports = {
    saveMedia,
    recordJob,
    getJobs,
    getRecentJobForUser
};
