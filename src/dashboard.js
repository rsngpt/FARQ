const http = require('http');
const config = require('./config');
const storage = require('./storage');
const session = require('./session');

let isConnected = false;
let latestQrDataUrl = null;

function setConnected(status) {
    isConnected = status;
}

function setQrCode(dataUrl) {
    latestQrDataUrl = dataUrl;
}

const server = http.createServer((req, res) => {
    // API endpoint to dispatch verdict or message
    if (req.url === '/api/send-verdict' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => { body += chunk; });
        req.on('end', async () => {
            try {
                const data = JSON.parse(body);
                const { getCurrentSock } = require('./whatsapp');
                const sock = getCurrentSock();
                if (!sock) {
                    res.writeHead(503, { 'Content-Type': 'application/json' });
                    return res.end(JSON.stringify({ error: 'Socket not connected' }));
                }
                const jid = data.jid || '47339163119817@lid';
                if (data.text) {
                    await sock.sendMessage(jid, { text: data.text });
                }
                if (data.imageUrl) {
                    await sock.sendMessage(jid, {
                        image: { url: data.imageUrl },
                        caption: data.caption || ''
                    });
                }
                console.log(`[DISPATCH] Sent verdict message to ${jid}`);
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true }));
            } catch (err) {
                console.error('[DISPATCH ERROR]', err.message);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: err.message }));
            }
        });
        return;
    }

    // API endpoint for deepfake backend / judges
    if (req.url === '/jobs') {
        const jobs = storage.getJobs();
        res.writeHead(200, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify({
            isConnected,
            activeSessions: session.count(),
            totalJobs: jobs.length,
            jobs
        }, null, 2));
    }

    // Web Status UI
    res.writeHead(200, { 'Content-Type': 'text/html' });
    if (isConnected) {
        return res.end(`
            <!DOCTYPE html>
            <html>
            <head><title>FARQ WhatsApp Intake Engine</title><meta http-equiv="refresh" content="5"></head>
            <body style="font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 90vh; background: #0f172a; color: white; margin: 0;">
                <div style="background: #1e293b; padding: 32px; border-radius: 16px; max-width: 500px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                    <h1 style="color: #22c55e; margin: 0 0 12px 0; font-size: 22px;">🛡️ FARQ WhatsApp Intake Active</h1>
                    <p style="color: #94a3b8; line-height: 1.6;">Protocol: <b>Baileys WebSocket (Zero Browser)</b></p>
                    <p style="color: #94a3b8;">Active Intake Sessions: <b>${session.count()}</b></p>
                    <p style="color: #94a3b8;">Queued Media Jobs: <b>${storage.getJobs().length}</b></p>
                    <p style="margin-top: 20px;"><a href="/jobs" style="color: #38bdf8; text-decoration: none; font-weight: 500;">📂 View Staged Jobs JSON (/jobs)</a></p>
                </div>
            </body>
            </html>
        `);
    }

    if (latestQrDataUrl) {
        return res.end(`
            <!DOCTYPE html>
            <html>
            <head><title>Link WhatsApp Bot</title><meta http-equiv="refresh" content="4"></head>
            <body style="font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 90vh; background: #0f172a; color: white; margin: 0;">
                <div style="background: #1e293b; padding: 32px; border-radius: 16px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                    <h2>Link FARQ WhatsApp Bot</h2>
                    <img src="${latestQrDataUrl}" alt="WhatsApp QR Code" width="280" height="280" style="border-radius: 8px; background: white; padding: 12px; margin: 16px 0;" />
                    <p style="color: #94a3b8;">WhatsApp &gt; Settings &gt; Linked Devices &gt; Link a Device</p>
                </div>
            </body>
            </html>
        `);
    }

    res.end(`
        <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 90vh; background: #0f172a; color: white;">
            <h2>Connecting WhatsApp WebSocket... please wait 2 seconds.</h2>
            <script>setTimeout(() => location.reload(), 2000);</script>
        </body>
    `);
});

function startDashboard() {
    server.listen(config.port, () => {
        console.log(`[DASHBOARD] Web status running at http://localhost:${config.port}`);
    });
}

module.exports = {
    startDashboard,
    setConnected,
    setQrCode
};
