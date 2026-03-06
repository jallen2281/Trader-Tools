/**
 * Admin Dashboard - JavaScript functionality
 */

document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadUsers();
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
    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}

async function loadUsers() {
    try {
        const res = await fetch('/api/admin/users');
        if (!res.ok) {
            if (res.status === 403) {
                document.getElementById('usersTableBody').innerHTML =
                    '<tr><td colspan="8" style="text-align:center;padding:40px;color:#ef4444;">Access denied. Admin role required.</td></tr>';
            }
            return;
        }
        const data = await res.json();
        renderUsers(data.users);
    } catch (e) {
        console.error('Failed to load users:', e);
    }
}

function renderUsers(users) {
    const tbody = document.getElementById('usersTableBody');
    if (!users.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-secondary);">No users found</td></tr>';
        return;
    }

    tbody.innerHTML = users.map(u => {
        const roleClass = `role-${u.role || 'user'}`;
        const isActive = u.is_active !== false;
        const statusClass = isActive ? 'status-active' : 'status-disabled';
        const avatar = u.picture_url
            ? `<img src="${escapeHtml(u.picture_url)}" class="user-avatar" alt="" referrerpolicy="no-referrer">`
            : '<span style="display:inline-block;width:32px;height:32px;border-radius:50%;background:var(--bg-tertiary);text-align:center;line-height:32px;margin-right:8px;">👤</span>';

        return `<tr>
            <td>${avatar}${escapeHtml(u.name || 'Unknown')}</td>
            <td>${escapeHtml(u.email)}</td>
            <td>
                <select class="action-select" onchange="changeRole(${u.id}, this.value)" data-uid="${u.id}">
                    <option value="user" ${u.role === 'user' ? 'selected' : ''}>User</option>
                    <option value="moderator" ${u.role === 'moderator' ? 'selected' : ''}>Moderator</option>
                    <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
                </select>
            </td>
            <td class="${statusClass}">${isActive ? '● Active' : '○ Disabled'}</td>
            <td>${u.copy_trading_enabled ? '✅' : '—'}</td>
            <td>${u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
            <td>${u.last_login ? new Date(u.last_login).toLocaleDateString() : '—'}</td>
            <td>
                <button class="toggle-btn" onclick="toggleActive(${u.id}, ${!isActive})">
                    ${isActive ? '🚫 Disable' : '✅ Enable'}
                </button>
            </td>
        </tr>`;
    }).join('');
}

async function changeRole(userId, newRole) {
    try {
        const res = await fetch(`/api/admin/users/${userId}/role`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: newRole }),
        });
        const data = await res.json();
        if (!res.ok) {
            alert(data.error || 'Failed to change role');
            loadUsers();
            return;
        }
        showToast(`Role updated to ${newRole}`);
    } catch (e) {
        console.error('Failed to change role:', e);
        alert('Failed to change role');
        loadUsers();
    }
}

async function toggleActive(userId, active) {
    try {
        const res = await fetch(`/api/admin/users/${userId}/active`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: active }),
        });
        const data = await res.json();
        if (!res.ok) {
            alert(data.error || 'Failed to update status');
            return;
        }
        loadUsers();
        showToast(`User ${active ? 'enabled' : 'disabled'}`);
    } catch (e) {
        console.error('Failed to toggle active:', e);
        alert('Failed to update status');
    }
}

function escapeHtml(str) {
    if (!str) return '';
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
