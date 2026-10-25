const config = require('./config');

/**
 * Guided Questions Manager (Section 5.4 & 6.4 of FARQ Spec)
 * Delivers native option drawers and buttons (Zero polls).
 */
class GuidedQuestionsManager {
    constructor() {
        this.activeSessions = new Map(); // keyed by userRef
        this.lastCompletedAnswers = new Map(); // userRef -> { caseId, answers }
    }

    setBackendCaseId(userRef, backendCaseId) {
        const session = this.activeSessions.get(userRef);
        if (session) {
            session.caseId = backendCaseId;
            console.log(`[QUESTIONS] Updated session caseId to backend UUID: ${backendCaseId}`);
        }
        const last = this.lastCompletedAnswers.get(userRef);
        if (last && last.answers) {
            console.log(`[QUESTIONS] Dispatching queued answers to backend UUID: ${backendCaseId}`);
            this.dispatchAnswersToBackend(backendCaseId, last.answers).catch(() => {});
            this.lastCompletedAnswers.delete(userRef);
        }
    }

    start(userRef, caseId) {
        this.activeSessions.set(userRef, {
            caseId,
            step: 1,
            answers: {},
            startedAt: Date.now()
        });

        return this.getQuestion1Payload();
    }

    hasActive(userRef) {
        return this.activeSessions.has(userRef);
    }

    end(userRef) {
        this.activeSessions.delete(userRef);
    }

    getAnswers(userRef) {
        const session = this.activeSessions.get(userRef);
        if (session && session.answers) return session.answers;
        const last = this.lastCompletedAnswers.get(userRef);
        return (last && last.answers) || {};
    }

    getQuestion1Payload() {
        return {
            type: 'poll',
            step: 1,
            name: '🏛️ 1. Who is it claiming to be?',
            values: [
                '🏛️ Govt / RBI / Police',
                '🌟 Famous Person / Expert',
                '🏦 Bank or UPI App',
                '👥 Family or Friend',
                '🏢 Company or Boss',
                '❓ Not Sure'
            ],
            selectableCount: 1
        };
    }

    getQuestion2Payload() {
        return {
            type: 'poll',
            step: 2,
            name: '📈 2. What do they want you to do?',
            values: [
                '📈 Invest in Trading App',
                '💸 Send Money / Transfer',
                '🔑 OTP, Link or KYC',
                '⏳ Nothing Yet'
            ],
            selectableCount: 1
        };
    }

    getQuestion3Payload() {
        return {
            type: 'poll',
            step: 3,
            name: '🚨 3. Have you already sent any money?',
            values: [
                '🚨 Yes, Sent Money',
                '🛡️ Not Yet'
            ],
            selectableCount: 1
        };
    }

    async handleResponse(userRef, rawInput) {
        const session = this.activeSessions.get(userRef);
        if (!session) return null;

        const input = (rawInput || '').trim().toLowerCase();

        // Step 1: Who is it claiming to be?
        if (session.step === 1) {
            let choice = 'not_sure';
            if (input === 'ans_official' || input === '1' || input.includes('govt') || input.includes('rbi') || input.includes('official') || input.includes('police')) {
                choice = 'official';
            } else if (input === 'ans_famous' || input === '2' || input.includes('famous') || input.includes('expert')) {
                choice = 'famous_expert';
            } else if (input === 'ans_bank' || input === '3' || input.includes('bank') || input.includes('upi')) {
                choice = 'bank_upi';
            } else if (input === 'ans_family' || input === '4' || input.includes('family') || input.includes('friend')) {
                choice = 'family_friend';
            } else if (input === 'ans_boss' || input === '5' || input.includes('boss') || input.includes('company')) {
                choice = 'company_boss';
            }

            session.answers.claims_to_be = choice;
            session.step = 2;
            console.log(`[QUESTIONS] User ${userRef.slice(0, 8)} Q1 Answer: ${choice}`);

            return {
                nextPayload: this.getQuestion2Payload(),
                completed: false
            };
        }

        // Step 2: What do they want?
        if (session.step === 2) {
            let choice = 'nothing_yet';
            if (input === 'ans_invest' || input === '1' || input.includes('invest') || input.includes('trading') || input.includes('app')) {
                choice = 'invest';
            } else if (input === 'ans_money' || input === '2' || input.includes('send') || input.includes('money') || input.includes('transfer')) {
                choice = 'send_money';
            } else if (input === 'ans_otp' || input === '3' || input.includes('otp') || input.includes('link') || input.includes('kyc')) {
                choice = 'otp_link_kyc';
            }

            session.answers.asks_for = choice;
            session.step = 3;
            console.log(`[QUESTIONS] User ${userRef.slice(0, 8)} Q2 Answer: ${choice}`);

            return {
                nextPayload: this.getQuestion3Payload(),
                completed: false
            };
        }

        // Step 3: Have you already sent money?
        if (session.step === 3) {
            const isYes = input === 'ans_yes' || input === '1' || input === 'yes' || input.includes('sent') || input.includes('paid');
            session.answers.money_sent = isYes;
            console.log(`[QUESTIONS] User ${userRef.slice(0, 8)} Q3 Answer (money_sent): ${isYes}`);

            const finalAnswers = { ...session.answers };
            const caseId = session.caseId;
            this.activeSessions.delete(userRef);
            this.lastCompletedAnswers.set(userRef, { caseId, answers: finalAnswers });

            // Send PATCH to backend in background
            if (caseId && caseId.includes('-')) {
                this.dispatchAnswersToBackend(caseId, finalAnswers).catch(() => {});
            }

            if (isYes) {
                return {
                    completed: true,
                    answers: finalAnswers,
                    emergencyAlert:
`🚨 *Call 1930 now* (national cyber fraud helpline) and call your bank's official number to block the payment.

The sooner you report, the better the chance of recovery.
I will keep checking the video and send you a report you can file.`
                };
            }

            return {
                completed: true,
                answers: finalAnswers,
                confirmation: `✅ *Answers recorded.* Verifying media against official speeches...`
            };
        }

        return null;
    }

    async dispatchAnswersToBackend(caseId, answers) {
        const backend = require('./backend');
        return await backend.patchAnswers(caseId, answers);
    }
}

module.exports = new GuidedQuestionsManager();
