const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcodeTerminal = require('qrcode-terminal');
const QRCode = require('qrcode');
const http = require('http');
const fs = require('fs');

let latestQrDataUrl = null;
let isConnected = false;

// 1. Web server to show the QR code cleanly in the browser at http://localhost:3000
const server = http.createServer((req, res) => {
    if (isConnected) {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        return res.end(`
            <!DOCTYPE html>
            <html>
            <head><title>FARQ Bot Connected</title><meta http-equiv="refresh" content="10"></head>
            <body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 90vh; background: #0f172a; color: white;">
                <h1 style="color: #22c55e;">✅ FARQ WhatsApp Bot is Connected & Active!</h1>
                <p>Send <b>/FARQ</b> in any WhatsApp chat to test the bot.</p>
            </body>
            </html>
        `);
    }

    if (latestQrDataUrl) {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        return res.end(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Scan WhatsApp QR Code</title>
                <meta http-equiv="refresh" content="5">
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 90vh; background: #0f172a; color: white; margin: 0; }
                    .card { background: #1e293b; padding: 32px; border-radius: 16px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
                    img { border-radius: 8px; margin: 16px 0; background: white; padding: 12px; }
                    .instructions { color: #94a3b8; font-size: 15px; max-width: 380px; line-height: 1.5; margin: 0 auto; }
                    .step { margin: 8px 0; text-align: left; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h2 style="margin: 0 0 10px 0;">Link FARQ WhatsApp Bot</h2>
                    <img src="${latestQrDataUrl}" alt="WhatsApp QR Code" width="280" height="280" />
                    <div class="instructions">
                        <div class="step">1. Open <b>WhatsApp</b> on your phone</div>
                        <div class="step">2. Go to <b>Settings</b> &gt; <b>Linked Devices</b></div>
                        <div class="step">3. Tap <b>Link a Device</b> and point camera here</div>
                    </div>
                </div>
            </body>
            </html>
        `);
    }

    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(`
        <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 90vh; background: #0f172a; color: white;">
            <h2>Generating QR code, please wait 5 seconds and refresh...</h2>
            <script>setTimeout(() => location.reload(), 3000);</script>
        </body>
    `);
});

server.listen(3000, () => {
    console.log('[WEB UI] Open http://localhost:3000 in your browser to scan the QR code visually!');
});

// 2. WhatsApp Client Initialization
const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const puppeteerConfig = {
    headless: true,
    args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--no-first-run',
        '--no-zygote',
        '--disable-gpu'
    ]
};

if (process.env.PUPPETEER_EXECUTABLE_PATH) {
    puppeteerConfig.executablePath = process.env.PUPPETEER_EXECUTABLE_PATH;
} else if (fs.existsSync(chromePath)) {
    puppeteerConfig.executablePath = chromePath;
}

const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: './.wwebjs_auth'
    }),
    puppeteer: puppeteerConfig
});

client.on('qr', async (qr) => {
    console.log('\n[QR] New QR code generated!');
    qrcodeTerminal.generate(qr, { small: true });

    try {
        latestQrDataUrl = await QRCode.toDataURL(qr, { width: 300, margin: 2 });
        await QRCode.toFile('./qr.png', qr, { width: 400, margin: 2 });
        console.log('[QR] Saved crisp image to ./qr.png and available on http://localhost:3000');
    } catch (e) {
        console.error('Error generating QR image:', e);
    }
});

client.on('authenticated', () => {
    console.log('[AUTH] Authentication successful! Session stored in .wwebjs_auth');
});

client.on('auth_failure', (msg) => {
    console.error('[AUTH ERROR] Authentication failure:', msg);
});

client.on('ready', () => {
    isConnected = true;
    console.log('\n=================================================');
    console.log('  FARQ WhatsApp Bot is now ONLINE and ready!     ');
    console.log('  Trigger configured: ONLY responds to /FARQ     ');
    console.log('=================================================\n');
});

// 3. Message Trigger - ONLY triggers on "/FARQ"
client.on('message', async (msg) => {
    // Ignore status broadcast updates
    if (msg.from === 'status@broadcast') return;

    const rawText = (msg.body || '').trim();

    // Check if message starts with or equals "/FARQ" (case-insensitive)
    const match = rawText.match(/^\/FARQ(\s+.*)?$/i);
    if (!match) {
        // Do NOT trigger for any other message
        return;
    }

    const commandArg = (match[1] || '').trim();
    console.log(`\n[TRIGGERED /FARQ] From: ${msg.from}`);
    console.log(`[QUERY] "${commandArg}"`);

    if (!commandArg) {
        await msg.reply(
`🛡️ *FARQ Bot Online*

Usage:
• \`/FARQ <query>\` - Ask FARQ a question or verify information
• \`/FARQ help\` - Show bot commands
• \`/FARQ status\` - Check bot server health`
        );
        return;
    }

    const lowerArg = commandArg.toLowerCase();

    if (lowerArg === 'help') {
        await msg.reply(
`📖 *FARQ Commands Help*
• \`/FARQ <text>\` : Send your query or claim to FARQ
• \`/FARQ status\` : Check current uptime and connectivity
• \`/FARQ ping\`   : Check response latency`
        );
    } else if (lowerArg === 'status' || lowerArg === 'ping') {
        await msg.reply(`✅ *FARQ Bot* is running active and connected! (Uptime: ${Math.round(process.uptime())}s)`);
    } else {
        // Placeholder for FARQ processing / AI / Verification logic
        await msg.reply(`🔍 *FARQ Processed Request:*\n\n"${commandArg}"\n\n_(FARQ core response active)_`);
    }
});

client.on('disconnected', (reason) => {
    isConnected = false;
    console.log('[DISCONNECTED] Bot was disconnected:', reason);
});

client.initialize();
