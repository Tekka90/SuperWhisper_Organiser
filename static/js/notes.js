// Notes Viewer JavaScript

let currentNote = null;
let originalContent = '';
let isEditing = false;
let pendingMerge = null;  // Store merge info for modal
let detectedNames = [];  // Store detected names for current note
let currentNameToCorrect = null;  // Store name being corrected
let searchTimeout = null;  // Debounce search
let currentSearchTerm = '';  // Active search term for highlighting

// Progress indicator functions
function showProgress(message) {
    const progress = document.getElementById('ai-progress');
    const messageEl = document.getElementById('progress-message');
    messageEl.textContent = message;
    progress.style.display = 'flex';
}

function hideProgress() {
    const progress = document.getElementById('ai-progress');
    progress.style.display = 'none';
}

function updateProgress(message) {
    const messageEl = document.getElementById('progress-message');
    messageEl.textContent = message;
}

document.addEventListener('DOMContentLoaded', () => {
    loadNotesTree();
    
    // Check for file parameter in URL
    const urlParams = new URLSearchParams(window.location.search);
    const fileParam = urlParams.get('file');
    if (fileParam) {
        // Wait for tree to load, then select the file
        setTimeout(() => {
            loadNote(fileParam);
        }, 500);
    }
    
    // Setup event listeners
    document.getElementById('refresh-tree-btn').addEventListener('click', loadNotesTree);
    document.getElementById('note-search').addEventListener('input', searchNotes);
    document.getElementById('detect-names-btn').addEventListener('click', detectNames);
    document.getElementById('unmerge-btn').addEventListener('click', showExtractDialog);
    document.getElementById('rename-btn').addEventListener('click', renameNote);
    document.getElementById('delete-btn').addEventListener('click', deleteNote);
    document.getElementById('edit-btn').addEventListener('click', startEditing);
    document.getElementById('save-btn').addEventListener('click', saveNote);
    document.getElementById('cancel-btn').addEventListener('click', cancelEditing);
    
    // Modal button handlers
    document.getElementById('merge-btn-cancel').addEventListener('click', closeMergeModal);
    document.getElementById('extract-btn-cancel').addEventListener('click', closeExtractModal);
    document.getElementById('name-correction-cancel-btn').addEventListener('click', closeNameCorrectionModal);
    document.getElementById('apply-name-correction-btn').addEventListener('click', applyNameCorrection);
    
    // Close modals when clicking outside
    document.getElementById('merge-modal').addEventListener('click', (e) => {
        if (e.target.id === 'merge-modal') closeMergeModal();
    });
    document.getElementById('extract-modal').addEventListener('click', (e) => {
        if (e.target.id === 'extract-modal') closeExtractModal();
    });
    document.getElementById('name-correction-modal').addEventListener('click', (e) => {
        if (e.target.id === 'name-correction-modal') closeNameCorrectionModal();
    });
});

async function loadNotesTree() {
    try {
        const response = await fetch('/api/note-tree');
        const data = await response.json();
        
        if (data.success) {
            renderNotesTree(data.tree);
        }
    } catch (error) {
        console.error('Error loading notes tree:', error);
        document.getElementById('notes-tree').innerHTML = '<div class="tree-error">Error loading notes</div>';
    }
}

function renderNotesTree(tree, container = null, level = 0) {
    if (!container) {
        container = document.getElementById('notes-tree');
        container.innerHTML = '';
    }
    
    if (tree.length === 0) {
        container.innerHTML = '<div class="tree-empty">No notes found</div>';
        return;
    }
    
    for (const item of tree) {
        if (item.type === 'folder') {
            // Create folder container
            const folderDiv = document.createElement('div');
            folderDiv.className = 'tree-folder-container';
            folderDiv.style.paddingLeft = `${level * 1}rem`;
            
            // Create folder header (clickable)
            const folderHeader = document.createElement('div');
            folderHeader.className = 'tree-folder expanded';
            folderHeader.innerHTML = `<span class="folder-icon">📂</span> ${item.name}`;
            folderHeader.dataset.expanded = 'true';
            folderHeader.dataset.folderPath = item.path || item.name;
            
            // Create children container
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'tree-folder-children';
            childrenContainer.style.display = 'block';
            
            // Toggle folder on click
            folderHeader.addEventListener('click', (e) => {
                e.stopPropagation();
                const isExpanded = folderHeader.dataset.expanded === 'true';
                folderHeader.dataset.expanded = !isExpanded;
                folderHeader.classList.toggle('expanded', !isExpanded);
                folderHeader.classList.toggle('collapsed', isExpanded);
                childrenContainer.style.display = isExpanded ? 'none' : 'block';
                
                // Update icon
                const icon = folderHeader.querySelector('.folder-icon');
                icon.textContent = isExpanded ? '📁' : '📂';
            });
            
            // Enable drop on folders to move files
            folderHeader.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.stopPropagation();
                e.dataTransfer.dropEffect = 'move';
                folderHeader.classList.add('drag-over');
            });
            
            folderHeader.addEventListener('dragleave', (e) => {
                folderHeader.classList.remove('drag-over');
            });
            
            folderHeader.addEventListener('drop', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                folderHeader.classList.remove('drag-over');
                
                const sourcePath = e.dataTransfer.getData('text/plain');
                const targetFolder = folderHeader.dataset.folderPath;
                
                if (sourcePath && targetFolder) {
                    await moveNoteToFolder(sourcePath, targetFolder);
                }
            });
            
            folderDiv.appendChild(folderHeader);
            folderDiv.appendChild(childrenContainer);
            container.appendChild(folderDiv);
            
            // Render children
            if (item.children && item.children.length > 0) {
                renderNotesTree(item.children, childrenContainer, level + 1);
            }
        } else {
            // Create file item
            const itemDiv = document.createElement('div');
            itemDiv.className = 'tree-file tree-item';
            itemDiv.style.paddingLeft = `${level * 1}rem`;
            itemDiv.innerHTML = `📄 ${item.name}`;
            itemDiv.dataset.path = item.path;
            itemDiv.draggable = true;
            
            // Click to load
            itemDiv.addEventListener('click', () => loadNote(item.path));
            
            // Drag and drop for merging
            itemDiv.addEventListener('dragstart', (e) => {
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', item.path);
                itemDiv.classList.add('dragging');
            });
            
            itemDiv.addEventListener('dragend', (e) => {
                itemDiv.classList.remove('dragging');
            });
            
            itemDiv.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                if (!itemDiv.classList.contains('dragging')) {
                    itemDiv.classList.add('drag-over');
                }
            });
            
            itemDiv.addEventListener('dragleave', (e) => {
                itemDiv.classList.remove('drag-over');
            });
            
            itemDiv.addEventListener('drop', async (e) => {
                e.preventDefault();
                itemDiv.classList.remove('drag-over');
                
                const sourcePath = e.dataTransfer.getData('text/plain');
                const targetPath = item.path;
                
                if (sourcePath !== targetPath) {
                    await mergeNotes(sourcePath, targetPath);
                }
            });
            
            container.appendChild(itemDiv);
        }
    }
}

function searchNotes() {
    const searchInput = document.getElementById('note-search');
    const searchTerm = searchInput.value.trim();
    
    // Clear previous timeout
    if (searchTimeout) {
        clearTimeout(searchTimeout);
    }
    
    // If search is empty, show all files
    if (!searchTerm) {
        currentSearchTerm = '';
        const treeItems = document.querySelectorAll('.tree-file, .tree-folder');
        treeItems.forEach(item => {
            item.style.display = 'flex';
            // Remove highlights
            const textNode = item.childNodes[0];
            if (textNode && textNode.nodeType === Node.TEXT_NODE) {
                const plainText = textNode.textContent.replace(/[📄📁]\s*/, '');
                item.innerHTML = `${item.classList.contains('tree-folder') ? '📁' : '📄'} ${plainText}`;
            }
        });
        return;
    }
    
    // Debounce API call (wait 300ms after user stops typing)
    searchTimeout = setTimeout(async () => {
        if (searchTerm === currentSearchTerm) {
            return; // Same query, no need to search again
        }
        
        currentSearchTerm = searchTerm;
        
        try {
            const response = await fetch(`/api/notes/search?q=${encodeURIComponent(searchTerm)}`);
            const data = await response.json();
            
            if (data.success) {
                const matchingPaths = new Set(data.results.map(r => r.path));
                const treeItems = document.querySelectorAll('.tree-file');
                
                treeItems.forEach(item => {
                    const itemPath = item.dataset.path;
                    
                    if (matchingPaths.has(itemPath)) {
                        item.style.display = 'flex';
                        
                        // Find the result to check for title match
                        const result = data.results.find(r => r.path === itemPath);
                        
                        // Highlight search term in filename
                        if (result && result.title_match) {
                            const icon = item.classList.contains('tree-folder') ? '📁' : '📄';
                            const filename = result.filename;
                            const regex = new RegExp(`(${escapeRegex(searchTerm)})`, 'gi');
                            const highlighted = filename.replace(regex, '<mark>$1</mark>');
                            item.innerHTML = `${icon} ${highlighted}`;
                            
                            // Add a badge if there's also a content match
                            if (result.content_match) {
                                const badge = document.createElement('span');
                                badge.className = 'content-match-badge';
                                badge.textContent = `${result.snippets.length} match${result.snippets.length > 1 ? 'es' : ''}`;
                                badge.title = 'Content matches found';
                                badge.style.cssText = 'margin-left: 8px; background: #4a90e2; color: white; padding: 2px 6px; border-radius: 10px; font-size: 10px;';
                                item.appendChild(badge);
                            }
                        } else if (result && result.content_match) {
                            // Content match only (not in title)
                            const icon = item.classList.contains('tree-folder') ? '📁' : '📄';
                            const filename = result.filename;
                            const badge = document.createElement('span');
                            badge.className = 'content-match-badge';
                            badge.textContent = `${result.snippets.length} in content`;
                            badge.title = 'Content matches found';
                            badge.style.cssText = 'margin-left: 8px; background: #50c878; color: white; padding: 2px 6px; border-radius: 10px; font-size: 10px;';
                            item.innerHTML = `${icon} ${filename}`;
                            item.appendChild(badge);
                        }
                    } else {
                        item.style.display = 'none';
                    }
                });
                
                // Show/hide folders based on whether they have visible children
                updateFolderVisibility();
            }
        } catch (error) {
            console.error('Search error:', error);
        }
    }, 300);
}

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function updateFolderVisibility() {
    const folders = document.querySelectorAll('.tree-folder');
    folders.forEach(folder => {
        const nextSibling = folder.nextElementSibling;
        if (nextSibling && nextSibling.classList.contains('tree-children')) {
            const visibleChildren = nextSibling.querySelectorAll('.tree-file:not([style*="display: none"])');
            if (visibleChildren.length > 0) {
                folder.style.display = 'flex';
            } else {
                folder.style.display = 'none';
            }
        }
    });
}

async function loadNote(path) {
    if (isEditing) {
        if (!confirm('You have unsaved changes. Discard them?')) {
            return;
        }
        cancelEditing();
    }
    
    try {
        const response = await fetch(`/api/notes/${encodeURIComponent(path)}`);
        const data = await response.json();
        
        if (data.success) {
            currentNote = data;
            originalContent = data.content;
            
            // Load detected names from database
            detectedNames = data.detected_names || [];
            
            displayNote();
            
            // Update selection in tree
            document.querySelectorAll('.tree-item').forEach(item => {
                item.classList.toggle('selected', item.dataset.path === path);
            });
        } else {
            alert('Error loading note: ' + data.error);
        }
    } catch (error) {
        console.error('Error loading note:', error);
        alert('Error loading note: ' + error.message);
    }
}

function displayNote() {
    if (!currentNote) return;
    
    // Update header
    document.getElementById('note-title').textContent = currentNote.filename;
    
    // Update metadata
    const meta = document.getElementById('note-meta');
    meta.style.display = 'flex';
    document.getElementById('note-modified').textContent = formatDateTime(currentNote.modified);
    document.getElementById('note-size').textContent = formatSize(currentNote.size);
    
    // Render markdown
    const viewer = document.getElementById('note-viewer');
    viewer.innerHTML = marked.parse(currentNote.content);
    
    // Make checkboxes interactive in read mode
    enableInteractiveCheckboxes(viewer);
    
    // Highlight search term if there's an active search
    if (currentSearchTerm) {
        highlightSearchTermInViewer();
    }
    
    // Highlight names if detected (do this after search highlighting)
    if (detectedNames.length > 0) {
        highlightNamesInViewer();
    }
    
    viewer.style.display = 'block';
    
    // Check if file has multiple meetings (can be un-merged)
    const hasMeetings = currentNote.content.includes('---') || 
                        (currentNote.content.match(/^## /gm) || []).length > 1;
    
    // Update buttons
    document.getElementById('detect-names-btn').disabled = false;
    document.getElementById('unmerge-btn').disabled = !hasMeetings;
    document.getElementById('rename-btn').disabled = false;
    document.getElementById('delete-btn').disabled = false;
    document.getElementById('edit-btn').disabled = false;
    
    // Hide editor
    document.getElementById('note-editor').style.display = 'none';
}

function enableInteractiveCheckboxes(viewer) {
    // marked.js renders `- [ ]` as <input type="checkbox" disabled>.
    // Remove the disabled attribute and attach a click handler that
    // toggles the corresponding line in the raw markdown, then saves.
    const checkboxes = viewer.querySelectorAll('input[type="checkbox"]');

    checkboxes.forEach((checkbox, index) => {
        checkbox.removeAttribute('disabled');
        checkbox.style.cursor = 'pointer';

        checkbox.addEventListener('change', async () => {
            // Toggle the nth checkbox item in the raw markdown source.
            // We count occurrences of `- [ ]` and `- [x]` (case-insensitive)
            // to find the one matching `index`.
            const checkboxRegex = /^(\s*[-*+]\s*)\[( |x)\]/gim;
            let count = 0;
            const newContent = currentNote.content.replace(checkboxRegex, (match, prefix, state) => {
                if (count === index) {
                    count++;
                    return checkbox.checked ? `${prefix}[x]` : `${prefix}[ ]`;
                }
                count++;
                return match;
            });

            if (newContent === currentNote.content) return; // Nothing changed

            // Optimistically update in-memory content so re-renders stay in sync
            currentNote.content = newContent;

            try {
                const response = await fetch(`/api/notes/${encodeURIComponent(currentNote.filename)}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: newContent })
                });
                const data = await response.json();
                if (!data.success) {
                    console.error('Failed to save checkbox state:', data.error);
                    // Revert the checkbox visually on failure
                    checkbox.checked = !checkbox.checked;
                    currentNote.content = currentNote.content.replace(
                        checkbox.checked ? /^(\s*[-*+]\s*)\[ \]/im : /^(\s*[-*+]\s*)\[x\]/im,
                        (m, p) => checkbox.checked ? `${p}[x]` : `${p}[ ]`
                    );
                }
            } catch (err) {
                console.error('Error saving checkbox state:', err);
                checkbox.checked = !checkbox.checked;
            }
        });
    });
}

async function renameNote() {
    if (!currentNote || isEditing) return;
    
    const currentPath = currentNote.filename; // Full path to the file
    
    // Extract just the filename (last part of path) without extension
    const pathParts = currentPath.split('/');
    const currentFilename = pathParts[pathParts.length - 1];
    const nameWithoutExt = currentFilename.replace(/\.md$/, '');
    
    const newName = prompt(`Rename note:\n\nCurrent name: ${nameWithoutExt}\n\nEnter new name (without .md extension):`, nameWithoutExt);
    
    if (!newName || newName === nameWithoutExt) {
        return; // User cancelled or entered same name
    }
    
    // Add .md extension if not present
    const newFilename = newName.endsWith('.md') ? newName : `${newName}.md`;
    
    const renameBtn = document.getElementById('rename-btn');
    renameBtn.disabled = true;
    renameBtn.textContent = 'Renaming...';
    
    try {
        const response = await fetch('/api/notes/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                old_path: currentPath,
                new_name: newFilename
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            const status = document.getElementById('save-status');
            status.className = 'save-status success';
            status.textContent = '✓ File renamed successfully';
            
            if (data.correction_detected) {
                status.textContent += ' (Name correction learned!)';
            }
            
            setTimeout(() => {
                status.className = 'save-status';
            }, 3000);
            
            // Reload the tree and load the renamed note
            await loadNotesTree();
            await loadNote(data.new_path);
        } else {
            alert('Error renaming note: ' + data.error);
        }
    } catch (error) {
        console.error('Error renaming note:', error);
        alert('Error renaming note: ' + error.message);
    } finally {
        renameBtn.disabled = false;
        renameBtn.textContent = 'Rename';
    }
}

async function mergeNotes(sourcePath, targetPath) {
    if (!sourcePath || !targetPath || sourcePath === targetPath) return;
    
    // Extract file names for display
    const sourceFile = sourcePath.split('/').pop().replace('.md', '');
    const targetFile = targetPath.split('/').pop().replace('.md', '');
    
    // Store merge info and show custom modal
    pendingMerge = { sourcePath, targetPath, sourceFile, targetFile };
    showMergeModal(sourceFile, targetFile);
}

function showMergeModal(sourceFile, targetFile) {
    const modal = document.getElementById('merge-modal');
    const message = document.getElementById('merge-message');
    const btn1 = document.getElementById('merge-btn-option1');
    const btn2 = document.getElementById('merge-btn-option2');
    
    message.innerHTML = `
        <strong>Source:</strong> ${sourceFile}<br>
        <strong>Target:</strong> ${targetFile}<br><br>
        Choose which filename to keep for the merged file:
    `;
    
    btn1.textContent = sourceFile;
    btn2.textContent = targetFile;
    
    // Store the choice function on the buttons themselves
    btn1.onclick = () => executeMerge(sourceFile);
    btn2.onclick = () => executeMerge(targetFile);
    
    modal.classList.add('show');
}

function closeMergeModal() {
    const modal = document.getElementById('merge-modal');
    modal.classList.remove('show');
    pendingMerge = null;
}

async function executeMerge(finalName) {
    // Save pendingMerge data before closing modal
    if (!pendingMerge) return;
    
    const { sourcePath, targetPath } = pendingMerge;
    
    // Now close the modal
    closeMergeModal();
    
    try {
        const response = await fetch('/api/notes/merge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_path: sourcePath,
                target_path: targetPath,
                final_name: finalName + '.md'
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            const status = document.getElementById('save-status');
            status.className = 'save-status success';
            status.textContent = `✓ Files merged successfully into ${data.final_path}`;
            
            setTimeout(() => {
                status.className = 'save-status';
            }, 4000);
            
            // Reload tree and open merged file
            await loadNotesTree();
            await loadNote(data.final_path);
        } else {
            alert('Error merging notes: ' + data.error);
        }
    } catch (error) {
        console.error('Error merging notes:', error);
        alert('Error merging notes: ' + error.message);
    }
}

async function deleteNote() {
    if (!currentNote) return;
    
    const filename = currentNote.filename.split('/').pop();
    
    if (!confirm(`Are you sure you want to delete this note?\n\n"${filename}"\n\nThis action cannot be undone.`)) {
        return;
    }
    
    const deleteBtn = document.getElementById('delete-btn');
    deleteBtn.disabled = true;
    deleteBtn.textContent = 'Deleting...';
    
    try {
        const response = await fetch('/api/notes/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: currentNote.filename
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            const status = document.getElementById('save-status');
            status.className = 'save-status success';
            status.textContent = '✓ Note deleted successfully';
            
            setTimeout(() => {
                status.className = 'save-status';
            }, 3000);
            
            // Clear current note
            currentNote = null;
            document.getElementById('note-title').textContent = 'Select a note to view';
            document.getElementById('note-viewer').innerHTML = '<div class="empty-state"><p>Note deleted</p></div>';
            document.getElementById('note-meta').style.display = 'none';
            
            // Disable buttons
            document.getElementById('unmerge-btn').disabled = true;
            document.getElementById('rename-btn').disabled = true;
            document.getElementById('delete-btn').disabled = true;
            document.getElementById('edit-btn').disabled = true;
            
            // Reload tree
            await loadNotesTree();
        } else {
            alert('Error deleting note: ' + data.error);
        }
    } catch (error) {
        console.error('Error deleting note:', error);
        alert('Error deleting note: ' + error.message);
    } finally {
        deleteBtn.disabled = false;
        deleteBtn.textContent = 'Delete';
    }
}

async function moveNoteToFolder(sourcePath, targetFolder) {
    if (!sourcePath || !targetFolder) return;
    
    const fileName = sourcePath.split('/').pop();
    
    if (!confirm(`Move "${fileName}" to "${targetFolder}"?`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/notes/move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_path: sourcePath,
                target_folder: targetFolder
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            const status = document.getElementById('save-status');
            status.className = 'save-status success';
            status.textContent = `✓ Moved to ${targetFolder}`;
            
            setTimeout(() => {
                status.className = 'save-status';
            }, 3000);
            
            // Reload tree and load moved file
            await loadNotesTree();
            await loadNote(data.new_path);
        } else {
            alert('Error moving note: ' + data.error);
        }
    } catch (error) {
        console.error('Error moving note:', error);
        alert('Error moving note: ' + error.message);
    }
}

function startEditing() {
    if (!currentNote) return;
    
    isEditing = true;
    
    // Show editor, hide viewer
    const viewer = document.getElementById('note-viewer');
    const editor = document.getElementById('note-editor');
    
    viewer.style.display = 'none';
    editor.style.display = 'block';
    editor.value = originalContent;
    
    // Update buttons
    document.getElementById('edit-btn').style.display = 'none';
    document.getElementById('save-btn').style.display = 'inline-block';
    document.getElementById('cancel-btn').style.display = 'inline-block';
    
    editor.focus();
}

async function saveNote() {
    if (!currentNote) return;
    
    const editor = document.getElementById('note-editor');
    const newContent = editor.value;
    
    const saveBtn = document.getElementById('save-btn');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    
    try {
        const response = await fetch(
            `/api/notes/${encodeURIComponent(currentNote.filename)}`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: newContent })
            }
        );
        
        const data = await response.json();
        
        if (data.success) {
            originalContent = newContent;
            currentNote.content = newContent;
            
            // Show success message
            const status = document.getElementById('save-status');
            status.className = 'save-status success';
            status.textContent = '✓ Note saved successfully';
            
            setTimeout(() => {
                status.className = 'save-status';
            }, 3000);
            
            // Exit edit mode
            cancelEditing();
            displayNote();
        } else {
            alert('Error saving note: ' + data.error);
        }
    } catch (error) {
        console.error('Error saving note:', error);
        alert('Error saving note: ' + error.message);
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
    }
}

function cancelEditing() {
    isEditing = false;
    
    // Show viewer, hide editor
    document.getElementById('note-viewer').style.display = 'block';
    document.getElementById('note-editor').style.display = 'none';
    
    // Update buttons
    document.getElementById('edit-btn').style.display = 'inline-block';
    document.getElementById('save-btn').style.display = 'none';
    document.getElementById('cancel-btn').style.display = 'none';
}

function showExtractDialog() {
    if (!currentNote) return;
    
    const modal = document.getElementById('extract-modal');
    const list = document.getElementById('extract-list');
    
    // Parse meetings from content
    const meetings = extractMeetingsFromContent(currentNote.content);
    
    if (meetings.length <= 1) {
        alert('This file only contains one meeting entry.');
        return;
    }
    
    // Display meetings
    list.innerHTML = '';
    meetings.forEach((meeting, index) => {
        const item = document.createElement('div');
        item.className = 'extract-item';
        
        // Extract title from ## header
        const titleMatch = meeting.match(/^##\s+(.+)$/m);
        const title = titleMatch ? titleMatch[1] : `Meeting ${index + 1}`;
        
        // Get first few lines as preview
        const lines = meeting.split('\n').slice(0, 4);
        const preview = lines.join('\n');
        
        item.innerHTML = `
            <h4>${title}</h4>
            <p>${preview.replace(/^##\s+.+$/m, '').trim().substring(0, 150)}...</p>
        `;
        
        item.addEventListener('click', () => extractMeeting(index, title));
        
        list.appendChild(item);
    });
    
    modal.classList.add('show');
}

function closeExtractModal() {
    const modal = document.getElementById('extract-modal');
    modal.classList.remove('show');
}

function extractMeetingsFromContent(content) {
    const meetings = [];
    
    // Split by --- separator first
    if (content.includes('---')) {
        const parts = content.split(/\n---\n+/);
        return parts.filter(p => p.trim().length > 0);
    }
    
    // Otherwise split by ## headers
    const parts = content.split(/\n(?=## )/);
    return parts.filter(p => p.trim().length > 0);
}

async function extractMeeting(index, suggestedTitle) {
    closeExtractModal();
    
    if (!currentNote) return;
    
    const meetings = extractMeetingsFromContent(currentNote.content);
    
    if (index < 0 || index >= meetings.length) {
        alert('Invalid meeting selection');
        return;
    }
    
    const meetingContent = meetings[index];
    
    // Ask for new filename
    const newName = prompt(
        `Extract this meeting to a new file.\n\nSuggested name:`,
        suggestedTitle
    );
    
    if (!newName) return;
    
    const newFilename = newName.endsWith('.md') ? newName : `${newName}.md`;
    
    try {
        const response = await fetch('/api/notes/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_path: currentNote.filename,
                meeting_index: index,
                new_filename: newFilename
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            const status = document.getElementById('save-status');
            status.className = 'save-status success';
            status.textContent = `✓ Meeting extracted to ${data.new_file}`;
            
            setTimeout(() => {
                status.className = 'save-status';
            }, 4000);
            
            // Reload tree and reload current file (now with one less meeting)
            await loadNotesTree();
            await loadNote(currentNote.filename);
        } else {
            alert('Error extracting meeting: ' + data.error);
        }
    } catch (error) {
        console.error('Error extracting meeting:', error);
        alert('Error extracting meeting: ' + error.message);
    }
}

async function detectNames() {
    if (!currentNote) return;
    
    const detectBtn = document.getElementById('detect-names-btn');
    detectBtn.disabled = true;
    detectBtn.textContent = 'Detecting...';
    
    try {
        // Show progress
        showProgress('🤖 Analyzing transcript with AI...');
        
        const response = await fetch('/api/notes/detect-names', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: currentNote.filename,
                content: currentNote.content
            })
        });
        
        updateProgress('📝 Processing AI response...');
        const data = await response.json();
        
        if (data.success) {
            detectedNames = data.names || [];
            
            updateProgress('✨ Highlighting detected names...');
            
            // Show success message
            const status = document.getElementById('save-status');
            status.className = 'save-status success';
            status.textContent = `✓ Detected ${detectedNames.length} names. Click on any highlighted name to correct it.`;
            
            setTimeout(() => {
                status.className = 'save-status';
            }, 4000);
            
            // Re-render with highlighted names
            displayNote();
        } else {
            alert('Error detecting names: ' + data.error);
        }
    } catch (error) {
        console.error('Error detecting names:', error);
        alert('Error detecting names: ' + error.message);
    } finally {
        hideProgress();
        detectBtn.disabled = false;
        detectBtn.textContent = 'Detect Names';
    }
}

function highlightSearchTermInViewer() {
    if (!currentNote || !currentSearchTerm) return;
    
    const viewer = document.getElementById('note-viewer');
    let html = viewer.innerHTML;
    
    // Create regex to match search term (case-insensitive, whole or partial words)
    // Don't match inside HTML tags or already highlighted content
    const regex = new RegExp(`(${escapeRegex(currentSearchTerm)})(?![^<]*>|[^<]*</mark>)`, 'gi');
    html = html.replace(regex, '<mark>$1</mark>');
    
    viewer.innerHTML = html;
}

function highlightNamesInViewer() {
    if (!currentNote || detectedNames.length === 0) return;
    
    const viewer = document.getElementById('note-viewer');
    let html = viewer.innerHTML;
    
    // Sort names by length (longest first) to avoid partial matches
    const sortedNames = [...detectedNames].sort((a, b) => b.length - a.length);
    
    sortedNames.forEach(name => {
        // Create a more specific regex that doesn't match inside HTML tags
        // Match the name as a whole word, not inside tags or marks
        const regex = new RegExp(`\\b(${escapeRegex(name)})\\b(?![^<]*>|[^<]*</mark>)`, 'gi');
        html = html.replace(regex, (match) => {
            return `<span class="detected-name" data-name="${match}" onclick="showNameCorrectionDialog('${match}')">${match}</span>`;
        });
    });
    
    viewer.innerHTML = html;
}

function showNameCorrectionDialog(name) {
    currentNameToCorrect = name;
    
    const modal = document.getElementById('name-correction-modal');
    const currentNameDisplay = document.getElementById('current-name-display');
    const input = document.getElementById('corrected-name-input');
    
    currentNameDisplay.textContent = name;
    input.value = '';
    input.placeholder = name;
    
    modal.classList.add('show');
    
    // Focus input
    setTimeout(() => input.focus(), 100);
}

function closeNameCorrectionModal() {
    const modal = document.getElementById('name-correction-modal');
    modal.classList.remove('show');
    currentNameToCorrect = null;
}

async function applyNameCorrection() {
    if (!currentNote || !currentNameToCorrect) return;
    
    const input = document.getElementById('corrected-name-input');
    const newName = input.value.trim();
    
    if (!newName) {
        alert('Please enter a corrected name.');
        return;
    }
    
    const applyBtn = document.getElementById('apply-name-correction-btn');
    applyBtn.disabled = true;
    applyBtn.textContent = 'Applying...';
    
    try {
        // Show progress
        showProgress(`🔄 Replacing "${currentNameToCorrect}" with "${newName}"...`);
        
        // Use regex to replace the name (word boundaries)
        const pattern = new RegExp('\\b' + currentNameToCorrect.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'g');
        const updatedContent = currentNote.content.replace(pattern, newName);
        
        updateProgress('💾 Saving changes...');
        
        // Save the updated content using the correct endpoint
        const saveResponse = await fetch(`/api/notes/${currentNote.filename}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: updatedContent
            })
        });
        
        const saveData = await saveResponse.json();
        
        if (!saveData.success) {
            alert('Error saving file: ' + saveData.error);
            return;
        }
        
        updateProgress('📝 Updating database...');
        
        // Update database
        const response = await fetch('/api/notes/correct-name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: currentNote.filename,
                old_name: currentNameToCorrect,
                new_name: newName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            updateProgress('✅ Complete!');
            
            // Update current note content
            currentNote.content = updatedContent;
            originalContent = updatedContent;
            
            // Update detected names list
            detectedNames = detectedNames.filter(n => n !== currentNameToCorrect);
            detectedNames.push(newName);
            
            // Show success message
            const status = document.getElementById('save-status');
            status.className = 'save-status success';
            status.textContent = `✓ Corrected "${currentNameToCorrect}" to "${newName}"`;
            
            setTimeout(() => {
                status.className = 'save-status';
            }, 4000);
            
            // Close modal
            closeNameCorrectionModal();
            
            // Re-render note
            displayNote();
            
            // Reload from server to ensure consistency
            await loadNote(currentNote.filename);
        } else {
            alert('Error correcting name: ' + data.error);
        }
    } catch (error) {
        console.error('Error correcting name:', error);
        alert('Error correcting name: ' + error.message);
    } finally {
        hideProgress();
        applyBtn.disabled = false;
        applyBtn.textContent = 'Apply Correction';
    }
}

function formatDateTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString();
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Warning on page leave if editing
window.addEventListener('beforeunload', (e) => {
    if (isEditing) {
        e.preventDefault();
        e.returnValue = '';
    }
});
