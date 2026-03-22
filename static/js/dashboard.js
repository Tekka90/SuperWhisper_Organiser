// Dashboard JavaScript

let statusRefreshInterval;

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    loadStatus();
    loadStats();
    loadRecentActivity();
    
    // Setup auto-refresh for status
    statusRefreshInterval = setInterval(loadStatus, 5000); // Refresh every 5 seconds
    
    // Setup event listeners
    document.getElementById('refresh-status').addEventListener('click', loadStatus);
    document.getElementById('refresh-all-btn').addEventListener('click', refreshAll);
    document.getElementById('scan-notes-btn').addEventListener('click', scanNotes);
});

async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.success) {
            updateStatusUI(data.status);
        }
    } catch (error) {
        console.error('Error loading status:', error);
    }
}

function updateStatusUI(status) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    const details = document.getElementById('status-details');
    
    if (status.is_processing) {
        dot.className = 'status-dot processing';
        text.textContent = 'Processing...';
        details.style.display = 'block';
        
        document.getElementById('current-folder').textContent = status.current_folder || 'Unknown';
        document.getElementById('started-at').textContent = formatDateTime(status.started_at);
        document.getElementById('progress-percent').textContent = status.progress_percent || 0;
        document.getElementById('progress-fill').style.width = `${status.progress_percent || 0}%`;
    } else {
        dot.className = 'status-dot idle';
        text.textContent = 'Idle - Monitoring for new recordings';
        details.style.display = 'none';
    }
}

async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        if (data.success) {
            updateStatsUI(data.stats);
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

function updateStatsUI(stats) {
    document.getElementById('stat-total').textContent = stats.total_processed;
    document.getElementById('stat-recent').textContent = stats.last_7_days;
    
    // Calculate success rate
    const total = Object.values(stats.by_status).reduce((a, b) => a + b, 0);
    const completed = stats.by_status.completed || 0;
    const successRate = total > 0 ? Math.round((completed / total) * 100) : 100;
    document.getElementById('stat-success').textContent = successRate;
    
    // Update type chart
    updateTypeChart(stats.by_type);
}

function updateTypeChart(byType) {
    const chartDiv = document.getElementById('type-chart');
    
    if (Object.keys(byType).length === 0) {
        chartDiv.innerHTML = '<div class="chart-placeholder">No data yet</div>';
        return;
    }
    
    // Create simple bar chart
    let html = '<div class="chart-bars">';
    const maxCount = Math.max(...Object.values(byType));
    
    for (const [type, count] of Object.entries(byType)) {
        const percentage = (count / maxCount) * 100;
        html += `
            <div class="chart-row">
                <div class="chart-label">${type}</div>
                <div class="chart-bar-container">
                    <div class="chart-bar" style="width: ${percentage}%"></div>
                    <div class="chart-value">${count}</div>
                </div>
            </div>
        `;
    }
    
    html += '</div>';
    chartDiv.innerHTML = html;
    
    // Add inline styles for chart
    const style = document.createElement('style');
    style.textContent = `
        .chart-bars { display: flex; flex-direction: column; gap: 1rem; }
        .chart-row { display: flex; align-items: center; gap: 1rem; }
        .chart-label { min-width: 120px; font-weight: 500; }
        .chart-bar-container { flex: 1; display: flex; align-items: center; gap: 0.5rem; }
        .chart-bar { height: 24px; background: linear-gradient(90deg, #4a90e2, #357abd); border-radius: 4px; transition: width 0.3s; }
        .chart-value { font-weight: bold; color: #4a90e2; min-width: 30px; }
    `;
    if (!document.getElementById('chart-styles')) {
        style.id = 'chart-styles';
        document.head.appendChild(style);
    }
}

async function loadRecentActivity() {
    try {
        const response = await fetch('/api/history?limit=5');
        const data = await response.json();
        
        if (data.success) {
            updateRecentActivityUI(data.history);
        }
    } catch (error) {
        console.error('Error loading recent activity:', error);
    }
}

function updateRecentActivityUI(history) {
    const activityDiv = document.getElementById('recent-activity');
    
    if (history.length === 0) {
        activityDiv.innerHTML = '<div class="activity-placeholder">No activity yet</div>';
        return;
    }
    
    let html = '<div class="activity-list">';
    
    for (const item of history) {
        const statusClass = `status-${item.status}`;
        let noteLink = '';
        if (item.note_file) {
            // Extract relative path from absolute path (strip everything up to and including "/notes/")
            const notesIdx = item.note_file.indexOf('/notes/');
            const relPath = notesIdx !== -1 ? item.note_file.slice(notesIdx + '/notes/'.length) : item.note_file;
            const noteName = item.note_file.split('/').pop();
            noteLink = `→ <a class="note-link" href="/notes-viewer?file=${encodeURIComponent(relPath)}">${noteName}</a>`;
        }
        html += `
            <div class="activity-item">
                <div class="activity-header">
                    <span class="status-badge ${statusClass}">${item.status}</span>
                    <span class="activity-time">${formatDateTime(item.started_at)}</span>
                </div>
                <div class="activity-content">
                    <strong>${item.folder_name}</strong>
                    ${noteLink}
                </div>
                ${item.participants ? `<div class="activity-meta">👥 ${item.participants}</div>` : ''}
            </div>
        `;
    }
    
    html += '</div>';
    activityDiv.innerHTML = html;
    
    // Add inline styles for activity list
    const style = document.createElement('style');
    style.textContent = `
        .activity-list { display: flex; flex-direction: column; gap: 1rem; }
        .activity-item { padding: 1rem; background: var(--bg-color); border-radius: 8px; }
        .activity-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
        .activity-time { font-size: 0.9rem; color: var(--text-secondary); }
        .activity-content { margin: 0.5rem 0; }
        .activity-meta { font-size: 0.9rem; color: var(--text-secondary); margin-top: 0.5rem; }
        .note-link { color: #4a90e2; text-decoration: none; font-style: italic; }
        .note-link:hover { text-decoration: underline; }
    `;
    if (!document.getElementById('activity-styles')) {
        style.id = 'activity-styles';
        document.head.appendChild(style);
    }
}

async function scanNotes() {
    const btn = document.getElementById('scan-notes-btn');
    const resultDiv = document.getElementById('action-result');
    
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    resultDiv.className = 'action-result';
    resultDiv.textContent = '';
    
    try {
        const response = await fetch('/api/scan-notes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force: false })
        });
        
        const data = await response.json();
        
        if (data.success) {
            resultDiv.className = 'action-result success';
            resultDiv.textContent = '✓ ' + data.message;
            loadStats(); // Refresh stats
        } else {
            resultDiv.className = 'action-result error';
            resultDiv.textContent = '✗ Error: ' + data.error;
        }
    } catch (error) {
        resultDiv.className = 'action-result error';
        resultDiv.textContent = '✗ Error: ' + error.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Scan Existing Notes';
        
        setTimeout(() => {
            resultDiv.className = 'action-result';
        }, 5000);
    }
}

function refreshAll() {
    loadStatus();
    loadStats();
    loadRecentActivity();
    
    const resultDiv = document.getElementById('action-result');
    resultDiv.className = 'action-result success';
    resultDiv.textContent = '✓ Data refreshed';
    
    setTimeout(() => {
        resultDiv.className = 'action-result';
    }, 3000);
}

function formatDateTime(isoString) {
    if (!isoString) return '-';
    
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hours ago`;
    if (diffDays < 7) return `${diffDays} days ago`;
    
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (statusRefreshInterval) {
        clearInterval(statusRefreshInterval);
    }
});
