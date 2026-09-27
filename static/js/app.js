/**
 * app.js - Production Readiness Assessment Platform (PRAP)
 * Client-side interactivity, asynchronous uploads, and exception workflows.
 */

// =========================================================================
// Modal Utilities
// =========================================================================

function openScanModal() {
    const modal = document.getElementById('scan-modal');
    if (modal) {
        modal.style.display = 'flex';
        resetScanForm();
    }
}

function closeScanModal() {
    const modal = document.getElementById('scan-modal');
    if (modal) modal.style.display = 'none';
}

function switchScanTab(tab) {
    const tabZip = document.getElementById('tab-btn-zip');
    const tabPath = document.getElementById('tab-btn-path');
    const formZip = document.getElementById('form-scan-zip');
    const formPath = document.getElementById('form-scan-path');

    if (tab === 'zip') {
        tabZip.classList.add('active');
        tabPath.classList.remove('active');
        formZip.style.display = 'block';
        formPath.style.display = 'none';
    } else {
        tabPath.classList.add('active');
        tabZip.classList.remove('active');
        formPath.style.display = 'block';
        formZip.style.display = 'none';
    }
}

function resetScanForm() {
    const fileInput = document.getElementById('zip_file_input');
    const badge = document.getElementById('selected-file-badge');
    const progressWrapper = document.getElementById('upload-progress-wrapper');
    const submitBtn = document.getElementById('btn-submit-scan');

    if (fileInput) fileInput.value = '';
    if (badge) {
        badge.style.display = 'none';
        badge.textContent = '';
    }
    if (progressWrapper) progressWrapper.style.display = 'none';
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.querySelector('span').textContent = 'Start Assessment';
    }
}

// =========================================================================
// Drag & Drop and File Selection
// =========================================================================

let selectedZipFile = null;

function handleFileSelect(e) {
    const files = e.target.files;
    if (files && files.length > 0) {
        setZipFile(files[0]);
    }
}

function setZipFile(file) {
    if (!file.name.toLowerCase().endsWith('.zip')) {
        showToast('Please select a valid .zip archive.', 'error');
        return;
    }
    selectedZipFile = file;
    const badge = document.getElementById('selected-file-badge');
    if (badge) {
        const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
        badge.textContent = `Selected: ${file.name} (${sizeMb} MB)`;
        badge.style.display = 'inline-block';
    }

    // Auto-populate project name if empty
    const nameInput = document.getElementById('project_name_input');
    if (nameInput && !nameInput.value.trim()) {
        const cleanName = file.name.replace(/\.[^/.]+$/, "");
        nameInput.value = cleanName;
    }
}

// Initialize Drag & Drop listeners
document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    if (dropZone) {
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('dragover');
            }, false);
        });

        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files.length > 0) {
                setZipFile(files[0]);
            }
        });
    }

    // Mobile Sidebar Toggle
    const toggle = document.getElementById('sidebar-toggle');
    const sidebar = document.querySelector('.sidebar');
    if (toggle && sidebar) {
        toggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }

    // Animate score dial if on assessment detail page
    initScoreDial();
});

// =========================================================================
// Form Submissions
// =========================================================================

async function handleZipSubmit(e) {
    e.preventDefault();
    const fileInput = document.getElementById('zip_file_input');
    const file = selectedZipFile || (fileInput ? fileInput.files[0] : null);

    if (!file) {
        showToast('Please select a .zip archive first.', 'error');
        return;
    }

    const projectName = document.getElementById('project_name_input').value.trim();
    const formData = new FormData();
    formData.append('file', file);
    if (projectName) {
        formData.append('project_name', projectName);
    }

    const progressWrapper = document.getElementById('upload-progress-wrapper');
    const progressBar = document.getElementById('progress-bar-fill');
    const progressStatus = document.getElementById('progress-status-text');
    const progressPercent = document.getElementById('progress-percent-text');
    const submitBtn = document.getElementById('btn-submit-scan');

    if (progressWrapper) progressWrapper.style.display = 'block';
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.querySelector('span').textContent = 'Assessing...';
    }

    // Simulated progress tick while server evaluates 26 rules
    let currentPercent = 15;
    const progressInterval = setInterval(() => {
        if (currentPercent < 90) {
            currentPercent += 10;
            if (progressBar) progressBar.style.width = currentPercent + '%';
            if (progressPercent) progressPercent.textContent = currentPercent + '%';
            if (currentPercent > 60 && progressStatus) {
                progressStatus.textContent = 'Evaluating 26 production-readiness rules...';
            }
        }
    }, 200);

    try {
        const response = await fetch('/api/assessments', {
            method: 'POST',
            body: formData
        });

        clearInterval(progressInterval);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to complete assessment.');
        }

        if (progressBar) progressBar.style.width = '100%';
        if (progressPercent) progressPercent.textContent = '100%';
        if (progressStatus) progressStatus.textContent = 'Assessment Completed! Redirecting...';

        showToast('Assessment Completed Successfully!', 'success');
        setTimeout(() => {
            window.location.href = `/assessments/${data.assessment.id}`;
        }, 600);

    } catch (err) {
        clearInterval(progressInterval);
        if (progressWrapper) progressWrapper.style.display = 'none';
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.querySelector('span').textContent = 'Start Assessment';
        }
        showToast(err.message, 'error');
    }
}

async function handlePathSubmit(e) {
    e.preventDefault();
    const path = document.getElementById('path_input').value.trim();
    const name = document.getElementById('path_project_name').value.trim();

    if (!path) {
        showToast('Please provide a server directory path.', 'error');
        return;
    }

    const submitBtn = document.getElementById('btn-submit-path');
    if (submitBtn) submitBtn.disabled = true;

    try {
        const response = await fetch('/api/assessments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_path: path, project_name: name })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to run path assessment.');

        showToast('Local Path Assessment completed!', 'success');
        setTimeout(() => {
            window.location.href = `/assessments/${data.assessment.id}`;
        }, 500);
    } catch (err) {
        if (submitBtn) submitBtn.disabled = false;
        showToast(err.message, 'error');
    }
}

// =========================================================================
// Risk Exception Modal & Workflow
// =========================================================================

function openExceptionModal(findingId, ruleId, ruleName, category, severity) {
    const modal = document.getElementById('exception-modal');
    if (!modal) return;

    document.getElementById('exc_finding_id').value = findingId;
    document.getElementById('exc_rule_id').value = ruleId;

    const summaryBox = document.getElementById('exc_finding_summary');
    if (summaryBox) {
        summaryBox.innerHTML = `
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <strong style="color:var(--accent-cyan); font-family:var(--font-mono);">${ruleId}</strong>
                <span class="severity-pill severity-${severity.toLowerCase()}">${severity}</span>
            </div>
            <div style="color:var(--text-primary); font-weight:600;">${ruleName}</div>
            <div style="color:var(--text-muted); font-size:0.75rem; margin-top:2px;">Category: ${category} • Finding #${findingId}</div>
        `;
    }

    // Default expiry date to 30 days from now
    const expiryInput = document.getElementById('exc_expiry_date');
    if (expiryInput) {
        const d = new Date();
        d.setDate(d.getDate() + 30);
        expiryInput.value = d.toISOString().split('T')[0];
    }

    modal.style.display = 'flex';
}

function closeExceptionModal() {
    const modal = document.getElementById('exception-modal');
    if (modal) modal.style.display = 'none';
}

async function handleExceptionSubmit(e) {
    e.preventDefault();
    const findingId = document.getElementById('exc_finding_id').value;
    const owner = document.getElementById('exc_owner').value.trim();
    const requestedBy = document.getElementById('exc_requested_by').value.trim();
    const reason = document.getElementById('exc_reason').value.trim();
    const expiryDate = document.getElementById('exc_expiry_date').value;

    const submitBtn = document.getElementById('btn-submit-exception');
    if (submitBtn) submitBtn.disabled = true;

    try {
        const response = await fetch('/api/exceptions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                finding_id: parseInt(findingId, 10),
                owner: owner,
                requested_by: requestedBy,
                reason: reason,
                expiry_date: expiryDate
            })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Failed to submit exception.');

        showToast('Risk Exception recorded successfully.', 'success');
        closeExceptionModal();

        // Update finding status UI if present on page
        const findingStatusEl = document.getElementById(`finding-status-${findingId}`);
        if (findingStatusEl) {
            findingStatusEl.textContent = 'Exception Granted';
            findingStatusEl.className = 'status-badge status-warning';
        }

        // Reload page to reflect exception state after short pause
        setTimeout(() => {
            window.location.reload();
        }, 700);

    } catch (err) {
        if (submitBtn) submitBtn.disabled = false;
        showToast(err.message, 'error');
    }
}

// Update finding status via inline dropdown
async function updateFindingStatus(findingId, newStatus) {
    try {
        const response = await fetch(`/api/findings/${findingId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Status update failed.');
        showToast(`Finding #${findingId} marked as ${newStatus}`, 'info');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// Delete Assessment
async function deleteAssessment(assessmentId) {
    if (!confirm(`Are you sure you want to delete Assessment #${assessmentId}?`)) return;

    try {
        const response = await fetch(`/api/assessments/${assessmentId}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error('Failed to delete assessment.');
        showToast('Assessment deleted.', 'info');
        setTimeout(() => {
            window.location.href = '/assessments';
        }, 500);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// =========================================================================
// Radial Score Dial Animation
// =========================================================================

function initScoreDial() {
    const dial = document.getElementById('score-dial-circle');
    if (!dial) return;

    const score = parseInt(dial.getAttribute('data-score') || '0', 10);
    const radius = 56;
    const circumference = 2 * Math.PI * radius; // ~351.85

    dial.style.strokeDasharray = `${circumference} ${circumference}`;
    dial.style.strokeDashoffset = `${circumference}`;

    // Color gradient based on score
    if (score >= 85) {
        dial.style.stroke = '#10b981'; // Green
    } else if (score >= 60) {
        dial.style.stroke = '#f59e0b'; // Amber
    } else {
        dial.style.stroke = '#ef4444'; // Red
    }

    setTimeout(() => {
        const offset = circumference - (score / 100) * circumference;
        dial.style.strokeDashoffset = offset;
    }, 150);
}

// =========================================================================
// Toast Notification Engine
// =========================================================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div style="flex:1;">${message}</div>
        <button style="background:none; border:none; color:inherit; cursor:pointer;" onclick="this.parentElement.remove()">&times;</button>
    `;
    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4500);
}
