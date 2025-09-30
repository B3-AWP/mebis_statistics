// Frontend Logging System für Mebis Dashboard
// Ersetzt console.log mit konfigurierbaren Log-Levels

class DashboardLogger {
    constructor() {
        // Log-Levels (höhere Nummer = weniger wichtig)
        this.levels = {
            ERROR: 0,
            WARN: 1,
            INFO: 2,
            DEBUG: 3
        };

        // Bestimme Log-Level basierend auf Environment
        this.isDevelopment = this.checkDevelopmentMode();
        this.logLevel = this.getLogLevel();

        // Environment-Settings werden später vom Backend geladen
        this.backendEnvironment = null;
    }

    checkDevelopmentMode() {
        // 1. Prüfe Backend-Settings (wenn verfügbar)
        if (this.backendEnvironment) {
            return this.backendEnvironment.mode === 'development';
        }

        // 2. Fallback: Lokale Erkennung
        return (
            window.location.hostname === 'localhost' ||
            window.location.hostname === '127.0.0.1' ||
            window.location.search.includes('debug=true') ||
            localStorage.getItem('dashboard_debug') === 'true'
        );
    }

    setBackendEnvironment(environment) {
        // Wird vom Dashboard nach API-Call aufgerufen
        this.backendEnvironment = environment;
        this.isDevelopment = this.checkDevelopmentMode();
        this.logLevel = this.getLogLevel();

        this.info('SYSTEM', 'Environment loaded from backend', environment);
    }

    getLogLevel() {
        // Hole Log-Level aus localStorage oder verwende Default
        const savedLevel = localStorage.getItem('dashboard_log_level');
        if (savedLevel && this.levels.hasOwnProperty(savedLevel)) {
            return this.levels[savedLevel];
        }

        // Default: INFO in Production, DEBUG in Development
        return this.isDevelopment ? this.levels.DEBUG : this.levels.INFO;
    }

    setLogLevel(level) {
        if (this.levels.hasOwnProperty(level)) {
            this.logLevel = this.levels[level];
            localStorage.setItem('dashboard_log_level', level);
        }
    }

    shouldLog(level) {
        return this.levels[level] <= this.logLevel;
    }

    formatMessage(level, category, message, data = null) {
        const timestamp = new Date().toISOString().substr(11, 12); // HH:MM:SS.mmm
        const prefix = `[${timestamp}] ${level} [${category}]`;

        if (data) {
            return { message: `${prefix} ${message}`, data: data };
        }
        return { message: `${prefix} ${message}` };
    }

    error(category, message, data = null) {
        if (this.shouldLog('ERROR')) {
            const formatted = this.formatMessage('ERROR', category, message, data);
            if (data) {
                console.error(formatted.message, formatted.data);
            } else {
                console.error(formatted.message);
            }
        }
    }

    warn(category, message, data = null) {
        if (this.shouldLog('WARN')) {
            const formatted = this.formatMessage('WARN', category, message, data);
            if (data) {
                console.warn(formatted.message, formatted.data);
            } else {
                console.warn(formatted.message);
            }
        }
    }

    info(category, message, data = null) {
        if (this.shouldLog('INFO')) {
            const formatted = this.formatMessage('INFO', category, message, data);
            if (data) {
                console.info(formatted.message, formatted.data);
            } else {
                console.info(formatted.message);
            }
        }
    }

    debug(category, message, data = null) {
        if (this.shouldLog('DEBUG')) {
            const formatted = this.formatMessage('DEBUG', category, message, data);
            if (data) {
                console.debug(formatted.message, formatted.data);
            } else {
                console.debug(formatted.message);
            }
        }
    }

    // Spezielle Methoden für Migration von bestehenden console.log Statements
    dataLoaded(message, data = null) {
        this.info('DATA', message, data);
    }

    userAction(message, data = null) {
        this.debug('USER', message, data);
    }

    calculation(message, data = null) {
        this.debug('CALC', message, data);
    }

    apiCall(message, data = null) {
        this.info('API', message, data);
    }

    performance(message, data = null) {
        this.debug('PERF', message, data);
    }
}

// Globale Logger-Instanz
const dashboardLogger = new DashboardLogger();

// Convenience-Funktionen für einfache Migration
function logError(category, message, data = null) {
    dashboardLogger.error(category, message, data);
}

function logWarn(category, message, data = null) {
    dashboardLogger.warn(category, message, data);
}

function logInfo(category, message, data = null) {
    dashboardLogger.info(category, message, data);
}

function logDebug(category, message, data = null) {
    dashboardLogger.debug(category, message, data);
}

// Ersatz für häufige console.log Patterns
function debugLog(message, data = null) {
    dashboardLogger.debug('DEBUG', message, data);
}

// Development Tools
if (dashboardLogger.isDevelopment) {
    // Füge Debug-Tools zum Window hinzu
    window.dashboardDebug = {
        setLogLevel: (level) => dashboardLogger.setLogLevel(level),
        enableDebug: () => {
            localStorage.setItem('dashboard_debug', 'true');
            dashboardLogger.isDevelopment = true;
            dashboardLogger.logLevel = dashboardLogger.levels.DEBUG;
        },
        disableDebug: () => {
            localStorage.removeItem('dashboard_debug');
            location.reload();
        },
        clearLogs: () => console.clear(),
        logger: dashboardLogger
    };

    console.info('Dashboard Debug Tools verfügbar unter window.dashboardDebug');
}