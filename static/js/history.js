// History Page JavaScript

let currentPage = 0;
const pageSize = 50;
let allHistory = [];
let filteredHistory = [];

document.addEventListener('DOMContentLoaded', () => {
    loadHistory();
    
    // Setup event listeners
    document.getElementById('prev-page').addEventListener('click', () => changePage(-1));
    document.getElementById('next-page').addEventListener('click', () => changePage(1));
    document.getElementById('search-filter').addEventListener('input', filterHistory);
    document.getElementById('status-filter').addEventListener('change', filterHistory);
});

async function loadHistory() {
    try {
        const response = await fetch(`/api/history?limit=500&offset=0`);
        const data = await response.json();
        
        if (data.success) {
            allHistory = data.history;
            filteredHistory = allHistory;
            currentPage = 0;
            renderHistory();
        }
    } catch (error) {
        console.error('Error loading history:', error);
        document.getElementById('history-tbody').innerHTML = `
            <tr>
                <td colspan="7" class="error-row">Error loading history: ${error.message}</td>
            </tr>
        `;
    }
}

function filterHistory() {
    const searchTerm = document.getElementById('search-filter').value.toLowerCase();
    const statusFilter = document.getElementById('status-filter').value;
    
    filteredHistory = allHistory.filter(item => {
        const matchesSearch = !searchTerm || item.folder_name.toLowerCase().includes(searchTerm);
        const matchesStatus = !statusFilter || item.status === statusFilter;
        return matchesSearch && matchesStatus;
    });
    
    currentPage = 0;
    renderHistory();
}

function renderHistory() {
    const tbody = document.getElementById('history-tbody');
    const start = currentPage * pageSize;
    const end = start + pageSize;
    const pageItems = filteredHistory.slice(start, end);
    
    if (pageItems.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No history items found</td></tr>';
        updatePaginationButtons();
        return;
    }
    
    let html = '';
    for (const item of pageItems) {
        const duration = calculateDuration(item.started_at, item.completed_at);
        const statusClass = `status-${item.status}`;
        
        html += `
            <tr>
                <td><code>${item.folder_name}</code></td>
                <td>${formatDateTime(item.started_at)}</td>
                <td>${duration}</td>
                <td><span class="status-badge ${statusClass}">${item.status}</span></td>
                <td>${item.meeting_type || '-'}</td>
                <td>${item.participants || '-'}</td>
                <td>${item.note_file ? `<code>${item.note_file}</code>` : '-'}</td>
            </tr>
        `;
        
        if (item.error_message) {
            html += `
                <tr class="error-detail">
                    <td colspan="7"><strong>Error:</strong> ${item.error_message}</td>
                </tr>
            `;
        }
    }
    
    tbody.innerHTML = html;
    updatePaginationButtons();
}

function updatePaginationButtons() {
    const prevBtn = document.getElementById('prev-page');
    const nextBtn = document.getElementById('next-page');
    const pageInfo = document.getElementById('page-info');
    
    const totalPages = Math.ceil(filteredHistory.length / pageSize);
    
    prevBtn.disabled = currentPage === 0;
    nextBtn.disabled = currentPage >= totalPages - 1 || totalPages === 0;
    
    pageInfo.textContent = `Page ${currentPage + 1} of ${totalPages || 1} (${filteredHistory.length} items)`;
}

function changePage(delta) {
    currentPage += delta;
    renderHistory();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function calculateDuration(startStr, endStr) {
    if (!startStr || !endStr) return '-';
    
    const start = new Date(startStr);
    const end = new Date(endStr);
    const diffMs = end - start;
    
    if (diffMs < 0) return '-';
    
    const seconds = Math.floor(diffMs / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) {
        return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
        return `${minutes}m ${seconds % 60}s`;
    } else {
        return `${seconds}s`;
    }
}

function formatDateTime(isoString) {
    if (!isoString) return '-';
    
    const date = new Date(isoString);
    return date.toLocaleString();
}
