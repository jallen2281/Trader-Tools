/**
 * Admin Dashboard — stats, user management (roles, status, groups, soft-delete/
 * restore/purge), and RBAC group management.
 */

let PERM_REGISTRY = {};   // {key: label}
let ALL_GROUPS = [];      // [{id,name,description,permissions,is_system,member_count}]

document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadGroups().then(loadUsers);  // groups first so the user table can render group pickers
});

async function loadStats() {
    try {
        const res = await fetch('/api/admin/stats');
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById('statUsers').textContent = data.total_users;
        document.getElementById('statActive').textContent = data.active_users;
        document.getElementById('statThreads').textContent = data.total_threads;
        document.getElementById('statHoldings').textContent = data.total_holdings;
    } catch (e) { console.error('Failed to load stats:', e); }
}

/* ============ Users ============ */

async function loadUsers() {
    try {
        const res = await fetch('/api/admin/users');
        if (!res.ok) {
            if (res.status === 403) {
                document.getElementById('usersTableBody').innerHTML =
                    '<tr><td colspan="6" style="text-align:center;padding:40px;color:#ef4444;">Access denied. Admin role required.</td></tr>';
            }
            return;
        }
        const data = await res.json();
        renderUsers(data.users);
    } catch (e) { console.error('Failed to load users:', e); }
}

function renderUsers(users) {
    const tbody = document.getElementById('usersTableBody');
    if (!users.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-secondary);">No users found</td></tr>';
        return;
    }
    tbody.innerHTML = users.map(u => {
        const isActive = u.is_active !== false;
        const deleted = !!u.deleted_at;
        const avatar = u.picture_url
            ? `<img src="${escapeHtml(u.picture_url)}" class="user-avatar" alt="" referrerpolicy="no-referrer">`
            : '<span style="display:inline-block;width:32px;height:32px;border-radius:50%;background:var(--bg-tertiary);text-align:center;line-height:32px;margin-right:8px;">👤</span>';
        const groupChips = (u.groups || []).map(g => `<span class="grp-chip">${escapeHtml(g.name)}</span>`).join('') || '<span style="color:var(--text-secondary);font-size:0.8em;">—</span>';

        let actions;
        if (deleted) {
            actions = `<button class="toggle-btn" onclick="restoreUser(${u.id})">♻️ Restore</button>
                       <button class="toggle-btn danger" onclick="purgeUser(${u.id}, '${escapeHtml(u.email)}')">🗑️ Purge</button>`;
        } else {
            actions = `<button class="toggle-btn" onclick="manageGroups(${u.id})">👥 Groups</button>
                       <button class="toggle-btn" onclick="toggleActive(${u.id}, ${!isActive})">${isActive ? '🚫 Disable' : '✅ Enable'}</button>
                       <button class="toggle-btn danger" onclick="deleteUser(${u.id})">Delete</button>`;
        }

        const roleCell = deleted
            ? '<span style="color:var(--text-secondary);">—</span>'
            : `<select class="action-select" onchange="changeRole(${u.id}, this.value)">
                    <option value="user" ${u.role === 'user' ? 'selected' : ''}>User</option>
                    <option value="moderator" ${u.role === 'moderator' ? 'selected' : ''}>Moderator</option>
                    <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
               </select>`;

        const nameCell = `${avatar}${escapeHtml(u.name || 'Unknown')}${deleted ? ' <span class="sys-badge" style="background:rgba(239,68,68,0.15);color:#ef4444;">deleted</span>' : ''}<div style="font-size:0.78em;color:var(--text-secondary);margin-left:40px;">${escapeHtml(u.email)}</div>`;

        return `<tr class="${deleted ? 'deleted' : ''}">
            <td>${nameCell}</td>
            <td>${roleCell}</td>
            <td class="${isActive ? 'status-active' : 'status-disabled'}">${deleted ? '—' : (isActive ? '● Active' : '○ Disabled')}</td>
            <td>${deleted ? '—' : groupChips}</td>
            <td>${u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
            <td style="white-space:nowrap;">${actions}</td>
        </tr>`;
    }).join('');
    window._USERS = users;
}

async function changeRole(userId, newRole) {
    try {
        const res = await fetch(`/api/admin/users/${userId}/role`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: newRole }),
        });
        const data = await res.json();
        if (!res.ok) { alert(data.error || 'Failed to change role'); loadUsers(); return; }
        showToast(`Role updated to ${newRole}`);
    } catch (e) { alert('Failed to change role'); loadUsers(); }
}

async function toggleActive(userId, active) {
    try {
        const res = await fetch(`/api/admin/users/${userId}/active`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: active }),
        });
        const data = await res.json();
        if (!res.ok) { alert(data.error || 'Failed to update status'); return; }
        loadUsers(); showToast(`User ${active ? 'enabled' : 'disabled'}`);
    } catch (e) { alert('Failed to update status'); }
}

async function deleteUser(userId) {
    if (!confirm('Soft-delete this account? Login is disabled and PII is scrubbed, but data is retained. You can restore or purge afterward.')) return;
    try {
        const res = await fetch(`/api/admin/users/${userId}/delete`, { method: 'PUT' });
        const data = await res.json();
        if (!res.ok) { alert(data.error || 'Failed to delete'); return; }
        loadUsers(); showToast('Account soft-deleted');
    } catch (e) { alert('Failed to delete'); }
}

async function restoreUser(userId) {
    try {
        const res = await fetch(`/api/admin/users/${userId}/restore`, { method: 'PUT' });
        const data = await res.json();
        if (!res.ok) { alert(data.error || 'Failed to restore'); return; }
        loadUsers(); showToast('Account restored (PII re-populates on next login)');
    } catch (e) { alert('Failed to restore'); }
}

async function purgeUser(userId, email) {
    if (!confirm(`PERMANENTLY delete this account and ALL its data? This cannot be undone.`)) return;
    const typed = prompt(`This is irreversible. Type the account email to confirm:\n${email}`);
    if (typed !== email) { if (typed !== null) alert('Email did not match — purge cancelled.'); return; }
    try {
        const res = await fetch(`/api/admin/users/${userId}/purge`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) { alert(data.error || 'Failed to purge'); return; }
        loadUsers(); showToast('Account permanently purged');
    } catch (e) { alert('Failed to purge'); }
}

/* ============ User → group assignment ============ */

function manageGroups(userId) {
    const user = (window._USERS || []).find(u => u.id === userId);
    if (!user) return;
    const current = new Set((user.groups || []).map(g => g.id));
    const rows = ALL_GROUPS.map(g => `
        <label class="perm-check">
            <input type="checkbox" class="ug-chk" value="${g.id}" ${current.has(g.id) ? 'checked' : ''}>
            <div><div style="font-weight:600;">${escapeHtml(g.name)}${g.is_system ? ' <span class="sys-badge">system</span>' : ''}</div>
            <div style="font-size:0.82em;color:var(--text-secondary);">${escapeHtml(g.description || '')}</div></div>
        </label>`).join('') || '<p style="color:var(--text-secondary);">No groups exist yet.</p>';
    showModal(`
        <h2 style="margin:0 0 4px;">Groups for ${escapeHtml(user.name || user.email)}</h2>
        <p style="font-size:0.85em;color:var(--text-secondary);margin-top:0;">Select the groups this user belongs to.</p>
        ${rows}
        <div style="display:flex;gap:10px;margin-top:16px;">
            <button class="btn2 primary" onclick="saveUserGroups(${userId})">Save</button>
            <button class="btn2" onclick="closeModal()">Cancel</button>
            <span id="ugMsg" style="align-self:center;font-size:0.85em;color:var(--text-secondary);"></span>
        </div>`);
}

async function saveUserGroups(userId) {
    const ids = [...document.querySelectorAll('.ug-chk:checked')].map(c => parseInt(c.value));
    const msg = document.getElementById('ugMsg');
    msg.textContent = 'Saving…';
    try {
        const res = await fetch(`/api/admin/users/${userId}/groups`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ group_ids: ids }),
        });
        if (!res.ok) throw new Error((await res.json()).error || 'save failed');
        closeModal(); await loadGroups(); loadUsers(); showToast('Groups updated');
    } catch (e) { msg.textContent = e.message; msg.style.color = '#ef4444'; }
}

/* ============ Groups management ============ */

async function loadGroups() {
    try {
        const res = await fetch('/api/admin/groups');
        if (!res.ok) return;
        const data = await res.json();
        PERM_REGISTRY = data.registry || {};
        ALL_GROUPS = data.groups || [];
        renderGroups();
    } catch (e) { console.error('Failed to load groups:', e); }
}

function renderGroups() {
    const grid = document.getElementById('groupsGrid');
    if (!ALL_GROUPS.length) { grid.innerHTML = '<p style="color:var(--text-secondary);">No groups yet. Create one to start granting permissions.</p>'; return; }
    grid.innerHTML = ALL_GROUPS.map(g => {
        const perms = (g.permissions || []).map(p => `<span class="perm-tag">${escapeHtml(PERM_REGISTRY[p] || p)}</span>`).join('') || '<span style="color:var(--text-secondary);font-size:0.82em;">no permissions</span>';
        return `<div class="group-card">
            <h3>${escapeHtml(g.name)} ${g.is_system ? '<span class="sys-badge">system</span>' : ''}</h3>
            <div style="font-size:0.85em;color:var(--text-secondary);margin-bottom:8px;">${escapeHtml(g.description || '')}</div>
            <div style="font-size:0.78em;color:var(--text-secondary);margin-bottom:8px;">${g.member_count || 0} member${g.member_count === 1 ? '' : 's'}</div>
            <div style="margin-bottom:12px;">${perms}</div>
            <div style="display:flex;gap:8px;">
                <button class="btn2" onclick="openGroupEditor(${g.id})">Edit</button>
                ${g.is_system ? '' : `<button class="btn2 danger" onclick="deleteGroup(${g.id}, '${escapeHtml(g.name)}')">Delete</button>`}
            </div>
        </div>`;
    }).join('');
}

function openGroupEditor(groupId) {
    const g = groupId ? ALL_GROUPS.find(x => x.id === groupId) : { name: '', description: '', permissions: [], is_system: false };
    const sel = new Set(g.permissions || []);
    const permRows = Object.entries(PERM_REGISTRY).map(([k, label]) => `
        <label class="perm-check">
            <input type="checkbox" class="gp-chk" value="${k}" ${sel.has(k) ? 'checked' : ''}>
            <div><div style="font-weight:600;">${escapeHtml(label)}</div>
            <div style="font-size:0.78em;color:var(--text-secondary);">${escapeHtml(k)}</div></div>
        </label>`).join('');
    showModal(`
        <h2 style="margin:0 0 10px;">${groupId ? 'Edit Group' : 'New Group'}</h2>
        <label class="fld">Name</label>
        <input type="text" id="gName" value="${escapeHtml(g.name)}" ${g.is_system ? 'disabled title="System group name is fixed"' : ''} placeholder="e.g. Beta Testers">
        <label class="fld">Description</label>
        <textarea id="gDesc" rows="2" placeholder="What this group is for">${escapeHtml(g.description || '')}</textarea>
        <label class="fld">Permissions</label>
        <div style="border:1px solid var(--border);border-radius:8px;padding:6px 12px;">${permRows}</div>
        <div style="display:flex;gap:10px;margin-top:16px;">
            <button class="btn2 primary" onclick="saveGroup(${groupId || 'null'}, ${g.is_system})">Save</button>
            <button class="btn2" onclick="closeModal()">Cancel</button>
            <span id="gMsg" style="align-self:center;font-size:0.85em;color:var(--text-secondary);"></span>
        </div>`);
}

async function saveGroup(groupId, isSystem) {
    const msg = document.getElementById('gMsg');
    const permissions = [...document.querySelectorAll('.gp-chk:checked')].map(c => c.value);
    const body = { description: document.getElementById('gDesc').value, permissions };
    if (!isSystem) body.name = document.getElementById('gName').value.trim();
    if (!groupId && !body.name) { msg.textContent = 'Name required.'; msg.style.color = '#ef4444'; return; }
    msg.textContent = 'Saving…'; msg.style.color = 'var(--text-secondary)';
    try {
        const res = await fetch(groupId ? `/api/admin/groups/${groupId}` : '/api/admin/groups', {
            method: groupId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error((await res.json()).error || 'save failed');
        closeModal(); await loadGroups(); loadUsers(); showToast('Group saved');
    } catch (e) { msg.textContent = e.message; msg.style.color = '#ef4444'; }
}

async function deleteGroup(groupId, name) {
    if (!confirm(`Delete the group "${name}"? Members lose the permissions it granted.`)) return;
    try {
        const res = await fetch(`/api/admin/groups/${groupId}`, { method: 'DELETE' });
        if (!res.ok) { alert((await res.json()).error || 'Failed to delete'); return; }
        await loadGroups(); loadUsers(); showToast('Group deleted');
    } catch (e) { alert('Failed to delete group'); }
}

/* ============ helpers ============ */

function showModal(html) {
    const root = document.getElementById('modalRoot');
    root.innerHTML = `<div class="modal-back" id="_modalBack"><div class="modal-box">${html}</div></div>`;
    document.getElementById('_modalBack').addEventListener('click', e => { if (e.target.id === '_modalBack') closeModal(); });
}
function closeModal() { document.getElementById('modalRoot').innerHTML = ''; }

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:var(--accent);color:white;padding:12px 20px;border-radius:8px;z-index:10000;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,0.3);';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}
