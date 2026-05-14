/**
 * Jarvis Brain Dashboard — Frontend
 * Handles WebSocket, state updates, chat, emotion/hormone display
 */

(function () {
    'use strict';

    // ---------------------------------------------------------------------------
    // Configuration
    // ---------------------------------------------------------------------------
    const CFG = {
        WS_URL: () => `ws://${window.location.host}/ws`,
        MAX_EVENTS: 50,
        MAX_CHAT: 200,
        RECONNECT_DELAY: 3000,
        HEARTBEAT_INTERVAL: 30000,
    };

    // ---------------------------------------------------------------------------
    // State
    // ---------------------------------------------------------------------------
    const state = {
        connected: false,
        wsReconnectAttempts: 0,
        lastState: null,
        modules: {},          // module_id → module dict
        eventCount: 0,
        lastEventTs: 0,
        currentTab: 'brain',
        thinkingMode: 'REACTIVE',
        imaginationActive: false,
        chatReady: false,     // cleared welcome screen after first message
    };

    // ---------------------------------------------------------------------------
    // DOM helpers
    // ---------------------------------------------------------------------------
    const $ = (id) => document.getElementById(id);
    const els = {};

    function cacheElements() {
        els.statusDot        = $('status-dot');
        els.statusText       = $('status-text');
        els.statusIndicator  = $('status-indicator');
        els.timestamp        = $('current-timestamp');
        els.moduleList       = $('module-list');
        els.focusTags        = $('focus-tags');
        els.activeModulesList = $('active-modules-list');
        els.goalsList        = $('goals-list');
        els.eventLog         = $('event-log');
        els.eventCount       = $('event-count');
        els.tickCounter      = $('tick-counter');
        els.uptime           = $('uptime');
        els.queueSize        = $('queue-size');
        els.wsStatus         = $('ws-status');
        els.moduleCount      = $('module-count');
        els.apiLatency       = $('api-latency');
        els.shutdownModal    = $('shutdown-modal');
        els.loadModuleModal  = $('load-module-modal');
        els.monologueStream  = $('monologue-stream');
        els.thinkingModeBadge = $('thinking-mode-badge');
        // Chat
        els.chatMessages     = $('chat-messages');
        els.chatInput        = $('chat-input');
        els.chatSend         = $('chat-send');
        els.chatModeBadge    = $('chat-mode-badge');
        els.imaginationDot   = $('imagination-dot');
    }

    // ---------------------------------------------------------------------------
    // Utilities
    // ---------------------------------------------------------------------------
    const fmt = {
        time: (d = new Date()) => d.toLocaleTimeString('en-GB', { hour12: false }),
        ts: (unix) => {
            const d = new Date(unix * 1000);
            return d.toLocaleTimeString('en-GB', { hour12: false });
        },
        duration: (s) => {
            if (s < 60) return `${Math.floor(s)}s`;
            if (s < 3600) return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`;
            return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
        },
        pct: (v) => (typeof v === 'number' ? `${v.toFixed(1)}%` : '--%'),
        f2: (v)  => (typeof v === 'number' ? v.toFixed(2) : '--'),
        f1: (v)  => (typeof v === 'number' ? v.toFixed(1) : '--'),
        json: (d) => {
            try { return typeof d === 'string' ? d : JSON.stringify(d); }
            catch { return String(d); }
        },
    };

    function escapeHtml(t) {
        if (!t) return '';
        const div = document.createElement('div');
        div.textContent = t;
        return div.innerHTML;
    }

    function setBar(id, pct) {
        const el = $(id);
        if (el) el.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    }

    function setText(id, val) {
        const el = $(id);
        if (el) el.textContent = val;
    }

    // ---------------------------------------------------------------------------
    // API
    // ---------------------------------------------------------------------------
    const api = {
        async post(path, body = {}) {
            const t0 = performance.now();
            try {
                const res = await fetch(path, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await res.json();
                if (els.apiLatency)
                    els.apiLatency.textContent = `${Math.round(performance.now() - t0)} ms`;
                return data;
            } catch (e) {
                console.error(`POST ${path} failed:`, e);
                throw e;
            }
        },
    };

    // ---------------------------------------------------------------------------
    // WebSocket
    // ---------------------------------------------------------------------------
    const ws = {
        socket: null,
        reconnectTimer: null,

        connect() {
            if (this.socket?.readyState === WebSocket.OPEN) return;
            try {
                this.socket = new WebSocket(CFG.WS_URL());
                this.socket.onopen    = () => this._onOpen();
                this.socket.onmessage = (e) => this._onMessage(e);
                this.socket.onclose   = () => this._onClose();
                this.socket.onerror   = () => this._onError();
            } catch (e) {
                this._scheduleReconnect();
            }
        },

        send(obj) {
            if (this.socket?.readyState === WebSocket.OPEN)
                this.socket.send(JSON.stringify(obj));
        },

        _onOpen() {
            state.connected = true;
            state.wsReconnectAttempts = 0;
            updateWSStatus('Connected', true);
        },

        _onMessage(e) {
            try {
                const msg = JSON.parse(e.data);
                dispatchWSMessage(msg);
            } catch (err) {
                console.error('WS parse error:', err);
            }
        },

        _onClose() {
            state.connected = false;
            updateWSStatus('Disconnected', false);
            this._scheduleReconnect();
        },

        _onError() {
            state.connected = false;
            updateWSStatus('Error', false);
        },

        _scheduleReconnect() {
            state.wsReconnectAttempts++;
            const delay = Math.min(CFG.RECONNECT_DELAY * state.wsReconnectAttempts, 30000);
            updateWSStatus(`Reconnecting (${state.wsReconnectAttempts})...`, false);
            this.reconnectTimer = setTimeout(() => this.connect(), delay);
        },
    };

    // ---------------------------------------------------------------------------
    // WS message dispatcher
    // ---------------------------------------------------------------------------
    function dispatchWSMessage(msg) {
        switch (msg.type) {
            case 'state_update':
                handleStateUpdate(msg.data, msg.modules);
                break;
            case 'event_update':
                handleEventUpdate(msg.events || []);
                break;
            case 'pong':
                break;
            case 'error':
                console.error('WS error:', msg.msg);
                break;
        }
    }

    // ---------------------------------------------------------------------------
    // State update handler
    // ---------------------------------------------------------------------------
    function handleStateUpdate(data, modules) {
        if (!data) return;
        state.lastState = data;

        const core = data.core_state || {};
        const subj = data.subjective_field || {};

        // Status
        const running = data.running !== false;
        els.statusText.textContent = running ? 'RUNNING' : 'STOPPED';
        els.statusIndicator.classList.toggle('stopped', !running);

        // Core gauges
        updateGauge('consciousness', (core.consciousness || 0) * 100);
        updateGauge('energy',        (core.energy_level  || 0) * 100);
        updateGauge('mental-overload', (core.mental_overload || 0) * 100);
        updateGauge('motivation',    (core.motivation    || 0) * 100);

        // Footer
        setText('tick-counter', core.tick_count || 0);
        setText('uptime', fmt.duration(core.uptime_seconds || 0));
        setText('queue-size', core.queue_size || 0);

        // Thinking mode
        if (core.thinking_mode !== undefined) {
            const MODES = ['REFLEX','REACTIVE','DELIBERATIVE','IMAGINATION','DEEP_ANALYSIS','BACKGROUND'];
            const modeName = MODES[core.thinking_mode] || 'REACTIVE';
            if (modeName !== state.thinkingMode) {
                state.thinkingMode = modeName;
                updateThinkingModeBadge(modeName);
            }
        }

        // Imagination active
        if (core.imagination_active !== undefined) {
            state.imaginationActive = core.imagination_active;
            if (els.imaginationDot)
                els.imaginationDot.classList.toggle('active', !!core.imagination_active);
        }

        // Focus tags
        renderFocus(core.active_focus || subj.focus || []);

        // Process modules list
        if (modules && Array.isArray(modules)) {
            renderModules(modules);
            updateFromModules(modules);
        }
    }

    // ---------------------------------------------------------------------------
    // Module-derived displays
    // ---------------------------------------------------------------------------
    function updateFromModules(modules) {
        modules.forEach(mod => {
            state.modules[mod.module_id] = mod;
        });

        const emotion = state.modules['emotion_module'];
        if (emotion) updateEmotionDisplay(emotion);

        const hormone = state.modules['hormone_module'];
        if (hormone) updateHormoneDisplay(hormone);

        const goals = state.modules['goal_module'];
        if (goals) updateGoalsDisplay(goals);
    }

    function updateEmotionDisplay(mod) {
        const label = mod.current_emotion || mod.emotion || 'neutral';
        setText('emotion-label', label);

        // VAD range: typically -1..1 for valence, 0..1 for arousal/dominance
        const valence   = mod.valence   != null ? mod.valence   : 0;
        const arousal   = mod.arousal   != null ? mod.arousal   : 0.5;
        const dominance = mod.dominance != null ? mod.dominance : 0.5;

        // Valence: -1..1 → 0..100%
        const vPct = ((valence + 1) / 2) * 100;
        // Arousal/Dominance: 0..1 → 0..100%
        const aPct = arousal   * 100;
        const dPct = dominance * 100;

        setBar('bar-valence',   vPct);
        setBar('bar-arousal',   aPct);
        setBar('bar-dominance', dPct);

        setText('val-valence',   fmt.f2(valence));
        setText('val-arousal',   fmt.f2(arousal));
        setText('val-dominance', fmt.f2(dominance));

        // Update emotion label color
        const labelEl = $('emotion-label');
        if (labelEl) {
            const colors = {
                joy: '#ffd93d', sadness: '#7b8cde', anger: '#ff6b6b',
                fear: '#9b59b6', anticipation: '#f39c12', trust: '#00e676',
                surprise: '#00d4ff', disgust: '#a8a8a8', neutral: '#00d4ff',
            };
            labelEl.style.color = colors[label] || '#00d4ff';
        }
    }

    function updateHormoneDisplay(mod) {
        const hormones = ['dopamine', 'cortisol', 'oxytocin', 'serotonin'];
        hormones.forEach(h => {
            const val = mod[h] != null ? mod[h] : 0.5;
            setBar(`bar-${h}`,  val * 100);
            setText(`val-${h}`, fmt.f2(val));
        });
    }

    function updateGoalsDisplay(mod) {
        const goals = mod.active_goals || mod.goals || [];
        if (!els.goalsList) return;
        if (!goals.length) {
            els.goalsList.innerHTML = '<span class="text-muted">No active goals</span>';
            return;
        }
        els.goalsList.innerHTML = goals.slice(0, 5).map(g => {
            const desc = typeof g === 'string' ? g : (g.description || g.name || JSON.stringify(g));
            return `<div class="goal-item">${escapeHtml(desc)}</div>`;
        }).join('');
    }

    // ---------------------------------------------------------------------------
    // Gauges
    // ---------------------------------------------------------------------------
    function updateGauge(name, pct) {
        const barEl = $(`bar-${name}`);
        const valEl = $(`val-${name}`);
        if (barEl) barEl.style.width = `${Math.max(0, Math.min(100, pct))}%`;
        if (valEl) valEl.textContent = fmt.pct(pct);
    }

    // ---------------------------------------------------------------------------
    // Thinking mode badge
    // ---------------------------------------------------------------------------
    function updateThinkingModeBadge(modeName) {
        [els.thinkingModeBadge, els.chatModeBadge].forEach(el => {
            if (!el) return;
            el.textContent = modeName;
            el.className = `thinking-mode-badge mode-${modeName}`;
        });
    }

    // ---------------------------------------------------------------------------
    // Event update handler (near-realtime push from server)
    // ---------------------------------------------------------------------------
    function handleEventUpdate(events) {
        // Events arrive newest-first from the server buffer.
        // Process oldest-first so chat appears in order.
        const sorted = [...events].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));

        sorted.forEach(evt => {
            if ((evt.timestamp || 0) <= state.lastEventTs) return;
            state.lastEventTs = Math.max(state.lastEventTs, evt.timestamp || 0);

            // Always add to event log
            addToEventLog(evt);

            // Chat-relevant events
            switch (evt.type) {
                case 'response_generated':
                    appendChatMsg('bot', evt.data?.text || '', evt.data?.mode);
                    break;
                case 'internal_monologue':
                    appendMonologueToStream(evt.data?.text || '');
                    appendChatMsg('monologue', evt.data?.text || '');
                    break;
                case 'thinking_mode_changed': {
                    const mode = evt.data?.mode || evt.data?.value;
                    if (mode) { state.thinkingMode = mode; updateThinkingModeBadge(mode); }
                    break;
                }
                case 'imagination_started':
                    state.imaginationActive = true;
                    if (els.imaginationDot) els.imaginationDot.classList.add('active');
                    break;
                case 'imagination_complete':
                    state.imaginationActive = false;
                    if (els.imaginationDot) els.imaginationDot.classList.remove('active');
                    break;
            }
        });
    }

    // ---------------------------------------------------------------------------
    // Event log (BRAIN tab right panel)
    // ---------------------------------------------------------------------------
    function addToEventLog(evt) {
        state.eventCount++;
        if (els.eventCount) els.eventCount.textContent = state.eventCount;

        const item = document.createElement('div');
        item.className = 'event-item';
        item.innerHTML = `
            <div class="event-meta">
                <span class="event-type">${escapeHtml(evt.type)}</span>
                <span class="event-timestamp">${fmt.ts(evt.timestamp || Date.now() / 1000)}</span>
            </div>
            <div class="event-data">${escapeHtml(fmt.json(evt.data)).slice(0, 120)}</div>`;
        els.eventLog.insertBefore(item, els.eventLog.firstChild);
        while (els.eventLog.children.length > CFG.MAX_EVENTS)
            els.eventLog.removeChild(els.eventLog.lastChild);
    }

    // ---------------------------------------------------------------------------
    // Monologue stream (BRAIN tab)
    // ---------------------------------------------------------------------------
    function appendMonologueToStream(text) {
        if (!els.monologueStream || !text) return;
        // Clear placeholder
        if (els.monologueStream.querySelector('.text-muted')) {
            els.monologueStream.innerHTML = '';
        }
        const line = document.createElement('div');
        line.className = 'monologue-line';
        line.textContent = text;
        els.monologueStream.appendChild(line);
        // Keep only latest 5 lines
        while (els.monologueStream.children.length > 5)
            els.monologueStream.removeChild(els.monologueStream.firstChild);
        els.monologueStream.scrollTop = els.monologueStream.scrollHeight;
    }

    // ---------------------------------------------------------------------------
    // Chat messages
    // ---------------------------------------------------------------------------
    function clearWelcome() {
        if (!state.chatReady) {
            state.chatReady = true;
            const welcome = els.chatMessages.querySelector('.chat-welcome');
            if (welcome) welcome.remove();
        }
    }

    function appendChatMsg(role, text, modeName) {
        if (!els.chatMessages || !text.trim()) return;
        clearWelcome();

        const row = document.createElement('div');
        row.className = `msg-row ${role}`;

        if (role === 'monologue') {
            row.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
        } else {
            const timeStr = fmt.time();
            const modeHtml = modeName
                ? `<span class="msg-mode mode-${modeName}">${escapeHtml(modeName)}</span>` : '';
            row.innerHTML = `
                <div>
                    <div class="msg-bubble">${escapeHtml(text)}</div>
                    <div class="msg-meta">
                        <span class="msg-time">${timeStr}</span>
                        ${modeHtml}
                    </div>
                </div>`;
        }

        els.chatMessages.appendChild(row);
        // Cap history size
        while (els.chatMessages.children.length > CFG.MAX_CHAT)
            els.chatMessages.removeChild(els.chatMessages.firstChild);
        els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
    }

    function sendChatMessage() {
        const text = els.chatInput?.value.trim();
        if (!text) return;
        appendChatMsg('user', text);
        ws.send({ action: 'chat', text });
        els.chatInput.value = '';
        els.chatInput.style.height = 'auto';
    }

    // ---------------------------------------------------------------------------
    // Module list render
    // ---------------------------------------------------------------------------
    function renderModules(modules) {
        if (!els.moduleList) return;
        els.moduleList.innerHTML = '';

        // Sort: enabled first, then alphabetical
        const sorted = [...modules].sort((a, b) => {
            if (a.enabled !== b.enabled) return a.enabled ? -1 : 1;
            return (a.module_id || '').localeCompare(b.module_id || '');
        });

        sorted.forEach(mod => {
            const enabled = mod.enabled !== false;
            const costVal = mod.cost ? Object.values(mod.cost).reduce((s, v) => s + v, 0).toFixed(2) : '?';
            const item = document.createElement('div');
            item.className = 'module-item';
            item.innerHTML = `
                <div class="module-info">
                    <div class="module-name">${escapeHtml(mod.module_id || mod.name || 'unknown')}</div>
                    <div class="module-meta">
                        <span class="module-cost">${costVal} pts</span>
                    </div>
                </div>
                <div class="toggle-switch ${enabled ? 'active' : ''}"
                     onclick="window.jarvis.toggleModule('${escapeHtml(mod.module_id)}')">
                </div>`;
            els.moduleList.appendChild(item);
        });

        setText('module-count', modules.length);

        // Active modules in center panel
        renderActiveModules(modules.filter(m => m.enabled !== false));
    }

    function renderActiveModules(modules) {
        if (!els.activeModulesList) return;
        if (!modules.length) {
            els.activeModulesList.innerHTML = '<span class="text-muted">None</span>';
            return;
        }
        els.activeModulesList.innerHTML = modules.map(m =>
            `<div class="active-module-item">
                <span class="active-module-dot"></span>
                ${escapeHtml(m.module_id || m.name || '?')}
             </div>`
        ).join('');
    }

    // ---------------------------------------------------------------------------
    // Focus tags
    // ---------------------------------------------------------------------------
    function renderFocus(items) {
        if (!els.focusTags) return;
        if (!items || !items.length) {
            els.focusTags.innerHTML = '<span class="focus-tag">None</span>';
            return;
        }
        els.focusTags.innerHTML = items.map(i =>
            `<span class="focus-tag">${escapeHtml(i)}</span>`
        ).join('');
    }

    // ---------------------------------------------------------------------------
    // Tab switching
    // ---------------------------------------------------------------------------
    function switchTab(name) {
        state.currentTab = name;
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === name);
        });
        document.querySelectorAll('.tab-content').forEach(panel => {
            panel.classList.toggle('active', panel.id === `tab-${name}`);
        });
    }

    // ---------------------------------------------------------------------------
    // WS status
    // ---------------------------------------------------------------------------
    function updateWSStatus(text, connected) {
        if (!els.wsStatus) return;
        els.wsStatus.textContent = text;
        els.wsStatus.className = 'footer-value ' + (connected ? 'connected' : 'disconnected');
    }

    // ---------------------------------------------------------------------------
    // Module toggle
    // ---------------------------------------------------------------------------
    function toggleModule(moduleId) {
        api.post(`/api/modules/${moduleId}/toggle`).catch(e => console.error(e));
    }

    // ---------------------------------------------------------------------------
    // Emit event (BRAIN tab form)
    // ---------------------------------------------------------------------------
    function emitEvent(body) {
        api.post('/api/event/emit', body).catch(e => console.error(e));
    }

    // ---------------------------------------------------------------------------
    // Shutdown
    // ---------------------------------------------------------------------------
    function shutdownKernel() {
        api.post('/api/shutdown').then(() => {
            closeModal(els.shutdownModal);
        }).catch(e => console.error(e));
    }

    // ---------------------------------------------------------------------------
    // Modal helpers
    // ---------------------------------------------------------------------------
    const openModal  = (m) => m?.classList.add('show');
    const closeModal = (m) => m?.classList.remove('show');

    // ---------------------------------------------------------------------------
    // Event listeners
    // ---------------------------------------------------------------------------
    function setupListeners() {
        // Tab buttons (also handled inline in HTML)
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.tab));
        });

        // Chat send button
        els.chatSend?.addEventListener('click', sendChatMessage);

        // Chat input — Enter sends, Shift+Enter newline
        els.chatInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });

        // Auto-resize chat textarea
        els.chatInput?.addEventListener('input', () => {
            els.chatInput.style.height = 'auto';
            els.chatInput.style.height = Math.min(els.chatInput.scrollHeight, 120) + 'px';
        });

        // Load module modal
        $('btn-load-module')?.addEventListener('click', () => openModal(els.loadModuleModal));
        $('modal-close')?.addEventListener('click', () => closeModal(els.loadModuleModal));

        // Load module form
        $('load-module-form')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const path = $('module-path')?.value.trim();
            if (path) {
                api.post('/api/module/load', { path_to_module: path }).then(() => {
                    closeModal(els.loadModuleModal);
                }).catch(err => alert('Failed: ' + err.message));
            }
        });

        // Shutdown modal
        $('btn-shutdown')?.addEventListener('click', () => openModal(els.shutdownModal));
        $('shutdown-modal-close')?.addEventListener('click', () => closeModal(els.shutdownModal));
        $('shutdown-cancel')?.addEventListener('click', () => closeModal(els.shutdownModal));
        $('shutdown-confirm')?.addEventListener('click', shutdownKernel);

        // Emit event form (BRAIN tab)
        $('event-form')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const type     = $('event-type')?.value.trim();
            const dataStr  = $('event-data')?.value.trim();
            const priority = $('event-priority')?.value || 'COGNITIVE';
            let data = {};
            if (dataStr) { try { data = JSON.parse(dataStr); } catch { data = { raw: dataStr }; } }
            if (type) emitEvent({ type, data, priority });
            e.target.reset();
        });

        // Close modal on backdrop click
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal') && e.target.classList.contains('show'))
                closeModal(e.target);
        });
    }

    // ---------------------------------------------------------------------------
    // Init
    // ---------------------------------------------------------------------------
    function init() {
        cacheElements();
        setupListeners();
        updateThinkingModeBadge('REACTIVE');
        updateWSStatus('Connecting...', false);
        ws.connect();

        // Heartbeat
        setInterval(() => {
            if (state.connected) ws.send({ action: 'ping' });
        }, CFG.HEARTBEAT_INTERVAL);

        // Clock
        setInterval(() => { if (els.timestamp) els.timestamp.textContent = fmt.time(); }, 1000);
        if (els.timestamp) els.timestamp.textContent = fmt.time();
    }

    // ---------------------------------------------------------------------------
    // Expose to global (for inline onclick and external use)
    // ---------------------------------------------------------------------------
    window.jarvis = { toggleModule, emitEvent, shutdownKernel, switchTab };
    // Legacy alias kept so existing HTML works
    window.pca = window.jarvis;

    if (document.readyState === 'loading')
        document.addEventListener('DOMContentLoaded', init);
    else
        init();
})();
