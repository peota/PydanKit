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
const toolsList = document.getElementById('tools-list');
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const sendButton = document.getElementById('send-button');
const configError = document.getElementById('config-error');
const configErrorMessage = document.getElementById('config-error-message');

// State
let isFirstMessage = true;

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
}

function updateInfoPanel(info) {
    // Update debug status
    debugStatus.textContent = info.debug ? 'Active' : 'Inactive';
    debugStatus.className = `text-sm font-medium ${info.debug ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500 dark:text-slate-400'}`;

    // Update logfire status
    logfireStatus.textContent = info.logfire_enabled ? 'Connected' : 'Disconnected';
    logfireStatus.className = `text-sm font-medium ${info.logfire_enabled ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-500 dark:text-slate-400'}`;

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
    messageDiv.className = `flex w-full ${role === 'user' ? 'justify-end' : 'justify-start'}`;

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

    try {
        const response = await fetch('/weather/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt })
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
                    contentElement.textContent = fullContent;
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                }
            }
        }
    } catch (error) {
        console.error('Weather error:', error);
        contentElement.textContent = 'Sorry, there was an error processing your request. Please check the connection.';
    } finally {
        setLoading(false);
    }
}

function createAgentMessagePlaceholder() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'flex w-full justify-start';

    const avatarHtml = `
        <div class="w-8 h-8 rounded-full bg-slate-900 dark:bg-slate-800 flex items-center justify-center shrink-0 mr-3 mt-1 shadow-sm p-1.5">
            <img src="/static/assets/logo.svg" alt="Agent" class="w-4 h-4 brightness-0 invert" />
        </div>
    `;

    const bubbleClass = 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 rounded-2xl rounded-tl-sm shadow-sm';

    messageDiv.innerHTML = `
        ${avatarHtml}
        <div class="max-w-[85%] md:max-w-[75%]">
            <div class="px-5 py-3.5 ${bubbleClass}">
                <p class="message-content text-sm leading-relaxed whitespace-pre-wrap"></p>
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
document.addEventListener('DOMContentLoaded', loadDashboard);
