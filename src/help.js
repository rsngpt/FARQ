/**
 * FARQ Consultation & Advisory Module
 * Provides native option lists and clean guidance for financial scam triage.
 */

class ConsultationManager {
    constructor() {
        this.consultingUsers = new Set();
    }

    startConsultation(userRef) {
        this.consultingUsers.add(userRef);
    }

    endConsultation(userRef) {
        this.consultingUsers.delete(userRef);
    }

    isConsulting(userRef) {
        return this.consultingUsers.has(userRef);
    }

    /**
     * Payload for WhatsApp Native Option List
     */
    getConsultationMenuPayload() {
        return {
            title: '🛡️ FARQ Fraud Advisory & Help Desk',
            body: 
`_Your 24/7 Shield Against Financial Cyber Scams_
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 *What We Inspect:*
• *Deepfake Videos* — Fabricated VIP trading endorsements & fake schemes
• *Cloned Voices* — Urgent voice notes demanding transfers
• *Scam Messages* — Task jobs, fake APKs, & phishing links

Tap below to select a topic and consult our advisory assistant:`,
            footer: 'FARQ • Team Off-Grid',
            buttonText: '📋 Select a Topic',
            sections: [
                {
                    title: 'Fraud Consultation Topics',
                    rows: [
                        { id: 'opt_call', title: '📞 Digital Arrest / Police Call', description: 'Fake Police, CBI, ED, TRAI video calls' },
                        { id: 'opt_trading', title: '📈 Viral Trading Video', description: 'Deepfakes of FM, RBI Governor, VIPs' },
                        { id: 'opt_task', title: '📱 WhatsApp Task / Job Scam', description: 'Like YouTube videos, advance deposits' },
                        { id: 'opt_emergency', title: '🚨 Emergency: Already Paid', description: 'Immediate 1930 & bank freeze protocol' },
                        { id: 'opt_privacy', title: 'ℹ️ How FARQ Works & Privacy', description: 'Detection insight & privacy rules' }
                    ]
                }
            ]
        };
    }

    /**
     * Handle user selection (supports both option IDs and text replies)
     */
    handleChoice(userRef, rawInput) {
        const input = (rawInput || '').trim().toLowerCase();

        // 1. Digital Arrest / Fake Police Call
        if (input === 'opt_call' || input === '1' || input.includes('call') || input.includes('police') || input.includes('cbi') || input.includes('arrest')) {
            return `📞 *Advisory: Digital Arrest & Fake Police Calls*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ *Critical Facts:*
• Real Police, CBI, ED, or TRAI *never* interrogate or arrest citizens over WhatsApp or Skype video calls.
• Real courts never ask you to transfer funds to a "verification account" or "security deposit".

🛡️ *Action Plan:*
1. *Hang up immediately.* Do not stay on the call.
2. *Do not transfer funds* or share Aadhaar/OTP.
3. If they sent a fake warrant/notice, forward the photo here.

📞 Dial *1930* or visit *cybercrime.gov.in* immediately if threatened.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_Reply *menu* to return, or forward any document to check._`;
        }

        // 2. Viral Stock / Trading Video
        if (input === 'opt_trading' || input === '2' || input.includes('stock') || input.includes('trading') || input.includes('video') || input.includes('invest')) {
            return `📈 *Advisory: Viral Stock & Trading Videos*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ *How This Scam Works:*
Scammers take authentic public speeches (e.g. Finance Minister, RBI Governor) and use AI to re-sync their lips to promote fake trading apps or Telegram groups.

🔍 *Red Flags:*
• Unnatural mouth movement while head and body move normally.
• Promises of "guaranteed 300% returns" or "zero-risk AI trading".
• Directing you to private Telegram channels or WhatsApp links.

🛡️ *Action Plan:*
Forward the video to this chat right now. FARQ will verify it against official speech archives.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_Forward the video here to start, or reply *menu*._`;
        }

        // 3. Task / Job Scam
        if (input === 'opt_task' || input === '3' || input.includes('job') || input.includes('task') || input.includes('part-time')) {
            return `📱 *Advisory: Task & Part-Time Job Scams*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ *How This Scam Works:*
1. Offers ₹2,000–₹10,000/day for "liking YouTube videos" or "hotel reviews".
2. Pays ₹150 initially to build false trust.
3. Then demands "prepaid deposits" to unlock your accumulated earnings.

🛡️ *Action Plan:*
• Cut off communication immediately.
• Never pay money to withdraw your own earnings.
• Never install `.apk` files sent over WhatsApp.

Forward the scam message or phone number here to log the evidence.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_Reply *menu* to return, or forward the message._`;
        }

        // 4. Emergency: Already Sent Money
        if (input === 'opt_emergency' || input === '4' || input.includes('paid') || input.includes('sent') || input.includes('emergency') || input.includes('lost')) {
            return `🚨 *EMERGENCY PROTOCOL (MONEY ALREADY SENT)*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏱️ *Every minute counts for fund recovery:*

1. 📞 *Call 1930 Immediately*
   National Cyber Crime Reporting Helpline. They can freeze the recipient's bank account before funds are withdrawn.

2. 🏦 *Call Your Bank's Fraud Desk*
   Number on the back of your card. Request an immediate fraud block and reversal.

3. 📁 *Generate Evidence Report*
   Forward the scam video or chat screenshot here to receive a ready-to-file police PDF for *cybercrime.gov.in*.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_Type */farq* to start evidence intake._`;
        }

        // 5. How FARQ Works & Privacy
        if (input === 'opt_privacy' || input === '5' || input.includes('how') || input.includes('privacy') || input.includes('about')) {
            return `ℹ️ *How FARQ Protects You & Privacy Guarantee*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 *Core Detection Insight:*
_"The face is real. The voice is real. The video is fake."_
FARQ checks whether the pieces belong together by matching head/body motion against voice pitch and searching official archives.

🔒 *Privacy Rules:*
• Phone numbers are *never stored or shared* (irreversible cryptographic HMAC hashes only).
• Downloaded media is deleted after verification.
• Send *"delete my data"* anytime to wipe your case history.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_Reply *menu* to return, or forward media to check._`;
        }

        return null;
    }
}

module.exports = new ConsultationManager();
