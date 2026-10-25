const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    downloadMediaMessage
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const QRCode = require('qrcode');
const qrcodeTerminal = require('qrcode-terminal');
const config = require('./config');
const storage = require('./storage');
const session = require('./session');
const dashboard = require('./dashboard');
const backend = require('./backend');
const crypto = require('./crypto');
const questions = require('./questions');
const help = require('./help');
const interactive = require('./interactive');
const imageCard = require('./image_card');
const fs = require('fs');

let currentSock = null;

function getCurrentSock() {
    return currentSock;
}

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState(config.paths.authDir);

    const sock = makeWASocket({
        auth: state,
        logger: pino({ level: 'silent' }),
        printQRInTerminal: false,
        browser: ['FARQ Bot', 'Chrome', '1.0.0']
    });

    sock.ev.on('creds.update', saveCreds);

    // Connection Lifecycle
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log('\n[QR] New QR code generated!');
            qrcodeTerminal.generate(qr, { small: true });
            const dataUrl = await QRCode.toDataURL(qr, { width: 300, margin: 2 });
            dashboard.setQrCode(dataUrl);
            console.log(`[QR] Also available on http://localhost:${config.port}`);
        }

        if (connection === 'close') {
            currentSock = null;
            dashboard.setConnected(false);
            const shouldReconnect = (lastDisconnect?.error)?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log('[DISCONNECTED] Reason:', lastDisconnect?.error?.message, '| Reconnecting:', shouldReconnect);
            if (shouldReconnect) {
                setTimeout(connectToWhatsApp, 3000);
            }
        } else if (connection === 'open') {
            currentSock = sock;
            dashboard.setConnected(true);
            console.log('\n======================================================');
            console.log('🛡️  FARQ WhatsApp Bot is LIVE (Team Off-Grid)');
            console.log('   Commands:                                          ');
            console.log('   • Start / Close session : /FARQ                    ');
            console.log('   • Advisory Help Desk    : /FARQ help               ');
            console.log('   • Force quit session   : /FARQ quit               ');
            console.log('   (Native interactive drawer menus & buttons active) ');
            console.log('======================================================\n');
        }
    });

    // Incoming Messages and Media Handler
    sock.ev.on('messages.upsert', async (m) => {
        if (m.type !== 'notify') return;

        for (const msg of m.messages) {
            if (!msg.message) continue;

            const jid = msg.key.remoteJid;
            if (jid === 'status@broadcast') continue;

            const userRef = crypto.getUserRef(jid);

            // Extract selected option ID or text from interactive UI / text / poll votes
            const selection = (interactive.extractUserSelection(msg, sock, jid) || '').trim();
            const lower = selection.toLowerCase();

            // Detect media presence
            const isMedia = !!(
                msg.message.imageMessage ||
                msg.message.videoMessage ||
                msg.message.audioMessage ||
                msg.message.documentMessage
            );

            let mediaType = 'text';
            if (msg.message.imageMessage) mediaType = 'image';
            else if (msg.message.videoMessage) mediaType = 'video';
            else if (msg.message.audioMessage) mediaType = 'audio';
            else if (msg.message.documentMessage) mediaType = 'document';

            const isForwarded = !!(
                msg.message[Object.keys(msg.message)[0]]?.contextInfo?.isForwarded
            );

            // Strict Initiation Rule: Only initiate if user writes /farq first
            const isFarqCommand = lower === '/farq' || lower.startsWith('/farq ') || lower.startsWith('/farq');
            if (!session.isActive(jid) && !isFarqCommand) {
                // Completely ignore all incoming messages and media from chats until /farq is sent
                continue;
            }

            // Command: Explicit /FARQ quit
            if (lower === '/farq quit' || lower === '/farq exit') {
                session.end(jid);
                help.endConsultation(userRef);
                questions.end(userRef);
                console.log(`[STANDBY] Session ended for ${userRef.slice(0, 8)}. Engine is idle.`);
                await sock.sendMessage(jid, {
                    text:
`🔴 *FARQ Intake Engine: STANDBY*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Session closed. Verification pipeline is now *OFFLINE*.
• Processing status: Idle (0% server usage)
• Staged session files preserved in ./media_storage/

Type */farq* or */farq help* anytime to reactivate.`
                }, { quoted: msg });
                continue;
            }

            // Command: /FARQ help (or 'help' / 'menu' if session is already active)
            if (lower === '/farq help' || (session.isActive(jid) && (lower === 'help' || lower === 'menu'))) {
                session.start(jid);
                help.startConsultation(userRef);
                console.log(`[HELP DESK] Sending Native Option Drawer to ${userRef.slice(0, 8)}`);

                // Send Native Option Drawer Menu
                await interactive.sendOptionList(sock, jid, help.getConsultationMenuPayload());
                continue;
            }

            // Command: /FARQ (Toggle Session On / Off)
            if (/^\/farq$/i.test(selection)) {
                const isNowActive = session.toggle(jid);

                if (isNowActive) {
                    console.log(`[ONLINE] Session activated for ${userRef.slice(0, 8)}.`);
                    const health = await backend.checkHealth();

                    await sock.sendMessage(jid, {
                        text:
`🟢 *FARQ Intake Engine: ONLINE*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ *Status:* Active & Listening
🛡️ *Focus:* Financial Scam & Collaged Video Detection
🌐 *Backend Model:* ${health.ok ? 'Connected (Live GPU)' : 'Standalone Local Demo Mode'}

*How to use:*
• Forward any suspicious *Video, Voice Note, Image, or Claim*.
• Or type */farq help* to open the fraud advisory helper desk.

Type */farq* again when finished to return engine to standby.`
                    }, { quoted: msg });
                } else {
                    help.endConsultation(userRef);
                    questions.end(userRef);
                    console.log(`[STANDBY] Session toggled off for ${userRef.slice(0, 8)}.`);
                    await sock.sendMessage(jid, {
                        text:
`🔴 *FARQ Intake Engine: STANDBY*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Session closed. Verification pipeline is now *OFFLINE*.
• Processing status: Idle (0% server usage)

Type */farq* anytime to reactivate.`
                    }, { quoted: msg });
                }
                continue;
            }

            // Safety check: Ignore if session is NOT active
            if (!session.isActive(jid)) {
                continue;
            }

            // Check if user is currently answering Guided Questions (via option tap or text)
            if (!isMedia && questions.hasActive(userRef)) {
                const qRes = await questions.handleResponse(userRef, selection);
                if (qRes) {
                    if (qRes.emergencyAlert) {
                        // 1930 Cyber Fraud Emergency fast-path (Section 6.4)
                        await sock.sendMessage(jid, { text: qRes.emergencyAlert });
                    } else if (qRes.nextPayload) {
                        if (qRes.nextPayload.type === 'poll') {
                            await interactive.sendPoll(sock, jid, qRes.nextPayload, userRef, qRes.nextPayload.step);
                        } else if (qRes.nextPayload.type === 'list') {
                            await interactive.sendOptionList(sock, jid, qRes.nextPayload);
                        } else if (qRes.nextPayload.type === 'buttons') {
                            await interactive.sendQuickButtons(sock, jid, qRes.nextPayload);
                        }
                    } else if (qRes.confirmation) {
                        await sock.sendMessage(jid, { text: qRes.confirmation });
                    }
                    continue;
                }
            } else if (!isMedia && !questions.hasActive(userRef) && (selection === '1' || selection === '2' || selection === '3')) {
                const recentJob = storage.getRecentJobForUser(userRef);
                if (recentJob) {
                    const targetCaseId = recentJob.backendCaseId || recentJob.caseId || recentJob.jobId;
                    console.log(`[QUESTIONS RECOVERY] Re-linking user ${userRef.slice(0, 8)} to case ${targetCaseId}`);
                    questions.start(userRef, targetCaseId);
                    const qRes = await questions.handleResponse(userRef, selection);
                    if (qRes) {
                        if (qRes.emergencyAlert) {
                            await sock.sendMessage(jid, { text: qRes.emergencyAlert });
                        } else if (qRes.nextPayload) {
                            if (qRes.nextPayload.type === 'poll') {
                                await interactive.sendPoll(sock, jid, qRes.nextPayload, userRef, qRes.nextPayload.step);
                            } else if (qRes.nextPayload.type === 'list') {
                                await interactive.sendOptionList(sock, jid, qRes.nextPayload);
                            } else if (qRes.nextPayload.type === 'buttons') {
                                await interactive.sendQuickButtons(sock, jid, qRes.nextPayload);
                            }
                        } else if (qRes.confirmation) {
                            await sock.sendMessage(jid, { text: qRes.confirmation });
                        }
                        continue;
                    }
                }
            }

            // Check if user is in Consultation Mode (asking advice via option tap or text)
            if (!isMedia && help.isConsulting(userRef)) {
                const advice = help.handleChoice(userRef, selection);
                if (advice) {
                    await sock.sendMessage(jid, { text: advice });
                    continue;
                }
            }

            // If user forwards or sends media/content, clear consultation and process case
            help.endConsultation(userRef);

            console.log(`\n======================================================`);
            console.log(`[ACTIVE INTAKE] UserRef: ${userRef.slice(0, 8)} | Type: ${mediaType} | Forwarded: ${isForwarded}`);
            console.log(`[CONTENT] "${selection || '(Binary Media File)'}"`);

            let savedFile = null;

            // 1. Download media directly from Baileys stream
            if (isMedia) {
                try {
                    console.log(`[DOWNLOADING] Ingesting ${mediaType} buffer...`);
                    const buffer = await downloadMediaMessage(msg, 'buffer', {});
                    if (buffer) {
                        const rawMime = (
                            msg.message.imageMessage?.mimetype ||
                            msg.message.videoMessage?.mimetype ||
                            msg.message.audioMessage?.mimetype ||
                            msg.message.documentMessage?.mimetype ||
                            ''
                        );
                        savedFile = storage.saveMedia(buffer, msg.key.id, rawMime, mediaType);
                    }
                } catch (err) {
                    console.error('[DOWNLOAD ERROR]', err.message);
                    await sock.sendMessage(jid, {
                        text: '❌ Could not ingest media file. Please try re-sending.'
                    }, { quoted: msg });
                    continue;
                }
            }

            // Generate clean case ID (c_...)
            const caseId = `c_${Date.now().toString(36)}_${Math.random().toString(36).substring(2, 6)}`;

            // Construct structured Deepfake Job
            const job = {
                caseId: caseId,
                jobId: caseId,
                userRef: userRef,
                receivedAt: new Date().toISOString(),
                mediaType: mediaType,
                isForwarded: isForwarded,
                content: selection,
                file: savedFile,
                status: 'QUEUED'
            };

            // Stage in jobs.json
            storage.recordJob(job);

            // 1. Instant Upload: POST /cases as soon as media arrives (Fix 1)
            console.log(`[INSTANT INTAKE] Uploading case ${caseId} to backend POST /cases right away...`);
            backend.createCase(job).then((caseRes) => {
                if (caseRes && caseRes.case_id) {
                    const backendUuid = caseRes.case_id;
                    job.backendCaseId = backendUuid;
                    job.caseId = backendUuid;
                    console.log(`[BACKEND ACCEPTED] Case UUID: ${backendUuid} | Initial Status: ${caseRes.status}`);

                    // Link UUID to active questions session (Fix 2: immediately dispatches answers)
                    questions.setBackendCaseId(userRef, backendUuid);

                    // 2. Poll GET /cases/{case_id} every 2-3s and show result as soon as status is 'done' (Fix 3)
                    backend.pollCaseUntilDone(backendUuid, async (analysis) => {
                        console.log(`[VERDICT READY] Case ${backendUuid} status is DONE. Generating visual verdict image...`);

                        // 1. Generate visual verdict PNG image card (A HUGE SCAM ALERT / LIKELY NOT A SCAM / NO SCAM FOUND)
                        const cardImagePath = await imageCard.generateCardImage(analysis);
                        const simplifiedText = backend.formatSimplifiedVerdict(analysis, job);

                        if (cardImagePath && fs.existsSync(cardImagePath)) {
                            console.log(`[SENDING VERDICT IMAGE] ${cardImagePath}`);
                            await sock.sendMessage(jid, {
                                image: { url: cardImagePath },
                                caption: simplifiedText
                            });
                        } else {
                            const replyCard = backend.formatVerdict(analysis, job);
                            await sock.sendMessage(jid, { text: replyCard });
                        }

                        if (analysis.timeline_image_url) {
                            try {
                                await sock.sendMessage(jid, {
                                    image: { url: analysis.timeline_image_url },
                                    caption: "Where this video came from"
                                });
                            } catch (err) {
                                console.warn('[TIMELINE IMAGE ERROR]', err.message);
                            }
                        }
                        console.log(`[REPLIED] Sent visual verdict for case ${backendUuid} (${analysis.verdict})`);
                        console.log(`======================================================\n`);
                    }, (err) => {
                        console.error(`[POLLER ERROR] Case ${backendUuid}:`, err.message);
                    }, 2500, 120); // 2.5-second interval, max 5 minutes
                }
            }).catch(async (err) => {
                console.warn(`[BACKEND UNAVAILABLE] Running in Standalone Local Demo Mode for case ${caseId} (${err.message})`);

                // Allow 12-14 seconds for user to tap through native WhatsApp polls
                setTimeout(async () => {
                    try {
                        const answers = questions.getAnswers(userRef) || {};
                        const localAnalysis = backend.generateLocalVerdict(job, answers);
                        console.log(`[STANDALONE VERDICT] Delivering local verdict card for ${caseId}...`);

                        const cardImagePath = await imageCard.generateCardImage(localAnalysis);
                        const simplifiedText = backend.formatSimplifiedVerdict(localAnalysis, job);

                        if (cardImagePath && fs.existsSync(cardImagePath)) {
                            console.log(`[SENDING STANDALONE IMAGE] ${cardImagePath}`);
                            await sock.sendMessage(jid, {
                                image: { url: cardImagePath },
                                caption: simplifiedText
                            });
                        } else {
                            const replyCard = backend.formatVerdict(localAnalysis, job);
                            await sock.sendMessage(jid, { text: replyCard });
                        }
                        console.log(`[STANDALONE REPLIED] Delivered standalone verdict card for case ${caseId}`);
                        console.log(`======================================================\n`);
                    } catch (cardErr) {
                        console.error('[STANDALONE CARD ERROR]', cardErr);
                    }
                }, 12000);
            });

            // 2. Concurrently start Guided Questions as Native WhatsApp Poll (Zero delay!)
            const q1Payload = questions.start(userRef, caseId);
            if (q1Payload.type === 'poll') {
                await interactive.sendPoll(sock, jid, q1Payload, userRef, 1);
            } else {
                await interactive.sendOptionList(sock, jid, q1Payload);
            }
            console.log(`======================================================\n`);
        }
    });
}

module.exports = {
    connectToWhatsApp,
    getCurrentSock
};
