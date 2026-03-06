/**
 * Community Discussion - JavaScript functionality
 */

let currentCategory = 'all';
let currentPage = 1;
let currentThreadId = null;
let currentThreadData = null;

document.addEventListener('DOMContentLoaded', () => {
    loadThreads();
    loadOnlineUsers();
    startHeartbeat();
});

// ===================== HEARTBEAT =====================
function startHeartbeat() {
    fetch('/api/user/heartbeat', { method: 'POST' }).catch(() => {});
    setInterval(() => {
        fetch('/api/user/heartbeat', { method: 'POST' }).catch(() => {});
        loadOnlineUsers();
    }, 60000);
}

// ===================== ONLINE USERS =====================
async function loadOnlineUsers() {
    try {
        const res = await fetch('/api/community/online');
        if (!res.ok) return;
        const data = await res.json();
        const container = document.getElementById('sidebarOnline');
        if (!data.online.length) {
            container.innerHTML = '<span>No users online</span>';
            return;
        }
        container.innerHTML = data.online.map(u => {
            const avatar = u.picture_url
                ? `<img src="${escapeHtml(u.picture_url)}" class="online-avatar" alt="" referrerpolicy="no-referrer">`
                : '👤';
            return `<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">${avatar} <span>${escapeHtml(u.name)}</span></div>`;
        }).join('');
    } catch (e) { console.error('Failed to load online users:', e); }
}

// ===================== THREADS LIST =====================
async function loadThreads() {
    try {
        const params = new URLSearchParams({ category: currentCategory, page: currentPage });
        const res = await fetch(`/api/community/threads?${params}`);
        if (!res.ok) return;
        const data = await res.json();
        renderThreadList(data.threads);
        renderPagination(data.pages, data.current_page);
    } catch (e) {
        console.error('Failed to load threads:', e);
        document.getElementById('threadList').innerHTML =
            '<div style="text-align:center;padding:40px;color:var(--text-secondary);">Failed to load threads</div>';
    }
}

function renderThreadList(threads) {
    const container = document.getElementById('threadList');
    if (!threads.length) {
        container.innerHTML = `<div style="text-align:center;padding:60px;color:var(--text-secondary);">
            <div style="font-size:3em;margin-bottom:15px;">💬</div>
            <div>No threads yet. Be the first to start a discussion!</div>
        </div>`;
        return;
    }

    container.innerHTML = threads.map(t => {
        const catClass = `category-${t.category}`;
        const pinnedClass = t.pinned ? 'pinned' : '';
        const pinnedIcon = t.pinned ? '📌 ' : '';
        const lockedIcon = t.locked ? ' 🔒' : '';
        const avatar = t.author_picture
            ? `<img src="${escapeHtml(t.author_picture)}" class="author-avatar" alt="" referrerpolicy="no-referrer">`
            : '';
        const symbolTag = t.symbol ? `<span class="symbol-tag">$${escapeHtml(t.symbol)}</span>` : '';

        return `<div class="thread-card ${pinnedClass}" onclick="openThread(${t.id})">
            <div style="display:flex;align-items:flex-start;">
                <div class="vote-box">
                    <span class="vote-count">${t.upvotes || 0}</span>
                </div>
                <div style="flex:1;">
                    <div class="thread-title">${pinnedIcon}${escapeHtml(t.title)}${lockedIcon}</div>
                    <div class="thread-meta">
                        <span>${avatar}${escapeHtml(t.author_name || 'Unknown')}</span>
                        <span class="category-badge ${catClass}">${t.category}</span>
                        ${symbolTag}
                        <span>💬 ${t.reply_count || 0}</span>
                        <span>👁 ${t.views || 0}</span>
                        <span>${timeAgo(t.created_at)}</span>
                    </div>
                </div>
            </div>
        </div>`;
    }).join('');
}

function renderPagination(totalPages, current) {
    const container = document.getElementById('pagination');
    if (totalPages <= 1) { container.innerHTML = ''; return; }
    let html = '';
    for (let i = 1; i <= totalPages; i++) {
        const active = i === current ? 'background:var(--accent);color:white;' : '';
        html += `<button class="btn btn-secondary" style="min-width:36px;${active}" onclick="goToPage(${i})">${i}</button>`;
    }
    container.innerHTML = html;
}

function goToPage(page) {
    currentPage = page;
    loadThreads();
}

function filterCategory(cat) {
    currentCategory = cat;
    currentPage = 1;
    document.querySelectorAll('.cat-tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    loadThreads();
}

// ===================== CREATE THREAD =====================
function toggleCreateForm() {
    const form = document.getElementById('createForm');
    form.style.display = form.style.display === 'none' || !form.style.display ? 'block' : 'none';
}

async function submitThread() {
    const title = document.getElementById('newTitle').value.trim();
    const body = document.getElementById('newBody').value.trim();
    const category = document.getElementById('newCategory').value;
    const symbol = document.getElementById('newSymbol').value.trim().toUpperCase();

    if (!title || !body) { showToast('Title and body are required', 'error'); return; }

    try {
        const res = await fetch('/api/community/threads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, body, category, symbol }),
        });
        if (!res.ok) {
            const err = await res.json();
            showToast(err.error || 'Failed to create thread', 'error');
            return;
        }
        document.getElementById('newTitle').value = '';
        document.getElementById('newBody').value = '';
        document.getElementById('newSymbol').value = '';
        document.getElementById('createForm').style.display = 'none';
        showToast('Thread created!');
        loadThreads();
    } catch (e) {
        console.error('Failed to create thread:', e);
        showToast('Failed to create thread', 'error');
    }
}

// ===================== THREAD DETAIL =====================
async function openThread(threadId) {
    currentThreadId = threadId;
    try {
        const res = await fetch(`/api/community/threads/${threadId}`);
        if (!res.ok) return;
        currentThreadData = await res.json();
        renderThreadDetail(currentThreadData);
        document.getElementById('threadListView').style.display = 'none';
        document.getElementById('threadDetailView').style.display = 'block';
    } catch (e) {
        console.error('Failed to load thread:', e);
    }
}

function renderThreadDetail(t) {
    const userVotes = t.user_votes || {};
    const threadVote = userVotes['thread'] || 0;
    const avatar = t.author_picture
        ? `<img src="${escapeHtml(t.author_picture)}" style="width:28px;height:28px;border-radius:50%;vertical-align:middle;margin-right:6px;" alt="" referrerpolicy="no-referrer">`
        : '';
    const symbolTag = t.symbol ? `<span class="symbol-tag" style="font-size:0.9em;">$${escapeHtml(t.symbol)}</span>` : '';
    const lockedBadge = t.locked ? '<span class="locked-badge">🔒 Locked</span>' : '';

    document.getElementById('threadContent').innerHTML = `
        <div style="background:var(--card-bg);border:1px solid var(--border);border-radius:12px;padding:24px;">
            <div style="display:flex;align-items:flex-start;">
                <div class="vote-box" style="margin-right:16px;">
                    <button class="vote-btn ${threadVote === 1 ? 'voted' : ''}" onclick="voteThread(1)">▲</button>
                    <span class="vote-count">${t.upvotes || 0}</span>
                    <button class="vote-btn ${threadVote === -1 ? 'voted' : ''}" onclick="voteThread(-1)">▼</button>
                </div>
                <div style="flex:1;">
                    <h2 style="color:var(--text-primary);margin-bottom:8px;">${escapeHtml(t.title)}</h2>
                    <div class="thread-meta" style="margin-bottom:16px;">
                        <span>${avatar}${escapeHtml(t.author_name || 'Unknown')}</span>
                        <span class="category-badge category-${t.category}">${t.category}</span>
                        ${symbolTag}
                        <span>👁 ${t.views || 0}</span>
                        <span>${timeAgo(t.created_at)}</span>
                        ${lockedBadge}
                    </div>
                    <div class="thread-body">${escapeHtml(t.body)}</div>
                </div>
            </div>
        </div>
    `;

    const replies = t.replies || [];
    document.getElementById('replyCount').textContent = `Replies (${replies.length})`;
    document.getElementById('repliesList').innerHTML = replies.map(r => {
        const rVote = userVotes[`reply_${r.id}`] || 0;
        const rAvatar = r.author_picture
            ? `<img src="${escapeHtml(r.author_picture)}" style="width:20px;height:20px;border-radius:50%;vertical-align:middle;" alt="" referrerpolicy="no-referrer">`
            : '👤';
        return `<div class="reply-card">
            <div style="display:flex;align-items:flex-start;">
                <div class="vote-box" style="margin-right:12px;">
                    <button class="vote-btn ${rVote === 1 ? 'voted' : ''}" onclick="voteReply(${r.id}, 1)">▲</button>
                    <span class="vote-count" id="replyVotes${r.id}">${r.upvotes || 0}</span>
                    <button class="vote-btn ${rVote === -1 ? 'voted' : ''}" onclick="voteReply(${r.id}, -1)">▼</button>
                </div>
                <div style="flex:1;">
                    <div class="reply-body">${escapeHtml(r.body)}</div>
                    <div class="reply-meta">
                        <span>${rAvatar} ${escapeHtml(r.author_name || 'Unknown')}</span>
                        <span>${timeAgo(r.created_at)}</span>
                    </div>
                </div>
            </div>
        </div>`;
    }).join('');

    // Hide reply form if thread is locked
    document.getElementById('replyForm').style.display = t.locked ? 'none' : 'block';
}

function backToList() {
    currentThreadId = null;
    currentThreadData = null;
    document.getElementById('threadDetailView').style.display = 'none';
    document.getElementById('threadListView').style.display = 'block';
    loadThreads();
}

// ===================== REPLIES =====================
async function submitReply() {
    const body = document.getElementById('replyBody').value.trim();
    if (!body) { showToast('Reply cannot be empty', 'error'); return; }

    try {
        const res = await fetch(`/api/community/threads/${currentThreadId}/replies`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ body }),
        });
        if (!res.ok) {
            const err = await res.json();
            showToast(err.error || 'Failed to post reply', 'error');
            return;
        }
        document.getElementById('replyBody').value = '';
        showToast('Reply posted!');
        openThread(currentThreadId);
    } catch (e) {
        console.error('Failed to post reply:', e);
        showToast('Failed to post reply', 'error');
    }
}

// ===================== VOTING =====================
async function voteThread(val) {
    try {
        const res = await fetch(`/api/community/threads/${currentThreadId}/vote`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vote: val }),
        });
        if (res.ok) openThread(currentThreadId);
    } catch (e) { console.error('Vote failed:', e); }
}

async function voteReply(replyId, val) {
    try {
        const res = await fetch(`/api/community/replies/${replyId}/vote`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vote: val }),
        });
        if (res.ok) {
            const data = await res.json();
            const el = document.getElementById(`replyVotes${replyId}`);
            if (el) el.textContent = data.upvotes;
        }
    } catch (e) { console.error('Vote failed:', e); }
}

// ===================== UTILITIES =====================
function timeAgo(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const now = new Date();
    const seconds = Math.floor((now - d) / 1000);
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return d.toLocaleDateString();
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showToast(message, type) {
    const bg = type === 'error' ? '#ef4444' : 'var(--accent)';
    const toast = document.createElement('div');
    toast.style.cssText = `position:fixed;bottom:20px;right:20px;background:${bg};color:white;padding:12px 20px;border-radius:8px;z-index:10000;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,0.3);`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}
