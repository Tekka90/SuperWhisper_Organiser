// Knowledge Base JavaScript

let knowledgeData = null;
let pendingMerge = null;  // Store merge info for modal

document.addEventListener('DOMContentLoaded', () => {
    loadKnowledge();
    
    // Setup tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
    
    // Setup refresh button
    document.getElementById('refresh-kb-btn').addEventListener('click', () => {
        loadKnowledge();
    });
    
    // Setup merge modal handlers
    document.getElementById('merge-keep-first-btn').addEventListener('click', () => executeMerge('first'));
    document.getElementById('merge-keep-second-btn').addEventListener('click', () => executeMerge('second'));
    document.getElementById('merge-cancel-btn').addEventListener('click', closeMergeModal);
    
    // Setup correction modal handlers
    document.getElementById('correct-name-apply-btn').addEventListener('click', executeCorrection);
    document.getElementById('correct-name-cancel-btn').addEventListener('click', closeCorrectNameModal);
    
    // Close modal when clicking outside
    document.getElementById('merge-names-modal').addEventListener('click', (e) => {
        if (e.target.id === 'merge-names-modal') closeMergeModal();
    });
    
    document.getElementById('correct-name-modal').addEventListener('click', (e) => {
        if (e.target.id === 'correct-name-modal') closeCorrectNameModal();
    });
});

async function loadKnowledge() {
    try {
        // Show loading state on button
        const refreshBtn = document.getElementById('refresh-kb-btn');
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.textContent = '⏳ Loading...';
        }
        
        // Add cache-busting parameter
        const response = await fetch('/api/knowledge?_=' + Date.now());
        const data = await response.json();
        
        if (data.success) {
            knowledgeData = data;
            updateSummaryStats();
            renderAllTabs();
        }
        
        // Reset button
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.textContent = '🔄 Refresh';
        }
    } catch (error) {
        console.error('Error loading knowledge:', error);
        const refreshBtn = document.getElementById('refresh-kb-btn');
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.textContent = '🔄 Refresh';
        }
    }
}

function updateSummaryStats() {
    const context = knowledgeData.context;
    
    document.getElementById('kb-people').textContent = context.known_people.all.length;
    document.getElementById('kb-projects').textContent = context.known_projects.length;
    document.getElementById('kb-corrections').textContent = Object.keys(context.name_corrections).length;
    document.getElementById('kb-one-on-ones').textContent = context.one_on_one_files.length;
}

function switchTab(tabName) {
    // Update buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    
    // Update panes
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.toggle('active', pane.id === `${tabName}-tab`);
    });
}

function renderAllTabs() {
    renderPeopleTab();
    renderProjectsTab();
    renderCorrectionsTab();
    renderPatternsTab();
    renderLearningContext();
}

function renderPeopleTab() {
    const people = knowledgeData.knowledge.people;
    const listDiv = document.getElementById('people-list');
    
    if (people.length === 0) {
        listDiv.innerHTML = '<div class="empty-state"><p>No people learned yet</p></div>';
        return;
    }
    
    // Sort people by usage count (most mentioned first)
    const sortedPeople = [...people].sort((a, b) => (b.usage_count || 0) - (a.usage_count || 0));
    
    let html = '<div class="knowledge-grid">';
    
    sortedPeople.forEach(person => {
        const fileCount = person.file_count || 0;
        const fileLink = person.source_file ? 
            `<a href="#" class="file-link" data-file-path="${person.source_file}" onclick="openNoteFile(event, '${person.source_file}'); return false;">📄 Last seen in: ${person.source_file}</a>` : 
            '';
        
        // Escape name for use in data attribute
        const escapedName = person.entity_name.replace(/"/g, '&quot;');
        
        html += `
            <div class="knowledge-item person-item" draggable="true" data-person-name="${escapedName}">
                <h4>👤 ${person.entity_name}</h4>
                <p>📊 Confidence: ${(person.confidence * 100).toFixed(0)}%</p>
                <p>🔢 Mentioned: ${person.usage_count} times</p>
                <p>📁 In ${fileCount} file${fileCount !== 1 ? 's' : ''}</p>
                <p>📅 Last seen: ${formatDateTime(person.last_seen)}</p>
                ${fileLink ? `<p class="meta-item">${fileLink}</p>` : ''}
                <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
                    <button class="correct-name-btn" data-name="${escapedName}" style="padding: 0.15rem 0.4rem; font-size: 0.75rem; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer;">✏️ Correct</button>
                    <button class="delete-name-btn" onclick="deleteName(event, '${person.entity_name}')" style="padding: 0.15rem 0.4rem; font-size: 0.75rem; background: #dc3545; color: white; border: none; border-radius: 3px; cursor: pointer;">🗑️ Delete</button>
                </div>
                <p class="help-text" style="margin-top: 0.5rem; font-size: 0.85rem;">💡 Drag onto another name to merge</p>
            </div>
        `;
    });
    
    html += '</div>';
    
    listDiv.innerHTML = html;
    
    // Add drag-and-drop event listeners to all person items
    document.querySelectorAll('.person-item').forEach(item => {
        item.addEventListener('dragstart', handleDragStart);
        item.addEventListener('dragover', handleDragOver);
        item.addEventListener('dragleave', handleDragLeave);
        item.addEventListener('drop', handleDrop);
        item.addEventListener('dragend', handleDragEnd);
    });
    
    // Add click listeners to correct buttons
    document.querySelectorAll('.correct-name-btn').forEach(btn => {
        btn.addEventListener('click', (event) => {
            event.stopPropagation();
            event.preventDefault();
            const name = btn.getAttribute('data-name');
            showCorrectNameModal(event, name);
        });
    });
}

function renderProjectsTab() {
    const projects = knowledgeData.knowledge.projects;
    const listDiv = document.getElementById('projects-list');
    
    if (projects.length === 0) {
        listDiv.innerHTML = '<div class="empty-state"><p>No projects learned yet</p></div>';
        return;
    }
    
    let html = '';
    projects.forEach(project => {
        html += `
            <div class="knowledge-item">
                <h4>📋 ${project.entity_name}</h4>
                <p>📊 Confidence: ${(project.confidence * 100).toFixed(0)}%</p>
                <p>🔢 Mentioned: ${project.usage_count} times</p>
                <p>📅 Last seen: ${formatDateTime(project.last_seen)}</p>
                ${project.source_file ? `<p class="meta-item">📄 Last seen in: ${project.source_file}</p>` : ''}
                ${project.context ? `<p class="meta-item">📑 Context: ${project.context}</p>` : ''}
            </div>
        `;
    });
    
    listDiv.innerHTML = html;
}

function renderCorrectionsTab() {
    const corrections = knowledgeData.knowledge.name_corrections;
    const listDiv = document.getElementById('corrections-list');
    
    if (corrections.length === 0) {
        listDiv.innerHTML = '<div class="empty-state"><p>No name corrections learned yet</p></div>';
        return;
    }
    
    let html = '';
    corrections.forEach(correction => {
        html += `
            <div class="knowledge-item">
                <h4>🔤 "${correction.incorrect_name}" → "${correction.correct_name}"</h4>
                <p>✅ Applied: ${correction.applied_count} times</p>
                <p>📅 Created: ${formatDateTime(correction.created_at)}</p>
                ${correction.source_file ? `<p class="meta-item">📄 First detected in: ${correction.source_file}</p>` : ''}
                ${correction.context ? `<p class="meta-item">📑 Context: ${correction.context}</p>` : ''}
            </div>
        `;
    });
    
    listDiv.innerHTML = html;
}

function renderPatternsTab() {
    const patterns = knowledgeData.knowledge.patterns;
    const listDiv = document.getElementById('patterns-list');
    
    if (patterns.length === 0) {
        listDiv.innerHTML = '<div class="empty-state"><p>No meeting patterns learned yet</p></div>';
        return;
    }
    
    // Group by pattern type
    const oneOnOnes = patterns.filter(p => p.entity_name.startsWith('1-on-1:'));
    const teamMeetings = patterns.filter(p => p.entity_name.startsWith('team:'));
    const others = patterns.filter(p => !p.entity_name.includes(':'));
    
    let html = '';
    
    if (oneOnOnes.length > 0) {
        html += '<h4>🤝 1-on-1 Meetings</h4><div class="knowledge-grid">';
        oneOnOnes.forEach(p => {
            const person = p.entity_name.split(':')[1];
            html += `
                <div class="knowledge-item">
                    <h4>👤 ${person}</h4>
                    <p>📄 Note file: ${p.source_file}</p>
                    <p>🔢 Notes: ${p.usage_count}</p>
                    <p>📅 Last seen: ${formatDateTime(p.last_seen)}</p>
                </div>
            `;
        });
        html += '</div>';
    }
    
    if (teamMeetings.length > 0) {
        html += '<h4>👥 Team Meetings</h4><div class="knowledge-grid">';
        teamMeetings.forEach(p => {
            const team = p.entity_name.split(':')[1];
            html += `
                <div class="knowledge-item">
                    <h4>👥 ${team}</h4>
                    <p>📄 Note file: ${p.source_file}</p>
                    <p>🔢 Meetings: ${p.usage_count}</p>
                    <p>📅 Last seen: ${formatDateTime(p.last_seen)}</p>
                </div>
            `;
        });
        html += '</div>';
    }
    
    if (others.length > 0) {
        html += '<h4>📋 Other Patterns</h4><div class="knowledge-grid">';
        others.forEach(p => {
            html += `
                <div class="knowledge-item">
                    <h4>${p.entity_name}</h4>
                    <p>📄 Note file: ${p.source_file}</p>
                    <p>🔢 Count: ${p.usage_count}</p>
                </div>
            `;
        });
        html += '</div>';
    }
    
    listDiv.innerHTML = html;
}

function renderLearningContext() {
    const context = knowledgeData.context;
    const contextDiv = document.getElementById('learning-context');
    
    let text = '';
    
    if (context.one_on_one_files.length > 0) {
        text += '1-on-1 Meeting Files:\n';
        context.one_on_one_files.forEach(person => {
            text += `  - ${person}\n`;
        });
        text += '\n';
    }
    
    if (context.known_projects.length > 0) {
        text += 'Known Projects:\n';
        context.known_projects.forEach(project => {
            text += `  - ${project}\n`;
        });
        text += '\n';
    }
    
    if (Object.keys(context.name_corrections).length > 0) {
        text += 'Name Corrections:\n';
        for (const [incorrect, correct] of Object.entries(context.name_corrections)) {
            text += `  - "${incorrect}" → "${correct}"\n`;
        }
        text += '\n';
    }
    
    if (context.known_people.all.length > 0) {
        text += `Known People (${context.known_people.all.length}):\n`;
        context.known_people.all.slice(0, 20).forEach(person => {
            text += `  - ${person}\n`;
        });
        if (context.known_people.all.length > 20) {
            text += `  ... and ${context.known_people.all.length - 20} more\n`;
        }
    }
    
    if (!text) {
        text = 'No learning context available yet. Process some recordings to build knowledge.';
    }
    
    contextDiv.textContent = text;
}

function formatDateTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString();
}

// Drag-and-drop handlers for name merging
let draggedPersonName = null;

function handleDragStart(e) {
    draggedPersonName = e.target.dataset.personName;
    e.target.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', draggedPersonName);
}

function handleDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';
    
    const targetName = e.currentTarget.dataset.personName;
    if (targetName && targetName !== draggedPersonName) {
        e.currentTarget.classList.add('drag-over');
    }
    
    return false;
}

function handleDragLeave(e) {
    e.currentTarget.classList.remove('drag-over');
}

function handleDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }
    
    e.currentTarget.classList.remove('drag-over');
    
    const targetName = e.currentTarget.dataset.personName;
    const sourceName = draggedPersonName;
    
    if (targetName && sourceName && targetName !== sourceName) {
        showMergeModal(sourceName, targetName);
    }
    
    return false;
}

function handleDragEnd(e) {
    e.target.classList.remove('dragging');
    document.querySelectorAll('.person-item').forEach(item => {
        item.classList.remove('drag-over');
    });
}

// Merge modal functions
function showMergeModal(name1, name2) {
    pendingMerge = { name1, name2 };
    
    const modal = document.getElementById('merge-names-modal');
    const message = document.getElementById('merge-names-message');
    const btn1 = document.getElementById('merge-keep-first-btn');
    const btn2 = document.getElementById('merge-keep-second-btn');
    
    message.textContent = `Merge "${name1}" and "${name2}" into one person?`;
    btn1.textContent = `Keep "${name1}"`;
    btn2.textContent = `Keep "${name2}"`;
    
    modal.style.display = 'block';
}

function closeMergeModal() {
    const modal = document.getElementById('merge-names-modal');
    modal.style.display = 'none';
    pendingMerge = null;
}

function openNoteFile(event, filePath) {
    event.preventDefault();
    event.stopPropagation();
    // Navigate to notes page with the file selected
    window.location.href = `/notes-viewer?file=${encodeURIComponent(filePath)}`;
}

function deleteName(event, name) {
    event.preventDefault();
    event.stopPropagation();
    
    if (!confirm(`Are you sure you want to delete "${name}" from the knowledge base?\n\nThis will remove it from all notes and cannot be undone.`)) {
        return;
    }
    
    fetch('/api/knowledge/delete-name', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: name })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`✓ Successfully deleted "${name}"`);
            loadKnowledge();
        } else {
            alert('Error: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error deleting name:', error);
        alert('Error deleting name: ' + error.message);
    });
}

async function executeMerge(choice) {
    if (!pendingMerge) return;
    
    const { name1, name2 } = pendingMerge;
    const keepName = choice === 'first' ? name1 : name2;
    const removeName = choice === 'first' ? name2 : name1;
    
    // Save before closing
    const mergeInfo = { name1, name2, keepName, removeName };
    closeMergeModal();
    
    try {
        // Show progress indicator
        const refreshBtn = document.getElementById('refresh-kb-btn');
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.textContent = '⏳ Merging names...';
        }
        
        const response = await fetch('/api/knowledge/merge-names', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name1: mergeInfo.name1,
                name2: mergeInfo.name2,
                keep_name: mergeInfo.keepName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✓ Successfully merged names into "${mergeInfo.keepName}"\n\nUpdated ${data.files_updated} note files.`);
            // Reload knowledge base
            await loadKnowledge();
        } else {
            alert('Error merging names: ' + data.error);
        }
        
        // Reset button
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.textContent = '🔄 Refresh';
        }
    } catch (error) {
        console.error('Error merging names:', error);
        alert('Error merging names: ' + error.message);
        
        const refreshBtn = document.getElementById('refresh-kb-btn');
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.textContent = '🔄 Refresh';
        }
    }
}

// Name Correction Functions
let currentNameToCorrect = null;

function showCorrectNameModal(event, name) {
    event.stopPropagation();
    event.preventDefault();
    
    console.log('showCorrectNameModal called with name:', name);
    
    currentNameToCorrect = name;
    
    const modal = document.getElementById('correct-name-modal');
    const message = document.getElementById('correct-name-message');
    const input = document.getElementById('correct-name-input');
    
    message.textContent = `Correct "${name}" to:`;
    input.value = name;  // Pre-fill with current name
    input.focus();
    input.select();  // Select all text for easy replacement
    
    modal.style.display = 'flex';
}

function closeCorrectNameModal() {
    const modal = document.getElementById('correct-name-modal');
    modal.style.display = 'none';
    currentNameToCorrect = null;
}

async function executeCorrection() {
    console.log('executeCorrection called, currentNameToCorrect:', currentNameToCorrect);
    
    if (!currentNameToCorrect) {
        alert('Error: No name selected for correction');
        return;
    }
    
    const input = document.getElementById('correct-name-input');
    const newName = input.value.trim();
    
    console.log('Correcting from:', currentNameToCorrect, 'to:', newName);
    
    if (!newName) {
        alert('Please enter a corrected name.');
        return;
    }
    
    if (newName === currentNameToCorrect) {
        alert('New name is the same as current name.');
        closeCorrectNameModal();
        return;
    }
    
    // Save the old name before closing the modal (which sets currentNameToCorrect to null)
    const oldName = currentNameToCorrect;
    
    // Close the input modal
    closeCorrectNameModal();
    
    // Show progress
    const progressModal = document.getElementById('correction-progress');
    const progressMessage = document.getElementById('correction-progress-message');
    progressMessage.textContent = `🔄 Correcting "${oldName}" to "${newName}" in all files...`;
    progressModal.style.display = 'flex';
    
    try {
        console.log('Sending request with:', { old_name: oldName, new_name: newName });
        
        const response = await fetch('/api/knowledge/correct-name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                old_name: oldName,
                new_name: newName
            })
        });
        
        const data = await response.json();
        
        console.log('Response:', data);
        
        // Hide progress
        progressModal.style.display = 'none';
        
        if (data.success) {
            alert(`✓ Successfully corrected "${oldName}" to "${newName}"\n\nUpdated ${data.files_updated} note files.`);
            // Reload knowledge base
            await loadKnowledge();
        } else {
            alert('Error correcting name: ' + data.error);
        }
    } catch (error) {
        console.error('Error correcting name:', error);
        progressModal.style.display = 'none';
        alert('Error correcting name: ' + error.message);
    }
}
