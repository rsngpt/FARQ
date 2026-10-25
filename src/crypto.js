const crypto = require('crypto');
const config = require('./config');

/**
 * Generate privacy-preserving keyed hash (user_ref) from phone number/JID.
 * Never stores or transmits raw phone numbers.
 */
function getUserRef(jid) {
    if (!jid) return 'anonymous';
    const cleanNumber = jid.split('@')[0];
    return crypto
        .createHmac('sha256', config.security.userHashPepper)
        .update(cleanNumber)
        .digest('hex');
}

/**
 * Verify HMAC signature of backend callbacks
 */
function verifySignature(payload, signatureHeader) {
    if (!signatureHeader || !signatureHeader.startsWith('sha256=')) return false;
    const expectedSig = signatureHeader.slice(7);
    const computedSig = crypto
        .createHmac('sha256', config.security.callbackSecret)
        .update(payload)
        .digest('hex');
    return crypto.timingSafeEqual(Buffer.from(expectedSig), Buffer.from(computedSig));
}

module.exports = {
    getUserRef,
    verifySignature
};
