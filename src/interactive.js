/**
 * WhatsApp Interactive Message Manager
 * Renders beautifully formatted option cards that work reliably across all
 * WhatsApp clients (iOS, Android, Web, Desktop) without getting dropped by Meta.
 */

/**
 * Send a clean interactive option list
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
 * Send clean quick-choice buttons
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
 * Extract selected option ID or text from any incoming message
 */
function extractUserSelection(msg) {
    if (!msg || !msg.message) return '';

    // 1. Native flow response
    const nativeRes = msg.message.interactiveResponseMessage?.nativeFlowResponseMessage;
    if (nativeRes && nativeRes.paramsJson) {
        try {
            const parsed = JSON.parse(nativeRes.paramsJson);
            if (parsed.id) return String(parsed.id);
        } catch {}
    }

    // 2. Legacy list response
    const listRowId = msg.message.listResponseMessage?.singleSelectReply?.selectedRowId;
    if (listRowId) return String(listRowId);

    // 3. Button response
    const buttonId = msg.message.buttonsResponseMessage?.selectedButtonId || msg.message.templateButtonReplyMessage?.selectedId;
    if (buttonId) return String(buttonId);

    // 4. Standard text or caption
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
    sendOptionList,
    sendQuickButtons,
    extractUserSelection
};
