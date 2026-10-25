const { decryptPollVote } = require('@whiskeysockets/baileys');
const crypto = require('crypto');

/**
 * In-memory map of active polls:
 * pollMsgId -> { encKey, options, userRef, step }
 */
const activePolls = new Map();

/**
 * Send a native WhatsApp poll (supported across all devices with 1-tap voting)
 */
async function sendPoll(sock, jid, { name, values, selectableCount = 1 }, userRef, step) {
    const sent = await sock.sendMessage(jid, {
        poll: {
            name: name,
            values: values,
            selectableCount: selectableCount
        }
    });

    if (sent?.key?.id && sent?.message?.messageContextInfo?.messageSecret) {
        activePolls.set(sent.key.id, {
            encKey: sent.message.messageContextInfo.messageSecret,
            options: values,
            userRef: userRef,
            step: step
        });
        console.log(`[POLL SENT] Stored poll ${sent.key.id} (step ${step}) with secret`);
    }

    return sent;
}

/**
 * Send a clean interactive option list (fallback)
 */
async function sendOptionList(sock, jid, { title, body, footer, buttonText, sections }) {
    let text = '';
    if (title) text += `*${title}*\n`;
    text += `${body}\n\n`;

    if (sections && sections.length > 0) {
        sections.forEach(sec => {
            if (sec.title) text += `*${sec.title.toUpperCase()}*\n`;
            sec.rows.forEach((row, i) => {
                text += `*[${i + 1}]* ${row.title}\n`;
                if (row.description) {
                    text += `     _${row.description}_\n`;
                }
            });
            text += '\n';
        });
    }

    text += `👉 *Reply with a number (e.g. 1, 2) or tap an option.*`;
    if (footer) text += `\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n_${footer}_`;

    return await sock.sendMessage(jid, { text: text.trim() });
}

/**
 * Send clean quick-choice buttons (fallback)
 */
async function sendQuickButtons(sock, jid, { title, body, footer, buttons }) {
    let text = '';
    if (title) text += `*${title}*\n`;
    text += `${body}\n\n`;

    if (buttons && buttons.length > 0) {
        buttons.forEach((b, i) => {
            text += `*[${i + 1}]* ${b.text}\n`;
        });
        text += '\n';
    }

    text += `👉 *Reply [1] for "${buttons[0]?.text}" or [2] for "${buttons[1]?.text}".*`;
    if (footer) text += `\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n_${footer}_`;

    return await sock.sendMessage(jid, { text: text.trim() });
}

/**
 * Extract selected option ID or text from any incoming message (including Poll Votes!)
 */
function extractUserSelection(msg, sock, jid) {
    if (!msg || !msg.message) return '';

    // 1. Native WhatsApp Poll Vote (Decrypted)
    if (msg.message.pollUpdateMessage) {
        const pollKey = msg.message.pollUpdateMessage.pollCreationMessageKey;
        const pollId = pollKey?.id;
        const pollData = activePolls.get(pollId);

        if (pollData && pollData.encKey) {
            try {
                const voters = [jid, msg.key.remoteJid, msg.key.participant].filter(Boolean);
                const creators = [pollKey.participant, sock?.user?.id?.split(':')[0] + '@s.whatsapp.net', sock?.user?.lid].filter(Boolean);

                let vote = null;
                for (const c of creators) {
                    for (const v of voters) {
                        try {
                            vote = decryptPollVote({
                                encPayload: msg.message.pollUpdateMessage.vote.encPayload,
                                encIv: msg.message.pollUpdateMessage.vote.encIv
                            }, {
                                pollCreatorJid: c,
                                pollMsgId: pollId,
                                pollEncKey: pollData.encKey,
                                voterJid: v
                            });
                            if (vote && vote.selectedOptions && vote.selectedOptions.length > 0) break;
                        } catch {}
                    }
                    if (vote && vote.selectedOptions && vote.selectedOptions.length > 0) break;
                }

                if (vote && vote.selectedOptions && vote.selectedOptions.length > 0) {
                    for (const opt of pollData.options) {
                        const optHash = crypto.createHash('sha256').update(Buffer.from(opt)).digest();
                        if (vote.selectedOptions.some(sel => Buffer.from(sel).equals(optHash))) {
                            console.log(`[POLL VOTE DECRYPTED] User voted: "${opt}"`);
                            return opt;
                        }
                    }
                }
            } catch (err) {
                console.warn('[POLL DECRYPT WARN]', err.message);
            }
        }
    }

    // 2. Native flow response
    const nativeRes = msg.message.interactiveResponseMessage?.nativeFlowResponseMessage;
    if (nativeRes && nativeRes.paramsJson) {
        try {
            const parsed = JSON.parse(nativeRes.paramsJson);
            if (parsed.id) return String(parsed.id);
        } catch {}
    }

    // 3. Legacy list response
    const listRowId = msg.message.listResponseMessage?.singleSelectReply?.selectedRowId;
    if (listRowId) return String(listRowId);

    // 4. Button response
    const buttonId = msg.message.buttonsResponseMessage?.selectedButtonId || msg.message.templateButtonReplyMessage?.selectedId;
    if (buttonId) return String(buttonId);

    // 5. Standard text or caption
    const text = (
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        msg.message.imageMessage?.caption ||
        msg.message.videoMessage?.caption ||
        ''
    ).trim();

    return text;
}

module.exports = {
    sendPoll,
    sendOptionList,
    sendQuickButtons,
    extractUserSelection,
    activePolls
};
