/**
 * Session Manager
 * Sessions are strictly opt-in: only initiated if a user writes /farq first.
 */
class SessionManager {
    constructor() {
        this.activeSessions = new Set(); // JIDs of currently active sessions
    }

    start(jid) {
        this.activeSessions.add(jid);
        return true;
    }

    end(jid) {
        this.activeSessions.delete(jid);
        return false;
    }

    toggle(jid) {
        if (this.isActive(jid)) {
            this.activeSessions.delete(jid);
            return false; // now idle
        } else {
            this.activeSessions.add(jid);
            return true; // now active
        }
    }

    isActive(jid) {
        return this.activeSessions.has(jid);
    }

    count() {
        return this.activeSessions.size;
    }
}

module.exports = new SessionManager();
