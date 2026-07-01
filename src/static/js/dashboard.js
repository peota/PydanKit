// Theme Logic
function initTheme() {
    if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }
}

function toggleTheme() {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.theme = isDark ? 'dark' : 'light';
}

// Mobile keyboard handling
function initMobileKeyboard() {
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');

    if (!chatInput || !chatMessages) return;

    // Use visualViewport API for better keyboard handling
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => {
            // Scroll to bottom when keyboard opens/closes
            requestAnimationFrame(() => {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            });
        });
    }

    // Scroll input into view on focus (for older browsers)
    chatInput.addEventListener('focus', () => {
        setTimeout(() => {
            chatInput.scrollIntoView({ behavior: 'smooth', block: 'end' });
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 300);
    });
}

// Sidebar Logic
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');

    sidebar.classList.toggle('-translate-x-full');

    if (backdrop.classList.contains('hidden')) {
        backdrop.classList.remove('hidden');
    } else {
        backdrop.classList.add('hidden');
    }
}

// Initialize Theme immediately
initTheme();

// DOM Elements
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');
const statusBadge = document.getElementById('status-badge');
const healthStatus = document.getElementById('health-status');
const modelName = document.getElementById('model-name');
const debugStatus = document.getElementById('debug-status');
const logfireStatus = document.getElementById('logfire-status');
const memoryStatus = document.getElementById('memory-status');
const memoryDetails = document.getElementById('memory-details');
const memoryStorage = document.getElementById('memory-storage');
const memoryMaxMessages = document.getElementById('memory-max-messages');
const sessionIdDisplay = document.getElementById('session-id');
const toolsList = document.getElementById('tools-list');
const apiKeyInput = document.getElementById('api-key-input');
const appVersion = document.getElementById('app-version');
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const sendButton = document.getElementById('send-button');
const configError = document.getElementById('config-error');
const configErrorMessage = document.getElementById('config-error-message');

// State
let isFirstMessage = true;
let currentSessionId = null;

// Session Management
function generateSessionId() {
    // Generate a random GUID
    return 'dashboard-' + 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function getOrCreateSessionId() {
    // Try to get from localStorage
    let sessionId = localStorage.getItem('dashboard_session_id');

    if (!sessionId) {
        sessionId = generateSessionId();
        localStorage.setItem('dashboard_session_id', sessionId);
    }

    return sessionId;
}

function resetSession() {
    // Generate new session ID
    currentSessionId = generateSessionId();
    localStorage.setItem('dashboard_session_id', currentSessionId);

    // Update display
    sessionIdDisplay.textContent = currentSessionId;

    // Clear chat
    chatMessages.innerHTML = `
        <div class="max-w-4xl mx-auto flex flex-col items-center justify-center h-full text-center space-y-4 opacity-50">
            <div class="w-12 h-12 bg-slate-100 dark:bg-slate-800 rounded-full flex items-center justify-center">
                <svg class="w-6 h-6 text-slate-400 dark:text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
            </div>
            <p class="text-slate-500 dark:text-slate-400 text-sm">New session started</p>
        </div>
    `;
    isFirstMessage = true;

    chatInput.focus();
}

// Initialize session on load
currentSessionId = getOrCreateSessionId();
sessionIdDisplay.textContent = currentSessionId;

// Optional API key (only needed if the server sets API_KEY). Persist in localStorage
// and send it as the X-API-Key header on gated requests.
function getApiKey() {
    return (localStorage.getItem('dashboard_api_key') || '').trim();
}

if (apiKeyInput) {
    apiKeyInput.value = getApiKey();
    apiKeyInput.addEventListener('input', () => {
        localStorage.setItem('dashboard_api_key', apiKeyInput.value.trim());
    });
}

// Initialize dashboard
async function loadDashboard() {
    try {
        const [healthResponse, infoResponse] = await Promise.all([
            fetch('/health'),
            fetch('/info')
        ]);

        if (!healthResponse.ok || !infoResponse.ok) {
            throw new Error('Failed to fetch dashboard data');
        }

        const health = await healthResponse.json();
        const info = await infoResponse.json();

        // If there's a config error, show partial status
        if (info.error) {
            setConfigErrorState(info);
        } else {
            updateStatusPanel(health);
        }
        updateInfoPanel(info);
        renderToolsList(info.tools);
    } catch (error) {
        console.error('Dashboard load error:', error);
        setErrorState();
    }
}

function updateStatusPanel(health) {
    const isHealthy = health.status === 'healthy';

    // Update status badge
    statusIndicator.className = `w-2 h-2 rounded-full ${isHealthy ? 'bg-emerald-500' : 'bg-rose-500'}`;
    statusText.textContent = isHealthy ? 'System Operational' : 'System Issues';
    statusText.className = `text-xs font-medium ${isHealthy ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-700 dark:text-rose-400'} hidden sm:inline`;
    statusBadge.className = `flex items-center gap-2 px-3 py-1.5 rounded-full border ${isHealthy ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-900/30' : 'bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-900/30'}`;

    // Update health status text
    healthStatus.textContent = isHealthy ? 'Online' : 'Offline';
    healthStatus.className = `text-sm font-medium ${isHealthy ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`;

    // Update model name
    modelName.textContent = health.model;

    // Show the backend-reported version (avoids a hard-coded string drifting)
    if (appVersion && health.version) {
        appVersion.textContent = 'v' + health.version;
    }
}

function updateInfoPanel(info) {
    // Update debug status
    debugStatus.textContent = info.debug ? 'Active' : 'Inactive';
    debugStatus.className = `text-sm font-medium ${info.debug ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500 dark:text-slate-400'}`;

    // Update logfire status
    logfireStatus.textContent = info.logfire_enabled ? 'Connected' : 'Disconnected';
    logfireStatus.className = `text-sm font-medium ${info.logfire_enabled ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-500 dark:text-slate-400'}`;

    // Update memory status
    const memoryEnabled = info.memory_enabled || false;
    memoryStatus.textContent = memoryEnabled ? 'Enabled' : 'Disabled';
    memoryStatus.className = `text-sm font-medium ${memoryEnabled ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-500 dark:text-slate-400'}`;

    // Show memory details if enabled
    if (memoryEnabled) {
        memoryDetails.classList.remove('hidden');
        memoryStorage.textContent = (info.memory_storage_type || 'memory').toUpperCase();
        memoryMaxMessages.textContent = info.memory_max_messages || '--';
    } else {
        memoryDetails.classList.add('hidden');
    }

    // Show configuration error if present
    if (info.error) {
        configErrorMessage.textContent = info.error;
        configError.classList.remove('hidden');
    } else {
        configError.classList.add('hidden');
    }
}

function renderToolsList(tools) {
    if (tools.length === 0) {
        toolsList.innerHTML = '<span class="text-xs text-slate-400 italic">No tools registered</span>';
        return;
    }

    toolsList.innerHTML = tools.map(tool =>
        `<span class="px-2.5 py-1 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md text-xs font-medium shadow-sm">${tool}</span>`
    ).join('');
}

function setErrorState() {
    statusIndicator.className = 'w-2 h-2 rounded-full bg-rose-500';
    statusText.textContent = 'Connection Error';
    statusText.className = 'text-xs font-medium text-rose-700 dark:text-rose-400 hidden sm:inline';
    statusBadge.className = 'flex items-center gap-2 px-3 py-1.5 rounded-full bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-900/30';

    healthStatus.textContent = 'Error';
    healthStatus.className = 'text-sm font-medium text-rose-600 dark:text-rose-400';

    toolsList.innerHTML = '<span class="text-xs text-rose-400">Failed to load</span>';
}

function setConfigErrorState(info) {
    // API is responding but there's a configuration issue
    statusIndicator.className = 'w-2 h-2 rounded-full bg-amber-500';
    statusText.textContent = 'Configuration Issue';
    statusText.className = 'text-xs font-medium text-amber-700 dark:text-amber-400 hidden sm:inline';
    statusBadge.className = 'flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900/30';

    healthStatus.textContent = 'Degraded';
    healthStatus.className = 'text-sm font-medium text-amber-600 dark:text-amber-400';

    modelName.textContent = info.model;
}

function appendMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `max-w-4xl mx-auto flex w-full ${role === 'user' ? 'justify-end' : 'justify-start'}`;

    const isUser = role === 'user';

    // Avatar for Agent
    const avatarHtml = !isUser ? `
        <div class="w-8 h-8 rounded-full bg-slate-900 dark:bg-slate-800 flex items-center justify-center shrink-0 mr-3 mt-1 shadow-sm p-1.5">
            <img src="/static/assets/logo.svg" alt="Agent" class="w-4 h-4 brightness-0 invert" />
        </div>
    ` : '';

    const bubbleClass = isUser
        ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 rounded-2xl rounded-tr-sm'
        : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 rounded-2xl rounded-tl-sm shadow-sm';

    const messageContent = `
        ${avatarHtml}
        <div class="max-w-[85%] md:max-w-[75%]">
            <div class="px-5 py-3.5 ${bubbleClass}">
                <p class="text-sm leading-relaxed whitespace-pre-wrap">${escapeHtml(content)}</p>
            </div>
        </div>
    `;

    messageDiv.innerHTML = messageContent;

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function setLoading(loading) {
    sendButton.disabled = loading;
    chatInput.disabled = loading;

    if (loading) {
        // Change icon to loader
        sendButton.innerHTML = `
            <svg class="animate-spin w-5 h-5 text-white dark:text-slate-900" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
        `;
    } else {
        // Restore send icon
        sendButton.innerHTML = `
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7" />
            </svg>
        `;
        chatInput.focus();
    }
}

async function sendMessage(prompt) {
    setLoading(true);

    // Clear placeholder welcome message if this is the first message
    if (isFirstMessage) {
        chatMessages.innerHTML = '';
        isFirstMessage = false;
    }

    appendMessage('user', prompt);

    // Create placeholder for agent message
    const agentMessageDiv = createAgentMessagePlaceholder();
    chatMessages.appendChild(agentMessageDiv);

    const contentElement = agentMessageDiv.querySelector('.message-content');
    let fullContent = '';
    let firstChunk = true;

    try {
        const headers = { 'Content-Type': 'application/json' };
        const apiKey = getApiKey();
        if (apiKey) {
            headers['X-API-Key'] = apiKey;
        }

        const response = await fetch('/chat/stream', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                prompt: prompt,
                session_id: currentSessionId
            })
        });

        if (!response.ok) {
            throw new Error('Failed to get response');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);

                    if (data === '[DONE]') {
                        break;
                    }

                    fullContent += data;

                    // First real content: drop the snug ".thinking" state so the
                    // bubble expands to full message padding (via CSS).
                    if (firstChunk) {
                        firstChunk = false;
                        const bubble = agentMessageDiv.querySelector('.agent-bubble');
                        if (bubble) bubble.classList.remove('thinking');
                    }

                    contentElement.textContent = fullContent;
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                }
            }
        }
    } catch (error) {
        console.error('Chat error:', error);
        contentElement.textContent = 'Sorry, there was an error processing your request. Please check the connection.';
    } finally {
        setLoading(false);
    }
}

function createAgentMessagePlaceholder() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'max-w-4xl mx-auto flex w-full justify-start';

    const avatarHtml = `
        <div class="w-8 h-8 rounded-full bg-slate-900 dark:bg-slate-800 flex items-center justify-center shrink-0 mr-3 mt-1 shadow-sm p-1.5">
            <img src="/static/assets/logo.svg" alt="Agent" class="w-4 h-4 brightness-0 invert" />
        </div>
    `;

    const bubbleClass = 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 rounded-2xl rounded-tl-sm shadow-sm';

    // Typing indicator (styled in index.html CSS, so it doesn't depend on the
    // Tailwind CDN emitting utility classes for these JS-injected nodes). The
    // bubble starts snug via .thinking; sendMessage() removes it on the first chunk.
    const typingIndicator = `
        <span class="typing-indicator" aria-label="Agent is thinking">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </span>
    `;

    messageDiv.innerHTML = `
        ${avatarHtml}
        <div class="max-w-[85%] md:max-w-[75%]">
            <div class="agent-bubble thinking ${bubbleClass}">
                <p class="message-content text-sm leading-relaxed whitespace-pre-wrap">${typingIndicator}</p>
            </div>
        </div>
    `;

    return messageDiv;
}

// Event listeners
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const prompt = chatInput.value.trim();
    if (!prompt) return;

    chatInput.value = '';
    await sendMessage(prompt);
});

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    initMobileKeyboard();
});
