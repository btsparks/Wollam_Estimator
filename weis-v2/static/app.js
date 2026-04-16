/* ============================================================
   WEIS v2 — Frontend Application
   Single-page app with vanilla JS routing
   ============================================================ */

// ── State ──
const state = {
    currentPage: 'jobs',
    currentJobId: null,
    jobs: [],
    jobDetail: null,
    selectedCostCode: null,
    filter: 'all',
    jobStatusFilter: 'all',
    searchQuery: '',
    viewMode: 'table',      // 'card' or 'table'
    sortField: 'data_richness',
    sortDir: 'desc',
    progress: null,
    ccSortDir: 'asc',       // 'asc' or 'desc' for cost code list
    // Chat state
    chatConversationId: null,
    chatConversations: [],
    chatMessages: [],
    chatLoading: false,
    chatDataSummary: null,
    chatBidId: null,        // Active bid context for vector search
    chatBids: [],           // Available bids for selector
    // Bidding state
    biddingStatusFilter: 'all',
    biddingTab: 'overview',
    biddingSovPreview: null,
    docSubTab: 'explorer',
    intelAgent: null,
};

// ── API Helpers ──
async function api(endpoint, options = {}) {
    const res = await fetch(`/api${endpoint}`, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'API error');
    }
    return res.json();
}

// ── Navigation ──
function navigate(page, jobId = null) {
    state.currentPage = page;
    state.currentJobId = jobId;
    state.selectedCostCode = null;
    estSelectedBidItemId = null;
    estSelectedActivityId = null;
    estExpandedBidItems = new Set();

    // Reset content area styles (chat uses custom layout)
    const contentArea = document.getElementById('contentArea');
    const content = document.getElementById('content');
    if (page !== 'chat') {
        contentArea.style.padding = '';
        contentArea.style.display = '';
        content.style.maxWidth = '';
        content.style.margin = '';
        content.style.width = '';
        content.style.display = '';
        content.style.height = '';
    }

    // Update sidebar active
    document.querySelectorAll('.sidebar-nav a').forEach(a => {
        a.classList.toggle('active', a.dataset.page === page);
    });

    if (page === 'jobs' && jobId) {
        loadJobDetail(jobId);
    } else if (page === 'jobs') {
        loadJobList();
    } else if (page === 'chat') {
        renderChat();
    } else if (page === 'estimates' && jobId) {
        loadEstimateDetail(jobId);
    } else if (page === 'estimates') {
        loadEstimateList();
    } else if (page === 'bidding' && jobId) {
        loadBidDetail(jobId);
    } else if (page === 'bidding') {
        loadBidBoard();
    } else if (page === 'vendors') {
        loadVendorDirectory();
    } else if (page === 'settings') {
        renderSettings();
    }
}

// ── Format Helpers ──
function fmt(n, decimals = 0) {
    if (n == null) return '—';
    return Number(n).toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

function fmtRate(n) {
    if (n == null) return '—';
    if (n >= 1) return fmt(n, 2);
    if (n >= 0.1) return fmt(n, 2);
    return fmt(n, 4);
}

function confidenceBadge(level) {
    if (!level) return '<span class="badge badge-none">NO DATA</span>';
    const l = level.toLowerCase();
    if (l === 'strong' || l === 'high') return `<span class="badge badge-high">HIGH</span>`;
    if (l === 'moderate') return `<span class="badge badge-moderate">MODERATE</span>`;
    if (l === 'limited' || l === 'low') return `<span class="badge badge-limited">LOW</span>`;
    return `<span class="badge badge-none">${level.toUpperCase()}</span>`;
}

function interviewBadge(status) {
    const map = {
        complete: '<span class="badge badge-complete">Complete</span>',
        in_progress: '<span class="badge badge-in-progress">In Progress</span>',
        not_started: '<span class="badge badge-not-started">Not Started</span>',
    };
    return map[status] || map.not_started;
}

function jobStatusBadge(status) {
    if (status === 'active') return '<span class="badge badge-active">Active</span>';
    if (status === 'completed') return '<span class="badge badge-completed">Completed</span>';
    return `<span class="badge badge-not-started">${status || 'Unknown'}</span>`;
}

// ── Load Job List ──
async function loadJobList() {
    const content = document.getElementById('content');
    document.getElementById('pageTitle').textContent = 'Jobs';
    document.getElementById('pageSubtitle').textContent = '';

    content.innerHTML = '<div class="empty-state"><p>Loading jobs...</p></div>';

    try {
        const [jobs, progress] = await Promise.all([
            api('/interview/jobs'),
            api('/interview/progress'),
        ]);
        state.jobs = jobs;
        renderJobList(jobs, progress);
    } catch (err) {
        content.innerHTML = `<div class="empty-state"><h3>Error loading jobs</h3><p>${err.message}</p></div>`;
    }
}

function renderJobList(jobs, progress) {
    const content = document.getElementById('content');
    if (progress) state.progress = progress;
    const p = state.progress || {};

    // Apply filters
    let filtered = jobs;
    if (state.jobStatusFilter !== 'all') {
        filtered = filtered.filter(j => j.status === state.jobStatusFilter);
    }
    if (state.filter !== 'all') {
        filtered = filtered.filter(j => j.interview_status === state.filter);
    }
    if (state.searchQuery) {
        const q = state.searchQuery.toLowerCase();
        filtered = filtered.filter(j =>
            j.job_number.toLowerCase().includes(q) ||
            j.name.toLowerCase().includes(q)
        );
    }

    // Count jobs by status for the filter tabs
    const activeCount = jobs.filter(j => j.status === 'active').length;
    const completedCount = jobs.filter(j => j.status === 'completed').length;

    // Sort
    filtered = sortJobs(filtered, state.sortField, state.sortDir);

    const isTable = state.viewMode === 'table';

    content.innerHTML = `
        <!-- KPI Cards -->
        <div class="kpi-grid">
            <div class="kpi-card card-animate">
                <div class="kpi-label">Total Jobs</div>
                <div class="kpi-value">${fmt(p.total_jobs)}</div>
            </div>
            <div class="kpi-card card-animate">
                <div class="kpi-label">Reviews Started</div>
                <div class="kpi-value">${fmt(p.jobs_with_context)}</div>
            </div>
            <div class="kpi-card card-animate">
                <div class="kpi-label">Reviews Complete</div>
                <div class="kpi-value">${fmt(p.jobs_complete)}</div>
            </div>
            <div class="kpi-card card-animate">
                <div class="kpi-label">Cost Codes with Context</div>
                <div class="kpi-value">${fmt(p.cost_codes_with_context)}<span style="font-size: 14px; font-weight: 500; color: var(--text-tertiary);"> / ${fmt(p.total_cost_codes_with_data)}</span></div>
            </div>
        </div>

        <!-- Diary Import -->
        <div class="diary-section card-animate" id="diaryImportSection">
            <div class="diary-header">
                <div class="diary-title">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                    HeavyJob Diary Notes
                </div>
                <button class="btn btn-sm" onclick="importDiaries()" id="importDiaryBtn">Import Diary Files</button>
            </div>
            <div class="diary-stats" id="diaryStats">
                ${getDiaryStatsHtml(jobs)}
            </div>
        </div>

        <!-- Toolbar: Filters + Search + View Toggle -->
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap;">
            <div class="filter-tabs">
                <button class="filter-tab ${state.jobStatusFilter === 'all' ? 'active' : ''}" onclick="setJobStatusFilter('all')">All Jobs (${jobs.length})</button>
                <button class="filter-tab ${state.jobStatusFilter === 'active' ? 'active' : ''}" onclick="setJobStatusFilter('active')">Active (${activeCount})</button>
                <button class="filter-tab ${state.jobStatusFilter === 'completed' ? 'active' : ''}" onclick="setJobStatusFilter('completed')">Completed (${completedCount})</button>
            </div>
            <div class="filter-tabs">
                <button class="filter-tab ${state.filter === 'all' ? 'active' : ''}" onclick="setFilter('all')">All</button>
                <button class="filter-tab ${state.filter === 'not_started' ? 'active' : ''}" onclick="setFilter('not_started')">Not Started</button>
                <button class="filter-tab ${state.filter === 'in_progress' ? 'active' : ''}" onclick="setFilter('in_progress')">In Progress</button>
                <button class="filter-tab ${state.filter === 'complete' ? 'active' : ''}" onclick="setFilter('complete')">Complete</button>
            </div>
            <div class="search-wrapper" style="flex: 1; min-width: 200px; max-width: 320px; margin-bottom: 0;">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                <input type="text" class="search-input" placeholder="Search jobs..." value="${state.searchQuery}" oninput="setSearch(this.value)">
            </div>
            <span id="jobFilterCount" style="font-size: 12px; color: var(--text-tertiary);">${filtered.length} job${filtered.length !== 1 ? 's' : ''}</span>
            <div class="view-toggle">
                <button class="view-toggle-btn ${!isTable ? 'active' : ''}" onclick="setViewMode('card')" title="Card view" aria-label="Card view">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                </button>
                <button class="view-toggle-btn ${isTable ? 'active' : ''}" onclick="setViewMode('table')" title="Table view" aria-label="Table view">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
                </button>
            </div>
        </div>

        <!-- Job List: Card or Table -->
        <div id="jobListArea">
        ${isTable ? renderJobTable(filtered) : renderJobGrid(filtered)}
        </div>
    `;
}

function renderJobGrid(filtered) {
    if (filtered.length === 0) {
        return '<div class="empty-state"><h3>No jobs match your filters</h3><p>Try adjusting your search or filter criteria.</p></div>';
    }
    return `<div class="job-grid">${filtered.map(j => renderJobCard(j)).join('')}</div>`;
}

function renderJobTable(filtered) {
    if (filtered.length === 0) {
        return '<div class="empty-state"><h3>No jobs match your filters</h3><p>Try adjusting your search or filter criteria.</p></div>';
    }

    const sortIcon = (field) => {
        if (state.sortField !== field) return '<span class="sort-icon">&#8597;</span>';
        return state.sortDir === 'asc'
            ? '<span class="sort-icon active">&#8593;</span>'
            : '<span class="sort-icon active">&#8595;</span>';
    };

    return `
        <div class="card" style="overflow-x: auto;">
            <table class="data-table">
                <thead>
                    <tr>
                        <th class="sortable" onclick="toggleSort('job_number')">Job # ${sortIcon('job_number')}</th>
                        <th class="sortable" onclick="toggleSort('name')">Name ${sortIcon('name')}</th>
                        <th class="sortable" onclick="toggleSort('status')" style="text-align: center;">Status ${sortIcon('status')}</th>
                        <th class="sortable" onclick="toggleSort('cost_code_count')" style="text-align: right;">Cost Codes ${sortIcon('cost_code_count')}</th>
                        <th class="sortable" onclick="toggleSort('cost_codes_with_data')" style="text-align: right;">With Data ${sortIcon('cost_codes_with_data')}</th>
                        <th style="text-align: center;">Estimate</th>
                        <th class="sortable" onclick="toggleSort('interview_status')" style="text-align: center;">Review ${sortIcon('interview_status')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${filtered.map(j => {
                        const estBadge = j.linked_estimate_id
                            ? `<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;background:rgba(37,99,235,0.1);color:var(--wollam-blue);border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;" onclick="event.stopPropagation();navigate('estimates',${j.linked_estimate_id})">${escHtml(j.linked_estimate_code || 'HB')} &rarr;</span>`
                            : `<span style="color:var(--text-tertiary);font-size:11px;">—</span>`;
                        return `
                        <tr class="data-row" onclick="navigate('jobs', ${j.job_id})">
                            <td style="font-weight: 700; color: var(--wollam-navy);">${j.job_number}</td>
                            <td style="max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${j.name || '—'}</td>
                            <td style="text-align: center;">${jobStatusBadge(j.status)}</td>
                            <td style="text-align: right; font-variant-numeric: tabular-nums;">${fmt(j.cost_code_count)}</td>
                            <td style="text-align: right; font-variant-numeric: tabular-nums;">${fmt(j.cost_codes_with_data)}</td>
                            <td style="text-align: center;">${estBadge}</td>
                            <td style="text-align: center;">${interviewBadge(j.interview_status)}</td>
                        </tr>`;
                    }).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function sortJobs(jobs, field, dir) {
    return [...jobs].sort((a, b) => {
        let va = a[field];
        let vb = b[field];
        // Handle strings
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        // Handle nulls
        if (va == null) va = '';
        if (vb == null) vb = '';
        if (va < vb) return dir === 'asc' ? -1 : 1;
        if (va > vb) return dir === 'asc' ? 1 : -1;
        return 0;
    });
}

function toggleSort(field) {
    if (state.sortField === field) {
        state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        state.sortField = field;
        state.sortDir = field === 'name' || field === 'job_number' ? 'asc' : 'desc';
    }
    renderJobList(state.jobs);
}

function setViewMode(mode) {
    state.viewMode = mode;
    renderJobList(state.jobs);
}

function renderJobCard(job) {
    const contextPct = job.cost_codes_with_data > 0
        ? Math.round((job.cost_codes_with_context / job.cost_codes_with_data) * 100)
        : 0;

    return `
        <div class="card card-clickable card-animate" onclick="navigate('jobs', ${job.job_id})">
            <div class="job-card">
                <div class="job-card-header">
                    <span class="job-number">Job ${job.job_number}</span>
                    <div style="display: flex; gap: 6px; align-items: center;">
                        ${jobStatusBadge(job.status)}
                        ${interviewBadge(job.interview_status)}
                    </div>
                </div>
                <div class="job-name">${job.name || 'Untitled Job'}</div>
                <div class="job-stats">
                    ${fmt(job.cost_code_count)} cost codes &middot; ${fmt(job.cost_codes_with_data)} with data
                    ${job.diary_entry_count > 0 ? ` &middot; <span class="badge badge-diary" style="font-size: 10px; padding: 1px 6px;">${fmt(job.diary_entry_count)} diary</span>` : ''}
                </div>
                <div style="margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span class="progress-label">Data Richness</span>
                        <span class="progress-label">${job.data_richness}%</span>
                    </div>
                    <div class="progress-bar"><div class="progress-fill navy" style="width: ${job.data_richness}%"></div></div>
                </div>
                ${job.cost_codes_with_data > 0 ? `
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span class="progress-label">Context Coverage</span>
                        <span class="progress-label">${job.cost_codes_with_context} of ${job.cost_codes_with_data} (${contextPct}%)</span>
                    </div>
                    <div class="progress-bar"><div class="progress-fill green" style="width: ${contextPct}%"></div></div>
                </div>
                ` : ''}
            </div>
        </div>
    `;
}

function setFilter(f) {
    state.filter = f;
    renderJobList(state.jobs);
}

function setJobStatusFilter(f) {
    state.jobStatusFilter = f;
    renderJobList(state.jobs);
}

function setSearch(q) {
    state.searchQuery = q;
    // Only re-render the job list area, not the whole page (preserves search input focus)
    const listContainer = document.getElementById('jobListArea');
    if (listContainer) {
        let filtered = state.jobs;
        if (state.jobStatusFilter !== 'all') filtered = filtered.filter(j => j.status === state.jobStatusFilter);
        if (state.filter !== 'all') filtered = filtered.filter(j => j.interview_status === state.filter);
        if (state.searchQuery) {
            const sq = state.searchQuery.toLowerCase();
            filtered = filtered.filter(j => j.job_number.toLowerCase().includes(sq) || j.name.toLowerCase().includes(sq));
        }
        filtered = sortJobs(filtered, state.sortField, state.sortDir);
        const isTable = state.viewMode === 'table';
        listContainer.innerHTML = isTable ? renderJobTable(filtered) : renderJobGrid(filtered);
        // Update count
        const countEl = document.getElementById('jobFilterCount');
        if (countEl) countEl.textContent = `${filtered.length} job${filtered.length !== 1 ? 's' : ''}`;
    } else {
        renderJobList(state.jobs);
    }
}

// ── Load Job Detail (Jobs Page) ──
async function loadJobDetail(jobId) {
    const content = document.getElementById('content');
    content.innerHTML = '<div class="empty-state"><p>Loading job detail...</p></div>';

    try {
        const [data, recast, linkedEstimates] = await Promise.all([
            api(`/interview/job/${jobId}`),
            api(`/settings/recast/${jobId}`).catch(() => null),
            api(`/estimates/?linked_job_id=${jobId}`).catch(() => []),
        ]);
        state.jobDetail = data;
        state.recastCosts = recast;
        state.linkedEstimates = linkedEstimates || [];
        state.selectedCostCode = data.cost_codes.length > 0 ? data.cost_codes[0].code : null;

        document.getElementById('pageTitle').textContent = `Job ${data.job.job_number}`;
        document.getElementById('pageSubtitle').textContent = data.job.name;

        renderJobDetail(data);

        // Load document list async (after render so the container exists)
        loadDocList(jobId);

        // Set up drag-and-drop on the upload area
        initDocUploadArea(jobId);
    } catch (err) {
        content.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${err.message}</p></div>`;
    }
}

function renderJobDetail(data) {
    const content = document.getElementById('content');
    const job = data.job;
    const pm = data.pm_context || {};
    const codes = data.cost_codes;
    const contextCount = codes.filter(c => c.has_context).length;

    // Build "View Estimate" link if linked
    const estLinks = (state.linkedEstimates || []);
    const estLinkHtml = estLinks.length > 0
        ? estLinks.map(e => `<button onclick="navigate('estimates',${e.estimate_id})" style="padding:6px 16px;background:rgba(37,99,235,0.1);color:var(--wollam-blue);border:1px solid rgba(37,99,235,0.2);border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;">View Estimate: ${escHtml(e.code || '')} &rarr;</button>`).join(' ')
        : '';

    content.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <button class="back-btn" onclick="navigate('jobs')">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
                Back to Jobs
            </button>
            <div>${estLinkHtml}</div>
        </div>

        <!-- Top Bar -->
        <div class="interview-topbar">
            <div class="topbar-info">
                <h2>Job ${job.job_number} — ${job.name} ${jobStatusBadge(job.status)}</h2>
                <span class="subtitle">${fmt(job.cost_codes_with_data)} cost codes with data &middot; ${contextCount} with context</span>
            </div>
            <div class="topbar-progress">
                <div class="count">${contextCount} / ${codes.length} reviewed</div>
                <div class="progress-bar" style="width: 160px;">
                    <div class="progress-fill green" style="width: ${codes.length > 0 ? (contextCount / codes.length * 100) : 0}%"></div>
                </div>
            </div>
        </div>

        <!-- Job Overview -->
        <div class="overview-section">
            <div class="overview-title">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--wollam-navy)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
                Job Overview
            </div>
            <div class="data-grid" style="grid-template-columns: repeat(3, 1fr); margin-bottom: 20px;">
                <div class="data-item">
                    <div class="data-item-label">Actual Hours</div>
                    <div class="data-item-value">${fmt(job.total_actual_hrs)}</div>
                </div>
                <div class="data-item">
                    <div class="data-item-label">Budget Hours</div>
                    <div class="data-item-value">${fmt(job.total_budget_hrs)}</div>
                </div>
                <div class="data-item">
                    <div class="data-item-label">Cost Codes</div>
                    <div class="data-item-value">${fmt(job.cost_codes_with_data)}<span style="font-size: 12px; color: var(--text-tertiary);"> / ${fmt(job.total_cost_codes)}</span></div>
                </div>
            </div>

            <!-- Cost Comparison Table -->
            <table class="cost-comparison-table">
                <thead>
                    <tr>
                        <th></th>
                        <th>Labor</th>
                        <th>Equipment</th>
                        <th>Material</th>
                        <th>Subs</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
                    ${job.total_budget_cost ? `
                    <tr class="cost-row-budget">
                        <td class="cost-row-label">Budget</td>
                        <td>$${fmt(job.total_budget_labor_cost)}</td>
                        <td>$${fmt(job.total_budget_equip_cost)}</td>
                        <td>$${fmt(job.total_budget_matl_cost)}</td>
                        <td>$${fmt(job.total_budget_sub_cost)}</td>
                        <td class="cost-row-total">$${fmt(job.total_budget_cost)}</td>
                    </tr>` : ''}
                    ${job.total_actual_cost ? `
                    <tr class="cost-row-actual">
                        <td class="cost-row-label"><span class="cost-dot cost-dot-actual"></span>Actual</td>
                        <td>$${fmt(job.total_actual_labor_cost)}</td>
                        <td>$${fmt(job.total_actual_equip_cost)}</td>
                        <td>$${fmt(job.total_actual_matl_cost)}</td>
                        <td>$${fmt(job.total_actual_sub_cost)}</td>
                        <td class="cost-row-total">$${fmt(job.total_actual_cost)}</td>
                    </tr>` : ''}
                    ${state.recastCosts ? `
                    <tr class="cost-row-recast">
                        <td class="cost-row-label"><span class="cost-dot cost-dot-recast"></span>Recast <span class="cost-row-hint">2026 rates</span></td>
                        <td>$${fmt(state.recastCosts.job_totals.labor_cost)}</td>
                        <td>$${fmt(state.recastCosts.job_totals.equip_cost)}</td>
                        <td class="cost-cell-na">--</td>
                        <td class="cost-cell-na">--</td>
                        <td class="cost-row-total">$${fmt(state.recastCosts.job_totals.total_cost)}</td>
                    </tr>` : ''}
                </tbody>
            </table>
        </div>

        <!-- Diary Intelligence Section -->
        ${data.diary_summary ? `
        <div class="diary-section">
            <div class="diary-header">
                <div class="diary-title">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                    Diary Intelligence Available
                </div>
                <button class="btn btn-sm" id="synthesizeBtn" onclick="synthesizeDiary(${job.job_id})"
                    style="background: rgba(139,92,246,0.1); color: #7C3AED; border-color: rgba(139,92,246,0.3);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                    Synthesize with AI
                </button>
            </div>
            <div class="diary-stats">
                <span><span class="diary-stat-value">${fmt(data.diary_summary.entry_count)}</span> diary entries</span>
                <span><span class="diary-stat-value">${data.diary_summary.cost_code_count}</span> cost codes</span>
                <span><span class="diary-stat-value">${data.diary_summary.foreman_count}</span> foremen</span>
                <span>${data.diary_summary.date_start} to ${data.diary_summary.date_end}</span>
            </div>
            ${data.diary_summary.foremen ? `
            <div style="margin-top: 8px; font-size: 12px; color: var(--text-tertiary);">
                Foremen: ${data.diary_summary.foremen.join(', ')}
            </div>` : ''}
        </div>
        ` : ''}

        <!-- Document Upload Section -->
        <div class="doc-section" id="docSection">
            <div class="doc-header">
                <div class="doc-title">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                    Project Documents
                    ${data.doc_summary ? `<span style="font-size: 12px; font-weight: 400; color: var(--text-secondary); margin-left: 4px;">(${data.doc_summary.doc_count})</span>` : ''}
                </div>
                <div style="display: flex; gap: 8px;">
                    ${data.doc_summary && data.doc_summary.doc_count > 0 ? `
                    <button class="btn btn-sm" id="enrichBtn" onclick="enrichFromDocs(${job.job_id})"
                        style="background: rgba(14,165,233,0.1); color: #0284C7; border-color: rgba(14,165,233,0.3);">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                        Enrich with AI
                    </button>` : ''}
                </div>
            </div>

            <!-- Upload area -->
            <div class="doc-upload-area" id="docUploadArea" onclick="document.getElementById('docFileInput').click()">
                <input type="file" id="docFileInput" style="display:none" accept=".pdf,.xlsx,.xls,.csv,.txt,.md" multiple onchange="handleDocUpload(${job.job_id}, this.files)">
                <div style="color: var(--text-tertiary); font-size: 13px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    Drop files here or click to upload
                    <div style="font-size: 11px; margin-top: 4px; color: var(--text-disabled);">PDF, Excel, CSV, or TXT &middot; Max 20 MB</div>
                </div>
            </div>

            <!-- Doc type selector (shown during upload) -->
            <div id="docTypeSelector" style="display: none; margin-top: 12px;">
                <label class="form-label">Document Type</label>
                <select id="docTypeSelect" class="form-input" style="max-width: 250px;">
                    <option value="change_order">Change Order Log</option>
                    <option value="production_kpi">Production / KPI Tracking</option>
                    <option value="rfi_submittal">RFI / Submittal Log</option>
                    <option value="material_tracking">Material Tracking</option>
                    <option value="other">Other</option>
                </select>
            </div>

            <!-- Document list -->
            <div class="doc-list" id="docList"></div>
        </div>

        <!-- Job-Level PM Context Form -->
        <div class="card" style="margin-bottom: 24px;">
            <div class="card-header">
                <div class="card-title">Job-Level Context ${pm.source ? sourceBadge(pm.source) : ''}</div>
                <span class="save-indicator" id="jobSaveIndicator">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    Saved
                </span>
            </div>
            <div class="card-body">
                <div class="form-group">
                    <label class="form-label">Your Name</label>
                    <input type="text" class="form-input" id="pm_name" placeholder="e.g., Mike Johnson"
                        value="${pm.pm_name || ''}" onblur="saveJobContext(${job.job_id})">
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <div class="form-group">
                        <label class="form-label">Project Summary</label>
                        <textarea class="form-textarea" id="project_summary" placeholder="What was this job? 2-3 sentences."
                            onblur="saveJobContext(${job.job_id})">${pm.project_summary || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Site Conditions</label>
                        <textarea class="form-textarea" id="site_conditions" placeholder="Access, terrain, weather, restrictions..."
                            onblur="saveJobContext(${job.job_id})">${pm.site_conditions || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Key Challenges</label>
                        <textarea class="form-textarea" id="key_challenges" placeholder="What made this job hard?"
                            onblur="saveJobContext(${job.job_id})">${pm.key_challenges || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Key Successes</label>
                        <textarea class="form-textarea" id="key_successes" placeholder="What went well?"
                            onblur="saveJobContext(${job.job_id})">${pm.key_successes || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Lessons Learned</label>
                        <textarea class="form-textarea" id="lessons_learned" placeholder="What would you do differently?"
                            onblur="saveJobContext(${job.job_id})">${pm.lessons_learned || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">General Notes</label>
                        <textarea class="form-textarea" id="general_notes" placeholder="Anything else relevant..."
                            onblur="saveJobContext(${job.job_id})">${pm.general_notes || ''}</textarea>
                    </div>
                    <div class="form-group" style="display: flex; align-items: center; gap: 16px;">
                        <label style="display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500; color: var(--text-primary); cursor: pointer;">
                            <input type="checkbox" id="has_per_diem" ${pm.has_per_diem ? 'checked' : ''}
                                onchange="document.getElementById('per_diem_rate').disabled = !this.checked; saveJobContext(${job.job_id})"
                                style="width: 16px; height: 16px; accent-color: var(--wollam-navy);">
                            Per Diem
                        </label>
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span style="font-size: 13px; color: var(--text-secondary);">$</span>
                            <input type="number" class="form-input" id="per_diem_rate"
                                placeholder="75.00" step="0.01" min="0" style="width: 100px;"
                                value="${pm.per_diem_rate || ''}"
                                ${pm.has_per_diem ? '' : 'disabled'}
                                onblur="saveJobContext(${job.job_id})">
                            <span style="font-size: 12px; color: var(--text-tertiary);">/day per worker</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Cost Code Walkthrough -->
        <div class="overview-title" style="margin-bottom: 16px;">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--wollam-navy)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            Cost Code Walkthrough
        </div>

        <div class="interview-layout">
            <!-- Cost Code Sidebar -->
            <div class="interview-sidebar">
                <div class="card" style="position: sticky; top: 0; max-height: calc(100vh - 200px); overflow-y: auto;">
                    <div style="padding: 12px 16px; border-bottom: 1px solid var(--border-default); display: flex; align-items: center; justify-content: space-between;">
                        <div style="font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em;">
                            Cost Codes (${codes.length})
                        </div>
                        <button class="btn-icon" onclick="toggleCcSort()" title="Sort ${state.ccSortDir === 'asc' ? 'descending' : 'ascending'}" style="width:24px;height:24px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                ${state.ccSortDir === 'asc'
                                    ? '<polyline points="17 11 12 6 7 11"/><line x1="12" y1="18" x2="12" y2="6"/>'
                                    : '<polyline points="7 13 12 18 17 13"/><line x1="12" y1="6" x2="12" y2="18"/>'}
                            </svg>
                        </button>
                    </div>
                    <div class="cc-list" style="padding: 8px;" id="ccList">
                        ${(() => { const maxTc = getCcMaxTimecards(); return sortCostCodes(codes).map(cc => renderCcListItem(cc, maxTc)).join(''); })()}
                    </div>
                </div>
            </div>

            <!-- Cost Code Detail -->
            <div class="interview-main" id="ccDetail">
                ${state.selectedCostCode ? renderCostCodeDetail(codes.find(c => c.code === state.selectedCostCode), job.job_id) : '<div class="empty-state"><p>Select a cost code from the list</p></div>'}
            </div>
        </div>

        <!-- Mark Complete -->
        <div style="text-align: center; padding: 32px 0; border-top: 1px solid var(--border-default); margin-top: 24px;">
            <button class="btn btn-gold" onclick="markComplete(${job.job_id})" style="font-size: 15px; padding: 12px 32px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Mark Review Complete
            </button>
        </div>
    `;
}

function renderCcListItem(cc, maxTc) {
    const tc = cc.timecard_count || 0;
    const ratio = maxTc > 0 ? tc / maxTc : 0;
    // Opacity from 0.08 (no data) to 1.0 (densest)
    const opacity = tc === 0 ? 0 : Math.max(0.12, ratio);
    const active = state.selectedCostCode === cc.code ? 'active' : '';
    return `<div class="cc-list-item ${active}" onclick="selectCostCode('${cc.code}')" style="border-left: 3px solid rgba(0, 52, 126, ${opacity.toFixed(2)});">
        <span class="cc-list-code">${cc.code}</span>
        <span class="cc-list-desc">${cc.description || ''}</span>
    </div>`;
}

function getCcMaxTimecards() {
    const codes = state.jobDetail?.cost_codes || [];
    return Math.max(1, ...codes.map(cc => cc.timecard_count || 0));
}

function sortCostCodes(codes) {
    const sorted = [...codes];
    sorted.sort((a, b) => {
        const aNum = parseInt(a.code, 10);
        const bNum = parseInt(b.code, 10);
        const aVal = isNaN(aNum) ? a.code : aNum;
        const bVal = isNaN(bNum) ? b.code : bNum;
        if (typeof aVal === 'number' && typeof bVal === 'number') {
            return state.ccSortDir === 'asc' ? aVal - bVal : bVal - aVal;
        }
        const cmp = String(a.code).localeCompare(String(b.code));
        return state.ccSortDir === 'asc' ? cmp : -cmp;
    });
    return sorted;
}

function toggleCcSort() {
    state.ccSortDir = state.ccSortDir === 'asc' ? 'desc' : 'asc';
    const codes = state.jobDetail?.cost_codes;
    if (!codes) return;
    // Re-render just the cost code list
    const listEl = document.getElementById('ccList');
    if (listEl) {
        const maxTc = getCcMaxTimecards();
        listEl.innerHTML = sortCostCodes(codes).map(cc => renderCcListItem(cc, maxTc)).join('');
    }
    // Update arrow icon
    const sortBtn = document.querySelector('.btn-icon[onclick="toggleCcSort()"] svg');
    if (sortBtn) {
        sortBtn.innerHTML = state.ccSortDir === 'asc'
            ? '<polyline points="17 11 12 6 7 11"/><line x1="12" y1="18" x2="12" y2="6"/>'
            : '<polyline points="7 13 12 18 17 13"/><line x1="12" y1="6" x2="12" y2="18"/>';
    }
}

function selectCostCode(code) {
    state.selectedCostCode = code;
    const cc = state.jobDetail.cost_codes.find(c => c.code === code);
    if (!cc) return;

    // Update sidebar active state
    document.querySelectorAll('.cc-list-item').forEach(el => {
        el.classList.toggle('active', el.querySelector('.cc-list-code')?.textContent === code);
    });

    // Render detail
    document.getElementById('ccDetail').innerHTML = renderCostCodeDetail(cc, state.jobDetail.job.job_id);
}

function renderCostCodeDetail(cc, jobId) {
    if (!cc) return '<div class="empty-state"><p>Select a cost code</p></div>';

    const ctx = cc.context || {};
    const cb = cc.crew_breakdown || {};
    const rawTrades = cb.trades || [];
    const equipment = Array.isArray(cb.equipment) ? cb.equipment : [];

    // Normalize trades: new format is array [{name, avg_count}], old format was dict {CODE: {workers, days}}
    const trades = Array.isArray(rawTrades)
        ? rawTrades
        : Object.entries(rawTrades).map(([code, info]) => ({
            name: code,
            avg_count: info.workers || 1,
            days_present: info.days || 0,
        }));

    let crewHtml = '';
    if (trades.length > 0) {
        crewHtml += `<div class="crew-grid">${trades.map(t => {
            const qty = t.avg_count >= 1 ? t.avg_count : 1;
            const label = t.name || t.trade || '?';
            return `<span class="crew-tag"><strong>${qty}</strong> ${label}</span>`;
        }).join('')}</div>`;
    }
    if (equipment.length > 0) {
        crewHtml += `<div style="margin-top: 6px;"><div class="form-label">Equipment</div><div class="crew-grid">${
            equipment.map(eq => {
                const qty = eq.avg_count >= 1 ? eq.avg_count : 1;
                const label = eq.name || eq.desc || eq.code || '?';
                return `<span class="crew-tag" style="background: rgba(14,165,233,0.06);">${qty > 1 ? `<strong>${qty}</strong> ` : ''}${label}</span>`;
            }).join('')
        }</div></div>`;
    }
    if (!crewHtml) {
        crewHtml = '<span style="color: var(--text-tertiary); font-size: 12px;">No crew data</span>';
    }

    return `
        <div class="card card-animate">
            <div class="card-header">
                <div>
                    <div class="card-title">${cc.code} — ${cc.description || 'No description'}</div>
                    <div style="font-size: 12px; color: var(--text-tertiary); margin-top: 2px;">
                        Unit: ${cc.unit || '—'} &middot; Discipline: ${cc.discipline || 'unmapped'}
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    ${confidenceBadge(cc.confidence)}
                    ${cc.timecard_count ? `<span style="font-size: 11px; color: var(--text-tertiary);">${cc.timecard_count} timecards</span>` : ''}
                    <span class="save-indicator" id="ccSaveIndicator">
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                        Saved
                    </span>
                </div>
            </div>
            <div class="card-body">
                <!-- Raw Data Display -->
                <div class="data-grid" style="margin-bottom: 20px;">
                    <div class="data-item">
                        <div class="data-item-label">Actual MH/Unit</div>
                        <div class="data-item-value hero">${fmtRate(cc.act_mh_per_unit)}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Actual Qty</div>
                        <div class="data-item-value">${fmt(cc.act_qty)} <span style="font-size: 11px; color: var(--text-tertiary);">${cc.unit || ''}</span></div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Actual Hours</div>
                        <div class="data-item-value">${fmt(cc.act_labor_hrs)}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Budget Qty</div>
                        <div class="data-item-value">${fmt(cc.bgt_qty)} <span style="font-size: 11px; color: var(--text-tertiary);">${cc.unit || ''}</span></div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Budget Hours</div>
                        <div class="data-item-value">${fmt(cc.bgt_labor_hrs)}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Typical Daily Crew</div>
                        <div class="data-item-value">${cb.typical_crew_size ? fmt(cb.typical_crew_size) : (cc.crew_size_avg ? fmt(cc.crew_size_avg, 1) : '—')}</div>
                    </div>
                </div>

                <!-- Cost Comparison Table (Cost Code Level) -->
                ${(() => {
                    const rc = state.recastCosts && state.recastCosts.cost_codes[cc.code];
                    const hasAny = cc.bgt_total || cc.act_total || (rc && rc.total_cost > 0);
                    if (!hasAny) return '';

                    const actCostPerUnit = (cc.act_qty && cc.act_qty > 0 && cc.act_total) ? cc.act_total / cc.act_qty : null;
                    const rcCostPerUnit = (rc && cc.act_qty && cc.act_qty > 0) ? rc.total_cost / cc.act_qty : null;

                    return `
                <table class="cost-comparison-table" style="margin-bottom: 16px;">
                    <thead>
                        <tr>
                            <th></th>
                            <th>Labor</th>
                            <th>Equipment</th>
                            <th>Material</th>
                            <th>Subs</th>
                            <th>Total</th>
                            <th>$/Unit</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${cc.bgt_total ? `
                        <tr class="cost-row-budget">
                            <td class="cost-row-label">Budget</td>
                            <td>$${fmt(cc.bgt_labor_cost)}</td>
                            <td>$${fmt(cc.bgt_equip_cost)}</td>
                            <td>$${fmt(cc.bgt_matl_cost)}</td>
                            <td>$${fmt(cc.bgt_sub_cost)}</td>
                            <td class="cost-row-total">$${fmt(cc.bgt_total)}</td>
                            <td>${cc.bgt_qty > 0 ? '$' + fmtRate(cc.bgt_total / cc.bgt_qty) : '—'}</td>
                        </tr>` : ''}
                        ${cc.act_total ? `
                        <tr class="cost-row-actual">
                            <td class="cost-row-label"><span class="cost-dot cost-dot-actual"></span>Actual</td>
                            <td>$${fmt(cc.act_labor_cost)}</td>
                            <td>$${fmt(cc.act_equip_cost)}</td>
                            <td>$${fmt(cc.act_matl_cost)}</td>
                            <td>$${fmt(cc.act_sub_cost)}</td>
                            <td class="cost-row-total">$${fmt(cc.act_total)}</td>
                            <td class="cost-row-total" style="color: #10B981;">${actCostPerUnit !== null ? '$' + fmtRate(actCostPerUnit) : '—'}</td>
                        </tr>` : ''}
                        ${rc && rc.total_cost > 0 ? `
                        <tr class="cost-row-recast">
                            <td class="cost-row-label"><span class="cost-dot cost-dot-recast"></span>Recast <span class="cost-row-hint">2026</span></td>
                            <td>$${fmt(rc.labor_cost)}</td>
                            <td>$${fmt(rc.equip_cost)}</td>
                            <td class="cost-cell-na">--</td>
                            <td class="cost-cell-na">--</td>
                            <td class="cost-row-total">$${fmt(rc.total_cost)}</td>
                            <td class="cost-row-total" style="color: #E67E22;">${rcCostPerUnit !== null ? '$' + fmtRate(rcCostPerUnit) : '—'}</td>
                        </tr>` : ''}
                    </tbody>
                </table>`;
                })()}

                <!-- Crew Breakdown -->
                <div style="margin-bottom: 20px;">
                    <div class="form-label">Crew Breakdown</div>
                    ${crewHtml}
                </div>

                ${cc.daily_qty_avg ? `
                <div class="data-grid" style="grid-template-columns: repeat(2, 1fr); margin-bottom: 20px;">
                    <div class="data-item">
                        <div class="data-item-label">Avg Daily Production</div>
                        <div class="data-item-value">${fmt(cc.daily_qty_avg, 1)} <span style="font-size: 11px; color: var(--text-tertiary);">${cc.unit || ''}/day</span></div>
                    </div>
                    <div class="data-item">
                        <div class="data-item-label">Peak Daily Production</div>
                        <div class="data-item-value">${fmt(cc.daily_qty_peak, 1)} <span style="font-size: 11px; color: var(--text-tertiary);">${cc.unit || ''}/day</span></div>
                    </div>
                </div>
                ` : ''}

                <hr style="border: none; border-top: 1px solid var(--border-default); margin: 20px 0;">

                <!-- PM Context Form -->
                <div style="font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 16px;">
                    PM Context ${ctx.source ? sourceBadge(ctx.source) : ''}
                    <span style="font-size: 11px; font-weight: 400; color: var(--text-tertiary); margin-left: 8px;">All fields optional — auto-saves on blur</span>
                </div>

                <div class="form-group">
                    <label class="form-label">What does this code actually cover?</label>
                    <textarea class="form-textarea" id="cc_scope_included"
                        placeholder="e.g., Forming and stripping walls 20-30' height, one-sided pours against excavation, EFCO forms"
                        onblur="saveCCContext(${jobId}, '${cc.code}')">${ctx.scope_included || ''}</textarea>
                </div>

                <div class="form-group">
                    <label class="form-label">What is NOT included in this code?</label>
                    <textarea class="form-textarea" id="cc_scope_excluded"
                        placeholder="e.g., Rebar is separate (code 2220), concrete placement is separate (code 2230)"
                        onblur="saveCCContext(${jobId}, '${cc.code}')">${ctx.scope_excluded || ''}</textarea>
                </div>

                <div class="form-group">
                    <label class="form-label">Related Cost Codes</label>
                    <input type="text" class="form-input" id="cc_related_codes"
                        placeholder="e.g., 2220, 2230"
                        value="${ctx.related_codes || ''}"
                        onblur="saveCCContext(${jobId}, '${cc.code}')">
                </div>

                <div class="form-group">
                    <label class="form-label">What conditions affected production?</label>
                    <textarea class="form-textarea" id="cc_conditions"
                        placeholder="e.g., Mine site access restrictions added 30 min/day for badging. Winter months required heat blankets."
                        onblur="saveCCContext(${jobId}, '${cc.code}')">${ctx.conditions || ''}</textarea>
                </div>

                <div class="form-group">
                    <label class="form-label">Anything else an estimator should know?</label>
                    <textarea class="form-textarea" id="cc_notes"
                        placeholder="e.g., This rate is conservative — crew was still learning the form system for the first 2 weeks."
                        onblur="saveCCContext(${jobId}, '${cc.code}')">${ctx.notes || ''}</textarea>
                </div>
            </div>
        </div>
    `;
}

// ── Save Handlers ──
async function saveJobContext(jobId) {
    const hasPerDiem = document.getElementById('has_per_diem')?.checked || false;
    const perDiemVal = document.getElementById('per_diem_rate')?.value;
    const data = {
        pm_name: document.getElementById('pm_name')?.value || null,
        project_summary: document.getElementById('project_summary')?.value || null,
        site_conditions: document.getElementById('site_conditions')?.value || null,
        key_challenges: document.getElementById('key_challenges')?.value || null,
        key_successes: document.getElementById('key_successes')?.value || null,
        lessons_learned: document.getElementById('lessons_learned')?.value || null,
        general_notes: document.getElementById('general_notes')?.value || null,
        has_per_diem: hasPerDiem,
        per_diem_rate: hasPerDiem && perDiemVal ? parseFloat(perDiemVal) : null,
    };

    // Skip if all fields are empty
    if (Object.values(data).every(v => !v)) return;

    try {
        await api('/interview/context', {
            method: 'POST',
            body: JSON.stringify({ job_id: jobId, type: 'job', data }),
        });
        showSaveIndicator('jobSaveIndicator');
    } catch (err) {
        console.error('Save failed:', err);
    }
}

async function saveCCContext(jobId, costCode) {
    const data = {
        scope_included: document.getElementById('cc_scope_included')?.value || null,
        scope_excluded: document.getElementById('cc_scope_excluded')?.value || null,
        related_codes: document.getElementById('cc_related_codes')?.value || null,
        conditions: document.getElementById('cc_conditions')?.value || null,
        notes: document.getElementById('cc_notes')?.value || null,
    };

    // Skip if all empty
    if (Object.values(data).every(v => !v)) return;

    try {
        await api('/interview/context', {
            method: 'POST',
            body: JSON.stringify({ job_id: jobId, type: 'cost_code', cost_code: costCode, data }),
        });
        showSaveIndicator('ccSaveIndicator');

        // Update the dot in the sidebar
        const cc = state.jobDetail.cost_codes.find(c => c.code === costCode);
        if (cc) {
            cc.has_context = true;
            cc.context = data;
        }
        // Update dot color
        const listItems = document.querySelectorAll('.cc-list-item');
        listItems.forEach(item => {
            if (item.querySelector('.cc-list-code')?.textContent === costCode) {
                const dot = item.querySelector('.cc-dot');
                if (dot) {
                    dot.classList.remove('no-context');
                    dot.classList.add('has-context');
                }
            }
        });
    } catch (err) {
        console.error('Save failed:', err);
    }
}

function showSaveIndicator(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add('visible');
    setTimeout(() => el.classList.remove('visible'), 2000);
}

async function markComplete(jobId) {
    try {
        await api(`/interview/complete/${jobId}`, { method: 'POST' });
        navigate('jobs');
    } catch (err) {
        console.error('Mark complete failed:', err);
    }
}

// ── Diary Helpers ──
function getDiaryStatsHtml(jobs) {
    const withDiary = jobs.filter(j => j.diary_entry_count > 0);
    const totalEntries = withDiary.reduce((s, j) => s + j.diary_entry_count, 0);
    if (withDiary.length === 0) {
        return '<span>No diary data imported yet. Place .txt exports in the Heavy Job Notes folder and click Import.</span>';
    }
    return `
        <span><span class="diary-stat-value">${withDiary.length}</span> jobs with diary data</span>
        <span><span class="diary-stat-value">${fmt(totalEntries)}</span> total entries</span>
    `;
}

async function importDiaries() {
    const btn = document.getElementById('importDiaryBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Importing...';
    }
    try {
        const result = await api('/diary/import', { method: 'POST' });
        // Reload the job list to pick up diary counts
        const [jobs, progress] = await Promise.all([
            api('/interview/jobs'),
            api('/interview/progress'),
        ]);
        state.jobs = jobs;
        renderJobList(jobs, progress);

        // Show result briefly
        const stats = document.getElementById('diaryStats');
        if (stats) {
            const matched = result.jobs_matched || 0;
            const total = result.total_entries || 0;
            stats.innerHTML = `<span style="color: var(--confidence-high); font-weight: 600;">Imported ${fmt(total)} entries across ${matched} jobs</span>`;
        }
    } catch (err) {
        console.error('Diary import failed:', err);
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Import Diary Files';
        }
    }
}

async function synthesizeDiary(jobId) {
    const btn = document.getElementById('synthesizeBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Synthesizing...';
    }
    try {
        const result = await api(`/diary/synthesize/${jobId}`, { method: 'POST' });
        // Reload the job detail to show synthesized context
        await loadJobDetail(jobId);
    } catch (err) {
        console.error('Synthesis failed:', err);
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Synthesize with AI';
        }
    }
}

// ── Document Upload Helpers ──

function initDocUploadArea(jobId) {
    const area = document.getElementById('docUploadArea');
    if (!area) return;

    area.addEventListener('dragover', (e) => {
        e.preventDefault();
        area.classList.add('dragover');
    });
    area.addEventListener('dragleave', () => {
        area.classList.remove('dragover');
    });
    area.addEventListener('drop', (e) => {
        e.preventDefault();
        area.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleDocUpload(jobId, e.dataTransfer.files);
        }
    });
}
const DOC_TYPE_LABELS = {
    change_order: 'Change Order',
    production_kpi: 'Production / KPI',
    rfi_submittal: 'RFI / Submittal',
    material_tracking: 'Material Tracking',
    other: 'Other',
};

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

async function loadDocList(jobId) {
    try {
        const docs = await api(`/documents/list/${jobId}`);
        const container = document.getElementById('docList');
        if (!container) return;

        if (!docs || docs.length === 0) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML = docs.map(doc => `
            <div class="doc-item">
                <div class="doc-item-info">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0284C7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <div>
                        <div class="doc-item-name">${doc.filename}</div>
                        <div class="doc-item-meta">
                            <span class="doc-type-badge">${DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type}</span>
                            &middot; ${formatFileSize(doc.file_size)}
                            &middot; ${doc.text_length ? fmt(doc.text_length) + ' chars extracted' : ''}
                            ${doc.extraction_error ? ' &middot; <span style="color: #EF4444;">extraction error</span>' : ''}
                        </div>
                    </div>
                </div>
                <div class="doc-item-actions">
                    ${doc.analyzed ? '<span class="badge-analyzed">Analyzed</span>' : '<span class="badge-pending">Pending</span>'}
                    <button class="btn-icon danger" onclick="deleteDoc(${doc.id}, ${jobId})" title="Delete">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        console.error('Failed to load documents:', err);
    }
}

async function handleDocUpload(jobId, files) {
    if (!files || files.length === 0) return;

    const docType = document.getElementById('docTypeSelect')?.value || 'other';
    const uploadArea = document.getElementById('docUploadArea');

    for (const file of files) {
        if (uploadArea) {
            uploadArea.innerHTML = `<div style="color: #0284C7; font-size: 13px;"><span class="spinner" style="border-top-color: #0284C7; border-color: rgba(14,165,233,0.2); border-top-color: #0284C7;"></span> Uploading ${file.name}...</div>`;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('doc_type', docType);

        try {
            const resp = await fetch(`/api/documents/upload/${jobId}`, {
                method: 'POST',
                body: formData,
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Upload failed');
            }
        } catch (err) {
            console.error('Upload failed:', err);
            alert(`Upload failed for ${file.name}: ${err.message}`);
        }
    }

    // Reset upload area
    if (uploadArea) {
        uploadArea.innerHTML = `
            <input type="file" id="docFileInput" style="display:none" accept=".pdf,.xlsx,.xls,.csv,.txt,.md" multiple onchange="handleDocUpload(${jobId}, this.files)">
            <div style="color: var(--text-tertiary); font-size: 13px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                Drop files here or click to upload
                <div style="font-size: 11px; margin-top: 4px; color: var(--text-disabled);">PDF, Excel, CSV, or TXT &middot; Max 20 MB</div>
            </div>`;
    }

    // Show the enrich button if it wasn't there
    const enrichBtn = document.getElementById('enrichBtn');
    if (!enrichBtn) {
        const docHeader = document.querySelector('.doc-header > div:last-child');
        if (docHeader) {
            docHeader.innerHTML = `
                <button class="btn btn-sm" id="enrichBtn" onclick="enrichFromDocs(${jobId})"
                    style="background: rgba(14,165,233,0.1); color: #0284C7; border-color: rgba(14,165,233,0.3);">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                    Enrich with AI
                </button>`;
        }
    }

    // Reload document list
    await loadDocList(jobId);

    // Reset file input
    const fileInput = document.getElementById('docFileInput');
    if (fileInput) fileInput.value = '';
}

async function deleteDoc(docId, jobId) {
    try {
        await api(`/documents/${docId}`, { method: 'DELETE' });
        await loadDocList(jobId);
    } catch (err) {
        console.error('Delete failed:', err);
    }
}

async function enrichFromDocs(jobId) {
    const btn = document.getElementById('enrichBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" style="border-top-color: #0284C7; border-color: rgba(14,165,233,0.2); border-top-color: #0284C7;"></span> Enriching...';
    }
    try {
        const result = await api(`/documents/enrich/${jobId}`, { method: 'POST' });
        // Reload the full job detail to show enriched context
        await loadJobDetail(jobId);
    } catch (err) {
        console.error('Enrichment failed:', err);
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Enrich with AI`;
        }
    }
}

function sourceBadge(source) {
    if (!source) return '';
    if (source === 'ai_synthesized') return '<span class="source-badge source-ai">AI Draft</span>';
    if (source === 'ai_document') return '<span class="source-badge source-document">AI + Docs</span>';
    if (source === 'manual') return '<span class="source-badge source-manual">PM</span>';
    return '';
}

// ── Settings Page ──
async function renderSettings() {
    document.getElementById('pageTitle').textContent = 'Rate Settings';
    document.getElementById('pageSubtitle').textContent = '';

    const content = document.getElementById('content');
    content.innerHTML = '<div class="empty-state"><p>Loading rates...</p></div>';

    try {
        const [laborData, groupData, coverage] = await Promise.all([
            api('/settings/labor-rates'),
            api('/settings/equipment-groups'),
            api('/settings/rate-coverage'),
        ]);

        const rates = laborData.rates;
        const groups = groupData.groups;

        content.innerHTML = `
            <div class="settings-page">
                <!-- Import Banner -->
                <div class="settings-banner">
                    <div class="banner-left">
                        <div class="banner-title">Rate Import</div>
                        <div class="banner-subtitle">Import rates from HeavyJob export files (PayClass.txt + EquipmentSetup.txt)</div>
                    </div>
                    <button class="btn btn-primary" onclick="importRates()" id="importBtn">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                        Import / Refresh Rates
                    </button>
                </div>

                <!-- Coverage Summary -->
                <div class="settings-coverage">
                    <div class="coverage-card">
                        <div class="coverage-label">Labor Rate Coverage</div>
                        <div class="coverage-value">${coverage.labor.coverage_pct}%</div>
                        <div class="coverage-detail">${fmt(coverage.labor.mapped_codes)} / ${fmt(coverage.labor.total_codes)} codes mapped &middot; ${fmt(coverage.labor.mapped_hours)} / ${fmt(coverage.labor.total_hours)} hrs</div>
                        ${coverage.unmapped_labor.length > 0 ? `
                        <div class="coverage-unmapped">
                            <strong>Unmapped:</strong> ${coverage.unmapped_labor.map(u => `${u.pay_class_code} (${fmt(u.hours)} hrs)`).join(', ')}
                        </div>` : ''}
                    </div>
                    <div class="coverage-card">
                        <div class="coverage-label">Equipment Rate Coverage</div>
                        <div class="coverage-value">${coverage.equipment.coverage_pct}%</div>
                        <div class="coverage-detail">${fmt(coverage.equipment.mapped_codes)} / ${fmt(coverage.equipment.total_codes)} codes mapped &middot; ${fmt(coverage.equipment.mapped_hours)} / ${fmt(coverage.equipment.total_hours)} hrs</div>
                        ${coverage.unmapped_equipment.length > 0 ? `
                        <div class="coverage-unmapped">
                            <strong>Unmapped (top ${coverage.unmapped_equipment.length}):</strong> ${coverage.unmapped_equipment.slice(0, 10).map(u => `${u.equipment_code} (${fmt(u.hours)} hrs)`).join(', ')}${coverage.unmapped_equipment.length > 10 ? '...' : ''}
                        </div>` : ''}
                    </div>
                </div>

                <!-- Tabs -->
                <div class="settings-tabs">
                    <button class="settings-tab active" onclick="switchSettingsTab('labor', this)">Labor Rates (${rates.length})</button>
                    <button class="settings-tab" onclick="switchSettingsTab('equipment', this)">Equipment Groups (${groups.length})</button>
                </div>

                <!-- Tab Content -->
                <div id="settingsTabContent">
                    ${renderLaborRatesTable(rates)}
                </div>
            </div>
        `;
    } catch (err) {
        content.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${err.message}</p></div>`;
    }
}

function renderLaborRatesTable(rates) {
    return `
        <div class="rates-table-wrap">
            <table class="rates-table">
                <thead>
                    <tr>
                        <th>Pay Class</th>
                        <th>Description</th>
                        <th class="num">Base Rate</th>
                        <th class="num">Tax %</th>
                        <th class="num">Fringe</th>
                        <th class="num">Loaded Rate</th>
                        <th class="num">T&M Rate</th>
                        <th class="num">Actual Hrs</th>
                        <th class="num">Jobs</th>
                        <th>Source</th>
                    </tr>
                </thead>
                <tbody>
                    ${rates.map(r => `
                    <tr>
                        <td><strong>${r.pay_class_code}</strong></td>
                        <td>${r.description || ''}</td>
                        <td class="num">$${fmtRate(r.base_rate)}</td>
                        <td class="num">${fmt(r.tax_pct, 2)}%</td>
                        <td class="num">$${fmtRate(r.fringe_non_ot)}</td>
                        <td class="num" style="font-weight: 700; color: var(--wollam-navy);">$${fmtRate(r.loaded_rate)}</td>
                        <td class="num">${r.tm_rate > 0 ? '$' + fmtRate(r.tm_rate) : '—'}</td>
                        <td class="num">${fmt(r.actual_hours)}</td>
                        <td class="num">${fmt(r.job_count)}</td>
                        <td>${r.source === 'imported' ? '<span class="source-badge source-ai">Imported</span>' : '<span class="source-badge source-manual">Manual</span>'}</td>
                    </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function renderEquipmentGroupsTable(groups) {
    return `
        <div class="rates-table-wrap">
            <table class="rates-table">
                <thead>
                    <tr>
                        <th>Group</th>
                        <th class="num">Items</th>
                        <th class="num">Avg Rate</th>
                        <th class="num">Min</th>
                        <th class="num">Max</th>
                        <th class="num">Actual Hrs</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    ${groups.map(g => `
                    <tr>
                        <td><strong>${g.group_name}</strong></td>
                        <td class="num">${fmt(g.item_count)}</td>
                        <td class="num" style="font-weight: 700; color: var(--wollam-navy);">$${fmtRate(g.avg_rate)}</td>
                        <td class="num">$${fmtRate(g.min_rate)}</td>
                        <td class="num">$${fmtRate(g.max_rate)}</td>
                        <td class="num">${fmt(g.total_actual_hours)}</td>
                        <td><button class="btn btn-sm" onclick="showEquipmentGroup('${g.group_name}')">View Items</button></td>
                    </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

async function switchSettingsTab(tab, btn) {
    document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    const tabContent = document.getElementById('settingsTabContent');

    if (tab === 'labor') {
        const data = await api('/settings/labor-rates');
        tabContent.innerHTML = renderLaborRatesTable(data.rates);
    } else {
        const data = await api('/settings/equipment-groups');
        tabContent.innerHTML = renderEquipmentGroupsTable(data.groups);
    }
}

async function showEquipmentGroup(groupName) {
    const tabContent = document.getElementById('settingsTabContent');
    tabContent.innerHTML = '<div class="empty-state" style="padding: 24px;"><p>Loading...</p></div>';

    const data = await api(`/settings/equipment-rates?group=${encodeURIComponent(groupName)}`);
    tabContent.innerHTML = `
        <div style="margin-bottom: 12px;">
            <button class="btn btn-sm" onclick="switchSettingsTab('equipment', document.querySelectorAll('.settings-tab')[1])">
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
                Back to Groups
            </button>
            <span style="margin-left: 12px; font-weight: 600;">${groupName}</span>
            <span style="color: var(--text-tertiary); font-size: 13px; margin-left: 8px;">${data.count} items</span>
        </div>
        <div class="rates-table-wrap">
            <table class="rates-table">
                <thead>
                    <tr>
                        <th>Code</th>
                        <th>Description</th>
                        <th class="num">Base Rate</th>
                        <th class="num">2nd Rate</th>
                        <th class="num">Actual Hrs</th>
                        <th class="num">Jobs</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.rates.map(r => `
                    <tr>
                        <td><strong>${r.equipment_code}</strong></td>
                        <td>${r.description || ''}</td>
                        <td class="num" style="font-weight: 600;">$${fmtRate(r.base_rate)}</td>
                        <td class="num">${r.second_rate > 0 ? '$' + fmtRate(r.second_rate) : '—'}</td>
                        <td class="num">${fmt(r.actual_hours)}</td>
                        <td class="num">${fmt(r.job_count)}</td>
                    </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

async function importRates() {
    const btn = document.getElementById('importBtn');
    btn.disabled = true;
    btn.innerHTML = 'Importing...';

    try {
        const result = await api('/settings/import-rates', { method: 'POST' });
        btn.innerHTML = `Imported ${result.labor_rates_imported} labor + ${result.equipment_rates_imported} equipment`;
        btn.style.background = 'var(--success-green)';
        setTimeout(() => renderSettings(), 1500);
    } catch (err) {
        btn.innerHTML = `Error: ${err.message}`;
        btn.style.background = 'var(--danger-red, #ef4444)';
        btn.disabled = false;
    }
}

// ── Chat Page ──

function renderChatBidSelector() {
    const bids = state.chatBids || [];
    if (bids.length === 0) return '';
    const selected = state.chatBidId;
    const selectedBid = selected ? bids.find(b => b.id === selected) : null;
    return `
        <div class="chat-bid-selector">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;opacity:0.6;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <select class="chat-bid-select" onchange="setChatBid(this.value)">
                <option value="">Historical data only (no bid context)</option>
                ${bids.map(b => `<option value="${b.id}" ${b.id === selected ? 'selected' : ''}>${escHtml(b.bid_name || b.bid_number)} — ${b.doc_count || 0} docs</option>`).join('')}
            </select>
            ${selectedBid ? `<span class="chat-bid-active-badge">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="var(--wollam-green, #22c55e)" stroke="none"><circle cx="12" cy="12" r="10"/></svg>
                Vector search active
            </span>` : ''}
        </div>
    `;
}

function setChatBid(bidId) {
    state.chatBidId = bidId ? parseInt(bidId) : null;
    // Update placeholder text
    const input = document.getElementById('chatInput');
    if (input) {
        input.placeholder = state.chatBidId
            ? 'Ask about this bid — specs, contracts, documents...'
            : 'Ask about historical rates, crews, production...';
    }
    // Update bid bar
    const bar = document.getElementById('chatBidBar');
    if (bar) bar.innerHTML = renderChatBidSelector();
    // Update welcome if no messages
    if (state.chatMessages.length === 0) renderChatWelcome();
}

async function renderChat() {
    document.getElementById('pageTitle').textContent = 'AI Estimating Chat';
    document.getElementById('pageSubtitle').textContent = '';

    // Load conversations list, data summary, and active bids in parallel
    const [convos, summary, bids] = await Promise.all([
        api('/chat/conversations').catch(() => []),
        api('/chat/data-summary').catch(() => null),
        api('/bidding/bids').catch(() => []),
    ]);
    state.chatConversations = convos;
    state.chatDataSummary = summary;
    state.chatBids = (bids || []).filter(b => b.status === 'active');

    // Override content area padding for full-height chat layout
    const contentArea = document.getElementById('contentArea');
    contentArea.style.padding = '0';
    contentArea.style.display = 'flex';

    document.getElementById('content').style.maxWidth = 'none';
    document.getElementById('content').style.margin = '0';
    document.getElementById('content').style.width = '100%';
    document.getElementById('content').style.display = 'flex';
    document.getElementById('content').style.height = '100%';

    document.getElementById('content').innerHTML = `
        <div class="chat-layout">
            <!-- Conversation sidebar -->
            <div class="chat-sidebar">
                <button class="btn btn-primary" style="width:100%; margin-bottom:12px;" onclick="chatNewConversation()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    New Conversation
                </button>
                <div class="chat-conv-list" id="chatConvList"></div>
            </div>

            <!-- Main chat area -->
            <div class="chat-main">
                <div class="chat-bid-bar" id="chatBidBar">
                    ${renderChatBidSelector()}
                </div>
                <div class="chat-messages" id="chatMessages"></div>
                <div class="chat-input-area">
                    <div class="chat-input-wrap">
                        <textarea id="chatInput" class="chat-input" placeholder="${state.chatBidId ? 'Ask about this bid — specs, contracts, documents...' : 'Ask about historical rates, crews, production...'}" rows="1"
                            onkeydown="chatInputKeydown(event)"></textarea>
                        <button class="chat-send-btn" id="chatSendBtn" onclick="chatSend()">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                        </button>
                    </div>
                    <div class="chat-input-meta">
                        ${summary ? `<span>${fmt(summary.total_jobs)} jobs &middot; ${fmt(summary.total_rate_items)} rate items &middot; ${fmt(summary.total_timecards)} timecards</span>` : ''}
                    </div>
                </div>
            </div>
        </div>
    `;

    renderChatConvList();

    // If we have an active conversation, load it; otherwise show welcome
    if (state.chatConversationId) {
        await chatLoadConversation(state.chatConversationId);
    } else {
        renderChatWelcome();
    }

    // Auto-resize textarea
    const input = document.getElementById('chatInput');
    if (input) {
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 150) + 'px';
        });
    }
}

function renderChatConvList() {
    const el = document.getElementById('chatConvList');
    if (!el) return;
    if (state.chatConversations.length === 0) {
        el.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--text-tertiary);text-align:center;">No conversations yet</div>';
        return;
    }
    el.innerHTML = state.chatConversations.map(c => {
        const active = c.id === state.chatConversationId ? 'active' : '';
        const date = new Date(c.updated_at || c.created_at);
        const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        // Show bid name badge if conversation is tied to a bid
        let bidBadge = '';
        if (c.bid_id) {
            const bid = state.chatBids.find(b => b.id === c.bid_id);
            const bidLabel = bid ? bid.bid_name : `Bid #${c.bid_id}`;
            bidBadge = `<span class="badge badge-document" style="font-size:10px;padding:1px 5px;margin-left:4px;" title="${escHtml(bidLabel)}">${escHtml(bidLabel.length > 20 ? bidLabel.slice(0, 20) + '…' : bidLabel)}</span>`;
        }
        return `
            <div class="chat-conv-item ${active}" onclick="chatLoadConversation(${c.id})">
                <div class="chat-conv-title">${escHtml(c.title || 'New Conversation')}${bidBadge}</div>
                <div class="chat-conv-meta">${dateStr} &middot; ${c.message_count || 0} msgs</div>
                <button class="chat-conv-delete" onclick="event.stopPropagation();chatDeleteConversation(${c.id})" title="Delete">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
        `;
    }).join('');
}

function renderChatWelcome() {
    const el = document.getElementById('chatMessages');
    if (!el) return;
    const s = state.chatDataSummary;
    el.innerHTML = `
        <div class="chat-welcome">
            <div class="chat-welcome-icon">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--wollam-navy)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            </div>
            <h2 style="font-size:20px;font-weight:700;color:var(--text-primary);margin-bottom:4px;">Ask WEIS</h2>
            <p style="color:var(--text-secondary);margin-bottom:20px;max-width:500px;">
                Query Wollam's historical field data — real man-hours, crews, production rates, and costs from every project tracked in HeavyJob.
            </p>
            ${s ? `<div class="chat-welcome-stats">
                <div class="chat-welcome-stat"><span class="chat-welcome-stat-value">${fmt(s.total_jobs)}</span><span class="chat-welcome-stat-label">Jobs</span></div>
                <div class="chat-welcome-stat"><span class="chat-welcome-stat-value">${fmt(s.total_rate_items)}</span><span class="chat-welcome-stat-label">Rate Items</span></div>
                <div class="chat-welcome-stat"><span class="chat-welcome-stat-value">${fmt(s.total_timecards)}</span><span class="chat-welcome-stat-label">Timecards</span></div>
                <div class="chat-welcome-stat"><span class="chat-welcome-stat-value">${s.jobs_with_pm_context}</span><span class="chat-welcome-stat-label">PM Context</span></div>
                ${s.total_estimates > 0 ? `<div class="chat-welcome-stat"><span class="chat-welcome-stat-value">${s.total_estimates}</span><span class="chat-welcome-stat-label">Estimates</span></div>` : ''}
            </div>` : ''}
            <div class="chat-suggested">
                <div class="chat-suggested-label">Try asking:</div>
                <div class="chat-suggested-grid">
                    ${state.chatBidId ? `
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">What are the liquidated damages on this project?</button>
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">What does the spec say about compaction testing requirements?</button>
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">Summarize the bonding and insurance requirements</button>
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">What subcontractor scopes should we plan for?</button>
                    ` : `
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">What are our historical rates for concrete wall forming?</button>
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">How many hours should I plan for HDPE pipe fusing?</button>
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">What crew size works best for structural steel erection?</button>
                    <button class="chat-suggested-btn" onclick="chatSendSuggested(this.textContent)">Compare earthwork production across our completed jobs</button>
                    `}
                </div>
            </div>
        </div>
    `;
}

function renderChatMessages() {
    const el = document.getElementById('chatMessages');
    if (!el) return;
    if (state.chatMessages.length === 0) {
        renderChatWelcome();
        return;
    }
    el.innerHTML = state.chatMessages.map(m => {
        if (m.role === 'user') {
            return `<div class="chat-msg chat-msg-user"><div class="chat-msg-bubble chat-msg-user-bubble">${escHtml(m.content)}</div></div>`;
        }
        // AI message — render markdown-ish content
        const html = renderMarkdown(m.content);
        const sources = m.sources || [];
        let sourcesHtml = '';
        if (sources.length > 0) {
            sourcesHtml = `
                <div class="chat-sources">
                    <div class="chat-sources-label" onclick="this.parentElement.classList.toggle('expanded')">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                        Sources (${sources.length})
                    </div>
                    <div class="chat-sources-list">
                        ${sources.map(s => {
                            if (s.source_type === 'document') {
                                return `<span class="chat-source-badge badge-document" title="${escHtml(s.section || '')}">
                                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-1px;margin-right:3px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                                    ${escHtml(s.filename || 'Document')}${s.section ? ' &middot; ' + escHtml(s.section) : ''}
                                </span>`;
                            }
                            if (s.source_type === 'estimate') {
                                return `<span class="chat-source-badge badge-estimate">
                                    &#9670; ${escHtml(s.job_number)} &middot; ESTIMATE &middot; $${s.bid_total ? Number(s.bid_total).toLocaleString() : '?'}
                                </span>`;
                            }
                            return `<span class="chat-source-badge badge-${(s.confidence || 'none').toLowerCase()}">
                                ${escHtml(s.job_number)} &middot; ${escHtml(s.cost_code)} &middot; ${(s.confidence || 'N/A').toUpperCase()}
                                ${s.has_pm_context ? '<span title="Has PM context" style="margin-left:2px;">&#9679;</span>' : ''}
                            </span>`;
                        }).join('')}
                    </div>
                </div>
            `;
        }
        return `<div class="chat-msg chat-msg-ai"><div class="chat-msg-bubble chat-msg-ai-bubble">${html}${sourcesHtml}</div></div>`;
    }).join('');

    // Show loading indicator if waiting
    if (state.chatLoading) {
        el.innerHTML += `
            <div class="chat-msg chat-msg-ai">
                <div class="chat-msg-bubble chat-msg-ai-bubble">
                    <div class="chat-loading">
                        <div class="chat-loading-dot"></div>
                        <div class="chat-loading-dot"></div>
                        <div class="chat-loading-dot"></div>
                    </div>
                </div>
            </div>
        `;
    }

    // Scroll to bottom
    el.scrollTop = el.scrollHeight;
}

function renderMarkdown(text) {
    if (!text) return '';
    // Parse tables first (before escaping)
    let html = '';
    const lines = text.split('\n');
    let i = 0;
    while (i < lines.length) {
        // Detect markdown table (line with | characters, followed by separator row)
        if (lines[i].includes('|') && i + 1 < lines.length && /^\|?[\s-:|]+\|/.test(lines[i + 1])) {
            // Parse header
            const headers = lines[i].split('|').map(s => s.trim()).filter(s => s);
            i += 2; // skip header + separator
            const rows = [];
            while (i < lines.length && lines[i].includes('|')) {
                const cells = lines[i].split('|').map(s => s.trim()).filter(s => s);
                rows.push(cells);
                i++;
            }
            html += '<table><thead><tr>' + headers.map(h => `<th>${escHtml(h)}</th>`).join('') + '</tr></thead><tbody>';
            rows.forEach(r => {
                html += '<tr>' + r.map(c => `<td>${escHtml(c).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}</td>`).join('') + '</tr>';
            });
            html += '</tbody></table>';
            continue;
        }
        html += escHtml(lines[i]) + '\n';
        i++;
    }
    // Headers
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Code blocks
    html = html.replace(/```([\s\S]*?)```/g, '<pre>$1</pre>');
    // Inline code
    html = html.replace(/`(.+?)`/g, '<code style="background:var(--bg-base);padding:1px 4px;border-radius:3px;font-size:11px;">$1</code>');
    // Bullet points
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    // Line breaks
    html = html.replace(/\n\n/g, '<br>');
    html = html.replace(/\n/g, '<br>');
    return html;
}

function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function chatSend() {
    const input = document.getElementById('chatInput');
    const message = input?.value?.trim();
    if (!message || state.chatLoading) return;

    input.value = '';
    input.style.height = 'auto';

    // Add user message to state
    state.chatMessages.push({ role: 'user', content: message });
    state.chatLoading = true;
    renderChatMessages();

    try {
        const result = await api('/chat/send', {
            method: 'POST',
            body: JSON.stringify({
                conversation_id: state.chatConversationId,
                message: message,
                bid_id: state.chatBidId || undefined,
            }),
        });

        state.chatConversationId = result.conversation_id;
        state.chatMessages.push({
            role: 'assistant',
            content: result.response,
            sources: result.sources || [],
        });

        // Update conversation list
        const convos = await api('/chat/conversations').catch(() => []);
        state.chatConversations = convos;
        renderChatConvList();
    } catch (err) {
        state.chatMessages.push({
            role: 'assistant',
            content: `**Error:** ${err.message || 'Failed to get response. Please try again.'}`,
            sources: [],
        });
    } finally {
        state.chatLoading = false;
        renderChatMessages();
    }
}

function chatSendSuggested(text) {
    const input = document.getElementById('chatInput');
    if (input) input.value = text;
    chatSend();
}

function chatInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatSend();
    }
}

async function chatLoadConversation(convId) {
    state.chatConversationId = convId;
    try {
        const conv = await api(`/chat/conversations/${convId}`);
        state.chatMessages = (conv.messages || []).map(m => ({
            role: m.role,
            content: m.content,
            sources: m.sources || [],
        }));
        // Restore bid context if conversation was tied to a bid
        if (conv.bid_id) {
            state.chatBidId = conv.bid_id;
            const bar = document.getElementById('chatBidBar');
            if (bar) bar.innerHTML = renderChatBidSelector();
        }
    } catch {
        state.chatMessages = [];
    }
    renderChatMessages();
    renderChatConvList();
}

function chatNewConversation() {
    state.chatConversationId = null;
    state.chatMessages = [];
    renderChatMessages();
    renderChatConvList();
    document.getElementById('chatInput')?.focus();
}

async function chatDeleteConversation(convId) {
    try {
        await api(`/chat/conversations/${convId}`, { method: 'DELETE' });
        state.chatConversations = state.chatConversations.filter(c => c.id !== convId);
        if (state.chatConversationId === convId) {
            state.chatConversationId = null;
            state.chatMessages = [];
            renderChatMessages();
        }
        renderChatConvList();
    } catch { /* ignore */ }
}

// ============================================================
// ESTIMATES PAGE — HeavyBid Estimate Insights
// ============================================================

let estList = [];
let estDetail = null;
let estBiditems = [];
let estActivities = [];
let estResources = [];
let estSearchQuery = '';
let estSyncLoading = false;
let estViewMode = 'table';  // 'card' or 'table'
let estSelectedBidItemId = null;
let estSelectedActivityId = null;
let estExpandedBidItems = new Set();

async function loadEstimateList() {
    document.getElementById('pageTitle').textContent = 'HeavyBid Estimates';
    document.getElementById('pageSubtitle').textContent = '';
    const content = document.getElementById('content');
    content.innerHTML = '<div class="empty-state"><p>Loading estimates...</p></div>';

    try {
        estList = await api('/estimates/');
        renderEstimateList();
    } catch (e) {
        content.innerHTML = `<div class="empty-state"><p>Error loading estimates: ${escHtml(e.message)}</p></div>`;
    }
}

function renderEstimateList() {
    const content = document.getElementById('content');
    const totalBid = estList.reduce((s, e) => s + (e.bid_total || 0), 0);
    const totalMH = estList.reduce((s, e) => s + (e.total_manhours || 0), 0);
    const linked = estList.filter(e => e.linked_job_id).length;

    const filtered = estList.filter(e => {
        if (!estSearchQuery) return true;
        const q = estSearchQuery.toLowerCase();
        return (e.code || '').toLowerCase().includes(q) || (e.name || '').toLowerCase().includes(q);
    });

    content.innerHTML = `
        <div class="kpi-row" style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap;">
            <div class="kpi-card" style="flex:1;min-width:180px;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;">
                <div style="font-size:28px;font-weight:700;color:var(--text-primary);">${estList.length}</div>
                <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">Total Estimates</div>
            </div>
            <div class="kpi-card" style="flex:1;min-width:180px;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;">
                <div style="font-size:28px;font-weight:700;color:var(--wollam-blue);">${linked}</div>
                <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">Linked to HeavyJob</div>
            </div>
            <div class="kpi-card" style="flex:1;min-width:180px;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;">
                <div style="font-size:28px;font-weight:700;color:var(--text-primary);">$${fmt(totalBid)}</div>
                <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">Total Bid Value</div>
            </div>
            <div class="kpi-card" style="flex:1;min-width:180px;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;">
                <div style="font-size:28px;font-weight:700;color:var(--text-primary);">${fmt(totalMH)}</div>
                <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">Total Manhours</div>
            </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
            <div style="display:flex;align-items:center;gap:12px;">
                <input type="text" placeholder="Search estimates..." value="${escHtml(estSearchQuery)}"
                       oninput="estSearchQuery=this.value;renderEstimateList()"
                       style="padding:8px 14px;border:1px solid var(--border);border-radius:8px;font-size:14px;width:300px;background:var(--bg-card);color:var(--text-primary);">
                <span style="font-size:12px;color:var(--text-tertiary);">${filtered.length} estimate${filtered.length !== 1 ? 's' : ''}</span>
                <div class="view-toggle">
                    <button class="view-toggle-btn ${estViewMode === 'card' ? 'active' : ''}" onclick="estViewMode='card';renderEstimateList()" title="Card view">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                    </button>
                    <button class="view-toggle-btn ${estViewMode === 'table' ? 'active' : ''}" onclick="estViewMode='table';renderEstimateList()" title="Table view">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
                    </button>
                </div>
            </div>
            <button onclick="openSyncModal()" style="padding:8px 20px;background:var(--wollam-blue);color:white;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500;">
                ${estSyncLoading ? 'Syncing...' : 'Sync from HeavyBid'}
            </button>
        </div>

        ${filtered.length === 0 ? '<div class="empty-state"><p>No estimates found. Use "Sync from HeavyBid" to pull estimate data.</p></div>' : (estViewMode === 'table' ? renderEstimateTable(filtered) : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:16px;">${filtered.map(est => renderEstimateCard(est)).join('')}</div>`)}

        <div id="syncModal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:1000;display:none;align-items:center;justify-content:center;">
            <div style="background:var(--bg-card);border-radius:16px;padding:32px;max-width:600px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
                <div id="syncModalContent">Loading...</div>
            </div>
        </div>
    `;
}

function renderEstimateCard(est) {
    const linkedBadge = est.linked_job_id
        ? `<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;background:rgba(37,99,235,0.1);color:var(--wollam-blue);border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;" onclick="event.stopPropagation();navigate('jobs',${est.linked_job_id})">HJ ${escHtml(est.hj_job_number || '')} &rarr;</span>`
        : `<span style="padding:2px 8px;background:rgba(156,163,175,0.1);color:var(--text-tertiary);border-radius:6px;font-size:11px;">Unlinked</span>`;

    return `
        <div class="card" onclick="navigate('estimates',${est.estimate_id})" style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;cursor:pointer;transition:all 0.15s;">
            <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:12px;">
                <div>
                    <div style="font-size:13px;font-weight:600;color:var(--wollam-blue);">${escHtml(est.code || '')}</div>
                    <div style="font-size:16px;font-weight:600;color:var(--text-primary);margin-top:2px;">${escHtml(est.name || '')}</div>
                </div>
                ${linkedBadge}
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px;">
                <div><span style="color:var(--text-tertiary);">Bid Total</span><br><strong>$${fmt(est.bid_total)}</strong></div>
                <div><span style="color:var(--text-tertiary);">Manhours</span><br><strong>${fmt(est.total_manhours)}</strong></div>
                <div><span style="color:var(--text-tertiary);">Items</span><br><strong>${est.biditem_count || 0} bid items</strong></div>
                <div><span style="color:var(--text-tertiary);">Activities</span><br><strong>${est.activity_count || 0} activities</strong></div>
            </div>
            ${est.state || est.estimator ? `<div style="margin-top:10px;font-size:12px;color:var(--text-tertiary);">${est.state ? escHtml(est.state) : ''}${est.state && est.estimator ? ' · ' : ''}${est.estimator ? 'Est: ' + escHtml(est.estimator) : ''}</div>` : ''}
        </div>
    `;
}

function renderEstimateTable(filtered) {
    return `
        <div class="card" style="overflow-x:auto;">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Code</th>
                        <th>Name</th>
                        <th style="text-align:center;">Linked</th>
                        <th style="text-align:right;">Bid Total</th>
                        <th style="text-align:right;">Manhours</th>
                        <th style="text-align:right;">Bid Items</th>
                        <th style="text-align:right;">Activities</th>
                        <th style="text-align:center;">Estimator</th>
                    </tr>
                </thead>
                <tbody>
                    ${filtered.map(est => {
                        const linkedBadge = est.linked_job_id
                            ? `<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;background:rgba(37,99,235,0.1);color:var(--wollam-blue);border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;" onclick="event.stopPropagation();navigate('jobs',${est.linked_job_id})">HJ ${escHtml(est.hj_job_number || '')} &rarr;</span>`
                            : `<span style="padding:2px 8px;background:rgba(156,163,175,0.1);color:var(--text-tertiary);border-radius:6px;font-size:11px;">—</span>`;
                        return `
                        <tr class="data-row" onclick="navigate('estimates',${est.estimate_id})">
                            <td style="font-weight:700;color:var(--wollam-navy);white-space:nowrap;">${escHtml(est.code || '')}</td>
                            <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escHtml(est.name || '')}</td>
                            <td style="text-align:center;">${linkedBadge}</td>
                            <td style="text-align:right;font-variant-numeric:tabular-nums;font-weight:600;">$${fmt(est.bid_total)}</td>
                            <td style="text-align:right;font-variant-numeric:tabular-nums;">${fmt(est.total_manhours)}</td>
                            <td style="text-align:right;font-variant-numeric:tabular-nums;">${est.biditem_count || 0}</td>
                            <td style="text-align:right;font-variant-numeric:tabular-nums;">${est.activity_count || 0}</td>
                            <td style="text-align:center;font-size:12px;color:var(--text-secondary);">${escHtml(est.estimator || '—')}</td>
                        </tr>`;
                    }).join('')}
                </tbody>
            </table>
        </div>
    `;
}

// ── Estimate Detail ──

async function loadEstimateDetail(estimateId) {
    document.getElementById('pageTitle').textContent = 'Estimate Detail';
    document.getElementById('pageSubtitle').textContent = 'Loading...';
    const content = document.getElementById('content');
    content.innerHTML = '<div class="empty-state"><p>Loading estimate...</p></div>';

    try {
        const [detail, biditems, activities, resources] = await Promise.all([
            api(`/estimates/${estimateId}`),
            api(`/estimates/${estimateId}/biditems`),
            api(`/estimates/${estimateId}/activities`),
            api(`/estimates/${estimateId}/resources`),
        ]);
        estDetail = detail;
        estBiditems = biditems;
        estActivities = activities;
        estResources = resources;
        renderEstimateDetail();

        // Auto-select first activity
        if (estBiditems.length > 0 && estActivities.length > 0) {
            const firstBi = estBiditems[0];
            const firstAct = estActivities.find(a => a.hcss_biditem_id === firstBi.hcss_bi_id);
            if (firstAct) {
                estExpandedBidItems.add(firstBi.hcss_bi_id);
                selectEstActivity(firstBi.hcss_bi_id, firstAct.hcss_act_id);
            }
        }
    } catch (e) {
        content.innerHTML = `<div class="empty-state"><p>Error: ${escHtml(e.message)}</p></div>`;
    }
}

function renderEstimateDetail() {
    const d = estDetail;
    document.getElementById('pageTitle').textContent = `${d.code || ''} — ${d.name || ''}`;
    document.getElementById('pageSubtitle').textContent = `HeavyBid Estimate · ${estBiditems.length} bid items · ${estActivities.length} activities · ${estResources.length} resources`;

    const content = document.getElementById('content');

    // Cross-link button
    const crossLink = d.linked_job_id
        ? `<button onclick="navigate('jobs',${d.linked_job_id})" style="padding:8px 20px;background:var(--wollam-blue);color:white;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500;">View Actuals &rarr;</button>`
        : '';

    content.innerHTML = `
        <div style="margin-bottom:24px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <button onclick="navigate('estimates')" style="padding:6px 16px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;cursor:pointer;font-size:13px;color:var(--text-secondary);">&larr; Back to Estimates</button>
                ${d.linked_job_id ? `<button onclick="navigate('jobs',${d.linked_job_id})" style="padding:8px 20px;background:var(--wollam-blue);color:white;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500;">View Job ${escHtml(d.hj_job_number || '')} &rarr;</button>` : ''}
            </div>
            ${d.linked_job_id ? `<div onclick="navigate('jobs',${d.linked_job_id})" style="margin-bottom:12px;padding:8px 14px;background:rgba(37,99,235,0.05);border:1px solid rgba(37,99,235,0.15);border-radius:8px;font-size:13px;color:var(--wollam-blue);cursor:pointer;transition:background 0.15s;" onmouseover="this.style.background='rgba(37,99,235,0.1)'" onmouseout="this.style.background='rgba(37,99,235,0.05)'">Linked to HeavyJob: <strong>${escHtml(d.hj_job_number || '')} — ${escHtml(d.hj_job_name || '')}</strong> (${escHtml(d.hj_job_status || '')}) &rarr;</div>` : ''}
        </div>

        <!-- KPI Bar -->
        <div style="display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap;">
            ${estKpi('Bid Total', '$' + fmt(d.bid_total))}
            ${estKpi('Labor', '$' + fmt(d.total_labor))}
            ${estKpi('Burden', '$' + fmt(d.total_burden))}
            ${estKpi('Equipment', '$' + fmt(d.total_equip))}
            ${estKpi('Material', '$' + fmt(d.total_perm_material))}
            ${estKpi('Subs', '$' + fmt(d.total_subcontract))}
            ${estKpi('Markup', '$' + fmt(d.actual_markup))}
            ${estKpi('Manhours', fmt(d.total_manhours))}
        </div>

        <!-- Master-Detail Layout -->
        <div class="interview-layout">
            <!-- Left: Bid Item / Activity Tree -->
            <div class="interview-sidebar">
                <div class="card" style="position:sticky;top:0;max-height:calc(100vh - 200px);overflow-y:auto;">
                    <div style="padding:12px 16px;border-bottom:1px solid var(--border-default);">
                        <div style="font-size:12px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em;">
                            Bid Items (${estBiditems.length}) &middot; Activities (${estActivities.length})
                        </div>
                    </div>
                    <div class="cc-list" style="padding:8px;" id="estTree">
                        ${renderEstTree()}
                    </div>
                </div>
            </div>

            <!-- Right: Activity Detail -->
            <div class="interview-main" id="estActivityDetail">
                <div class="empty-state"><p>Select an activity from the list</p></div>
            </div>
        </div>
    `;
}

function estKpi(label, value) {
    return `<div style="flex:1;min-width:120px;background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;">
        <div style="font-size:18px;font-weight:700;color:var(--text-primary);">${value}</div>
        <div style="font-size:12px;color:var(--text-secondary);margin-top:2px;">${label}</div>
    </div>`;
}

// ── Estimate Tree Sidebar ──

function renderEstTree() {
    const maxBiMH = Math.max(1, ...estBiditems.map(bi => bi.manhours || 0));
    const maxActMH = Math.max(1, ...estActivities.map(a => a.man_hours || 0));

    return estBiditems.map(bi => {
        const biCode = (bi.biditem_code || '').trim();
        const isExpanded = estExpandedBidItems.has(bi.hcss_bi_id);
        const biOpacity = bi.manhours ? Math.max(0.12, (bi.manhours || 0) / maxBiMH) : 0;
        const acts = estActivities.filter(a => a.hcss_biditem_id === bi.hcss_bi_id);
        const chevron = isExpanded ? '&#9662;' : '&#9656;';

        let html = `<div class="cc-list-item est-tree-bi" onclick="toggleEstBidItem('${bi.hcss_bi_id}')" style="border-left:3px solid rgba(0,52,126,${biOpacity.toFixed(2)});">
            <span class="cc-list-code">${escHtml(biCode)}</span>
            <span class="cc-list-desc">${escHtml(bi.description || '')}</span>
            <span class="est-tree-chevron">${chevron}</span>
        </div>`;

        if (isExpanded) {
            html += acts.map(act => {
                const actOpacity = act.man_hours ? Math.max(0.12, (act.man_hours || 0) / maxActMH) : 0;
                const isActive = estSelectedActivityId === act.hcss_act_id;
                return `<div class="cc-list-item est-tree-act ${isActive ? 'active' : ''}" onclick="event.stopPropagation();selectEstActivity('${bi.hcss_bi_id}','${act.hcss_act_id}')" style="border-left:3px solid rgba(252,185,0,${actOpacity.toFixed(2)});">
                    <span class="cc-list-code">${escHtml(act.activity_code || '')}</span>
                    <span class="cc-list-desc">${escHtml(act.description || '')}</span>
                </div>`;
            }).join('');

            if (acts.length === 0) {
                html += `<div style="padding:6px 28px;font-size:12px;color:var(--text-tertiary);font-style:italic;">No activities</div>`;
            }
        }

        return html;
    }).join('');
}

function toggleEstBidItem(biId) {
    if (estExpandedBidItems.has(biId)) {
        estExpandedBidItems.delete(biId);
    } else {
        estExpandedBidItems.add(biId);
    }
    const treeEl = document.getElementById('estTree');
    if (treeEl) treeEl.innerHTML = renderEstTree();
}

function selectEstActivity(biId, actId) {
    estSelectedBidItemId = biId;
    estSelectedActivityId = actId;

    // Ensure parent bid item is expanded
    if (!estExpandedBidItems.has(biId)) {
        estExpandedBidItems.add(biId);
    }

    // Re-render tree to update active state
    const treeEl = document.getElementById('estTree');
    if (treeEl) treeEl.innerHTML = renderEstTree();

    // Render detail panel
    const act = estActivities.find(a => a.hcss_act_id === actId);
    const bi = estBiditems.find(b => b.hcss_bi_id === biId);
    const detailEl = document.getElementById('estActivityDetail');
    if (detailEl && act && bi) {
        detailEl.innerHTML = renderEstActivityDetail(act, bi);
    }
}

function renderEstActivityDetail(act, bi) {
    const biCode = (bi.biditem_code || '').trim();
    const res = estResources.filter(r => r.hcss_activity_id === act.hcss_act_id);
    const hasNotes = act.notes && act.notes.trim();

    // Crew counts from resources (sum pieces for labor, count for equipment)
    const crewLabor = res.filter(r => (r.type_cost || '').toUpperCase().trim() === 'L')
        .reduce((sum, r) => sum + (r.pieces || 0), 0);
    const crewEquip = res.filter(r => (r.type_cost || '').toUpperCase().trim() === 'E').length;

    // Production type determines how to interpret production_rate
    const prodType = (act.production_type || '').toUpperCase();
    let mhPerUnit = null;
    let unitsPerHr = null;

    if (prodType === 'MU' && act.production_rate) {
        // Manhours per Unit: rate IS MH/Unit
        mhPerUnit = act.production_rate;
        unitsPerHr = crewLabor ? (crewLabor / mhPerUnit) : null;
    } else if (prodType === 'UH' && act.production_rate) {
        // Units per Hour: rate IS Units/Hr
        unitsPerHr = act.production_rate;
        mhPerUnit = crewLabor ? (crewLabor / unitsPerHr) : null;
    } else if (prodType === 'HU' && act.production_rate) {
        // Hours per Unit (crew-level): rate is crew-hours per unit
        unitsPerHr = 1 / act.production_rate;
        mhPerUnit = crewLabor ? (crewLabor * act.production_rate) : null;
    } else {
        // S (Shifts), empty, or unknown: derive from actuals
        mhPerUnit = (act.man_hours && act.quantity) ? (act.man_hours / act.quantity) : null;
        unitsPerHr = (mhPerUnit && crewLabor) ? (crewLabor / mhPerUnit) : null;
    }

    // Un/Shift: Units/Hr * hours_per_day (universal)
    const unPerShift = (unitsPerHr && act.hours_per_day) ? (unitsPerHr * act.hours_per_day) : null;

    // Crew$/Unit: crew_cost / quantity (NOT direct_total)
    const crewCostPerUnit = (act.crew_cost && act.quantity) ? (act.crew_cost / act.quantity) : null;

    // Shifts: manhours / (crew_labor * hours_per_day) (universal)
    const shifts = (act.man_hours && crewLabor && act.hours_per_day)
        ? (act.man_hours / (crewLabor * act.hours_per_day)) : null;

    // Unit costs ($/unit) for headers
    const biUnitCost = (bi.total_cost && bi.quantity) ? (bi.total_cost / bi.quantity) : null;
    const actUnitCost = (act.direct_total && act.quantity) ? (act.direct_total / act.quantity) : null;

    return `
        <!-- Parent Bid Item Context -->
        <div class="est-bi-context">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <div style="font-size:11px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.04em;">Parent Bid Item</div>
                <div>
                    <span style="font-weight:600;color:var(--wollam-navy);">${escHtml(biCode)}</span>
                    <span style="margin-left:8px;color:var(--text-primary);">${escHtml(bi.description || '')}</span>
                </div>
            </div>
            <div class="est-productivity-grid" style="grid-template-columns:repeat(5,1fr);">
                <div class="est-prod-cell"><span class="est-prod-label">Quantity</span><span class="est-prod-value">${bi.quantity || 0} ${escHtml(bi.units || '')}</span></div>
                <div class="est-prod-cell"><span class="est-prod-label">Cost</span><span class="est-prod-value">$${fmt(bi.total_cost)}</span></div>
                <div class="est-prod-cell"><span class="est-prod-label">Bid</span><span class="est-prod-value">$${fmt(bi.bid_price)}</span></div>
                <div class="est-prod-cell"><span class="est-prod-label">Manhours</span><span class="est-prod-value">${fmt(bi.manhours)}</span></div>
                <div class="est-prod-cell"><span class="est-prod-label">U.Cost</span><span class="est-prod-value" style="color:var(--wollam-navy);">$${biUnitCost != null ? fmt(biUnitCost, 2) : '—'}/${escHtml(bi.units || 'unit')}</span></div>
            </div>
        </div>

        <!-- Activity Detail Card -->
        <div class="card card-animate">
            <div class="card-header">
                <div>
                    <div class="card-title">${escHtml(act.activity_code || '')} — ${escHtml(act.description || '')}</div>
                    <div style="font-size:12px;color:var(--text-tertiary);margin-top:2px;">
                        ${act.quantity || 0} ${escHtml(act.units || '')}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="display:flex;align-items:baseline;gap:12px;justify-content:flex-end;">
                        <div style="font-size:18px;font-weight:700;color:var(--text-primary);">$${fmt(act.direct_total)}</div>
                    </div>
                    <div style="font-size:13px;font-weight:700;color:var(--wollam-navy);margin-top:2px;">U.Cost: $${actUnitCost != null ? fmt(actUnitCost, 2) : '—'}/${escHtml(act.units || 'unit')}</div>
                    <div style="font-size:12px;color:var(--text-tertiary);margin-top:1px;">${fmt(act.man_hours)} MH</div>
                </div>
            </div>
            <div class="card-body">

                <!-- Activity Main: Crew + Production + Crew Hrs / Hrs/Shift / Days -->
                <div class="est-activity-main">
                    <div class="est-field"><span class="est-field-label">Crew</span><span class="est-field-value">${escHtml(act.crew || '—')}</span></div>
                    <div class="est-field"><span class="est-field-label">Prod</span><span class="est-field-value">${escHtml(act.production_type || '—')}</span></div>
                    <div class="est-field"><span class="est-field-label">Rate</span><span class="est-field-value">${act.production_rate != null ? fmtRate(act.production_rate) : '—'}</span></div>
                    <div class="est-field"><span class="est-field-label">Crew Hrs</span><span class="est-field-value est-field-highlight">${act.crew_hours != null ? fmtRate(act.crew_hours) : '—'}</span></div>
                    <div class="est-field"><span class="est-field-label">Hrs/Shift</span><span class="est-field-value">${act.hours_per_day != null ? fmtRate(act.hours_per_day) : '—'}</span></div>
                    <div class="est-field"><span class="est-field-label">Days</span><span class="est-field-value">${act.calculated_duration != null ? fmtRate(act.calculated_duration) : '—'}</span></div>
                </div>

                <!-- Activity Productivity Information — mirrors HeavyBid 2x4 grid -->
                <div class="est-productivity-section">
                    <div class="est-productivity-title">Activity Productivity Information</div>
                    <div class="est-productivity-grid">
                        <div class="est-prod-cell"><span class="est-prod-label">Manhours</span><span class="est-prod-value">${act.man_hours != null ? fmt(act.man_hours, 3) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Units/Hr</span><span class="est-prod-value">${unitsPerHr != null ? fmt(unitsPerHr, 4) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Un/Shift</span><span class="est-prod-value">${unPerShift != null ? fmt(unPerShift, 4) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Crew Labor</span><span class="est-prod-value">${crewLabor ? fmt(crewLabor, 2) : '—'}</span></div>

                        <div class="est-prod-cell"><span class="est-prod-label">MH/Unit</span><span class="est-prod-value">${mhPerUnit != null ? fmt(mhPerUnit, 4) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Crew$/Unit</span><span class="est-prod-value">${crewCostPerUnit != null ? fmt(crewCostPerUnit, 4) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Shifts</span><span class="est-prod-value">${shifts != null ? fmt(shifts, 4) : '—'}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Crew Equip</span><span class="est-prod-value">${crewEquip ? fmt(crewEquip, 2) : '—'}</span></div>
                    </div>
                </div>

                <!-- Cost Breakdown -->
                <div style="margin-bottom:16px;">
                    <div style="font-size:11px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border-default);">Cost Breakdown</div>
                    <div class="est-productivity-grid" style="grid-template-columns:repeat(6,1fr);">
                        <div class="est-prod-cell"><span class="est-prod-label">Labor</span><span class="est-prod-value">$${fmt(act.labor)}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Burden</span><span class="est-prod-value">$${fmt(act.burden)}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Material</span><span class="est-prod-value">$${fmt(act.perm_material)}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Equip OE</span><span class="est-prod-value">$${fmt(act.equip_oe)}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Co Equip</span><span class="est-prod-value">$${fmt(act.company_equip)}</span></div>
                        <div class="est-prod-cell"><span class="est-prod-label">Subs</span><span class="est-prod-value">$${fmt(act.subcontract)}</span></div>
                    </div>
                </div>

                ${hasNotes ? `
                <!-- Estimator Notes -->
                <div style="margin-bottom:16px;padding:12px 16px;background:rgba(245,158,11,0.06);border-left:3px solid rgba(245,158,11,0.5);border-radius:0 8px 8px 0;font-size:13px;line-height:1.5;color:var(--text-primary);white-space:pre-wrap;">${escHtml(act.notes)}</div>
                ` : ''}

                ${res.length > 0 ? `
                <!-- Resources -->
                <div style="margin-top:8px;">
                    <div style="font-size:12px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px;">${res.length} Resources</div>
                    <table style="width:100%;font-size:12px;border-collapse:collapse;">
                        <thead><tr style="border-bottom:1px solid var(--border-default);">
                            <th style="text-align:left;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Code</th>
                            <th style="text-align:left;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Description</th>
                            <th style="text-align:left;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Type</th>
                            <th style="text-align:right;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Qty</th>
                            <th style="text-align:right;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Unit Price</th>
                            <th style="text-align:right;padding:6px 8px;color:var(--text-tertiary);font-weight:500;">Total</th>
                        </tr></thead>
                        <tbody>
                            ${res.map(r => {
                                const tc = (r.type_cost || '').toUpperCase().trim();
                                const color = tc === 'L' ? '#22c55e' : (tc === 'E' || tc === 'C') ? '#eab308' : (tc === 'P' || tc === 'M') ? '#00347E' : tc === 'S' ? '#ef4444' : '#94a3b8';
                                return `<tr style="border-bottom:1px solid rgba(0,0,0,0.04);">
                                <td style="padding:6px 8px;font-weight:500;"><span style="display:inline-flex;align-items:center;gap:6px;"><span style="width:10px;height:10px;border-radius:2px;background:${color};flex-shrink:0;"></span>${escHtml(r.resource_code || '')}</span></td>
                                <td style="padding:6px 8px;">${escHtml(r.description || '')}</td>
                                <td style="padding:6px 8px;">${escHtml(r.type_cost || '')}</td>
                                <td style="padding:6px 8px;text-align:right;">${r.quantity || '—'}</td>
                                <td style="padding:6px 8px;text-align:right;">$${fmtRate(r.unit_price)}</td>
                                <td style="padding:6px 8px;text-align:right;">$${fmt(r.total)}</td>
                            </tr>`;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
                ` : '<div style="font-size:12px;color:var(--text-tertiary);font-style:italic;">No resources</div>'}
            </div>
        </div>
    `;
}

// ── Sync Modal ──

async function openSyncModal() {
    const modal = document.getElementById('syncModal');
    const modalContent = document.getElementById('syncModalContent');
    modal.style.display = 'flex';
    modalContent.innerHTML = '<p>Loading available estimates from HeavyBid...</p>';

    try {
        const available = await api('/estimates/available');
        if (available.length === 0) {
            modalContent.innerHTML = '<p>No estimates available in HeavyBid.</p><button onclick="closeSyncModal()" style="margin-top:16px;padding:8px 20px;background:var(--border);border:none;border-radius:8px;cursor:pointer;">Close</button>';
            return;
        }

        const syncedIds = new Set(available.filter(e => e.already_synced).map(e => e.hcss_est_id));
        const newEstimates = available.filter(e => !e.already_synced);

        modalContent.innerHTML = `
            <h3 style="margin-bottom:16px;font-size:18px;font-weight:600;">Sync Estimates from HeavyBid</h3>
            <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px;">${available.length} estimates available, ${syncedIds.size} already synced</p>
            <div style="max-height:400px;overflow-y:auto;">
                ${available.map(e => `
                    <label style="display:flex;align-items:center;gap:10px;padding:10px;border-bottom:1px solid var(--border);cursor:${e.already_synced ? 'default' : 'pointer'};">
                        <input type="checkbox" value="${e.hcss_est_id}" ${e.already_synced ? 'checked disabled' : ''} class="sync-checkbox">
                        <div style="flex:1;">
                            <div style="font-weight:600;font-size:14px;">${escHtml(e.code || '?')}</div>
                            <div style="font-size:12px;color:var(--text-secondary);">${escHtml(e.name || '')} · $${fmt(e.bid_total)} · ${fmt(e.total_manhours)} MH</div>
                        </div>
                        ${e.already_synced ? '<span style="font-size:11px;color:var(--text-tertiary);">Synced</span>' : '<span style="font-size:11px;color:var(--wollam-blue);">New</span>'}
                    </label>
                `).join('')}
            </div>
            <div style="display:flex;gap:12px;margin-top:20px;justify-content:flex-end;">
                <button onclick="closeSyncModal()" style="padding:8px 20px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;cursor:pointer;">Cancel</button>
                <button id="syncBtn" onclick="runSync()" style="padding:8px 20px;background:var(--wollam-blue);color:white;border:none;border-radius:8px;cursor:pointer;font-weight:500;">Sync Selected</button>
            </div>
        `;
    } catch (e) {
        modalContent.innerHTML = `<p>Error: ${escHtml(e.message)}</p><button onclick="closeSyncModal()" style="margin-top:16px;padding:8px 20px;background:var(--border);border:none;border-radius:8px;cursor:pointer;">Close</button>`;
    }
}

function closeSyncModal() {
    document.getElementById('syncModal').style.display = 'none';
}

async function runSync() {
    const checkboxes = document.querySelectorAll('.sync-checkbox:checked:not(:disabled)');
    const ids = Array.from(checkboxes).map(cb => cb.value);
    if (ids.length === 0) {
        alert('Select at least one estimate to sync.');
        return;
    }

    const btn = document.getElementById('syncBtn');
    btn.textContent = 'Syncing...';
    btn.disabled = true;

    try {
        const result = await api('/estimates/sync', {
            method: 'POST',
            body: JSON.stringify({ estimate_ids: ids }),
        });
        closeSyncModal();
        loadEstimateList();
    } catch (e) {
        btn.textContent = 'Error — retry';
        btn.disabled = false;
    }
}

// ══════════════════════════════════════════════════════════════
// ── Bidding Platform ──
// ══════════════════════════════════════════════════════════════

const GROUP_COLORS = [
    '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
    '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
];

const WORK_TYPE_LABELS = { self_perform: 'SP', subcontract: 'SUB', undecided: '—' };
const WORK_TYPE_COLORS = { self_perform: 'var(--wollam-navy)', subcontract: '#8B5CF6', undecided: 'var(--text-tertiary)' };
const WORK_TYPE_BORDER = { self_perform: '3px solid var(--wollam-navy)', subcontract: '3px solid #8B5CF6' };

function bidStatusBadge(status) {
    const map = {
        active: '<span class="badge badge-active">Active</span>',
        submitted: '<span class="badge badge-in-progress">Submitted</span>',
        'no-bid': '<span class="badge badge-not-started">No-Bid</span>',
        awarded: '<span class="badge badge-complete">Awarded</span>',
    };
    return map[status] || `<span class="badge badge-not-started">${escHtml(status || 'Unknown')}</span>`;
}

function bidDueCountdown(bidDate) {
    if (!bidDate) return '<span style="color:var(--text-tertiary)">No date</span>';
    const due = new Date(bidDate + 'T23:59:59');
    const now = new Date();
    const diff = Math.ceil((due - now) / (1000 * 60 * 60 * 24));
    if (diff < 0) return '<span style="color:var(--danger-red);font-weight:600;">OVERDUE</span>';
    if (diff === 0) return '<span style="color:var(--danger-red);font-weight:600;">DUE TODAY</span>';
    if (diff <= 3) return `<span style="color:var(--status-warning);font-weight:600;">Due in ${diff}d</span>`;
    return `<span style="color:var(--text-secondary);">Due in ${diff}d</span>`;
}

function docCategoryBadge(cat) {
    const colors = {
        spec: '--status-info', drawing: '--wollam-navy-light', contract: '--status-danger',
        bid_schedule: '--wollam-gold-dark', rfi_clarification: '--status-warning',
        addendum_package: '--confidence-moderate', bond_form: '--text-secondary',
        insurance: '--success-green', general: '--text-tertiary',
    };
    const color = colors[cat] || '--text-tertiary';
    const label = (cat || 'general').replace(/_/g, ' ');
    return `<span class="badge" style="background:var(${color});color:#fff;font-size:10px;text-transform:uppercase;">${label}</span>`;
}

// ── Bid Board ──

async function loadBidBoard() {
    const content = document.getElementById('content');
    document.getElementById('pageTitle').textContent = 'Bidding';
    document.getElementById('pageSubtitle').textContent = '';
    content.innerHTML = '<div class="empty-state"><p>Loading bids...</p></div>';

    try {
        const bids = await api('/bidding/bids');
        renderBidBoard(bids);
    } catch (err) {
        content.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${escHtml(err.message)}</p></div>`;
    }
}

function renderBidBoard(bids) {
    const content = document.getElementById('content');

    let filtered = bids;
    if (state.biddingStatusFilter !== 'all') {
        filtered = filtered.filter(b => b.status === state.biddingStatusFilter);
    }

    // Sort by due date (soonest first), nulls last
    filtered.sort((a, b) => {
        if (!a.bid_date && !b.bid_date) return 0;
        if (!a.bid_date) return 1;
        if (!b.bid_date) return -1;
        return a.bid_date.localeCompare(b.bid_date);
    });

    const activeCount = bids.filter(b => b.status === 'active').length;
    const submittedCount = bids.filter(b => b.status === 'submitted').length;
    const awardedCount = bids.filter(b => b.status === 'awarded').length;

    content.innerHTML = `
        <!-- KPI Cards -->
        <div class="kpi-grid">
            <div class="kpi-card card-animate"><div class="kpi-label">Total Bids</div><div class="kpi-value">${bids.length}</div></div>
            <div class="kpi-card card-animate"><div class="kpi-label">Active</div><div class="kpi-value">${activeCount}</div></div>
            <div class="kpi-card card-animate"><div class="kpi-label">Submitted</div><div class="kpi-value">${submittedCount}</div></div>
            <div class="kpi-card card-animate"><div class="kpi-label">Awarded</div><div class="kpi-value">${awardedCount}</div></div>
        </div>

        <!-- Toolbar -->
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
            <div class="filter-tabs">
                <button class="filter-tab ${state.biddingStatusFilter === 'all' ? 'active' : ''}" onclick="setBidFilter('all')">All (${bids.length})</button>
                <button class="filter-tab ${state.biddingStatusFilter === 'active' ? 'active' : ''}" onclick="setBidFilter('active')">Active (${activeCount})</button>
                <button class="filter-tab ${state.biddingStatusFilter === 'submitted' ? 'active' : ''}" onclick="setBidFilter('submitted')">Submitted (${submittedCount})</button>
                <button class="filter-tab ${state.biddingStatusFilter === 'awarded' ? 'active' : ''}" onclick="setBidFilter('awarded')">Awarded (${awardedCount})</button>
            </div>
            <div style="flex:1;"></div>
            <button class="btn btn-primary" onclick="showNewBidModal()">+ New Bid</button>
        </div>

        <!-- Bid Table -->
        ${filtered.length === 0 ? '<div class="empty-state"><p>No bids found. Create your first bid project.</p></div>' : `
        <div class="card" style="padding:0;overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                <thead>
                    <tr style="background:var(--bg-hover);border-bottom:2px solid var(--border-default);">
                        <th style="padding:10px 12px;text-align:left;font-weight:600;color:var(--text-secondary);">Bid Name</th>
                        <th style="padding:10px 12px;text-align:left;font-weight:600;color:var(--text-secondary);">Owner</th>
                        <th style="padding:10px 12px;text-align:left;font-weight:600;color:var(--text-secondary);">Location</th>
                        <th style="padding:10px 12px;text-align:left;font-weight:600;color:var(--text-secondary);">Due Date</th>
                        <th style="padding:10px 12px;text-align:center;font-weight:600;color:var(--text-secondary);">Status</th>
                        <th style="padding:10px 12px;text-align:center;font-weight:600;color:var(--text-secondary);">Docs</th>
                        <th style="padding:10px 12px;text-align:center;font-weight:600;color:var(--text-secondary);">SOV Items</th>
                    </tr>
                </thead>
                <tbody>
                    ${filtered.map(b => `
                    <tr style="border-bottom:1px solid var(--border-default);cursor:pointer;" onclick="navigate('bidding', ${b.id})" onmouseover="this.style.background='var(--bg-hover)'" onmouseout="this.style.background=''">
                        <td style="padding:10px 12px;font-weight:500;">${escHtml(b.bid_name)}</td>
                        <td style="padding:10px 12px;color:var(--text-secondary);">${escHtml(b.owner || '—')}</td>
                        <td style="padding:10px 12px;color:var(--text-secondary);">${escHtml(b.location || '—')}</td>
                        <td style="padding:10px 12px;">${bidDueCountdown(b.bid_date)}</td>
                        <td style="padding:10px 12px;text-align:center;">${bidStatusBadge(b.status)}</td>
                        <td style="padding:10px 12px;text-align:center;color:var(--text-secondary);">${b.doc_count || 0}</td>
                        <td style="padding:10px 12px;text-align:center;color:var(--text-secondary);">${b.sov_count || 0}</td>
                    </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>`}

        <!-- New Bid Modal -->
        <div id="newBidModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:1000;display:none;align-items:center;justify-content:center;">
            <div class="card" style="width:520px;max-height:80vh;overflow-y:auto;padding:24px;">
                <h2 style="font-size:18px;font-weight:600;margin:0 0 16px;">New Bid Project</h2>
                <div id="newBidForm"></div>
            </div>
        </div>
    `;
}

function setBidFilter(f) {
    state.biddingStatusFilter = f;
    loadBidBoard();
}

function showNewBidModal() {
    const modal = document.getElementById('newBidModal');
    modal.style.display = 'flex';
    state._newBidFiles = [];
    state._selectedFolder = null;
    document.getElementById('newBidForm').innerHTML = `
        <div style="display:flex;flex-direction:column;gap:12px;">
            <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Bid Name *</label>
                <input type="text" id="nb_name" class="search-input" style="width:100%;" placeholder="e.g. Bonanza Power Plant Piping"></div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Estimate Number</label>
                    <input type="text" id="nb_number" class="search-input" style="width:100%;" placeholder="e.g. 2574"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Owner / GC</label>
                    <input type="text" id="nb_owner" class="search-input" style="width:100%;" placeholder="Who issued the RFP?"></div>
            </div>

            <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Bid Due Date</label>
                <input type="date" id="nb_date" class="search-input" style="width:200px;"></div>

            <!-- Dropbox Folder Picker -->
            <div>
                <label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Dropbox Estimating Folder</label>
                <div id="nb_folder_selected" style="margin-bottom:6px;"></div>
                <div style="display:flex;gap:8px;align-items:center;">
                    <button type="button" class="btn btn-sm" onclick="openFolderBrowser('newBid')">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-2px;margin-right:4px;"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                        Browse Folders
                    </button>
                    <span style="font-size:11px;color:var(--text-tertiary);">or</span>
                    <input type="text" id="nb_folder_path" class="search-input" style="flex:1;font-size:12px;" placeholder="Paste folder path" onchange="manualFolderPath(this.value)">
                </div>
            </div>

            <!-- Manual file upload -->
            <details>
                <summary style="font-size:12px;color:var(--text-tertiary);cursor:pointer;margin-bottom:8px;">Upload RFP files manually</summary>
                <div id="nbDropZone" style="border:2px dashed var(--border-strong);border-radius:8px;padding:24px;text-align:center;cursor:pointer;background:var(--bg-hover);transition:border-color 0.15s;"
                     onclick="document.getElementById('nbFileInput').click()"
                     ondragover="event.preventDefault();this.style.borderColor='var(--wollam-navy)';"
                     ondragleave="this.style.borderColor='var(--border-strong)';"
                     ondrop="handleNewBidDrop(event)">
                    <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:6px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    <p style="margin:0;font-size:13px;color:var(--text-secondary);">Drag & drop RFP files here, or click to browse</p>
                    <p style="margin:4px 0 0;font-size:11px;color:var(--text-tertiary);">PDF, Excel, Word, CSV, TXT</p>
                </div>
                <input type="file" id="nbFileInput" style="display:none;" multiple accept=".pdf,.xlsx,.xls,.csv,.txt,.docx,.doc" onchange="handleNewBidFiles(this.files)">
                <div id="nbFileList" style="margin-top:8px;"></div>
            </details>

            <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:4px;">
                <button class="btn btn-sm" onclick="closeNewBidModal()">Cancel</button>
                <button class="btn btn-primary btn-sm" id="nbCreateBtn" onclick="createBid()">Create Bid</button>
            </div>
        </div>
    `;
}

function handleNewBidDrop(event) {
    event.preventDefault();
    document.getElementById('nbDropZone').style.borderColor = 'var(--border-strong)';
    handleNewBidFiles(event.dataTransfer.files);
}

function handleNewBidFiles(fileList) {
    for (const f of fileList) {
        state._newBidFiles.push(f);
    }
    renderNewBidFileList();
}

function removeNewBidFile(idx) {
    state._newBidFiles.splice(idx, 1);
    renderNewBidFileList();
}

function renderNewBidFileList() {
    const el = document.getElementById('nbFileList');
    if (!state._newBidFiles.length) { el.innerHTML = ''; return; }
    el.innerHTML = state._newBidFiles.map((f, i) => `
        <div style="display:flex;align-items:center;gap:6px;padding:4px 0;font-size:12px;">
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span style="flex:1;color:var(--text-primary);">${escHtml(f.name)}</span>
            <span style="color:var(--text-tertiary);">${(f.size / 1024).toFixed(0)} KB</span>
            <button onclick="removeNewBidFile(${i})" style="background:none;border:none;cursor:pointer;color:var(--danger-red);font-size:11px;padding:0 2px;">x</button>
        </div>
    `).join('');
}

// ── Native Folder Picker (server-side tkinter dialog) ──

let _folderPickerContext = null; // 'newBid' or bidId (number)

async function openFolderBrowser(context) {
    _folderPickerContext = context;

    try {
        const res = await fetch('/api/bidding/pick-folder', { method: 'POST' });
        const data = await res.json();

        if (!data.picked) return; // User cancelled or error

        if (_folderPickerContext === 'newBid') {
            state._selectedFolder = data.path;
            const selected = document.getElementById('nb_folder_selected');
            selected.innerHTML = `<div style="display:flex;align-items:center;gap:6px;padding:6px 10px;background:var(--bg-hover);border-radius:6px;border:1px solid var(--border-default);">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success-green)" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                <span style="font-size:13px;color:var(--text-primary);flex:1;">${escHtml(data.name)}</span>
                <button onclick="clearBidFolder()" style="background:none;border:none;cursor:pointer;color:var(--text-tertiary);font-size:12px;padding:0 2px;">&#x2715;</button>
            </div>`;
            // Clear the paste input if it exists
            const pathInput = document.getElementById('nb_folder_path');
            if (pathInput) pathInput.value = '';

            // Auto-fill bid name if empty
            const nameEl = document.getElementById('nb_name');
            if (nameEl && !nameEl.value.trim()) {
                const projectName = data.name.replace(/^\d{2}-\d{2}-\d{4}\s*/, '');
                nameEl.value = projectName;
            }
        } else if (typeof _folderPickerContext === 'number') {
            selectDetailFolder(_folderPickerContext, data.path);
        }
    } catch (err) {
        console.warn('Folder picker error:', err);
    }
}

function clearBidFolder() {
    state._selectedFolder = null;
    const selected = document.getElementById('nb_folder_selected');
    if (selected) selected.innerHTML = '';
    const pathInput = document.getElementById('nb_folder_path');
    if (pathInput) pathInput.value = '';
}

function manualFolderPath(value) {
    const path = value.trim().replace(/^["']+|["']+$/g, '');
    if (!path) { clearBidFolder(); return; }
    state._selectedFolder = path;
    const name = path.split(/[/\\]/).filter(Boolean).pop() || path;
    const selected = document.getElementById('nb_folder_selected');
    selected.innerHTML = `<div style="display:flex;align-items:center;gap:6px;padding:6px 10px;background:var(--bg-hover);border-radius:6px;border:1px solid var(--border-default);">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success-green)" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
        <span style="font-size:13px;color:var(--text-primary);flex:1;">${escHtml(name)}</span>
        <button onclick="clearBidFolder()" style="background:none;border:none;cursor:pointer;color:var(--text-tertiary);font-size:12px;padding:0 2px;">&#x2715;</button>
    </div>`;

    // Auto-fill bid name if empty
    const nameEl = document.getElementById('nb_name');
    if (nameEl && !nameEl.value.trim()) {
        const projectName = name.replace(/^\d{2}-\d{2}-\d{4}\s*/, '');
        nameEl.value = projectName;
    }
}

function closeNewBidModal() {
    document.getElementById('newBidModal').style.display = 'none';
    state._newBidFiles = [];
}

async function streamSync(bidId) {
    return new Promise((resolve, reject) => {
        const detail = document.getElementById('step_sync_detail');
        const evtSource = new EventSource(`/api/bidding/bids/${bidId}/sync-stream`);

        evtSource.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'progress') {
                    if (detail) detail.textContent = `${msg.current} of ${msg.total}: ${msg.filename}`;
                } else if (msg.type === 'done') {
                    evtSource.close();
                    resolve(msg.result);
                } else if (msg.type === 'error') {
                    evtSource.close();
                    reject(new Error(msg.message));
                }
            } catch (e) {
                // ignore parse errors
            }
        };

        evtSource.onerror = () => {
            evtSource.close();
            reject(new Error('Sync stream connection lost'));
        };
    });
}

async function createBid() {
    const bidNumber = document.getElementById('nb_number').value.trim();
    const name = document.getElementById('nb_name').value.trim();
    if (!name) { alert('Bid name is required'); return; }

    const hasFolder = !!state._selectedFolder;
    const fileCount = state._newBidFiles.length;

    // Replace form with progress panel
    const form = document.getElementById('newBidForm');
    form.innerHTML = `
        <div style="min-width:360px;">
            <h3 style="margin:0 0 16px;font-size:15px;color:var(--text-primary);">Setting up ${escHtml(name)}</h3>
            <div id="progressSteps" style="display:flex;flex-direction:column;gap:10px;"></div>
        </div>
    `;

    const steps = document.getElementById('progressSteps');
    function addStep(id, label) {
        steps.innerHTML += `
            <div id="step_${id}" style="display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:8px;background:var(--bg-hover);transition:all 0.3s;">
                <div id="step_${id}_icon" style="width:20px;height:20px;display:flex;align-items:center;justify-content:center;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2" style="animation:spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                </div>
                <div style="flex:1;">
                    <div style="font-size:13px;font-weight:500;color:var(--text-primary);">${label}</div>
                    <div id="step_${id}_detail" style="font-size:11px;color:var(--text-tertiary);margin-top:2px;"></div>
                </div>
            </div>
        `;
    }
    function completeStep(id, detail) {
        const icon = document.getElementById(`step_${id}_icon`);
        if (icon) icon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--success-green)" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`;
        const det = document.getElementById(`step_${id}_detail`);
        if (det && detail) det.textContent = detail;
    }
    function failStep(id, detail) {
        const icon = document.getElementById(`step_${id}_icon`);
        if (icon) icon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--danger-red)" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
        const det = document.getElementById(`step_${id}_detail`);
        if (det && detail) det.textContent = detail;
    }

    try {
        // Step 1: Create bid
        addStep('create', 'Creating bid');
        const bid = await api('/bidding/bids', {
            method: 'POST',
            body: JSON.stringify({
                bid_name: name,
                bid_number: bidNumber || null,
                owner: document.getElementById('nb_owner')?.value.trim() || null,
                bid_date: document.getElementById('nb_date')?.value || null,
                dropbox_folder_path: state._selectedFolder || null,
            }),
        });
        completeStep('create', `Bid #${bid.id} created`);

        // Step 2: Sync documents from Dropbox (streaming progress)
        if (bid.dropbox_folder_path) {
            addStep('sync', 'Syncing documents from Dropbox');
            try {
                const syncResult = await streamSync(bid.id);
                const parts = [];
                if (syncResult.new) parts.push(`${syncResult.new} new`);
                if (syncResult.updated) parts.push(`${syncResult.updated} updated`);
                if (syncResult.unchanged) parts.push(`${syncResult.unchanged} unchanged`);
                if (syncResult.errors?.length) parts.push(`${syncResult.errors.length} errors`);
                completeStep('sync', parts.join(', ') || 'No documents found');
            } catch (e) {
                failStep('sync', e.message || 'Sync failed');
            }
        }

        // Step 3: Upload manual files
        if (fileCount) {
            addStep('upload', `Uploading ${fileCount} file${fileCount > 1 ? 's' : ''}`);
            for (let i = 0; i < state._newBidFiles.length; i++) {
                const det = document.getElementById('step_upload_detail');
                if (det) det.textContent = `${i + 1} of ${fileCount}: ${state._newBidFiles[i].name}`;
                const formData = new FormData();
                formData.append('file', state._newBidFiles[i]);
                formData.append('addendum_number', '0');
                formData.append('doc_category', 'general');
                formData.append('date_received', new Date().toISOString().split('T')[0]);
                await fetch(`/api/bidding/bids/${bid.id}/documents`, { method: 'POST', body: formData });
            }
            completeStep('upload', `${fileCount} file${fileCount > 1 ? 's' : ''} uploaded`);
        }

        // Step 4: AI analysis
        if (bid.dropbox_folder_path || fileCount) {
            addStep('ai', 'AI analyzing documents for project details');
            try {
                const analysis = await api(`/bidding/bids/${bid.id}/analyze-overview`, { method: 'POST' });
                if (analysis.analyzed && analysis.fields_populated?.length) {
                    completeStep('ai', `Populated: ${analysis.fields_populated.join(', ')}`);
                } else {
                    completeStep('ai', analysis.message || 'No fields could be extracted');
                }
            } catch (e) {
                failStep('ai', e.message || 'Analysis failed');
            }
        }

        // Done — navigate after a brief pause so user can see results
        addStep('done', 'Ready');
        completeStep('done', 'Opening bid...');
        setTimeout(() => {
            closeNewBidModal();
            navigate('bidding', bid.id);
        }, 1200);

    } catch (err) {
        failStep('create', err.message);
        steps.innerHTML += `
            <div style="margin-top:12px;display:flex;gap:8px;justify-content:flex-end;">
                <button class="btn btn-sm" onclick="closeNewBidModal()">Close</button>
            </div>
        `;
    }
}

// ── Bid Detail ──

async function loadBidDetail(bidId) {
    const content = document.getElementById('content');
    document.getElementById('pageTitle').textContent = 'Bid Detail';
    document.getElementById('pageSubtitle').textContent = 'Loading...';
    content.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';

    try {
        const bid = await api(`/bidding/bids/${bidId}`);
        document.getElementById('pageTitle').textContent = bid.bid_name;
        document.getElementById('pageSubtitle').textContent = [bid.owner, bid.location].filter(Boolean).join(' — ') || 'Bid Project';
        renderBidDetail(bid);
        loadBidCostKpi(bid.id);
    } catch (err) {
        content.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${escHtml(err.message)}</p></div>`;
    }
}

async function renderBidDetail(bid) {
    const content = document.getElementById('content');
    const tab = state.biddingTab;

    // Load setup progress in background
    let setupHtml = '';
    try {
        const sp = await api(`/bidding/bids/${bid.id}/setup-progress`).catch(() => null);
        if (sp) setupHtml = renderSetupProgress(sp);
    } catch (e) {}

    content.innerHTML = `
        <div style="margin-bottom:16px;display:flex;align-items:center;gap:8px;">
            <button class="btn btn-sm" onclick="navigate('bidding')">
                &larr; Back to Bid Board
            </button>
            <div style="flex:1;"></div>
            <button class="btn btn-primary btn-sm" id="globalRefreshBtn" onclick="refreshIntelligence(${bid.id})" style="display:flex;align-items:center;gap:6px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
                Refresh Intelligence
            </button>
        </div>

        <div id="refreshProgress"></div>
        <div id="refreshBanner"></div>

        ${setupHtml}

        <!-- Summary bar -->
        <div class="kpi-grid" style="margin-bottom:16px;">
            <div class="kpi-card card-animate"><div class="kpi-label">Status</div><div class="kpi-value" style="font-size:16px;">${bidStatusBadge(bid.status)}</div></div>
            <div class="kpi-card card-animate"><div class="kpi-label">Due Date</div><div class="kpi-value" style="font-size:16px;">${bidDueCountdown(bid.bid_date)}</div></div>
            <div class="kpi-card card-animate"><div class="kpi-label">Documents</div><div class="kpi-value">${bid.doc_count || 0}</div></div>
            <div class="kpi-card card-animate"><div class="kpi-label">SOV Items</div><div class="kpi-value">${bid.sov_count || 0}</div></div>
            <div class="kpi-card card-animate" id="costKpi"><div class="kpi-label">API Cost</div><div class="kpi-value" style="font-size:16px;" id="costKpiValue">—</div></div>
        </div>

        <!-- Tabs -->
        <div class="filter-tabs" style="margin-bottom:16px;">
            <button class="filter-tab ${tab === 'overview' ? 'active' : ''}" onclick="switchBidTab('overview', ${bid.id})">Overview</button>
            <button class="filter-tab ${tab === 'sov' ? 'active' : ''}" onclick="switchBidTab('sov', ${bid.id})">Schedule of Values</button>
            <button class="filter-tab ${tab === 'documents' ? 'active' : ''}" onclick="switchBidTab('documents', ${bid.id})">Documents</button>
            <button class="filter-tab ${tab === 'intelligence' ? 'active' : ''}" onclick="switchBidTab('intelligence', ${bid.id})">Intelligence</button>
            <button class="filter-tab ${tab === 'procurement' ? 'active' : ''}" onclick="switchBidTab('procurement', ${bid.id})">Procurement</button>
        </div>

        <div id="bidTabContent"></div>
    `;

    if (tab === 'overview') renderBidOverview(bid);
    else if (tab === 'sov') renderBidSOV(bid.id);
    else if (tab === 'documents') renderBidDocuments(bid);
    else if (tab === 'intelligence') renderBidIntelligence(bid);
    else if (tab === 'procurement') renderBidProcurement(bid);
}

function renderSetupProgress(sp) {
    const steps = [
        { key: 'documents_synced', label: 'Documents synced', count: sp.counts.documents },
        { key: 'sov_defined', label: 'SOV defined', count: sp.counts.sov_items },
        { key: 'scope_designated', label: 'Scope designated', count: sp.counts.scoped_items },
        { key: 'intelligence_analyzed', label: 'Intelligence analyzed', count: sp.counts.agent_reports },
        { key: 'intelligence_mapped', label: 'Intelligence mapped', count: sp.counts.mapped_items },
    ];
    const completed = steps.filter(s => sp[s.key]).length;
    if (completed >= 5) return ''; // All done, no need to show

    return `
    <div style="display:flex;gap:4px;margin-bottom:12px;align-items:center;">
        ${steps.map(s => {
            const done = sp[s.key];
            return `<div style="display:flex;align-items:center;gap:4px;padding:4px 8px;border-radius:var(--radius-sm);font-size:11px;background:${done ? 'rgba(22,163,74,0.08)' : 'var(--bg-hover)'};color:${done ? 'var(--success-green)' : 'var(--text-tertiary)'};">
                <span>${done ? '&#10003;' : '&#9744;'}</span>
                <span>${s.label}</span>
                ${s.count > 0 ? `<span style="font-weight:600;">(${s.count})</span>` : ''}
            </div>`;
        }).join('<span style="color:var(--border-default);">&#8594;</span>')}
    </div>`;
}

function switchBidTab(tab, bidId) {
    state.biddingTab = tab;
    loadBidDetail(bidId);
}

async function loadBidCostKpi(bidId) {
    try {
        const data = await api(`/bidding/bids/${bidId}/cost-summary`);
        const el = document.getElementById('costKpiValue');
        if (!el) return;
        const cost = data.totals.combined_cost_est_usd;
        const tokens = data.totals.combined_tokens;
        if (cost > 0) {
            el.textContent = `$${cost.toFixed(2)}`;
            el.title = `${(tokens / 1000).toFixed(0)}K tokens total`;
            el.style.cursor = 'pointer';
            el.onclick = () => showCostDetail(bidId);
        } else {
            el.textContent = '$0.00';
        }
    } catch {
        // Cost tracking table may not exist yet
    }
}

async function showCostDetail(bidId) {
    const data = await api(`/bidding/bids/${bidId}/cost-summary`);
    const t = data.totals;

    let breakdown = '';
    // Agent costs
    if (data.agent_reports.length) {
        breakdown += '<div style="margin-bottom:8px;font-size:11px;font-weight:600;color:var(--text-secondary);">AGENT ANALYSIS</div>';
        data.agent_reports.forEach(a => {
            const est = (a.tokens_used * 0.8 * 1.0 / 1e6) + (a.tokens_used * 0.2 * 5.0 / 1e6);
            breakdown += `<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0;">
                <span>${escHtml(a.agent_name.replace(/_/g, ' '))}</span>
                <span style="color:var(--text-tertiary);">${(a.tokens_used/1000).toFixed(0)}K tok — $${est.toFixed(3)}</span>
            </div>`;
        });
    }

    // Logged usage
    if (data.usage_log.length) {
        breakdown += '<div style="margin:10px 0 8px;font-size:11px;font-weight:600;color:var(--text-secondary);">OTHER API CALLS</div>';
        data.usage_log.forEach(u => {
            breakdown += `<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0;">
                <span>${escHtml(u.operation)}</span>
                <span style="color:var(--text-tertiary);">${u.call_count} calls, ${(u.total_tokens/1000).toFixed(0)}K tok — $${u.cost_usd.toFixed(3)}</span>
            </div>`;
        });
    }

    // Show as a modal/overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.4);z-index:1000;display:flex;align-items:center;justify-content:center;';
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    overlay.innerHTML = `
        <div style="background:white;border-radius:var(--radius-md);padding:24px;max-width:500px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:var(--shadow-lg);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h3 style="margin:0;font-size:16px;font-weight:600;">API Cost Breakdown</h3>
                <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;font-size:20px;cursor:pointer;color:var(--text-tertiary);">&times;</button>
            </div>
            ${breakdown || '<p style="font-size:13px;color:var(--text-tertiary);">No API usage recorded yet.</p>'}
            <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-default);display:flex;justify-content:space-between;font-size:14px;font-weight:600;">
                <span>Total Estimated Cost</span>
                <span style="color:var(--wollam-navy);">$${t.combined_cost_est_usd.toFixed(2)}</span>
            </div>
            <div style="font-size:11px;color:var(--text-tertiary);margin-top:4px;">
                ${(t.combined_tokens/1000).toFixed(0)}K tokens total (Haiku: $1/M input, $5/M output)
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
}

// ── Overview Tab ──

function renderBidOverview(bid) {
    const tc = document.getElementById('bidTabContent');
    tc.innerHTML = `
        <div class="card" style="padding:20px;">
            <h3 style="font-size:15px;font-weight:600;margin:0 0 16px;">Bid Information</h3>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Bid Name</label>
                    <input type="text" id="be_name" class="search-input" style="width:100%;" value="${escAttr(bid.bid_name || '')}"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Bid Number</label>
                    <input type="text" id="be_number" class="search-input" style="width:100%;" value="${escAttr(bid.bid_number || '')}"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Owner</label>
                    <input type="text" id="be_owner" class="search-input" style="width:100%;" value="${escAttr(bid.owner || '')}"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">General Contractor</label>
                    <input type="text" id="be_gc" class="search-input" style="width:100%;" value="${escAttr(bid.general_contractor || '')}"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Bid Due Date</label>
                    <input type="date" id="be_date" class="search-input" style="width:100%;" value="${escAttr(bid.bid_date || '')}"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Bid Due Time</label>
                    <input type="time" id="be_time" class="search-input" style="width:100%;" value="${escAttr(bid.bid_due_time || '')}"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Location</label>
                    <input type="text" id="be_location" class="search-input" style="width:100%;" value="${escAttr(bid.location || '')}"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Project Type</label>
                    <input type="text" id="be_type" class="search-input" style="width:100%;" value="${escAttr(bid.project_type || '')}"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Contact Name</label>
                    <input type="text" id="be_contact" class="search-input" style="width:100%;" value="${escAttr(bid.contact_name || '')}"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Contact Email</label>
                    <input type="email" id="be_email" class="search-input" style="width:100%;" value="${escAttr(bid.contact_email || '')}"></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Status</label>
                    <select id="be_status" class="search-input" style="width:100%;">
                        <option value="active" ${bid.status === 'active' ? 'selected' : ''}>Active</option>
                        <option value="submitted" ${bid.status === 'submitted' ? 'selected' : ''}>Submitted</option>
                        <option value="no-bid" ${bid.status === 'no-bid' ? 'selected' : ''}>No-Bid</option>
                        <option value="awarded" ${bid.status === 'awarded' ? 'selected' : ''}>Awarded</option>
                    </select></div>
                <div><label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Estimated Value</label>
                    <input type="number" id="be_value" class="search-input" style="width:100%;" value="${bid.estimated_value || ''}"></div>
            </div>
            <div style="margin-top:12px;">
                <label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Description</label>
                <textarea id="be_desc" class="search-input" rows="3" style="width:100%;resize:vertical;">${escHtml(bid.description || '')}</textarea>
            </div>
            <div style="margin-top:12px;">
                <label style="font-size:12px;font-weight:500;color:var(--text-secondary);display:block;margin-bottom:4px;">Notes</label>
                <textarea id="be_notes" class="search-input" rows="2" style="width:100%;resize:vertical;">${escHtml(bid.notes || '')}</textarea>
            </div>

            <!-- Dropbox Folder Link -->
            <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border-default);">
                <label style="font-size:12px;font-weight:600;color:var(--text-secondary);display:block;margin-bottom:8px;">Dropbox Estimating Folder</label>
                ${bid.dropbox_folder_path
                    ? `<div style="display:flex;align-items:center;gap:8px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--success-green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                        <span style="font-size:13px;color:var(--text-primary);" title="${escAttr(bid.dropbox_folder_path)}">${escHtml(bid.dropbox_folder_path.split('\\\\').slice(-2).join('/'))}</span>
                        <span style="font-size:11px;color:var(--text-tertiary);">${bid.sync_status === 'complete' ? 'Linked' : bid.sync_status || 'never'}</span>
                    </div>`
                    : `<div id="linkFolderContainer">
                        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                            <button class="btn btn-sm" onclick="linkBidFolder(${bid.id})">Browse Folders</button>
                            <span style="font-size:11px;color:var(--text-tertiary);">or</span>
                            <input type="text" id="detail_folder_path" class="search-input" style="flex:1;min-width:200px;font-size:12px;" placeholder="Paste folder path" onchange="linkBidFolderByPath(${bid.id}, this.value)">
                        </div>
                    </div>`
                }
            </div>

            <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px;">
                <button class="btn btn-sm" style="color:var(--danger-red);" onclick="deleteBid(${bid.id})">Delete Bid</button>
                <button class="btn btn-primary btn-sm" onclick="saveBidOverview(${bid.id})">Save Changes</button>
            </div>
        </div>
    `;
}

function escAttr(s) {
    return String(s).replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

async function saveBidOverview(bidId) {
    try {
        await api(`/bidding/bids/${bidId}`, {
            method: 'PUT',
            body: JSON.stringify({
                bid_name: document.getElementById('be_name').value.trim(),
                bid_number: document.getElementById('be_number').value.trim() || null,
                owner: document.getElementById('be_owner').value.trim() || null,
                general_contractor: document.getElementById('be_gc').value.trim() || null,
                bid_date: document.getElementById('be_date').value || null,
                bid_due_time: document.getElementById('be_time').value || null,
                location: document.getElementById('be_location').value.trim() || null,
                project_type: document.getElementById('be_type').value.trim() || null,
                contact_name: document.getElementById('be_contact').value.trim() || null,
                contact_email: document.getElementById('be_email').value.trim() || null,
                status: document.getElementById('be_status').value,
                estimated_value: parseFloat(document.getElementById('be_value').value) || null,
                description: document.getElementById('be_desc').value.trim() || null,
                notes: document.getElementById('be_notes').value.trim() || null,
            }),
        });
        loadBidDetail(bidId);
    } catch (err) {
        alert('Error saving: ' + err.message);
    }
}

async function deleteBid(bidId) {
    if (!confirm('Delete this bid and all its documents and SOV items?')) return;
    try {
        await api(`/bidding/bids/${bidId}`, { method: 'DELETE' });
        navigate('bidding');
    } catch (err) {
        alert('Error deleting: ' + err.message);
    }
}

// ── SOV Tab ──

async function renderBidSOV(bidId) {
    const tc = document.getElementById('bidTabContent');
    tc.innerHTML = '<div class="empty-state"><p>Loading schedule...</p></div>';

    try {
        const [items, sections, intelSummary, procItems] = await Promise.all([
            api(`/bidding/bids/${bidId}/sov`),
            api(`/bidding/bids/${bidId}/sections`),
            api(`/bidding/bids/${bidId}/sov/intelligence-summary`).catch(() => []),
            api(`/bidding/bids/${bidId}/procurement`).catch(() => []),
        ]);

        // Build lookup maps
        const intelMap = {};
        intelSummary.forEach(s => { intelMap[s.sov_item_id] = s; });
        const hasIntel = intelSummary.length > 0;
        const hasStaleIntel = intelSummary.some(s => s.is_stale);

        // Build set of SOV item IDs that have procurement links
        const procLinkedSovIds = new Set();
        (procItems || []).forEach(p => (p.sov_links || []).forEach(l => procLinkedSovIds.add(l.sov_item_id)));
        window._procLinkedSovIds = procLinkedSovIds;

        // Split items: in-scope vs out-of-scope
        const inScopeItems = items.filter(i => i.in_scope !== 0);
        const outOfScopeItems = items.filter(i => i.in_scope === 0);

        // Group in-scope items by section
        const sectionMap = {};
        sections.forEach(s => { sectionMap[s.id] = { ...s, items: [] }; });
        const unsectioned = [];
        inScopeItems.forEach(item => {
            if (item.section_id && sectionMap[item.section_id]) {
                sectionMap[item.section_id].items.push(item);
            } else {
                unsectioned.push(item);
            }
        });
        const orderedSections = sections.sort((a, b) => a.sort_order - b.sort_order);

        // Track multi-select state
        window._sovSelectedIds = window._sovSelectedIds || new Set();

        const sovTableCols = 7; // #, HCSS#, Description, Type, Unit, Qty, Intel, Actions

        tc.innerHTML = `
            <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
                <button class="btn btn-primary btn-sm" onclick="showSOVUpload(${bidId})">Upload Schedule</button>
                <button class="btn btn-sm" onclick="showAddSOVItem(${bidId})">+ Add Item</button>
                <button class="btn btn-sm" onclick="autoRateAll(${bidId})">Auto-Rate All</button>
                <button class="btn btn-sm" style="background:var(--wollam-navy);color:white;" onclick="mapSOVIntelligence(${bidId})" id="mapIntelBtn">${hasStaleIntel ? 'Re-Map Intelligence' : 'Map Intelligence'}</button>
                <button class="btn btn-sm" onclick="showAddSection(${bidId})">+ Section</button>
                <div style="flex:1;"></div>
                <div id="sovBulkActions" style="display:none;gap:6px;align-items:center;">
                    <span id="sovSelectCount" style="font-size:12px;color:var(--text-secondary);"></span>
                    <button class="btn btn-sm" onclick="bulkSetWorkType(${bidId}, 'self_perform')" style="font-size:11px;">Set SP</button>
                    <button class="btn btn-sm" onclick="bulkSetWorkType(${bidId}, 'subcontract')" style="font-size:11px;">Set SUB</button>
                    <button class="btn btn-sm" onclick="clearSOVSelection()" style="font-size:11px;">Clear</button>
                </div>
            </div>

            ${hasStaleIntel ? `<div style="padding:8px 12px;margin-bottom:12px;background:#FFFBEB;border-left:3px solid #F59E0B;border-radius:var(--radius-sm);font-size:12px;color:#92400E;">&#9888; Intelligence mappings may be outdated — documents or agents have changed since last mapping.</div>` : ''}

            ${state.biddingSovPreview ? renderSOVPreview(bidId) : ''}

            <div id="sovAddForm" style="display:none;"></div>
            <div id="sectionAddForm" style="display:none;"></div>

            ${items.length === 0 ? '<div class="empty-state"><p>No schedule items yet. Upload a bid schedule or add items manually.</p></div>' : `
            <div style="margin-bottom:8px;font-size:12px;color:var(--text-secondary);">
                <span>${inScopeItems.length} in scope${outOfScopeItems.length > 0 ? `, ${outOfScopeItems.length} out of scope` : ''}</span>
            </div>

            <div class="card" style="padding:0;overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:13px;" id="sovMainTable">
                    <thead>
                        <tr style="background:var(--bg-hover);border-bottom:2px solid var(--border-default);">
                            <th style="padding:10px 8px;text-align:center;width:30px;">
                                <input type="checkbox" onchange="toggleAllSOVSelect(this.checked, ${bidId})" style="cursor:pointer;" title="Select all">
                            </th>
                            <th style="padding:10px 8px;text-align:left;font-weight:600;color:var(--text-secondary);width:55px;">#</th>
                            <th style="padding:10px 8px;text-align:left;font-weight:600;color:var(--text-secondary);width:65px;">HCSS #</th>
                            <th style="padding:10px 8px;text-align:left;font-weight:600;color:var(--text-secondary);">Description</th>
                            <th style="padding:10px 8px;text-align:center;font-weight:600;color:var(--text-secondary);width:50px;">Type</th>
                            <th style="padding:10px 8px;text-align:left;font-weight:600;color:var(--text-secondary);width:60px;">Unit</th>
                            <th style="padding:10px 8px;text-align:right;font-weight:600;color:var(--text-secondary);width:80px;">Qty</th>
                            <th style="padding:10px 8px;text-align:center;font-weight:600;color:var(--text-secondary);width:60px;">Intel</th>
                            <th style="padding:10px 8px;text-align:center;font-weight:600;color:var(--text-secondary);width:90px;">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${unsectioned.length > 0 && orderedSections.length > 0 ? `
                            <tr class="sov-section-header" style="background:var(--bg-hover);cursor:pointer;" onclick="toggleSectionCollapse('unsectioned')">
                                <td colspan="9" style="padding:8px 12px;font-weight:600;font-size:13px;color:var(--text-primary);border-bottom:2px solid var(--border-strong);">
                                    <span id="section-chevron-unsectioned" style="display:inline-block;transition:transform 0.2s;margin-right:6px;">&#9660;</span>
                                    Unassigned
                                    <span style="font-weight:400;color:var(--text-tertiary);font-size:11px;margin-left:8px;">${unsectioned.length} items</span>
                                </td>
                            </tr>
                            ${unsectioned.map(item => renderSOVItemRow(item, bidId, intelMap)).join('')}
                        ` : unsectioned.length > 0 ? unsectioned.map(item => renderSOVItemRow(item, bidId, intelMap)).join('') : ''}
                        ${orderedSections.map(sec => {
                            const secItems = sectionMap[sec.id] ? sectionMap[sec.id].items : [];
                            return `
                            <tr class="sov-section-header" style="background:var(--bg-hover);cursor:pointer;" onclick="toggleSectionCollapse(${sec.id})">
                                <td colspan="9" style="padding:8px 12px;font-weight:600;font-size:13px;color:var(--text-primary);border-bottom:2px solid var(--border-strong);">
                                    <span id="section-chevron-${sec.id}" style="display:inline-block;transition:transform 0.2s;margin-right:6px;">&#9660;</span>
                                    ${escHtml(sec.name)}
                                    <span style="font-weight:400;color:var(--text-tertiary);font-size:11px;margin-left:8px;">${secItems.length} items</span>
                                    <span style="float:right;" onclick="event.stopPropagation();">
                                        <button onclick="editSection(${sec.id}, ${bidId})" style="background:none;border:none;cursor:pointer;color:var(--text-tertiary);font-size:11px;padding:2px 4px;" title="Rename">&#9998;</button>
                                        <button onclick="deleteSection(${sec.id}, ${bidId})" style="background:none;border:none;cursor:pointer;color:var(--danger-red);font-size:11px;padding:2px 4px;" title="Delete section">&#10005;</button>
                                    </span>
                                </td>
                            </tr>
                            ${secItems.map(item => renderSOVItemRow(item, bidId, intelMap, sec.id)).join('')}`;
                        }).join('')}
                    </tbody>
                </table>
            </div>

            ${outOfScopeItems.length > 0 ? `
            <div style="margin-top:24px;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;cursor:pointer;" onclick="document.getElementById('outOfScopeTable').style.display = document.getElementById('outOfScopeTable').style.display === 'none' ? 'block' : 'none'; document.getElementById('oos-chevron').textContent = document.getElementById('outOfScopeTable').style.display === 'none' ? '▶' : '▼';">
                    <span id="oos-chevron" style="color:var(--text-tertiary);font-size:12px;">&#9660;</span>
                    <h4 style="margin:0;font-size:13px;font-weight:600;color:var(--text-tertiary);">Out of Scope Items</h4>
                    <span style="font-size:11px;color:var(--text-tertiary);">(${outOfScopeItems.length})</span>
                </div>
                <div id="outOfScopeTable" class="card" style="padding:0;overflow-x:auto;opacity:0.7;">
                    <table style="width:100%;border-collapse:collapse;font-size:13px;">
                        <thead>
                            <tr style="background:#F1F5F9;border-bottom:2px solid var(--border-default);">
                                <th style="padding:8px 12px;text-align:left;font-weight:600;color:var(--text-tertiary);width:60px;">#</th>
                                <th style="padding:8px 12px;text-align:left;font-weight:600;color:var(--text-tertiary);">Description</th>
                                <th style="padding:8px 12px;text-align:left;font-weight:600;color:var(--text-tertiary);width:60px;">Unit</th>
                                <th style="padding:8px 12px;text-align:right;font-weight:600;color:var(--text-tertiary);width:80px;">Qty</th>
                                <th style="padding:8px 12px;text-align:center;font-weight:600;color:var(--text-tertiary);width:60px;">Scope</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${outOfScopeItems.map(item => `
                            <tr style="border-bottom:1px solid var(--border-default);">
                                <td style="padding:6px 12px;color:var(--text-tertiary);font-family:monospace;font-size:12px;">${escHtml(item.item_number || '—')}</td>
                                <td style="padding:6px 12px;color:var(--text-tertiary);">${escHtml(item.description)}</td>
                                <td style="padding:6px 12px;color:var(--text-tertiary);">${escHtml(item.unit || '—')}</td>
                                <td style="padding:6px 12px;text-align:right;color:var(--text-tertiary);">${item.quantity != null ? fmt(item.quantity, 1) : '—'}</td>
                                <td style="padding:6px 12px;text-align:center;">
                                    <input type="checkbox" onchange="toggleItemScope(${item.id}, ${bidId}, true)" style="cursor:pointer;" title="Check to bring back in scope">
                                </td>
                            </tr>`).join('')}
                        </tbody>
                    </table>
                </div>
            </div>` : ''}`}
        `;
    } catch (err) {
        tc.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${escHtml(err.message)}</p></div>`;
    }
}

function renderSOVItemRow(item, bidId, intelMap, sectionId) {
    const intel = intelMap[item.id];
    const intelBadge = intel ? sovIntelBadge(intel) : '<span style="color:var(--text-tertiary);font-size:11px;">—</span>';
    const wt = item.work_type || 'undecided';
    const wtLabel = WORK_TYPE_LABELS[wt] || '—';
    const wtColor = WORK_TYPE_COLORS[wt] || 'var(--text-tertiary)';
    const leftBorder = WORK_TYPE_BORDER[wt] || '';
    const isHolding = item.is_holding_account === 1;
    const holdingBg = isHolding ? 'background:rgba(6,182,212,0.04);' : '';
    const isSelected = window._sovSelectedIds && window._sovSelectedIds.has(item.id);
    const needsProcurement = wt === 'subcontract' && window._procLinkedSovIds && !window._procLinkedSovIds.has(item.id);
    const procWarning = needsProcurement ? `<span onclick="event.stopPropagation();switchBidTab('procurement',${bidId});" style="color:#F59E0B;font-size:11px;cursor:pointer;" title="Subcontract item with no procurement link — click to open Procurement tab">&#9888;</span>` : '';

    return `
    <tr style="${leftBorder ? `border-left:${leftBorder};` : ''}border-bottom:1px solid var(--border-default);cursor:pointer;${holdingBg}" id="sov-row-${item.id}" class="sov-item-row ${sectionId ? `section-${sectionId}` : 'section-unsectioned'}" onclick="toggleSOVItemDetail(${item.id}, ${bidId})">
        <td style="padding:6px 8px;text-align:center;" onclick="event.stopPropagation();">
            <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleSOVSelect(${item.id}, this.checked, ${bidId})" style="cursor:pointer;">
        </td>
        <td style="padding:6px 8px;color:var(--text-secondary);font-family:monospace;font-size:12px;">${escHtml(item.item_number || '—')}</td>
        <td style="padding:6px 8px;font-family:monospace;font-size:12px;" onclick="event.stopPropagation();">
            <span class="sov-hcss-editable" onclick="editHCSSNumber(${item.id}, ${bidId}, this)" style="cursor:text;min-width:30px;display:inline-block;color:${item.hcss_number ? 'var(--text-primary)' : 'var(--text-tertiary)'};">${escHtml(item.hcss_number || '—')}</span>
        </td>
        <td style="padding:6px 8px;">
            ${escHtml(item.description)} ${procWarning}
            ${isHolding ? `<br><span style="font-size:10px;color:var(--text-tertiary);font-style:italic;">&#9881; ${escHtml(item.holding_description || 'Holding account')}</span>` : ''}
        </td>
        <td style="padding:6px 8px;text-align:center;" onclick="event.stopPropagation();">
            <span onclick="cycleWorkType(${item.id}, ${bidId}, '${wt}')" style="cursor:pointer;font-size:11px;font-weight:600;color:${wtColor};padding:2px 6px;border-radius:4px;${wt !== 'undecided' ? `background:${wtColor}11;` : ''}" title="Click to change: ${wt.replace('_', ' ')}">${wtLabel}</span>
        </td>
        <td style="padding:6px 8px;color:var(--text-secondary);font-size:12px;">${escHtml(item.unit || '—')}</td>
        <td style="padding:6px 8px;text-align:right;font-size:12px;">${item.quantity != null ? fmt(item.quantity, 1) : '—'}</td>
        <td style="padding:6px 8px;text-align:center;">${intelBadge}</td>
        <td style="padding:6px 8px;text-align:center;" onclick="event.stopPropagation();">
            <button onclick="editSOVItem(${item.id}, ${bidId})" style="background:none;border:none;cursor:pointer;color:var(--text-tertiary);padding:2px;" title="Edit">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button onclick="deleteSOVItem(${item.id}, ${bidId})" style="background:none;border:none;cursor:pointer;color:var(--danger-red);padding:2px;" title="Delete">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
            <input type="checkbox" checked onchange="toggleItemScope(${item.id}, ${bidId}, false)" style="cursor:pointer;margin-left:2px;vertical-align:middle;" title="In scope — uncheck to exclude">
        </td>
    </tr>
    <tr class="sov-item-row ${sectionId ? `section-${sectionId}` : 'section-unsectioned'}"><td colspan="9" style="padding:0;"><div id="detail-panel-${item.id}" style="display:none;"></div></td></tr>`;
}

function showSOVUpload(bidId) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx,.xls,.pdf,.csv,.txt,.docx';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const tc = document.getElementById('bidTabContent');
        tc.innerHTML = `<div class="empty-state"><p>Parsing schedule with AI... This may take a moment.</p></div>`;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch(`/api/bidding/bids/${bidId}/sov/upload`, {
                method: 'POST',
                body: formData,
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || 'Upload failed');
            }
            const data = await res.json();
            state.biddingSovPreview = data;
            renderBidSOV(bidId);
        } catch (err) {
            alert('Error parsing schedule: ' + err.message);
            renderBidSOV(bidId);
        }
    };
    input.click();
}

function renderSOVPreview(bidId) {
    const preview = state.biddingSovPreview;
    if (!preview) return '';

    return `
        <div class="card" style="padding:16px;margin-bottom:16px;border:2px solid var(--wollam-gold);background:var(--wollam-gold-faint);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                <h3 style="font-size:14px;font-weight:600;margin:0;">AI-Parsed Preview: ${preview.count} items from ${escHtml(preview.filename)}</h3>
                <div style="display:flex;gap:8px;">
                    <button class="btn btn-sm" onclick="cancelSOVPreview(${bidId})">Cancel</button>
                    <button class="btn btn-primary btn-sm" onclick="confirmSOVPreview(${bidId})">Confirm & Save</button>
                </div>
            </div>
            <div style="max-height:300px;overflow-y:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:12px;">
                    <thead><tr style="background:rgba(0,0,0,0.04);">
                        <th style="padding:6px 8px;text-align:left;">#</th>
                        <th style="padding:6px 8px;text-align:left;">Description</th>
                        <th style="padding:6px 8px;text-align:left;">Unit</th>
                        <th style="padding:6px 8px;text-align:right;">Qty</th>
                    </tr></thead>
                    <tbody>
                        ${preview.items.map(item => `
                            <tr style="border-bottom:1px solid var(--border-default);">
                                <td style="padding:4px 8px;font-family:monospace;">${escHtml(item.item_number || '—')}</td>
                                <td style="padding:4px 8px;">${escHtml(item.description || '')}</td>
                                <td style="padding:4px 8px;">${escHtml(item.unit || '—')}</td>
                                <td style="padding:4px 8px;text-align:right;">${item.quantity != null ? fmt(item.quantity, 1) : '—'}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

async function confirmSOVPreview(bidId) {
    const preview = state.biddingSovPreview;
    if (!preview) return;

    try {
        await api(`/bidding/bids/${bidId}/sov/confirm`, {
            method: 'POST',
            body: JSON.stringify({ items: preview.items }),
        });
        state.biddingSovPreview = null;
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error saving items: ' + err.message);
    }
}

function cancelSOVPreview(bidId) {
    state.biddingSovPreview = null;
    renderBidSOV(bidId);
}

function showAddSOVItem(bidId) {
    const form = document.getElementById('sovAddForm');
    form.style.display = 'block';
    form.innerHTML = `
        <div class="card" style="padding:16px;margin-bottom:16px;">
            <h4 style="font-size:13px;font-weight:600;margin:0 0 12px;">Add SOV Item</h4>
            <div style="display:grid;grid-template-columns:80px 1fr 80px 100px;gap:8px;align-items:end;">
                <div><label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:2px;">Item #</label>
                    <input type="text" id="sov_num" class="search-input" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:2px;">Description *</label>
                    <input type="text" id="sov_desc" class="search-input" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:2px;">Unit</label>
                    <input type="text" id="sov_unit" class="search-input" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:2px;">Qty</label>
                    <input type="number" id="sov_qty" class="search-input" style="width:100%;"></div>
            </div>
            <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:8px;">
                <button class="btn btn-sm" onclick="document.getElementById('sovAddForm').style.display='none'">Cancel</button>
                <button class="btn btn-primary btn-sm" onclick="addSOVItem(${bidId})">Add</button>
            </div>
        </div>
    `;
}

async function addSOVItem(bidId) {
    const desc = document.getElementById('sov_desc').value.trim();
    if (!desc) { alert('Description is required'); return; }

    try {
        await api(`/bidding/bids/${bidId}/sov`, {
            method: 'POST',
            body: JSON.stringify({
                item_number: document.getElementById('sov_num').value.trim() || null,
                description: desc,
                unit: document.getElementById('sov_unit').value.trim() || null,
                quantity: parseFloat(document.getElementById('sov_qty').value) || null,
            }),
        });
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function editSOVItem(itemId, bidId) {
    const row = document.getElementById(`sov-row-${itemId}`);
    if (!row) return;

    try {
        const items = await api(`/bidding/bids/${bidId}/sov`);
        const item = items.find(i => i.id === itemId);
        if (!item) return;

        const sections = await api(`/bidding/bids/${bidId}/sections`);

        row.innerHTML = `
            <td style="padding:4px 6px;"></td>
            <td style="padding:4px 6px;"><input type="text" id="edit_num_${itemId}" class="search-input" style="width:100%;font-size:12px;" value="${escAttr(item.item_number || '')}"></td>
            <td style="padding:4px 6px;"><input type="text" id="edit_hcss_${itemId}" class="search-input" style="width:100%;font-size:12px;" value="${escAttr(item.hcss_number || '')}"></td>
            <td style="padding:4px 6px;"><input type="text" id="edit_desc_${itemId}" class="search-input" style="width:100%;font-size:12px;" value="${escAttr(item.description || '')}"></td>
            <td style="padding:4px 6px;">
                <select id="edit_sec_${itemId}" class="search-input" style="width:100%;font-size:11px;">
                    <option value="">None</option>
                    ${sections.map(s => `<option value="${s.id}" ${item.section_id === s.id ? 'selected' : ''}>${escHtml(s.name)}</option>`).join('')}
                </select>
            </td>
            <td style="padding:4px 6px;"><input type="text" id="edit_unit_${itemId}" class="search-input" style="width:100%;font-size:12px;" value="${escAttr(item.unit || '')}"></td>
            <td style="padding:4px 6px;"><input type="number" id="edit_qty_${itemId}" class="search-input" style="width:100%;font-size:12px;" value="${item.quantity || ''}"></td>
            <td colspan="2" style="padding:4px 6px;text-align:center;">
                <button onclick="saveSOVEdit(${itemId}, ${bidId})" class="btn btn-primary btn-sm" style="font-size:11px;padding:2px 8px;">Save</button>
                <button onclick="renderBidSOV(${bidId})" class="btn btn-sm" style="font-size:11px;padding:2px 8px;">Cancel</button>
            </td>
        `;
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function saveSOVEdit(itemId, bidId) {
    try {
        const secVal = document.getElementById(`edit_sec_${itemId}`).value;
        await api(`/bidding/sov/${itemId}`, {
            method: 'PUT',
            body: JSON.stringify({
                item_number: document.getElementById(`edit_num_${itemId}`).value.trim() || null,
                hcss_number: document.getElementById(`edit_hcss_${itemId}`).value.trim() || null,
                description: document.getElementById(`edit_desc_${itemId}`).value.trim(),
                unit: document.getElementById(`edit_unit_${itemId}`).value.trim() || null,
                quantity: parseFloat(document.getElementById(`edit_qty_${itemId}`).value) || null,
                section_id: secVal ? parseInt(secVal) : null,
            }),
        });
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function deleteSOVItem(itemId, bidId) {
    if (!confirm('Delete this SOV item?')) return;
    try {
        await api(`/bidding/sov/${itemId}`, { method: 'DELETE' });
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// ── Section Management ──

function showAddSection(bidId) {
    const form = document.getElementById('sectionAddForm');
    if (form.style.display === 'block') { form.style.display = 'none'; return; }
    form.style.display = 'block';
    form.innerHTML = `
        <div class="card" style="padding:12px;margin-bottom:16px;">
            <div style="display:flex;gap:8px;align-items:center;">
                <input type="text" id="new_section_name" class="search-input" placeholder="Section name (e.g. Division 3 — Concrete)" style="flex:1;font-size:13px;">
                <button class="btn btn-primary btn-sm" onclick="createSection(${bidId})">Create</button>
                <button class="btn btn-sm" onclick="document.getElementById('sectionAddForm').style.display='none'">Cancel</button>
            </div>
        </div>
    `;
    document.getElementById('new_section_name').focus();
}

async function createSection(bidId) {
    const name = document.getElementById('new_section_name').value.trim();
    if (!name) return;
    try {
        await api(`/bidding/bids/${bidId}/sections`, {
            method: 'POST',
            body: JSON.stringify({ name }),
        });
        document.getElementById('sectionAddForm').style.display = 'none';
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function editSection(sectionId, bidId) {
    const newName = prompt('Rename section:');
    if (!newName || !newName.trim()) return;
    try {
        await api(`/bidding/sections/${sectionId}`, {
            method: 'PUT',
            body: JSON.stringify({ name: newName.trim() }),
        });
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function deleteSection(sectionId, bidId) {
    if (!confirm('Delete this section? Items will become unassigned.')) return;
    try {
        await api(`/bidding/sections/${sectionId}`, { method: 'DELETE' });
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

function toggleSectionCollapse(sectionId) {
    const rows = document.querySelectorAll(`.section-${sectionId}`);
    const chevron = document.getElementById(`section-chevron-${sectionId}`);
    const isCollapsed = rows.length > 0 && rows[0].style.display === 'none';
    rows.forEach(r => { r.style.display = isCollapsed ? '' : 'none'; });
    if (chevron) chevron.innerHTML = isCollapsed ? '&#9660;' : '&#9654;';
}

// ── HCSS Number Inline Edit ──

function editHCSSNumber(itemId, bidId, el) {
    const current = el.textContent === '—' ? '' : el.textContent;
    el.innerHTML = `<input type="text" class="search-input" value="${escAttr(current)}" style="width:60px;font-size:12px;font-family:monospace;padding:1px 4px;" onblur="saveHCSSNumber(${itemId}, ${bidId}, this.value)" onkeydown="if(event.key==='Enter'){this.blur();}">`;
    el.querySelector('input').focus();
}

async function saveHCSSNumber(itemId, bidId, value) {
    try {
        await api(`/bidding/sov/${itemId}`, {
            method: 'PUT',
            body: JSON.stringify({ hcss_number: value.trim() || null }),
        });
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// ── Work Type Cycling ──

async function cycleWorkType(itemId, bidId, current) {
    const cycle = { undecided: 'self_perform', self_perform: 'subcontract', subcontract: 'undecided' };
    const next = cycle[current] || 'undecided';
    try {
        await api(`/bidding/sov/${itemId}`, {
            method: 'PUT',
            body: JSON.stringify({ work_type: next }),
        });
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// ── SOV Multi-Select ──

function toggleSOVSelect(itemId, checked, bidId) {
    if (!window._sovSelectedIds) window._sovSelectedIds = new Set();
    if (checked) window._sovSelectedIds.add(itemId);
    else window._sovSelectedIds.delete(itemId);
    updateSOVBulkActions(bidId);
}

function toggleAllSOVSelect(checked, bidId) {
    const checkboxes = document.querySelectorAll('#sovMainTable .sov-item-row input[type="checkbox"]');
    window._sovSelectedIds = new Set();
    checkboxes.forEach(cb => {
        cb.checked = checked;
        if (checked) {
            const match = cb.getAttribute('onchange')?.match(/toggleSOVSelect\((\d+)/);
            if (match) window._sovSelectedIds.add(parseInt(match[1]));
        }
    });
    updateSOVBulkActions(bidId);
}

function clearSOVSelection() {
    window._sovSelectedIds = new Set();
    document.querySelectorAll('#sovMainTable input[type="checkbox"]').forEach(cb => { cb.checked = false; });
    document.getElementById('sovBulkActions').style.display = 'none';
}

function updateSOVBulkActions(bidId) {
    const bar = document.getElementById('sovBulkActions');
    const count = window._sovSelectedIds ? window._sovSelectedIds.size : 0;
    if (count > 0) {
        bar.style.display = 'flex';
        document.getElementById('sovSelectCount').textContent = `${count} selected`;
    } else {
        bar.style.display = 'none';
    }
}

async function bulkSetWorkType(bidId, workType) {
    if (!window._sovSelectedIds || window._sovSelectedIds.size === 0) return;
    try {
        await api(`/bidding/bids/${bidId}/sov/set-work-type`, {
            method: 'POST',
            body: JSON.stringify({ item_ids: [...window._sovSelectedIds], work_type: workType }),
        });
        window._sovSelectedIds = new Set();
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// ── Documents Tab ──

async function renderBidDocuments(bid) {
    const bidId = bid.id;
    const tc = document.getElementById('bidTabContent');
    const docTab = state.docSubTab || 'explorer';

    tc.innerHTML = `
        <div class="filter-tabs" style="margin-bottom:16px;font-size:12px;">
            <button class="filter-tab ${docTab === 'explorer' ? 'active' : ''}" onclick="state.docSubTab='explorer';renderBidDocuments(window._currentBid)">File Explorer</button>
            <button class="filter-tab ${docTab === 'registers' ? 'active' : ''}" onclick="state.docSubTab='registers';renderBidDocuments(window._currentBid)">Drawings & Specs</button>
            <button class="filter-tab ${docTab === 'rfi' ? 'active' : ''}" onclick="state.docSubTab='rfi';renderBidDocuments(window._currentBid)">RFI & Clarifications</button>
        </div>
        <div id="docSubContent"></div>
    `;
    window._currentBid = bid;

    if (docTab === 'explorer') renderDocExplorer(bid);
    else if (docTab === 'registers') renderDocRegisters(bid);
    else if (docTab === 'rfi') renderDocRFI(bid);
}

function formatFileSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function renderDocExplorer(bid) {
    const bidId = bid.id;
    const sc = document.getElementById('docSubContent');
    sc.innerHTML = '<div class="empty-state"><p>Loading documents...</p></div>';

    try {
        const treeData = await api(`/bidding/bids/${bidId}/documents/tree`);
        const hasFolder = !!bid.dropbox_folder_path;
        const lastSynced = bid.last_synced_at ? new Date(bid.last_synced_at).toLocaleString() : 'Never synced';
        const stats = treeData.stats || {};

        sc.innerHTML = `
            <!-- Toolbar -->
            <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
                ${hasFolder ? `
                <button class="btn btn-primary btn-sm" id="syncDropboxBtn" onclick="syncFromDropbox(${bidId})" style="display:flex;align-items:center;gap:6px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
                    Sync from Dropbox
                </button>
                <span style="font-size:11px;color:var(--text-tertiary);">Last: ${escHtml(lastSynced)}</span>
                ` : ''}
                <div style="flex:1;"></div>
                <input type="text" id="docSearchInput" class="search-input" placeholder="Search files..." style="width:200px;font-size:12px;" oninput="filterDocTree(this.value)">
                <button class="btn btn-sm" onclick="toggleAllDocFolders(true)">Expand All</button>
                <button class="btn btn-sm" onclick="toggleAllDocFolders(false)">Collapse All</button>
            </div>
            <div id="syncResult"></div>

            <!-- Summary -->
            <div style="margin-bottom:12px;font-size:12px;color:var(--text-secondary);">
                ${stats.total_documents || 0} documents${stats.new_since_last_sync ? ` &middot; <span style="color:var(--success-green);font-weight:600;">${stats.new_since_last_sync} new</span>` : ''}${stats.updated_since_last_sync ? ` &middot; <span style="color:#f59e0b;font-weight:600;">${stats.updated_since_last_sync} updated</span>` : ''}
            </div>

            ${hasFolder ? `
            <details style="margin-bottom:12px;">
                <summary style="font-size:11px;color:var(--text-tertiary);cursor:pointer;">Manual upload</summary>
                <div class="card" style="padding:16px;margin-top:8px;border:2px dashed var(--border-strong);text-align:center;cursor:pointer;background:var(--bg-hover);" onclick="triggerDocUpload(${bidId})"
                     ondragover="event.preventDefault();this.style.borderColor='var(--wollam-navy)';"
                     ondragleave="this.style.borderColor='var(--border-strong)';"
                     ondrop="handleDocDrop(event, ${bidId});this.style.borderColor='var(--border-strong)';">
                    <p style="margin:0;font-size:12px;color:var(--text-secondary);">Drag files here or click to upload</p>
                </div>
            </details>
            ` : `
            <div class="card" style="padding:16px;margin-bottom:12px;border:2px dashed var(--border-strong);text-align:center;cursor:pointer;background:var(--bg-hover);"
                 onclick="triggerDocUpload(${bidId})"
                 ondragover="event.preventDefault();this.style.borderColor='var(--wollam-navy)';"
                 ondragleave="this.style.borderColor='var(--border-strong)';"
                 ondrop="handleDocDrop(event, ${bidId});this.style.borderColor='var(--border-strong)';">
                <p style="margin:0;font-size:12px;color:var(--text-secondary);">Drag files here or click to upload</p>
            </div>
            `}

            <input type="file" id="docFileInput" style="display:none;" multiple accept=".pdf,.xlsx,.xls,.csv,.txt,.docx,.doc" onchange="uploadDocFiles(this.files, ${bidId})">
            <div id="docUploadMeta" style="display:none;"></div>

            <!-- File Tree -->
            <div id="docTree">
            ${treeData.tree.length === 0 ? '<div class="empty-state"><p>No documents yet.</p></div>' :
                treeData.tree.map(folder => renderDocFolder(folder, bidId)).join('')}
            </div>
        `;
    } catch (err) {
        sc.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${escHtml(err.message)}</p></div>`;
    }
}

function renderDocFolder(folder, bidId) {
    const folderId = 'doc-folder-' + (folder.path || 'root').replace(/[^a-zA-Z0-9]/g, '_');
    const nameStyle = (folder.has_new || folder.has_updated) ? 'font-weight:600;' : '';
    const newDot = folder.has_new ? '<span style="width:6px;height:6px;border-radius:50%;background:var(--success-green);display:inline-block;margin-left:4px;"></span>' : '';
    const updDot = folder.has_updated ? '<span style="width:6px;height:6px;border-radius:50%;background:#f59e0b;display:inline-block;margin-left:4px;"></span>' : '';

    return `
    <div class="doc-folder" style="margin-bottom:4px;">
        <div onclick="document.getElementById('${folderId}').style.display = document.getElementById('${folderId}').style.display === 'none' ? 'block' : 'none'; this.querySelector('.folder-chevron').textContent = document.getElementById('${folderId}').style.display === 'none' ? '▶' : '▼';"
             style="padding:6px 10px;background:var(--bg-hover);border-radius:var(--radius-sm);cursor:pointer;display:flex;align-items:center;gap:6px;">
            <span class="folder-chevron" style="font-size:10px;color:var(--text-tertiary);">&#9660;</span>
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="var(--wollam-gold)" stroke="var(--wollam-gold-dark)" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            <span style="font-size:13px;color:var(--text-primary);${nameStyle}">${escHtml(folder.name || 'Root')}</span>
            <span style="font-size:10px;color:var(--text-tertiary);">(${folder.doc_count})</span>
            ${newDot}${updDot}
        </div>
        <div id="${folderId}" style="padding-left:20px;margin-top:2px;">
            ${(folder.children || []).map(doc => renderDocRow(doc, bidId)).join('')}
        </div>
    </div>`;
}

function renderDocRow(doc, bidId) {
    const isNew = doc.sync_action === 'new';
    const isUpdated = doc.sync_action === 'updated';
    const isRemoved = doc.sync_action === 'removed';
    const borderColor = isNew ? 'var(--success-green)' : isUpdated ? '#f59e0b' : isRemoved ? 'var(--danger-red)' : 'transparent';
    const bgTint = isNew ? 'rgba(22,163,74,0.04)' : isUpdated ? 'rgba(245,158,11,0.04)' : '';
    const textStyle = isRemoved ? 'text-decoration:line-through;color:var(--text-tertiary);' : '';
    const fileLink = doc.dropbox_url
        ? `<a href="${escAttr(doc.dropbox_url)}" target="_blank" style="font-size:13px;font-weight:500;color:var(--text-primary);text-decoration:none;${textStyle}" title="Open file">${escHtml(doc.filename)}</a>`
        : `<span style="font-size:13px;font-weight:500;${textStyle}">${escHtml(doc.filename)}</span>`;

    return `
    <div class="doc-row" data-filename="${escAttr(doc.filename.toLowerCase())}" style="padding:6px 10px;margin-bottom:2px;border-left:3px solid ${borderColor};background:${bgTint};border-radius:0 var(--radius-sm) var(--radius-sm) 0;display:flex;align-items:center;gap:8px;">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        ${fileLink}
        ${isNew ? '<span class="badge" style="background:var(--success-green);color:white;font-size:9px;padding:1px 5px;">NEW</span>' : ''}
        ${isUpdated ? '<span class="badge" style="background:#f59e0b;color:white;font-size:9px;padding:1px 5px;">UPDATED</span>' : ''}
        ${docCategoryBadge(doc.doc_category)}
        ${doc.addendum_number > 0 ? `<span style="font-size:10px;color:var(--text-tertiary);">Add. ${doc.addendum_number}</span>` : ''}
        ${doc.date_received ? `<span style="font-size:10px;color:var(--text-tertiary);">${doc.date_received}</span>` : ''}
        <span style="font-size:10px;color:var(--text-tertiary);margin-left:auto;">${formatFileSize(doc.file_size_bytes)}</span>
        <button onclick="deleteDoc(${doc.id}, ${bidId})" style="background:none;border:none;cursor:pointer;color:var(--text-tertiary);padding:2px;font-size:11px;" title="Delete">&times;</button>
    </div>`;
}

function filterDocTree(query) {
    const q = query.toLowerCase().trim();
    document.querySelectorAll('.doc-row').forEach(row => {
        const fn = row.getAttribute('data-filename') || '';
        row.style.display = !q || fn.includes(q) ? '' : 'none';
    });
}

function toggleAllDocFolders(expand) {
    document.querySelectorAll('.doc-folder > div:last-child').forEach(el => { el.style.display = expand ? 'block' : 'none'; });
    document.querySelectorAll('.folder-chevron').forEach(el => { el.textContent = expand ? '▼' : '▶'; });
}

// ── Drawings & Specs Register ──

async function renderDocRegisters(bid) {
    const bidId = bid.id;
    const sc = document.getElementById('docSubContent');
    sc.innerHTML = '<div class="empty-state"><p>Loading registers...</p></div>';

    try {
        const [drawings, specs] = await Promise.all([
            api(`/bidding/bids/${bidId}/drawing-register`),
            api(`/bidding/bids/${bidId}/spec-register`),
        ]);

        const drawingNew = drawings.filter(d => d.is_new).length;
        const drawingRevised = drawings.filter(d => d.is_revised).length;
        const specNew = specs.filter(s => s.is_new).length;

        sc.innerHTML = `
            <!-- Status bar -->
            <div style="display:flex;gap:8px;margin-bottom:12px;align-items:center;flex-wrap:wrap;">
                <button class="btn btn-sm" onclick="rebuildRegisters(${bidId})" id="rebuildRegBtn">Rebuild from Documents</button>
                <button class="btn btn-sm" onclick="window.open('/api/bidding/bids/${bidId}/drawing-register/export','_blank')">Export Drawings</button>
                <button class="btn btn-sm" onclick="window.open('/api/bidding/bids/${bidId}/spec-register/export','_blank')">Export Specs</button>
                <div style="flex:1;"></div>
                <span style="font-size:12px;color:var(--text-secondary);">
                    ${drawings.length} drawings${drawingNew ? ` (<span style="color:var(--success-green);">${drawingNew} new</span>)` : ''}${drawingRevised ? ` (<span style="color:#f59e0b;">${drawingRevised} revised</span>)` : ''}
                    &middot; ${specs.length} spec sections${specNew ? ` (<span style="color:var(--success-green);">${specNew} new</span>)` : ''}
                </span>
            </div>
            <div id="rebuildProgress"></div>

            <!-- Drawing Register -->
            <h4 style="font-size:14px;font-weight:600;color:var(--text-primary);margin:0 0 8px;">Drawing Register</h4>
            ${drawings.length === 0 ? '<div class="empty-state" style="padding:20px;"><p>No drawings registered yet. Click "Rebuild from Documents" to scan.</p></div>' : `
            <div class="card" style="padding:0;overflow-x:auto;margin-bottom:20px;">
                <table style="width:100%;border-collapse:collapse;font-size:12px;">
                    <thead>
                        <tr style="background:var(--bg-hover);border-bottom:2px solid var(--border-default);">
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Drawing #</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Title</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Discipline</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);">Rev</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);">Add.</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Received</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${drawings.map(d => `
                        <tr style="border-bottom:1px solid var(--border-default);">
                            <td style="padding:6px 10px;font-family:monospace;font-weight:500;">${escHtml(d.drawing_number)}</td>
                            <td style="padding:6px 10px;">${escHtml(d.title || '—')}</td>
                            <td style="padding:6px 10px;color:var(--text-secondary);">${escHtml(d.discipline || '—')}</td>
                            <td style="padding:6px 10px;text-align:center;font-family:monospace;">${escHtml(d.revision || '0')}${d.previous_revision ? ` <span style="font-size:10px;color:var(--text-tertiary);" title="Was Rev ${escAttr(d.previous_revision)}">&#8592;${escHtml(d.previous_revision)}</span>` : ''}</td>
                            <td style="padding:6px 10px;text-align:center;">${d.addendum_number || 0}</td>
                            <td style="padding:6px 10px;color:var(--text-tertiary);font-size:11px;">${d.date_received || '—'}</td>
                            <td style="padding:6px 10px;text-align:center;">
                                ${d.is_new ? '<span class="badge" style="background:var(--success-green);color:white;font-size:9px;padding:1px 5px;">NEW</span>' : ''}
                                ${d.is_revised ? '<span class="badge" style="background:#f59e0b;color:white;font-size:9px;padding:1px 5px;">REVISED</span>' : ''}
                                ${!d.is_new && !d.is_revised ? '<span style="color:var(--text-tertiary);font-size:10px;">—</span>' : ''}
                            </td>
                        </tr>`).join('')}
                    </tbody>
                </table>
            </div>`}

            <!-- Spec Register -->
            <h4 style="font-size:14px;font-weight:600;color:var(--text-primary);margin:0 0 8px;">Spec Register</h4>
            ${specs.length === 0 ? '<div class="empty-state" style="padding:20px;"><p>No specs registered yet. Click "Rebuild from Documents" to scan.</p></div>' : `
            <div class="card" style="padding:0;overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:12px;">
                    <thead>
                        <tr style="background:var(--bg-hover);border-bottom:2px solid var(--border-default);">
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Section #</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Title</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Division</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);">Add.</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Received</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${specs.map(s => `
                        <tr style="border-bottom:1px solid var(--border-default);">
                            <td style="padding:6px 10px;font-family:monospace;font-weight:500;">${escHtml(s.spec_section)}</td>
                            <td style="padding:6px 10px;">${escHtml(s.title || '—')}</td>
                            <td style="padding:6px 10px;color:var(--text-secondary);">${escHtml(s.division || '—')}</td>
                            <td style="padding:6px 10px;text-align:center;">${s.addendum_number || 0}</td>
                            <td style="padding:6px 10px;color:var(--text-tertiary);font-size:11px;">${s.date_received || '—'}</td>
                            <td style="padding:6px 10px;text-align:center;">
                                ${s.is_new ? '<span class="badge" style="background:var(--success-green);color:white;font-size:9px;padding:1px 5px;">NEW</span>' : ''}
                                ${s.is_revised ? '<span class="badge" style="background:#f59e0b;color:white;font-size:9px;padding:1px 5px;">REVISED</span>' : ''}
                                ${!s.is_new && !s.is_revised ? '<span style="color:var(--text-tertiary);font-size:10px;">—</span>' : ''}
                            </td>
                        </tr>`).join('')}
                    </tbody>
                </table>
            </div>`}
        `;
    } catch (err) {
        sc.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${escHtml(err.message)}</p></div>`;
    }
}

async function rebuildRegisters(bidId) {
    const btn = document.getElementById('rebuildRegBtn');
    const prog = document.getElementById('rebuildProgress');
    btn.disabled = true;
    btn.textContent = 'Rebuilding...';
    prog.innerHTML = renderProgressBar(-1, 1, 'Rebuilding drawing register...', 'rebuild');

    try {
        const dResult = await api(`/bidding/bids/${bidId}/drawing-register/rebuild`, { method: 'POST' });
        prog.innerHTML = renderProgressBar(-1, 1, 'Rebuilding spec register...', 'rebuild');
        const sResult = await api(`/bidding/bids/${bidId}/spec-register/rebuild`, { method: 'POST' });

        prog.innerHTML = renderProgressBar(1, 1, `Done! Drawings: ${dResult.created || 0} created, ${dResult.updated || 0} updated. Specs: ${sResult.created || 0} created, ${sResult.updated || 0} updated.`, 'rebuild', true);
        setTimeout(() => { prog.innerHTML = ''; renderDocRegisters(window._currentBid); }, 2000);
    } catch (err) {
        prog.innerHTML = renderProgressBar(0, 1, 'Error: ' + err.message, 'rebuild', false, true);
        btn.disabled = false;
        btn.textContent = 'Rebuild from Documents';
    }
}

// ── RFI & Clarifications Log ──

async function renderDocRFI(bid) {
    const bidId = bid.id;
    const sc = document.getElementById('docSubContent');
    sc.innerHTML = '<div class="empty-state"><p>Loading RFI log...</p></div>';

    try {
        const rfis = await api(`/bidding/bids/${bidId}/rfi-log`);
        const addendums = [...new Set(rfis.map(r => r.addendum_number).filter(a => a != null))];

        sc.innerHTML = `
            <!-- Toolbar -->
            <div style="display:flex;gap:8px;margin-bottom:12px;align-items:center;flex-wrap:wrap;">
                <button class="btn btn-sm" onclick="rebuildRFILog(${bidId})" id="rebuildRfiBtn">Rebuild from Documents</button>
                <button class="btn btn-sm" onclick="showAddRFI(${bidId})">+ Add RFI</button>
                <button class="btn btn-sm" onclick="window.open('/api/bidding/bids/${bidId}/rfi-log/export','_blank')">Export to Excel</button>
                <div style="flex:1;"></div>
                <input type="text" id="rfiSearchInput" class="search-input" placeholder="Search RFIs..." style="width:200px;font-size:12px;" oninput="filterRFITable(this.value)">
                <span style="font-size:12px;color:var(--text-secondary);">${rfis.length} RFIs${addendums.length ? ` across ${addendums.length} addendums` : ''}</span>
            </div>
            <div id="rebuildRfiProgress"></div>
            <div id="rfiAddForm" style="display:none;"></div>

            ${rfis.length === 0 ? '<div class="empty-state"><p>No RFIs yet. Click "Rebuild from Documents" to scan RFI/clarification documents, or add entries manually.</p></div>' : `
            <div class="card" style="padding:0;overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:12px;" id="rfiTable">
                    <thead>
                        <tr style="background:var(--bg-hover);border-bottom:2px solid var(--border-default);">
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);width:70px;">RFI #</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Question</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);width:90px;">Asked By</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Response</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);width:50px;">Add.</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);width:70px;">Status</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);width:50px;"></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rfis.map(rfi => {
                            const q = rfi.question || '';
                            const r = rfi.response || '';
                            const qTrunc = q.length > 120 ? q.substring(0, 120) + '...' : q;
                            const rTrunc = r.length > 120 ? r.substring(0, 120) + '...' : r;
                            const statusColor = rfi.status === 'answered' ? 'var(--success-green)' : rfi.status === 'pending' ? '#f59e0b' : 'var(--text-tertiary)';
                            return `
                            <tr class="rfi-row" data-search="${escAttr((q + ' ' + r).toLowerCase())}" style="border-bottom:1px solid var(--border-default);cursor:pointer;" onclick="toggleRFIDetail(${rfi.id})">
                                <td style="padding:6px 10px;font-family:monospace;font-weight:500;">${escHtml(rfi.rfi_number || '—')}</td>
                                <td style="padding:6px 10px;">${escHtml(qTrunc)}</td>
                                <td style="padding:6px 10px;color:var(--text-secondary);font-size:11px;">${escHtml(rfi.asked_by || '—')}</td>
                                <td style="padding:6px 10px;color:var(--text-secondary);">${escHtml(rTrunc) || '<span style="color:var(--text-tertiary);font-style:italic;">No response</span>'}</td>
                                <td style="padding:6px 10px;text-align:center;">${rfi.addendum_number != null ? rfi.addendum_number : '—'}</td>
                                <td style="padding:6px 10px;text-align:center;"><span style="font-size:10px;font-weight:600;color:${statusColor};text-transform:uppercase;">${escHtml(rfi.status || 'answered')}</span></td>
                                <td style="padding:6px 10px;text-align:center;" onclick="event.stopPropagation();">
                                    <button onclick="deleteRFI(${rfi.id}, ${bidId})" style="background:none;border:none;cursor:pointer;color:var(--text-tertiary);font-size:11px;" title="Delete">&times;</button>
                                </td>
                            </tr>
                            <tr><td colspan="7" style="padding:0;">
                                <div id="rfi-detail-${rfi.id}" style="display:none;padding:10px 16px;background:var(--bg-hover);border-bottom:1px solid var(--border-default);">
                                    <div style="margin-bottom:8px;">
                                        <div style="font-size:11px;font-weight:600;color:var(--wollam-navy);margin-bottom:4px;">QUESTION</div>
                                        <div style="font-size:12px;color:var(--text-primary);white-space:pre-wrap;">${escHtml(q)}</div>
                                    </div>
                                    ${r ? `<div style="margin-bottom:8px;">
                                        <div style="font-size:11px;font-weight:600;color:var(--wollam-navy);margin-bottom:4px;">RESPONSE</div>
                                        <div style="font-size:12px;color:var(--text-primary);white-space:pre-wrap;">${escHtml(r)}</div>
                                    </div>` : ''}
                                    <div style="font-size:10px;color:var(--text-tertiary);">
                                        ${rfi.date_asked ? `Asked: ${rfi.date_asked}` : ''}
                                        ${rfi.date_responded ? ` | Responded: ${rfi.date_responded}` : ''}
                                        ${rfi.related_spec ? ` | Spec: ${escHtml(rfi.related_spec)}` : ''}
                                        ${rfi.related_drawing ? ` | Drawing: ${escHtml(rfi.related_drawing)}` : ''}
                                    </div>
                                </div>
                            </td></tr>`;
                        }).join('')}
                    </tbody>
                </table>
            </div>`}
        `;
    } catch (err) {
        sc.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${escHtml(err.message)}</p></div>`;
    }
}

function toggleRFIDetail(rfiId) {
    const el = document.getElementById(`rfi-detail-${rfiId}`);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function filterRFITable(query) {
    const q = query.toLowerCase().trim();
    document.querySelectorAll('.rfi-row').forEach(row => {
        const text = row.getAttribute('data-search') || '';
        row.style.display = !q || text.includes(q) ? '' : 'none';
    });
}

function showAddRFI(bidId) {
    const form = document.getElementById('rfiAddForm');
    if (form.style.display === 'block') { form.style.display = 'none'; return; }
    form.style.display = 'block';
    form.innerHTML = `
        <div class="card" style="padding:12px;margin-bottom:12px;">
            <h4 style="font-size:13px;font-weight:600;margin:0 0 8px;">Add RFI Entry</h4>
            <div style="display:grid;grid-template-columns:100px 1fr;gap:8px;margin-bottom:8px;">
                <div><label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:2px;">RFI #</label>
                    <input type="text" id="rfi_num" class="search-input" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:2px;">Question *</label>
                    <input type="text" id="rfi_question" class="search-input" style="width:100%;"></div>
            </div>
            <div style="margin-bottom:8px;">
                <label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:2px;">Response</label>
                <textarea id="rfi_response" class="search-input" style="width:100%;height:60px;resize:vertical;"></textarea>
            </div>
            <div style="display:flex;gap:8px;justify-content:flex-end;">
                <button class="btn btn-sm" onclick="document.getElementById('rfiAddForm').style.display='none'">Cancel</button>
                <button class="btn btn-primary btn-sm" onclick="addRFIEntry(${bidId})">Add</button>
            </div>
        </div>
    `;
}

async function addRFIEntry(bidId) {
    const question = document.getElementById('rfi_question').value.trim();
    if (!question) { alert('Question is required'); return; }
    try {
        await api(`/bidding/bids/${bidId}/rfi-log`, {
            method: 'POST',
            body: JSON.stringify({
                rfi_number: document.getElementById('rfi_num').value.trim() || null,
                question,
                response: document.getElementById('rfi_response').value.trim() || null,
            }),
        });
        renderDocRFI(window._currentBid);
    } catch (err) { alert('Error: ' + err.message); }
}

async function deleteRFI(rfiId, bidId) {
    if (!confirm('Delete this RFI entry?')) return;
    try {
        await api(`/bidding/rfi-log/${rfiId}`, { method: 'DELETE' });
        renderDocRFI(window._currentBid);
    } catch (err) { alert('Error: ' + err.message); }
}

async function rebuildRFILog(bidId) {
    const btn = document.getElementById('rebuildRfiBtn');
    const prog = document.getElementById('rebuildRfiProgress');
    btn.disabled = true;
    btn.textContent = 'Rebuilding...';
    prog.innerHTML = renderProgressBar(-1, 1, 'Scanning RFI documents...', 'rfi-rebuild');

    try {
        const result = await api(`/bidding/bids/${bidId}/rfi-log/rebuild`, { method: 'POST' });
        prog.innerHTML = renderProgressBar(1, 1, `Done! ${result.created || 0} created, ${result.skipped || 0} skipped (duplicates).`, 'rfi-rebuild', true);
        setTimeout(() => { prog.innerHTML = ''; renderDocRFI(window._currentBid); }, 2000);
    } catch (err) {
        prog.innerHTML = renderProgressBar(0, 1, 'Error: ' + err.message, 'rfi-rebuild', false, true);
        btn.disabled = false;
        btn.textContent = 'Rebuild from Documents';
    }
}

function triggerDocUpload(bidId) {
    // Show metadata form first
    const meta = document.getElementById('docUploadMeta');
    meta.style.display = 'block';
    meta.innerHTML = `
        <div class="card" style="padding:16px;margin-bottom:16px;">
            <h4 style="font-size:13px;font-weight:600;margin:0 0 12px;">Upload Details</h4>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px;">
                <div><label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:2px;">Addendum #</label>
                    <input type="number" id="upload_addendum" class="search-input" value="0" min="0" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:2px;">Category</label>
                    <select id="upload_category" class="search-input" style="width:100%;">
                        <option value="general">General</option>
                        <option value="spec">Spec</option>
                        <option value="drawing">Drawing</option>
                        <option value="contract">Contract</option>
                        <option value="bid_schedule">Bid Schedule</option>
                        <option value="rfi_clarification">RFI / Clarification</option>
                        <option value="addendum_package">Addendum Package</option>
                        <option value="bond_form">Bond Form</option>
                        <option value="insurance">Insurance</option>
                    </select></div>
                <div><label style="font-size:11px;color:var(--text-secondary);display:block;margin-bottom:2px;">Date Received</label>
                    <input type="date" id="upload_date" class="search-input" style="width:100%;" value="${new Date().toISOString().split('T')[0]}"></div>
            </div>
            <div style="display:flex;gap:8px;">
                <button class="btn btn-primary btn-sm" onclick="document.getElementById('docFileInput').click()">Choose Files</button>
                <button class="btn btn-sm" onclick="document.getElementById('docUploadMeta').style.display='none'">Cancel</button>
            </div>
        </div>
    `;
}

async function handleDocDrop(event, bidId) {
    event.preventDefault();
    const files = event.dataTransfer.files;
    if (files.length === 0) return;
    await uploadDocFiles(files, bidId);
}

async function uploadDocFiles(files, bidId) {
    const addendum = document.getElementById('upload_addendum')?.value || '0';
    const category = document.getElementById('upload_category')?.value || 'general';
    const dateReceived = document.getElementById('upload_date')?.value || null;

    for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('addendum_number', addendum);
        formData.append('doc_category', category);
        if (dateReceived) formData.append('date_received', dateReceived);

        try {
            await fetch(`/api/bidding/bids/${bidId}/documents`, {
                method: 'POST',
                body: formData,
            });
        } catch (err) {
            alert(`Error uploading ${file.name}: ${err.message}`);
        }
    }

    document.getElementById('docUploadMeta').style.display = 'none';
    renderBidDocuments(bidId);
}

async function toggleDocDetail(docId) {
    const detail = document.getElementById(`doc-detail-${docId}`);
    if (!detail) return;

    if (detail.style.display === 'block') {
        detail.style.display = 'none';
        return;
    }

    detail.style.display = 'block';
    detail.innerHTML = '<p style="font-size:12px;color:var(--text-tertiary);">Loading...</p>';

    try {
        const doc = await api(`/bidding/documents/${docId}`);
        const textPreview = doc.extracted_text
            ? doc.extracted_text.substring(0, 1000) + (doc.extracted_text.length > 1000 ? '...' : '')
            : 'No text extracted';

        detail.innerHTML = `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
                <div><label style="font-size:11px;color:var(--text-secondary);">Category</label>
                    <select id="doc_cat_${docId}" class="search-input" style="width:100%;font-size:12px;">
                        ${['general','spec','drawing','contract','bid_schedule','rfi_clarification','addendum_package','bond_form','insurance'].map(c =>
                            `<option value="${c}" ${doc.doc_category === c ? 'selected' : ''}>${c.replace(/_/g, ' ')}</option>`
                        ).join('')}
                    </select></div>
                <div><label style="font-size:11px;color:var(--text-secondary);">Addendum #</label>
                    <input type="number" id="doc_add_${docId}" class="search-input" value="${doc.addendum_number || 0}" style="width:100%;font-size:12px;"></div>
            </div>
            <div style="margin-bottom:8px;">
                <label style="font-size:11px;color:var(--text-secondary);">Notes</label>
                <textarea id="doc_notes_${docId}" class="search-input" rows="2" style="width:100%;font-size:12px;resize:vertical;">${escHtml(doc.notes || '')}</textarea>
            </div>
            <button class="btn btn-primary btn-sm" style="font-size:11px;margin-bottom:8px;" onclick="saveDocMeta(${docId})">Save Metadata</button>
            <div style="margin-top:4px;">
                <label style="font-size:11px;font-weight:500;color:var(--text-secondary);">Extracted Text Preview</label>
                <pre style="font-size:11px;background:var(--bg-hover);padding:8px;border-radius:6px;max-height:200px;overflow-y:auto;white-space:pre-wrap;margin-top:4px;">${escHtml(textPreview)}</pre>
            </div>
            <div id="doc-changes-${docId}"></div>
        `;

        // Load change summary if doc was updated
        if (doc.sync_action === 'updated' || doc.previous_extracted_text) {
            loadDocChanges(docId);
        }
    } catch (err) {
        detail.innerHTML = `<p style="color:var(--danger-red);font-size:12px;">${escHtml(err.message)}</p>`;
    }
}

async function saveDocMeta(docId) {
    try {
        await api(`/bidding/documents/${docId}`, {
            method: 'PUT',
            body: JSON.stringify({
                doc_category: document.getElementById(`doc_cat_${docId}`).value,
                addendum_number: parseInt(document.getElementById(`doc_add_${docId}`).value) || 0,
                notes: document.getElementById(`doc_notes_${docId}`).value.trim() || null,
            }),
        });
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function deleteDoc(docId, bidId) {
    if (!confirm('Delete this document?')) return;
    try {
        await api(`/bidding/documents/${docId}`, { method: 'DELETE' });
        renderBidDocuments(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// ── Dropbox Sync Helpers ──

function syncActionBadge(action) {
    if (!action) return '';
    const styles = {
        'new': 'background:var(--success-green);color:white;',
        'updated': 'background:#f59e0b;color:white;',
        'removed': 'background:var(--danger-red);color:white;',
        'unchanged': '',
    };
    if (action === 'unchanged') return '';
    return `<span style="font-size:10px;padding:2px 6px;border-radius:4px;font-weight:600;${styles[action] || ''}">${action.toUpperCase()}</span>`;
}

async function syncFromDropbox(bidId) {
    const btn = document.getElementById('syncDropboxBtn');
    const resultDiv = document.getElementById('syncResult');
    btn.disabled = true;
    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation:spin 1s linear infinite;"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Syncing...`;
    resultDiv.innerHTML = '<span style="font-size:12px;color:var(--text-tertiary);">Starting...</span>';

    try {
        const result = await new Promise((resolve, reject) => {
            const evtSource = new EventSource(`/api/bidding/bids/${bidId}/sync-stream`);
            evtSource.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'progress') {
                        resultDiv.innerHTML = `<span style="font-size:12px;color:var(--text-secondary);">${msg.current} of ${msg.total}: ${escHtml(msg.filename)}</span>`;
                    } else if (msg.type === 'done') {
                        evtSource.close();
                        resolve(msg.result);
                    } else if (msg.type === 'error') {
                        evtSource.close();
                        reject(new Error(msg.message));
                    }
                } catch (e) {}
            };
            evtSource.onerror = () => { evtSource.close(); reject(new Error('Sync stream lost')); };
        });

        const parts = [];
        if (result.new) parts.push(`${result.new} new`);
        if (result.updated) parts.push(`${result.updated} updated`);
        if (result.unchanged) parts.push(`${result.unchanged} unchanged`);
        if (result.removed) parts.push(`${result.removed} removed`);
        resultDiv.innerHTML = `<span style="font-size:12px;color:var(--success-green);font-weight:500;">Synced: ${parts.join(', ') || '0 files'}</span>`;
        setTimeout(() => {
            loadBidDetail(bidId);
            // Show refresh banner if documents changed
            const newCount = result.new || 0;
            const updCount = result.updated || 0;
            if (newCount > 0 || updCount > 0) {
                setTimeout(() => showRefreshBanner(bidId, newCount, updCount), 500);
            }
        }, 1500);
    } catch (err) {
        resultDiv.innerHTML = `<span style="font-size:12px;color:var(--danger-red);">Sync failed: ${escHtml(err.message)}</span>`;
        btn.disabled = false;
        btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Sync from Dropbox`;
    }
}

function linkBidFolder(bidId) {
    openFolderBrowser(bidId);  // Opens native OS folder picker
}

async function linkBidFolderByPath(bidId, value) {
    const path = value.trim();
    if (!path) return;
    try {
        const result = await api(`/bidding/bids/${bidId}/link-folder`, {
            method: 'POST',
            body: JSON.stringify({ folder_path: path }),
        });
        if (result.linked) {
            loadBidDetail(bidId);
        } else {
            alert(result.message || 'Failed to link folder.');
        }
    } catch (err) {
        alert('Error linking folder: ' + err.message);
    }
}

async function selectDetailFolder(bidId, folderPath) {
    try {
        const result = await api(`/bidding/bids/${bidId}/link-folder`, {
            method: 'POST',
            body: JSON.stringify({ folder_path: folderPath }),
        });
        if (result.linked) {
            loadBidDetail(bidId);
        } else {
            alert(result.message || 'Failed to link folder.');
        }
    } catch (err) {
        alert('Error linking folder: ' + err.message);
    }
}

// ── Intelligence Tab ──

function riskBadge(rating) {
    const map = {
        critical: '<span class="badge" style="background:var(--danger-red);color:white;">CRITICAL</span>',
        high: '<span class="badge" style="background:#EF4444;color:white;">HIGH</span>',
        medium: '<span class="badge" style="background:#F59E0B;color:white;">MEDIUM</span>',
        low: '<span class="badge" style="background:var(--success-green);color:white;">LOW</span>',
    };
    return map[rating] || '<span class="badge badge-not-started">—</span>';
}

function agentStatusIcon(status, isStale) {
    if (status === 'not_run') return '<span style="color:var(--text-tertiary);">—</span>';
    if (isStale) return '<span style="color:#F59E0B;" title="Stale — documents changed since last run">&#9888;</span>';
    if (status === 'error') return '<span style="color:var(--danger-red);" title="Error">&#10005;</span>';
    return '<span style="color:var(--success-green);" title="Complete">&#10003;</span>';
}

async function renderBidIntelligence(bid) {
    const bidId = bid.id;
    const tc = document.getElementById('bidTabContent');
    tc.innerHTML = '<div class="empty-state"><p>Loading intelligence...</p></div>';

    try {
        const [intel, reports] = await Promise.all([
            api(`/bidding/bids/${bidId}/intelligence-status`),
            api(`/bidding/bids/${bidId}/reports`),
        ]);

        const agents = intel.agents || {};
        const agentNames = Object.keys(agents).filter(n => n !== 'chief_estimator');
        const hasReports = reports.length > 0;
        const staleCount = intel.agents_needing_reanalysis || 0;
        const subReports = reports.filter(r => r.agent_name !== 'chief_estimator');

        // Compute risk dashboard
        let overallRisk = 'low';
        const riskOrder = { low: 0, medium: 1, high: 2, critical: 3 };
        subReports.forEach(r => {
            if (riskOrder[r.risk_rating] > riskOrder[overallRisk]) overallRisk = r.risk_rating;
        });
        const totalFlags = subReports.reduce((sum, r) => sum + (r.flags_count || 0), 0);

        // Count critical flags and clarifications across all reports
        let criticalCount = 0;
        let clarificationCount = 0;
        subReports.forEach(r => {
            const rj = r.report_json || {};
            (rj.key_risks || []).forEach(kr => { if (kr.severity === 'critical' || kr.severity === 'high') criticalCount++; });
            (rj.flags || []).forEach(() => criticalCount++);
            (rj.missing_documents || []).forEach(() => clarificationCount++);
        });

        const selectedAgent = state.intelAgent || (agentNames.length > 0 ? agentNames[0] : null);

        tc.innerHTML = `
            ${staleCount > 0 ? `
            <div style="padding:8px 12px;margin-bottom:12px;background:#FFFBEB;border-left:3px solid #F59E0B;border-radius:var(--radius-sm);font-size:12px;color:#92400E;">
                &#9888; ${staleCount} agent report(s) are stale — documents have changed since last analysis. Click <strong>Refresh Intelligence</strong> above.
            </div>` : ''}

            ${!hasReports ? `
            <div class="empty-state">
                <h3>No Intelligence Reports</h3>
                <p>${intel.total_documents > 0 ? 'Click "Refresh Intelligence" in the header to analyze bid documents.' : 'Upload or sync documents first, then refresh intelligence.'}</p>
                ${intel.total_documents > 0 && !(intel.agents && Object.values(intel.agents).some(a => a.status !== 'not_run')) ? `
                <div style="margin-top:12px;">
                    <button class="btn btn-primary btn-sm" onclick="refreshIntelligence(${bidId})">Refresh Intelligence Now</button>
                </div>` : ''}
            </div>` : `

            <!-- Bid Risk Dashboard -->
            <div class="card" style="padding:14px 16px;margin-bottom:16px;background:var(--bg-hover);">
                <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-size:13px;font-weight:600;">Risk:</span>
                        ${riskBadge(overallRisk)}
                    </div>
                    <div style="font-size:12px;color:var(--text-secondary);">
                        <span style="color:var(--danger-red);font-weight:600;">${totalFlags}</span> flag(s)
                    </div>
                    <div style="font-size:12px;color:var(--text-secondary);">
                        ${criticalCount > 0 ? `<span style="color:var(--danger-red);font-weight:600;">${criticalCount}</span> critical` : '<span style="color:var(--success-green);">0 critical</span>'}
                    </div>
                    <div style="font-size:12px;color:var(--text-secondary);">
                        ${intel.total_documents} docs analyzed
                    </div>
                    <div style="flex:1;"></div>
                    ${hasReports ? `<span style="font-size:11px;color:var(--text-tertiary);">Last run: ${subReports[0]?.updated_at ? new Date(subReports[0].updated_at).toLocaleString() : '—'}</span>` : ''}
                </div>
            </div>

            <!-- Sidebar + Content Layout -->
            <div style="display:flex;gap:16px;min-height:400px;">
                <!-- Agent Sidebar -->
                <div style="width:200px;flex-shrink:0;">
                    ${agentNames.map(name => {
                        const a = agents[name] || {};
                        const report = subReports.find(r => r.agent_name === name);
                        const isActive = name === selectedAgent;
                        const flagCount = report ? (report.flags_count || 0) : 0;
                        return `
                        <div onclick="state.intelAgent='${name}';renderBidIntelligence(window._currentBid);"
                             style="padding:10px 12px;margin-bottom:4px;border-radius:var(--radius-sm);cursor:pointer;display:flex;align-items:center;gap:8px;
                                    ${isActive ? 'background:var(--bg-selected);border-left:3px solid var(--wollam-navy);' : 'background:var(--bg-surface);border-left:3px solid transparent;'}
                                    ${a.is_stale ? 'opacity:0.7;' : ''}">
                            ${agentStatusIcon(a.status, a.is_stale)}
                            <div style="flex:1;min-width:0;">
                                <div style="font-size:12px;font-weight:${isActive ? '600' : '500'};color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escHtml(a.display_name || name)}</div>
                                ${a.status !== 'not_run' ? `<div style="font-size:10px;color:var(--text-tertiary);">${flagCount} flags ${a.risk_rating ? '· ' + a.risk_rating.toUpperCase() : ''}</div>` : '<div style="font-size:10px;color:var(--text-tertiary);">Not run</div>'}
                            </div>
                        </div>`;
                    }).join('')}
                </div>

                <!-- Agent Content Area -->
                <div style="flex:1;min-width:0;">
                    ${selectedAgent ? renderAgentContent(selectedAgent, agents[selectedAgent], subReports.find(r => r.agent_name === selectedAgent), bidId) : '<div class="empty-state"><p>Select an agent from the sidebar.</p></div>'}
                </div>
            </div>
            `}
        `;
    } catch (err) {
        tc.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${escHtml(err.message)}</p></div>`;
    }
}

function renderAgentContent(agentName, agentInfo, report, bidId) {
    if (!report) {
        return `<div class="empty-state" style="padding:20px;"><p>${escHtml(agentInfo?.display_name || agentName)} has not been run yet. Click "Refresh Intelligence" to analyze.</p></div>`;
    }

    const rj = report.report_json || {};
    let html = '';

    // Agent header
    html += `<div style="margin-bottom:12px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <h3 style="font-size:15px;font-weight:600;margin:0;color:var(--text-primary);">${escHtml(agentInfo?.display_name || agentName)}</h3>
            ${riskBadge(report.risk_rating)}
            ${report.is_stale ? '<span style="font-size:10px;color:#F59E0B;font-weight:600;">&#9888; STALE</span>' : ''}
        </div>
        ${report.summary_text ? `<p style="font-size:12px;color:var(--text-secondary);margin:0 0 12px;">${escHtml(report.summary_text)}</p>` : ''}
    </div>`;

    // Per-agent custom summary at top
    if (agentName === 'legal_analyst') html += renderLegalSummary(rj);
    else if (agentName === 'qaqc_manager') html += renderQAQCSummary(rj);
    else if (agentName === 'subcontract_manager') html += renderSubSummary(rj);
    else if (agentName === 'document_control') html += renderDocControlSummary(rj);

    // Priority 1: Critical Flags
    const flags = rj.flags || [];
    const criticalRisks = (rj.key_risks || []).filter(r => r.severity === 'critical' || r.severity === 'high');
    if (flags.length > 0 || criticalRisks.length > 0) {
        html += `<div style="margin-bottom:16px;">
            <div style="font-size:12px;font-weight:600;color:var(--danger-red);margin-bottom:8px;text-transform:uppercase;">&#9888; Critical Flags (${flags.length + criticalRisks.length})</div>`;
        flags.forEach(f => {
            html += `<div style="padding:8px 12px;margin-bottom:4px;background:rgba(239,68,68,0.05);border-left:3px solid var(--danger-red);border-radius:0 var(--radius-sm) var(--radius-sm) 0;font-size:12px;color:#991B1B;">${escHtml(typeof f === 'string' ? f : JSON.stringify(f))}</div>`;
        });
        criticalRisks.forEach(r => {
            html += `<div style="padding:8px 12px;margin-bottom:4px;background:rgba(239,68,68,0.05);border-left:3px solid ${r.severity === 'critical' ? 'var(--danger-red)' : '#F59E0B'};border-radius:0 var(--radius-sm) var(--radius-sm) 0;font-size:12px;">
                <span style="font-weight:600;color:var(--text-primary);">${escHtml(r.risk || '')}</span>
                ${r.clause ? `<span style="color:var(--text-tertiary);"> (${escHtml(r.clause)})</span>` : ''}
                ${r.recommendation ? `<div style="color:var(--text-secondary);margin-top:2px;font-style:italic;">${escHtml(r.recommendation)}</div>` : ''}
            </div>`;
        });
        html += `</div>`;
    }

    // Priority 2: Clarifications & RFI Candidates
    const missing = rj.missing_documents || [];
    const missingInfo = rj.missing_information || [];
    const clarItems = [...missing.map(m => ({text: m, type: 'missing'})), ...missingInfo.map(m => ({text: typeof m === 'string' ? m : m.detail || m.title || JSON.stringify(m), type: 'clarification'}))];
    if (clarItems.length > 0) {
        html += `<div style="margin-bottom:16px;">
            <div style="font-size:12px;font-weight:600;color:#92400E;margin-bottom:8px;text-transform:uppercase;">Clarifications & RFI Candidates (${clarItems.length})</div>`;
        clarItems.forEach((c, i) => {
            html += `<div style="padding:8px 12px;margin-bottom:4px;background:rgba(245,158,11,0.05);border-left:3px solid #F59E0B;border-radius:0 var(--radius-sm) var(--radius-sm) 0;font-size:12px;display:flex;align-items:center;gap:8px;">
                <span style="flex:1;color:var(--text-primary);">${escHtml(c.text)}</span>
                <button onclick="event.stopPropagation();addToRFIFromIntel(${bidId}, '${escAttr(c.text.substring(0,200))}')" class="btn btn-sm" style="font-size:10px;padding:2px 6px;white-space:nowrap;" title="Add to RFI Log">+ RFI</button>
            </div>`;
        });
        html += `</div>`;
    }

    // Priority 3: Key Requirements (medium/low severity risks + agent-specific content)
    const keyRisks = (rj.key_risks || []).filter(r => r.severity !== 'critical' && r.severity !== 'high');
    const hasKeyContent = keyRisks.length > 0 || (agentName === 'legal_analyst' && rj.insurance) || (agentName === 'qaqc_manager' && (rj.certifications_required || []).length > 0) || (agentName === 'subcontract_manager' && (rj.self_perform_recommended || []).length > 0);
    if (hasKeyContent) {
        html += `<div style="margin-bottom:16px;">
            <div style="font-size:12px;font-weight:600;color:var(--text-primary);margin-bottom:8px;text-transform:uppercase;">Key Requirements</div>`;
        if (agentName === 'legal_analyst') html += renderLegalKeyReqs(rj);
        else if (agentName === 'qaqc_manager') html += renderQAQCKeyReqs(rj);
        else if (agentName === 'subcontract_manager') html += renderSubKeyReqs(rj);
        else if (agentName === 'document_control') html += renderDocControlKeyReqs(rj);
        keyRisks.forEach(r => {
            const sevColor = r.severity === 'medium' ? '#F59E0B' : 'var(--text-tertiary)';
            html += `<div style="padding:6px 12px;margin-bottom:3px;border-left:3px solid ${sevColor};font-size:12px;">
                <span style="font-weight:500;">${escHtml(r.risk || '')}</span>
                ${r.clause ? `<span style="color:var(--text-tertiary);"> (${escHtml(r.clause)})</span>` : ''}
            </div>`;
        });
        html += `</div>`;
    }

    // Priority 4: Reference Details (collapsed by default)
    const docIndex = rj.document_index || [];
    const addendumChanges = rj.addendum_changes || [];
    if (docIndex.length > 0 || addendumChanges.length > 0) {
        const refId = `ref-${agentName}`;
        html += `<div style="margin-bottom:16px;">
            <div onclick="document.getElementById('${refId}').style.display = document.getElementById('${refId}').style.display === 'none' ? 'block' : 'none'; this.querySelector('.ref-chevron').textContent = document.getElementById('${refId}').style.display === 'none' ? '▶' : '▼';"
                 style="font-size:12px;font-weight:600;color:var(--text-tertiary);margin-bottom:8px;text-transform:uppercase;cursor:pointer;">
                <span class="ref-chevron">&#9654;</span> Reference Details
            </div>
            <div id="${refId}" style="display:none;">`;
        if (docIndex.length > 0) {
            html += `<div style="margin-bottom:8px;font-size:11px;color:var(--text-secondary);">${docIndex.length} documents reviewed</div>`;
            docIndex.slice(0, 20).forEach(d => {
                html += `<div style="font-size:11px;padding:2px 0;color:var(--text-tertiary);">${escHtml(d.filename || '')} ${d.category ? `[${escHtml(d.category)}]` : ''}</div>`;
            });
            if (docIndex.length > 20) html += `<div style="font-size:11px;color:var(--text-tertiary);">... and ${docIndex.length - 20} more</div>`;
        }
        if (addendumChanges.length > 0) {
            html += `<div style="margin-top:8px;font-size:11px;font-weight:600;color:var(--text-secondary);">Addendum Changes</div>`;
            addendumChanges.forEach(c => {
                html += `<div style="font-size:11px;padding:4px 0;border-bottom:1px solid var(--border-default);">Add. ${c.addendum || '?'}: ${escHtml(c.changes || '')}</div>`;
            });
        }
        html += `</div></div>`;
    }

    return html;
}

// Per-agent summary renderers (shown at top of agent content)

function renderLegalSummary(rj) {
    let html = '<div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">';
    const ld = rj.liquidated_damages || {};
    if (ld.has_ld) {
        html += `<div class="card" style="padding:10px 14px;flex:1;min-width:140px;">
            <div style="font-size:10px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;">LDs</div>
            <div style="font-size:16px;font-weight:700;">${ld.amount_per_day ? '$' + fmt(ld.amount_per_day) + '/day' : 'Yes'}</div>
            ${ld.cap ? `<div style="font-size:10px;color:var(--text-secondary);">Cap: $${fmt(ld.cap)}</div>` : '<div style="font-size:10px;color:var(--danger-red);font-weight:600;">NO CAP</div>'}
        </div>`;
    }
    const bond = rj.bonding || {};
    if (bond.estimated_cost_pct) {
        html += `<div class="card" style="padding:10px 14px;flex:1;min-width:140px;">
            <div style="font-size:10px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;">Bond</div>
            <div style="font-size:16px;font-weight:700;">${bond.estimated_cost_pct}%</div>
            <div style="font-size:10px;color:var(--text-secondary);">${[bond.bid_bond ? 'Bid' : '', bond.performance_bond ? 'Perf' : '', bond.payment_bond ? 'Payment' : ''].filter(Boolean).join(' · ')}</div>
        </div>`;
    }
    const ret = rj.retainage || {};
    if (ret.percentage) {
        html += `<div class="card" style="padding:10px 14px;flex:1;min-width:140px;">
            <div style="font-size:10px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;">Retainage</div>
            <div style="font-size:16px;font-weight:700;">${ret.percentage}%</div>
            ${ret.release_conditions ? `<div style="font-size:10px;color:var(--text-secondary);">${escHtml(ret.release_conditions)}</div>` : ''}
        </div>`;
    }
    const pay = rj.payment_terms || {};
    if (pay.frequency) {
        html += `<div class="card" style="padding:10px 14px;flex:1;min-width:140px;">
            <div style="font-size:10px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;">Payment</div>
            <div style="font-size:14px;font-weight:600;">${escHtml(pay.frequency)}</div>
            ${pay.net_days ? `<div style="font-size:10px;color:var(--text-secondary);">Net ${pay.net_days} days</div>` : ''}
        </div>`;
    }
    html += '</div>';
    return html;
}

function renderQAQCSummary(rj) {
    const tests = rj.testing_requirements || [];
    if (tests.length === 0) return '';
    return `<div style="margin-bottom:16px;">
        <div style="font-size:11px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;margin-bottom:6px;">Testing Requirements (${tests.length})</div>
        <table style="width:100%;border-collapse:collapse;font-size:11px;">
            <tr style="background:var(--bg-hover);"><th style="padding:4px 8px;text-align:left;">Test</th><th style="padding:4px 8px;text-align:left;">Frequency</th><th style="padding:4px 8px;text-align:left;">Spec</th><th style="padding:4px 8px;text-align:center;">Impact</th></tr>
            ${tests.map(t => `<tr style="border-bottom:1px solid var(--border-default);">
                <td style="padding:4px 8px;">${escHtml(t.test || '')}</td>
                <td style="padding:4px 8px;">${escHtml(t.frequency || '')}</td>
                <td style="padding:4px 8px;color:var(--text-tertiary);">${escHtml(t.spec_section || '')}</td>
                <td style="padding:4px 8px;text-align:center;">${t.cost_impact === 'high' ? '<span style="color:var(--danger-red);font-weight:600;">HIGH</span>' : t.cost_impact === 'moderate' ? '<span style="color:#F59E0B;">MOD</span>' : '<span style="color:var(--text-tertiary);">LOW</span>'}</td>
            </tr>`).join('')}
        </table>
    </div>`;
}

function renderSubSummary(rj) {
    const subs = rj.recommended_sub_scopes || [];
    if (subs.length === 0) return '';
    return `<div style="margin-bottom:16px;">
        <div style="font-size:11px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;margin-bottom:6px;">Recommended Sub Scopes (${subs.length})</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;">
            ${subs.map(s => `<div style="padding:8px 10px;border:1px solid var(--border-default);border-radius:var(--radius-sm);font-size:11px;">
                <div style="font-weight:600;">${escHtml(s.discipline || '')}</div>
                <div style="color:var(--text-secondary);margin-top:2px;">${escHtml(s.scope_summary || '')}</div>
                ${s.estimated_value_pct ? `<div style="color:var(--text-tertiary);margin-top:2px;">~${s.estimated_value_pct}% of bid</div>` : ''}
            </div>`).join('')}
        </div>
    </div>`;
}

function renderDocControlSummary(rj) {
    const docs = rj.document_index || [];
    const missing = rj.missing_documents || [];
    if (docs.length === 0 && missing.length === 0) return '';

    const cats = {};
    docs.forEach(d => { const c = d.category || 'general'; cats[c] = (cats[c] || 0) + 1; });

    return `<div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
        <div class="card" style="padding:10px 14px;min-width:120px;">
            <div style="font-size:10px;font-weight:600;color:var(--text-tertiary);text-transform:uppercase;">Documents</div>
            <div style="font-size:16px;font-weight:700;">${rj.documents_reviewed || docs.length}</div>
        </div>
        ${Object.entries(cats).slice(0, 4).map(([k, v]) => `
        <div style="padding:6px 10px;font-size:11px;background:var(--bg-hover);border-radius:var(--radius-sm);">
            <span style="font-weight:600;">${v}</span> ${k.replace(/_/g, ' ')}
        </div>`).join('')}
        ${missing.length > 0 ? `<div style="padding:6px 10px;font-size:11px;background:rgba(245,158,11,0.08);border-radius:var(--radius-sm);color:#92400E;font-weight:600;">
            &#9888; ${missing.length} missing
        </div>` : ''}
    </div>`;
}

// Key Requirements sub-renderers

function renderLegalKeyReqs(rj) {
    let html = '';
    const ins = rj.insurance || {};
    if (ins.gl_minimum || ins.auto_minimum || ins.umbrella_minimum || ins.workers_comp) {
        html += `<div style="margin-bottom:8px;font-size:12px;">
            <span style="font-weight:500;">Insurance Minimums:</span>
            ${ins.gl_minimum ? ` GL $${typeof ins.gl_minimum === 'number' ? fmt(ins.gl_minimum) : ins.gl_minimum}` : ''}
            ${ins.auto_minimum ? ` Auto $${typeof ins.auto_minimum === 'number' ? fmt(ins.auto_minimum) : ins.auto_minimum}` : ''}
            ${ins.umbrella_minimum ? ` Umbrella $${typeof ins.umbrella_minimum === 'number' ? fmt(ins.umbrella_minimum) : ins.umbrella_minimum}` : ''}
        </div>`;
    }
    return html;
}

function renderQAQCKeyReqs(rj) {
    let html = '';
    const certs = rj.certifications_required || [];
    if (certs.length > 0) {
        html += `<div style="margin-bottom:8px;"><span style="font-size:11px;font-weight:600;">Certifications:</span> `;
        html += certs.map(c => `<span style="font-size:11px;padding:2px 6px;background:var(--bg-hover);border-radius:4px;margin:0 2px;">${escHtml(c)}</span>`).join('');
        html += `</div>`;
    }
    const subs = rj.submittals_required || [];
    if (subs.length > 0) {
        html += `<div style="margin-bottom:8px;font-size:11px;color:var(--text-secondary);">${subs.length} submittals required</div>`;
    }
    return html;
}

function renderSubKeyReqs(rj) {
    let html = '';
    const self = rj.self_perform_recommended || [];
    if (self.length > 0) {
        html += `<div style="margin-bottom:8px;"><span style="font-size:11px;font-weight:600;">Self-Perform Recommended:</span>`;
        self.forEach(s => {
            html += `<div style="font-size:11px;padding:2px 0;margin-left:12px;">${escHtml(s.discipline || '')} — ${escHtml(s.reason || '')}</div>`;
        });
        html += `</div>`;
    }
    return html;
}

function renderDocControlKeyReqs(rj) {
    const changes = rj.addendum_changes || [];
    if (changes.length === 0) return '';
    let html = `<div style="margin-bottom:8px;font-size:11px;font-weight:600;">Addendum Changes:</div>`;
    changes.forEach(c => {
        html += `<div style="font-size:11px;padding:4px 0;border-bottom:1px solid var(--border-default);">Add. ${c.addendum || '?'}: ${escHtml(c.changes || '')}</div>`;
    });
    return html;
}

// Add to RFI from intelligence finding
async function addToRFIFromIntel(bidId, questionText) {
    try {
        await api(`/bidding/bids/${bidId}/rfi-log`, {
            method: 'POST',
            body: JSON.stringify({
                question: questionText,
                status: 'pending',
                notes: 'Added from intelligence finding',
            }),
        });
        alert('Added to RFI Log');
    } catch (err) {
        alert('Error adding to RFI: ' + err.message);
    }
}

function toggleAgentReport(agentName) {
    const el = document.getElementById(`report_${agentName}`);
    const arrow = document.getElementById(`arrow_${agentName}`);
    if (!el) return;
    const open = el.style.display === 'block';
    el.style.display = open ? 'none' : 'block';
    if (arrow) arrow.style.transform = open ? '' : 'rotate(90deg)';
}

// Legacy agent report renderers kept as stubs for any external callers
function renderLegalReport(rj) { return ''; }
function renderDocControlReport(rj) { return ''; }
function renderQAQCReport(rj) { return ''; }
function renderSubReport(rj) { return ''; }
function renderChiefBrief(report) { return ''; }
function renderAgentReport(report) { return ''; }

// ── Global Refresh Pipeline ──

async function refreshIntelligence(bidId) {
    const btn = document.getElementById('globalRefreshBtn');
    const prog = document.getElementById('refreshProgress');
    if (btn) { btn.disabled = true; btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation:spin 1s linear infinite;"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refreshing...'; }
    if (prog) prog.innerHTML = renderProgressBar(0, 1, 'Starting intelligence refresh...', 'refresh');

    try {
        const startTime = Date.now();
        await new Promise((resolve, reject) => {
            const evtSource = new EventSource(`/api/bidding/bids/${bidId}/refresh-stream`);
            evtSource.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'stage') {
                        const elapsed = Math.round((Date.now() - startTime) / 1000);
                        if (prog) prog.innerHTML = renderProgressBar(-1, 1, `${msg.message} (${elapsed}s)`, 'refresh');
                    } else if (msg.type === 'progress') {
                        const elapsed = Math.round((Date.now() - startTime) / 1000);
                        if (prog) prog.innerHTML = renderProgressBar(msg.current, msg.total, `${msg.stage}: ${msg.agent || ''} (${msg.current}/${msg.total}) — ${elapsed}s`, 'refresh');
                    } else if (msg.type === 'done') {
                        evtSource.close();
                        resolve(msg.result);
                    } else if (msg.type === 'error') {
                        evtSource.close();
                        reject(new Error(msg.message));
                    }
                } catch (e) { evtSource.close(); reject(e); }
            };
            evtSource.onerror = () => { evtSource.close(); reject(new Error('Connection lost')); };
        });

        if (prog) prog.innerHTML = renderProgressBar(1, 1, 'Refresh complete!', 'refresh', true);
        setTimeout(() => { if (prog) prog.innerHTML = ''; }, 3000);
        loadBidDetail(bidId);
    } catch (err) {
        if (prog) prog.innerHTML = renderProgressBar(0, 1, 'Error: ' + err.message, 'refresh', false, true);
        if (btn) { btn.disabled = false; btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refresh Intelligence'; }
    }
}

// Legacy run functions call refresh
async function runAllAgents(bidId) { return refreshIntelligence(bidId); }
async function runSingleAgent(bidId) { return refreshIntelligence(bidId); }

// Show banner after sync with changes
function showRefreshBanner(bidId, newCount, updatedCount) {
    const banner = document.getElementById('refreshBanner');
    if (!banner) return;
    if (newCount === 0 && updatedCount === 0) return;
    banner.innerHTML = `
        <div class="card" style="padding:10px 16px;margin-bottom:12px;border-left:3px solid var(--wollam-navy);background:rgba(0,52,126,0.04);display:flex;align-items:center;gap:12px;">
            <span style="font-size:13px;color:var(--text-primary);">${newCount + updatedCount} document change(s) detected. Refresh intelligence?</span>
            <button class="btn btn-primary btn-sm" onclick="refreshIntelligence(${bidId});this.parentElement.parentElement.innerHTML='';">Refresh Now</button>
            <button class="btn btn-sm" onclick="this.parentElement.parentElement.innerHTML='';">Dismiss</button>
        </div>
    `;
}

// OLD AGENT RENDERERS REMOVED — replaced by renderAgentContent with priority sections
// (keeping this comment as a marker)

// ── Rate Lookup (SOV) ──

async function lookupSOVRate(itemId, bidId) {
    const panel = document.getElementById(`rate-panel-${itemId}`);
    if (!panel) return;

    if (panel.style.display === 'block') { panel.style.display = 'none'; return; }
    panel.style.display = 'block';
    panel.innerHTML = '<p style="font-size:12px;color:var(--text-tertiary);padding:8px;">Looking up rates...</p>';

    try {
        const result = await api(`/bidding/bids/${bidId}/sov/${itemId}/lookup`, { method: 'POST' });
        const matches = result.matches || [];

        if (matches.length === 0) {
            panel.innerHTML = '<p style="font-size:12px;color:var(--text-tertiary);padding:8px;">No matching historical rates found.</p>';
            return;
        }

        panel.innerHTML = `
            <div style="padding:8px;background:var(--bg-hover);border-radius:6px;margin-top:4px;">
                <table style="width:100%;border-collapse:collapse;font-size:11px;">
                    <thead><tr style="border-bottom:1px solid var(--border-default);">
                        <th style="padding:4px 6px;text-align:left;">Cost Code</th>
                        <th style="padding:4px 6px;text-align:right;">MH/Unit</th>
                        <th style="padding:4px 6px;text-align:right;">$/Unit</th>
                        <th style="padding:4px 6px;text-align:right;">Min</th>
                        <th style="padding:4px 6px;text-align:right;">Max</th>
                        <th style="padding:4px 6px;text-align:center;">Jobs</th>
                        <th style="padding:4px 6px;text-align:center;">Conf.</th>
                        <th style="padding:4px 6px;text-align:center;"></th>
                    </tr></thead>
                    <tbody>
                        ${matches.slice(0, 8).map(m => `
                        <tr style="border-bottom:1px solid var(--border-default);">
                            <td style="padding:4px 6px;font-family:monospace;" title="${escAttr(m.description)}">${escHtml(m.cost_code)}</td>
                            <td style="padding:4px 6px;text-align:right;">${fmtRate(m.mh_per_unit)}</td>
                            <td style="padding:4px 6px;text-align:right;font-weight:500;">$${fmtRate(m.dollar_per_unit)}</td>
                            <td style="padding:4px 6px;text-align:right;color:var(--text-tertiary);">${fmtRate(m.min_rate)}</td>
                            <td style="padding:4px 6px;text-align:right;color:var(--text-tertiary);">${fmtRate(m.max_rate)}</td>
                            <td style="padding:4px 6px;text-align:center;">${m.job_count}</td>
                            <td style="padding:4px 6px;text-align:center;">${m.confidence === 'high' ? '<span style="color:var(--success-green);font-weight:600;">HIGH</span>' : m.confidence === 'medium' ? '<span style="color:#F59E0B;">MED</span>' : '<span style="color:var(--text-tertiary);">LOW</span>'}</td>
                            <td style="padding:4px 6px;text-align:center;">
                                <button class="btn btn-sm" style="font-size:10px;padding:2px 6px;"
                                    onclick="applyRate(${itemId}, ${bidId}, ${m.dollar_per_unit}, '${escAttr(m.cost_code)}', ${m.job_count}, '${escAttr(m.confidence)}')">Apply</button>
                            </td>
                        </tr>`).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (err) {
        panel.innerHTML = `<p style="font-size:12px;color:var(--danger-red);padding:8px;">${escHtml(err.message)}</p>`;
    }
}

async function applyRate(itemId, bidId, rate, costCode, jobCount, confidence) {
    try {
        await api(`/bidding/sov/${itemId}`, {
            method: 'PUT',
            body: JSON.stringify({
                unit_price: rate,
                rate_source: `Historical: CC ${costCode} (${jobCount} jobs)`,
                rate_confidence: confidence,
                cost_code: costCode,
            }),
        });
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// ── Document Change Summaries ──

async function loadDocChanges(docId) {
    const container = document.getElementById(`doc-changes-${docId}`);
    if (!container) return;
    container.innerHTML = '<p style="font-size:11px;color:var(--text-tertiary);margin-top:8px;">Loading change summary...</p>';

    try {
        const result = await api(`/bidding/documents/${docId}/changes`);
        if (!result.has_changes) {
            container.innerHTML = '';
            return;
        }

        const c = result.changes;
        let html = `<div style="margin-top:8px;padding:10px;border:1px solid #F59E0B;border-radius:6px;background:rgba(245,158,11,0.04);">
            <span style="font-size:11px;font-weight:600;color:#92400E;">Changes Detected</span>`;

        if (c.summary) {
            html += `<p style="font-size:12px;color:var(--text-secondary);margin:4px 0 8px;">${escHtml(c.summary)}</p>`;
        }

        const additions = c.additions || [];
        const deletions = c.deletions || [];
        const modifications = c.modifications || [];

        if (additions.length) {
            html += `<div style="margin-bottom:4px;">`;
            additions.forEach(a => { html += `<div style="font-size:11px;color:#166534;">+ ${escHtml(a)}</div>`; });
            html += `</div>`;
        }
        if (deletions.length) {
            html += `<div style="margin-bottom:4px;">`;
            deletions.forEach(d => { html += `<div style="font-size:11px;color:#991B1B;">- ${escHtml(d)}</div>`; });
            html += `</div>`;
        }
        if (modifications.length) {
            html += `<div style="margin-bottom:4px;">`;
            modifications.forEach(m => { html += `<div style="font-size:11px;color:#92400E;">~ ${escHtml(m)}</div>`; });
            html += `</div>`;
        }

        const impact = c.potential_sov_impact || [];
        if (impact.length) {
            html += `<div style="margin-top:4px;"><span style="font-size:10px;font-weight:600;color:#92400E;">SOV Impact:</span>`;
            impact.forEach(i => { html += `<div style="font-size:11px;color:#92400E;">${escHtml(i)}</div>`; });
            html += `</div>`;
        }

        html += `</div>`;
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = '';
    }
}

async function autoRateAll(bidId) {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = 'Rating...';

    let progressEl = document.getElementById('autoRateProgress');
    if (!progressEl) {
        progressEl = document.createElement('div');
        progressEl.id = 'autoRateProgress';
        progressEl.style.cssText = 'margin:12px 0;';
        btn.parentElement.after(progressEl);
    }
    progressEl.innerHTML = renderProgressBar(-1, 1, 'Auto-rating all SOV items...', 'rate');

    try {
        const result = await api(`/bidding/bids/${bidId}/sov/auto-rate`, { method: 'POST' });
        progressEl.innerHTML = renderProgressBar(1, 1, `Done! ${result.matched} matched, ${result.ambiguous} ambiguous, ${result.no_match} no match`, 'rate', true);
        setTimeout(() => { if (progressEl.parentNode) progressEl.remove(); }, 3000);
        renderBidSOV(bidId);
    } catch (err) {
        progressEl.innerHTML = renderProgressBar(0, 1, 'Error: ' + err.message, 'rate', false, true);
        btn.disabled = false;
        btn.textContent = 'Auto-Rate All';
    }
}

// ── SOV Scope Toggle ──

async function toggleItemScope(itemId, bidId, inScope) {
    try {
        await api(`/bidding/bids/${bidId}/sov/set-scope`, {
            method: 'POST',
            body: JSON.stringify({ item_ids: [itemId], in_scope: inScope ? 1 : 0 }),
        });
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
        renderBidSOV(bidId);
    }
}

async function toggleAllScope(bidId, inScope) {
    try {
        const items = await api(`/bidding/bids/${bidId}/sov`);
        const ids = items.map(i => i.id);
        await api(`/bidding/bids/${bidId}/sov/set-scope`, {
            method: 'POST',
            body: JSON.stringify({ item_ids: ids, in_scope: inScope ? 1 : 0 }),
        });
        renderBidSOV(bidId);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// ── Progress Bar ──

function renderProgressBar(current, total, label, id, done, error) {
    const pct = total > 0 && current >= 0 ? Math.round((current / total) * 100) : 0;
    const indeterminate = current < 0;
    const barColor = error ? 'var(--danger-red)' : done ? 'var(--success-green)' : 'var(--wollam-navy)';
    const barWidth = indeterminate ? '30%' : `${pct}%`;
    const animation = indeterminate ? 'animation:progressIndeterminate 1.5s ease-in-out infinite;' : '';

    return `<div style="background:var(--bg-surface);border:1px solid var(--border-default);border-radius:var(--radius-sm);padding:10px 14px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <span style="font-size:12px;color:${error ? 'var(--danger-red)' : 'var(--text-primary)'};">${escHtml(label)}</span>
            ${!indeterminate && !done && !error ? `<span style="font-size:11px;color:var(--text-tertiary);">${pct}%</span>` : ''}
        </div>
        <div style="height:6px;background:var(--bg-hover);border-radius:3px;overflow:hidden;">
            <div style="height:100%;width:${barWidth};background:${barColor};border-radius:3px;transition:width 0.3s ease;${animation}"></div>
        </div>
    </div>`;
}

// ── SOV Intelligence Mapper ──

function sovIntelBadge(intel) {
    if (!intel || !intel.finding_count) return '<span style="color:var(--text-tertiary);font-size:11px;">—</span>';
    const colorMap = {critical: '#EF4444', high: '#EF4444', medium: '#F59E0B', low: 'var(--success-green)', info: 'var(--text-tertiary)'};
    const color = colorMap[intel.max_severity] || 'var(--text-tertiary)';
    const stale = intel.is_stale ? ' &#9888;' : '';
    return `<span class="badge" style="background:${color};color:white;font-size:10px;padding:2px 6px;">${intel.finding_count}${stale}</span>`;
}

async function mapSOVIntelligence(bidId) {
    const btn = document.getElementById('mapIntelBtn');
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = 'Mapping...';

    // Insert progress bar
    let progressEl = document.getElementById('mapIntelProgress');
    if (!progressEl) {
        progressEl = document.createElement('div');
        progressEl.id = 'mapIntelProgress';
        progressEl.style.cssText = 'margin:12px 0;';
        btn.parentElement.after(progressEl);
    }
    progressEl.innerHTML = renderProgressBar(0, 1, 'Starting intelligence mapping...', 'intel');

    try {
        const result = await new Promise((resolve, reject) => {
            const startTime = Date.now();
            const evtSource = new EventSource(`/api/bidding/bids/${bidId}/sov/map-intelligence-stream`);
            evtSource.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'progress') {
                        const elapsed = Math.round((Date.now() - startTime) / 1000);
                        const perItem = msg.current > 1 ? elapsed / (msg.current - 1) : 0;
                        const remaining = perItem > 0 ? Math.round(perItem * (msg.total - msg.current + 1)) : 0;
                        const eta = remaining > 60 ? `~${Math.round(remaining/60)}m left` : remaining > 0 ? `~${remaining}s left` : '';
                        progressEl.innerHTML = renderProgressBar(msg.current, msg.total, `Mapping item ${msg.item} (${msg.current} of ${msg.total}) ${eta}`, 'intel');
                    } else if (msg.type === 'done') {
                        evtSource.close();
                        resolve(msg.result);
                    } else if (msg.type === 'error') {
                        evtSource.close();
                        reject(new Error(msg.message));
                    }
                } catch (e) { evtSource.close(); reject(e); }
            };
            evtSource.onerror = (e) => {
                // EventSource auto-reconnects on transient errors; only reject if closed
                if (evtSource.readyState === EventSource.CLOSED) {
                    reject(new Error('Connection lost'));
                }
            };
        });

        const mapped = result.items_mapped || 0;
        const findings = result.total_findings || 0;
        progressEl.innerHTML = renderProgressBar(1, 1, `Done! ${mapped} item(s), ${findings} finding(s) in ${result.duration_seconds}s`, 'intel', true);
        setTimeout(() => { if (progressEl.parentNode) progressEl.remove(); }, 4000);
        renderBidSOV(bidId);
    } catch (err) {
        progressEl.innerHTML = renderProgressBar(0, 1, 'Error: ' + err.message, 'intel', false, true);
        btn.disabled = false;
        btn.textContent = 'Map Intelligence';
    }
}

// ── Bid Item Detail View (Collapsible Accordion) ──

async function toggleSOVItemDetail(itemId, bidId) {
    const panel = document.getElementById(`detail-panel-${itemId}`);
    if (!panel) return;

    if (panel.style.display === 'block') { panel.style.display = 'none'; return; }

    // Close other detail panels
    document.querySelectorAll('[id^="detail-panel-"]').forEach(p => { if (p.id !== `detail-panel-${itemId}`) p.style.display = 'none'; });

    panel.style.display = 'block';
    panel.innerHTML = '<p style="font-size:12px;color:var(--text-tertiary);padding:12px;">Loading item detail...</p>';

    try {
        const [intelData, rateData] = await Promise.all([
            api(`/bidding/bids/${bidId}/sov/${itemId}/intelligence`).catch(() => null),
            api(`/bidding/bids/${bidId}/sov/${itemId}/rates`).catch(() => null),
        ]);
        panel.innerHTML = renderBidItemDetail(intelData, rateData, itemId, bidId);
    } catch (err) {
        panel.innerHTML = `<p style="font-size:12px;color:var(--danger-red);padding:12px;">Error: ${escHtml(err.message)}</p>`;
    }
}

function renderBidItemDetail(intelData, rateData, itemId, bidId) {
    const severityColors = {critical: '#EF4444', high: '#EF4444', medium: '#F59E0B', low: 'var(--success-green)', info: 'var(--text-tertiary)'};

    let html = '<div style="padding:12px 16px;background:var(--bg-hover);border-top:1px solid var(--border-default);">';

    // Stale warning
    if (intelData && intelData.is_stale) {
        html += '<div style="padding:6px 10px;margin-bottom:10px;background:#FFFBEB;border-left:3px solid #F59E0B;border-radius:var(--radius-sm);font-size:11px;color:#92400E;">&#9888; Intelligence may be outdated — re-map recommended.</div>';
    }

    // Estimator notes
    if (intelData && intelData.estimator_notes) {
        html += `<div style="padding:8px 10px;margin-bottom:10px;background:var(--bg-surface);border:1px solid var(--border-default);border-radius:var(--radius-sm);">
            <div style="font-size:11px;font-weight:600;color:var(--wollam-navy);margin-bottom:4px;">ESTIMATOR NOTES</div>
            <div style="font-size:12px;color:var(--text-primary);">${escHtml(intelData.estimator_notes)}</div>
        </div>`;
    }

    // Spec sections
    if (intelData && intelData.spec_sections_summary) {
        html += `<div style="font-size:11px;color:var(--text-secondary);margin-bottom:10px;"><strong>Relevant Specs:</strong> ${escHtml(intelData.spec_sections_summary)}</div>`;
    }

    // Accordion sections by domain
    const domainSections = [
        { key: 'historical_rates', label: 'Historical Rates', icon: '&#128200;' },
        { key: 'missing_information', label: 'Missing Information & Clarifications', icon: '&#10067;' },
        { key: 'qaqc', label: 'QA/QC Requirements', icon: '&#128269;' },
        { key: 'legal', label: 'Legal & Contract', icon: '&#9878;' },
        { key: 'subcontract', label: 'Subcontract Recommendations', icon: '&#128295;' },
        { key: 'document_control', label: 'Document Control', icon: '&#128196;' },
        { key: 'drawing', label: 'Drawing References', icon: '&#128208;' },
    ];

    domainSections.forEach(d => {
        let findings = [];
        let sectionContent = '';
        let statusText = '';

        if (d.key === 'historical_rates') {
            // Rate lookup section
            const hasRate = rateData && rateData.unit_price != null;
            statusText = hasRate ? `Applied: $${fmtRate(rateData.unit_price)} (${(rateData.rate_confidence || 'unknown').toUpperCase()})` : 'Not yet looked up';
            sectionContent = `
                <div style="padding:8px;">
                    ${hasRate ? `<div style="margin-bottom:8px;font-size:12px;">Current rate: <strong>$${fmtRate(rateData.unit_price)}</strong> (${escHtml(rateData.rate_confidence || 'unknown')})<br><span style="font-size:11px;color:var(--text-tertiary);">Source: ${escHtml(rateData.rate_source || 'N/A')}</span></div>` : ''}
                    <button class="btn btn-sm" onclick="event.stopPropagation();lookupSOVRate(${itemId}, ${bidId})" style="font-size:11px;">Look Up Rates</button>
                    <div id="rate-panel-${itemId}" style="margin-top:8px;"></div>
                </div>`;
        } else if (intelData && intelData.domains && intelData.domains[d.key]) {
            findings = intelData.domains[d.key];
        }

        const count = d.key === 'historical_rates' ? '' : findings.length;
        const maxSev = findings.length > 0 ? findings.reduce((max, f) => {
            const order = {critical: 5, high: 4, medium: 3, low: 2, info: 1};
            return (order[f.severity] || 0) > (order[max] || 0) ? f.severity : max;
        }, 'info') : null;
        const sevBadge = maxSev && maxSev !== 'info' ? `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${severityColors[maxSev] || 'var(--text-tertiary)'};margin-left:6px;"></span>` : '';
        const isMuted = d.key !== 'historical_rates' && findings.length === 0;

        const sectionId = `detail-section-${itemId}-${d.key}`;
        html += `
        <div style="margin-bottom:4px;border:1px solid var(--border-default);border-radius:var(--radius-sm);overflow:hidden;${isMuted ? 'opacity:0.5;' : ''}">
            <div onclick="toggleDetailSection('${sectionId}')" style="padding:8px 12px;background:var(--bg-surface);cursor:pointer;display:flex;align-items:center;gap:6px;border-bottom:1px solid var(--border-default);user-select:none;">
                <span id="${sectionId}-chevron" style="font-size:10px;color:var(--text-tertiary);transition:transform 0.2s;">&#9654;</span>
                <span style="font-size:12px;font-weight:600;color:var(--wollam-navy);">${d.icon} ${d.label}</span>
                ${d.key !== 'historical_rates' ? `<span style="font-size:10px;color:var(--text-tertiary);">(${count})</span>` : `<span style="font-size:10px;color:var(--text-tertiary);">${statusText}</span>`}
                ${sevBadge}
            </div>
            <div id="${sectionId}" style="display:none;padding:8px 12px;">`;

        if (d.key === 'historical_rates') {
            html += sectionContent;
        } else if (findings.length === 0) {
            html += '<p style="font-size:11px;color:var(--text-tertiary);margin:0;">No findings for this domain.</p>';
        } else if (d.key === 'missing_information') {
            html += renderMissingInfoFindings(findings);
        } else {
            html += renderDomainFindings(findings);
        }

        html += '</div></div>';
    });

    if (!intelData || (intelData.total_findings === 0 && !(rateData && rateData.unit_price != null))) {
        html += '<div style="font-size:11px;color:var(--text-tertiary);margin-top:8px;">Run agents and click "Map Intelligence" to populate domain sections.</div>';
    }

    html += '</div>';
    return html;
}

function toggleDetailSection(sectionId) {
    const el = document.getElementById(sectionId);
    const chevron = document.getElementById(`${sectionId}-chevron`);
    if (!el) return;
    const isOpen = el.style.display !== 'none';
    el.style.display = isOpen ? 'none' : 'block';
    if (chevron) chevron.innerHTML = isOpen ? '&#9654;' : '&#9660;';
}

function renderMissingInfoFindings(findings) {
    const actionColors = { rfi: '#EF4444', clarification: '#F59E0B', verify: '#3B82F6', assumption: '#94A3B8' };
    const actionLabels = { rfi: 'RFI', clarification: 'CLARIFY', verify: 'VERIFY', assumption: 'ASSUME' };

    let html = '';
    findings.forEach(f => {
        const meta = f.metadata || {};
        const action = meta.suggested_action || 'verify';
        const borderColor = actionColors[action] || '#94A3B8';
        const label = actionLabels[action] || action.toUpperCase();

        html += `<div style="padding:8px 10px;margin-bottom:6px;background:var(--bg-surface);border:1px solid var(--border-default);border-left:3px solid ${borderColor};border-radius:var(--radius-sm);font-size:12px;">
            <div style="font-weight:600;color:var(--text-primary);">
                <span class="badge" style="background:${borderColor};color:white;font-size:9px;padding:1px 5px;margin-right:4px;">${label}</span>
                ${escHtml(f.title)}
            </div>
            <div style="color:var(--text-secondary);margin-top:2px;">${escHtml(f.detail)}</div>
            ${meta.suggested_question ? `<div style="margin-top:4px;padding:4px 8px;background:var(--bg-hover);border-radius:4px;font-size:11px;color:var(--text-secondary);font-style:italic;">"${escHtml(meta.suggested_question)}"</div>` : ''}
            ${f.agent_name && f.agent_name !== 'sov_mapper' ? `<div style="font-size:10px;color:var(--text-tertiary);margin-top:2px;">Source: ${escHtml(f.agent_name.replace(/_/g, ' '))}</div>` : ''}
        </div>`;
    });
    return html;
}

function renderDomainFindings(findings) {
    const severityColors = {critical: '#EF4444', high: '#EF4444', medium: '#F59E0B', low: 'var(--success-green)', info: 'var(--text-tertiary)'};
    let html = '';
    findings.forEach(f => {
        const sevColor = severityColors[f.severity] || 'var(--text-tertiary)';
        html += `<div style="padding:6px 10px;margin-bottom:4px;background:var(--bg-surface);border:1px solid var(--border-default);border-left:3px solid ${sevColor};border-radius:var(--radius-sm);font-size:12px;">
            <div style="font-weight:500;color:var(--text-primary);">
                ${f.severity && f.severity !== 'info' ? `<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${sevColor};margin-right:4px;"></span>` : ''}
                ${escHtml(f.title)}
            </div>
            <div style="color:var(--text-secondary);margin-top:1px;">${escHtml(f.detail)}</div>
            <div style="font-size:10px;color:var(--text-tertiary);margin-top:2px;">
                ${f.spec_section ? `Spec: ${escHtml(f.spec_section)}` : ''}
                ${f.clause_reference ? ` | Clause: ${escHtml(f.clause_reference)}` : ''}
                ${f.source_document ? ` | Doc: ${escHtml(f.source_document)}` : ''}
            </div>
        </div>`;
    });
    return html;
}

// Keep legacy function name as alias for any external callers
async function toggleSOVIntelligence(itemId, bidId) {
    return toggleSOVItemDetail(itemId, bidId);
}

// ══════════════════════════════════════════════════════════════
// VENDOR DIRECTORY (Global)
// ══════════════════════════════════════════════════════════════

async function loadVendorDirectory() {
    const content = document.getElementById('content');
    document.getElementById('pageTitle').textContent = 'Vendor Directory';
    document.getElementById('pageSubtitle').textContent = 'Subcontractors & Suppliers';
    content.innerHTML = '<div class="empty-state"><p>Loading vendors...</p></div>';

    try {
        const includeArchived = state.vendorShowArchived || false;
        const [vendors, trades] = await Promise.all([
            api(`/vendors?include_archived=${includeArchived}`),
            api('/vendors/trades'),
        ]);

        // Group by trade
        const tradeMap = {};
        vendors.forEach(v => {
            if (!tradeMap[v.trade]) tradeMap[v.trade] = [];
            tradeMap[v.trade].push(v);
        });
        const tradeNames = Object.keys(tradeMap).sort();

        content.innerHTML = `
            <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
                <button class="btn btn-primary btn-sm" onclick="showAddVendor()">+ Add Vendor</button>
                <label class="btn btn-sm" style="cursor:pointer;">
                    Import Excel <input type="file" accept=".xlsx" style="display:none;" onchange="importVendorExcel(this.files[0])">
                </label>
                <button class="btn btn-sm" onclick="window.open('/api/vendors/export','_blank')">Export</button>
                <div style="flex:1;"></div>
                <input type="text" id="vendorSearch" class="search-input" placeholder="Search vendors..." style="width:220px;font-size:12px;" oninput="filterVendors(this.value)">
                <select id="vendorTypeFilter" class="search-input" style="font-size:12px;" onchange="loadVendorDirectory()">
                    <option value="">All Types</option>
                    <option value="construction">Construction</option>
                    <option value="materials">Materials</option>
                </select>
                <label style="font-size:12px;color:var(--text-secondary);display:flex;align-items:center;gap:4px;">
                    <input type="checkbox" ${includeArchived ? 'checked' : ''} onchange="state.vendorShowArchived=this.checked;loadVendorDirectory()"> Archived
                </label>
            </div>
            <div id="vendorAddForm" style="display:none;"></div>
            <div style="margin-bottom:8px;font-size:12px;color:var(--text-secondary);">
                ${vendors.length} vendors across ${tradeNames.length} trades
            </div>
            <div id="vendorList">
                ${tradeNames.length === 0 ? '<div class="empty-state"><p>No vendors yet. Import from Excel or add manually.</p></div>' :
                tradeNames.map(trade => {
                    const vds = tradeMap[trade];
                    const tradeId = 'vtrade-' + trade.replace(/[^a-zA-Z0-9]/g, '_');
                    return `
                    <div class="vendor-trade-group" style="margin-bottom:4px;">
                        <div onclick="document.getElementById('${tradeId}').style.display = document.getElementById('${tradeId}').style.display === 'none' ? 'block' : 'none'; this.querySelector('.vt-chevron').textContent = document.getElementById('${tradeId}').style.display === 'none' ? '▶' : '▼';"
                             style="padding:8px 12px;background:var(--bg-hover);border-radius:var(--radius-sm);cursor:pointer;display:flex;align-items:center;gap:8px;">
                            <span class="vt-chevron" style="font-size:10px;color:var(--text-tertiary);">&#9654;</span>
                            <span style="font-size:13px;font-weight:600;color:var(--text-primary);">${escHtml(trade)}</span>
                            <span style="font-size:11px;color:var(--text-tertiary);">(${vds.length})</span>
                        </div>
                        <div id="${tradeId}" style="display:none;padding-left:12px;">
                            ${vds.map(v => `
                            <div class="vendor-row" data-search="${escAttr((v.company + ' ' + (v.contact_name||'') + ' ' + (v.specialties||'') + ' ' + (v.trade||'')).toLowerCase())}" style="padding:6px 12px;margin:2px 0;border-bottom:1px solid var(--border-default);display:flex;align-items:center;gap:10px;font-size:12px;${!v.is_active ? 'opacity:0.5;' : ''}">
                                <span style="font-weight:500;min-width:160px;">${escHtml(v.company)}</span>
                                <span style="color:var(--text-secondary);min-width:120px;">${escHtml(v.contact_name || '—')}</span>
                                <span style="color:var(--text-tertiary);min-width:100px;">${escHtml(v.city ? v.city + (v.state ? ', ' + v.state : '') : '—')}</span>
                                <span style="color:var(--text-secondary);min-width:110px;">${escHtml(v.phone || '—')}</span>
                                <span style="color:var(--text-tertiary);min-width:160px;overflow:hidden;text-overflow:ellipsis;">${v.email ? `<a href="mailto:${escAttr(v.email)}" style="color:var(--wollam-navy);">${escHtml(v.email)}</a>` : '—'}</span>
                                ${v.is_dbe ? '<span class="badge" style="background:var(--wollam-gold);color:var(--wollam-black);font-size:9px;">DBE</span>' : ''}
                                <span style="flex:1;color:var(--text-tertiary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escHtml(v.specialties || '')}</span>
                            </div>`).join('')}
                        </div>
                    </div>`;
                }).join('')}
            </div>
        `;
    } catch (err) {
        content.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${escHtml(err.message)}</p></div>`;
    }
}

function filterVendors(query) {
    const q = query.toLowerCase().trim();
    document.querySelectorAll('.vendor-row').forEach(row => {
        row.style.display = !q || (row.getAttribute('data-search') || '').includes(q) ? '' : 'none';
    });
}

function showAddVendor() {
    const form = document.getElementById('vendorAddForm');
    if (form.style.display === 'block') { form.style.display = 'none'; return; }
    form.style.display = 'block';
    form.innerHTML = `
        <div class="card" style="padding:12px;margin-bottom:12px;">
            <h4 style="font-size:13px;font-weight:600;margin:0 0 8px;">Add Vendor</h4>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:8px;">
                <div><label style="font-size:11px;color:var(--text-secondary);">Trade *</label><input type="text" id="v_trade" class="search-input" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);">Company *</label><input type="text" id="v_company" class="search-input" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);">Contact</label><input type="text" id="v_contact" class="search-input" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);">Phone</label><input type="text" id="v_phone" class="search-input" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);">Email</label><input type="text" id="v_email" class="search-input" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);">Type</label><select id="v_type" class="search-input" style="width:100%;"><option value="construction">Construction</option><option value="materials">Materials</option></select></div>
            </div>
            <div style="display:flex;gap:8px;justify-content:flex-end;">
                <button class="btn btn-sm" onclick="document.getElementById('vendorAddForm').style.display='none'">Cancel</button>
                <button class="btn btn-primary btn-sm" onclick="addVendor()">Add</button>
            </div>
        </div>`;
}

async function addVendor() {
    const trade = document.getElementById('v_trade').value.trim();
    const company = document.getElementById('v_company').value.trim();
    if (!trade || !company) { alert('Trade and Company are required'); return; }
    try {
        await api('/vendors', { method: 'POST', body: JSON.stringify({
            trade, company,
            contact_name: document.getElementById('v_contact').value.trim() || null,
            phone: document.getElementById('v_phone').value.trim() || null,
            email: document.getElementById('v_email').value.trim() || null,
            vendor_type: document.getElementById('v_type').value,
        })});
        loadVendorDirectory();
    } catch (err) { alert('Error: ' + err.message); }
}

async function importVendorExcel(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
        const result = await fetch('/api/vendors/import', { method: 'POST', body: formData }).then(r => r.json());
        alert(`Imported: ${result.created || 0} created, ${result.updated || 0} updated`);
        loadVendorDirectory();
    } catch (err) { alert('Import failed: ' + err.message); }
}

// ══════════════════════════════════════════════════════════════
// PROCUREMENT TAB (Per-Bid)
// ══════════════════════════════════════════════════════════════

async function renderBidProcurement(bid) {
    const bidId = bid.id;
    const tc = document.getElementById('bidTabContent');
    tc.innerHTML = '<div class="empty-state"><p>Loading procurement...</p></div>';

    try {
        const [items, dashboard] = await Promise.all([
            api(`/bidding/bids/${bidId}/procurement`),
            api(`/bidding/bids/${bidId}/procurement/dashboard`),
        ]);

        const daysUntilDue = bid.bid_date ? Math.ceil((new Date(bid.bid_date) - new Date()) / 86400000) : null;

        tc.innerHTML = `
            <!-- Dashboard -->
            <div class="kpi-grid" style="margin-bottom:16px;">
                <div class="kpi-card card-animate"><div class="kpi-label">Total Items</div><div class="kpi-value">${dashboard.total_items}</div></div>
                <div class="kpi-card card-animate"><div class="kpi-label">RFPs Sent</div><div class="kpi-value">${dashboard.rfps_sent}</div></div>
                <div class="kpi-card card-animate"><div class="kpi-label">Quotes Received</div><div class="kpi-value">${dashboard.quotes_received}</div></div>
                <div class="kpi-card card-animate"><div class="kpi-label">No Vendors</div><div class="kpi-value" style="color:${dashboard.no_vendors > 0 ? 'var(--danger-red)' : 'var(--success-green)'};">${dashboard.no_vendors}</div></div>
            </div>

            ${daysUntilDue !== null && daysUntilDue <= 14 && dashboard.no_vendors > 0 ? `
            <div style="padding:8px 12px;margin-bottom:12px;background:#FFFBEB;border-left:3px solid #F59E0B;border-radius:var(--radius-sm);font-size:12px;color:#92400E;">
                &#9888; Bid due in ${daysUntilDue} days. ${dashboard.no_vendors} procurement item(s) have no vendors assigned.
            </div>` : ''}

            <!-- Actions -->
            <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;">
                <button class="btn btn-sm" onclick="showAddProcurement(${bidId})">+ Add Item</button>
                <button class="btn btn-sm" onclick="analyzeGaps(${bidId})">Analyze Gaps</button>
                <button class="btn btn-sm" onclick="window.open('/api/bidding/bids/${bidId}/procurement/export','_blank')">Export</button>
                <button class="btn btn-sm" disabled title="Coming soon" style="opacity:0.5;">Generate RFP Package</button>
            </div>
            <div id="procAddForm" style="display:none;"></div>
            <div id="gapAnalysisPanel" style="display:none;"></div>

            <!-- Procurement Register -->
            ${items.length === 0 ? '<div class="empty-state"><p>No procurement items yet. Add items manually or click "Analyze Gaps" for AI suggestions.</p></div>' : `
            <div class="card" style="padding:0;overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:12px;">
                    <thead>
                        <tr style="background:var(--bg-hover);border-bottom:2px solid var(--border-default);">
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);">Name</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);width:90px;">Type</th>
                            <th style="padding:8px 10px;text-align:left;font-weight:600;color:var(--text-secondary);width:100px;">Trade</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);width:90px;">Status</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);width:70px;">Vendors</th>
                            <th style="padding:8px 10px;text-align:center;font-weight:600;color:var(--text-secondary);width:50px;"></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${items.map(item => {
                            const statusColors = {not_started:'var(--text-tertiary)',rfp_sent:'var(--status-info)',quotes_received:'var(--success-green)',awarded:'var(--wollam-navy)',not_needed:'var(--text-disabled)'};
                            const sc = statusColors[item.status] || 'var(--text-tertiary)';
                            const solCount = (item.solicitations || []).length;
                            return `
                            <tr style="border-bottom:1px solid var(--border-default);cursor:pointer;" onclick="toggleProcDetail(${item.id}, ${bidId})">
                                <td style="padding:6px 10px;font-weight:500;">
                                    ${item.ai_suggested ? '<span title="AI suggested" style="color:var(--wollam-gold);">&#10024;</span> ' : ''}${escHtml(item.name)}
                                    ${item.ai_source ? `<br><span style="font-size:10px;color:var(--text-tertiary);font-style:italic;">${escHtml(item.ai_source.substring(0, 80))}</span>` : ''}
                                </td>
                                <td style="padding:6px 10px;color:var(--text-secondary);">${escHtml(item.procurement_type.replace(/_/g, ' '))}</td>
                                <td style="padding:6px 10px;color:var(--text-tertiary);">${escHtml(item.trade_match || '—')}</td>
                                <td style="padding:6px 10px;text-align:center;"><span style="font-size:10px;font-weight:600;color:${sc};text-transform:uppercase;">${escHtml(item.status.replace(/_/g, ' '))}</span></td>
                                <td style="padding:6px 10px;text-align:center;">${solCount} / 3</td>
                                <td style="padding:6px 10px;text-align:center;" onclick="event.stopPropagation();">
                                    <button onclick="deleteProcItem(${item.id}, ${bidId})" style="background:none;border:none;cursor:pointer;color:var(--text-tertiary);font-size:11px;">&times;</button>
                                </td>
                            </tr>
                            <tr><td colspan="6" style="padding:0;">
                                <div id="proc-detail-${item.id}" style="display:none;padding:12px 16px;background:var(--bg-hover);border-bottom:1px solid var(--border-default);">
                                    ${renderProcDetail(item, bidId)}
                                </div>
                            </td></tr>`;
                        }).join('')}
                    </tbody>
                </table>
            </div>`}
        `;
    } catch (err) {
        tc.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${escHtml(err.message)}</p></div>`;
    }
}

function renderProcDetail(item, bidId) {
    const sols = item.solicitations || [];
    const links = item.sov_links || [];
    return `
        <div style="margin-bottom:8px;">
            <span style="font-size:11px;font-weight:600;color:var(--text-secondary);">LINKED SOV ITEMS</span>
            ${links.length === 0 ? '<span style="font-size:11px;color:var(--text-tertiary);margin-left:8px;">None</span>' :
                links.map(l => `<span style="font-size:11px;padding:2px 6px;background:var(--bg-hover);border-radius:4px;margin:0 2px;">${escHtml(l.item_number || '')} ${escHtml(l.description || '')}</span>`).join('')}
        </div>
        <div style="margin-bottom:8px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                <span style="font-size:11px;font-weight:600;color:var(--text-secondary);">SOLICITATIONS</span>
                <button class="btn btn-sm" style="font-size:10px;padding:2px 6px;" onclick="event.stopPropagation();addSolicitation(${item.id}, ${bidId})">+ Vendor</button>
            </div>
            ${sols.length === 0 ? '<div style="font-size:11px;color:var(--text-tertiary);">No vendors contacted yet.</div>' : `
            <table style="width:100%;border-collapse:collapse;font-size:11px;">
                <tr style="background:var(--bg-surface);"><th style="padding:3px 6px;text-align:left;">Company</th><th style="padding:3px 6px;">Contact</th><th style="padding:3px 6px;">Status</th><th style="padding:3px 6px;">Quote</th></tr>
                ${sols.map(s => `<tr style="border-bottom:1px solid var(--border-default);">
                    <td style="padding:3px 6px;font-weight:500;">${escHtml(s.company_name || '—')}</td>
                    <td style="padding:3px 6px;">${escHtml(s.contact_name || '—')}</td>
                    <td style="padding:3px 6px;text-align:center;"><span style="font-size:10px;font-weight:600;text-transform:uppercase;">${escHtml(s.status)}</span></td>
                    <td style="padding:3px 6px;">${s.quote_amount != null ? '$' + fmt(s.quote_amount) : '—'}</td>
                </tr>`).join('')}
            </table>`}
        </div>`;
}

function toggleProcDetail(itemId, bidId) {
    const el = document.getElementById(`proc-detail-${itemId}`);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function showAddProcurement(bidId) {
    const form = document.getElementById('procAddForm');
    if (form.style.display === 'block') { form.style.display = 'none'; return; }
    form.style.display = 'block';
    form.innerHTML = `
        <div class="card" style="padding:12px;margin-bottom:12px;">
            <div style="display:grid;grid-template-columns:1fr 120px 120px;gap:8px;margin-bottom:8px;">
                <div><label style="font-size:11px;color:var(--text-secondary);">Name *</label><input type="text" id="proc_name" class="search-input" style="width:100%;"></div>
                <div><label style="font-size:11px;color:var(--text-secondary);">Type</label><select id="proc_type" class="search-input" style="width:100%;"><option value="subcontract">Subcontract</option><option value="material">Material</option><option value="testing">Testing</option><option value="equipment_rental">Equipment</option><option value="specialty_service">Specialty</option></select></div>
                <div><label style="font-size:11px;color:var(--text-secondary);">Trade</label><input type="text" id="proc_trade" class="search-input" style="width:100%;"></div>
            </div>
            <div style="display:flex;gap:8px;justify-content:flex-end;">
                <button class="btn btn-sm" onclick="document.getElementById('procAddForm').style.display='none'">Cancel</button>
                <button class="btn btn-primary btn-sm" onclick="createProcItem(${bidId})">Add</button>
            </div>
        </div>`;
}

async function createProcItem(bidId) {
    const name = document.getElementById('proc_name').value.trim();
    if (!name) { alert('Name is required'); return; }
    try {
        await api(`/bidding/bids/${bidId}/procurement`, { method: 'POST', body: JSON.stringify({
            name,
            procurement_type: document.getElementById('proc_type').value,
            trade_match: document.getElementById('proc_trade').value.trim() || null,
        })});
        renderBidProcurement(window._currentBid);
    } catch (err) { alert('Error: ' + err.message); }
}

async function deleteProcItem(itemId, bidId) {
    if (!confirm('Delete this procurement item?')) return;
    try {
        await api(`/bidding/procurement/${itemId}`, { method: 'DELETE' });
        renderBidProcurement(window._currentBid);
    } catch (err) { alert('Error: ' + err.message); }
}

async function addSolicitation(itemId, bidId) {
    const company = prompt('Company name:');
    if (!company) return;
    try {
        await api(`/bidding/procurement/${itemId}/solicitations`, {
            method: 'POST',
            body: JSON.stringify({ company_name: company }),
        });
        renderBidProcurement(window._currentBid);
    } catch (err) { alert('Error: ' + err.message); }
}

async function analyzeGaps(bidId) {
    const panel = document.getElementById('gapAnalysisPanel');
    panel.style.display = 'block';
    panel.innerHTML = '<div class="card" style="padding:16px;margin-bottom:12px;"><p style="font-size:12px;color:var(--text-tertiary);">Analyzing procurement gaps...</p></div>';

    try {
        const result = await api(`/bidding/bids/${bidId}/procurement/analyze-gaps`, { method: 'POST' });
        const suggestions = result.suggestions || [];

        if (suggestions.length === 0) {
            panel.innerHTML = '<div class="card" style="padding:16px;margin-bottom:12px;"><p style="font-size:12px;color:var(--success-green);">&#10003; No procurement gaps found. All subcontract SOV items have procurement links.</p></div>';
            return;
        }

        panel.innerHTML = `
            <div class="card" style="padding:16px;margin-bottom:12px;">
                <h4 style="font-size:13px;font-weight:600;margin:0 0 8px;">${suggestions.length} Gap(s) Found — Review & Accept</h4>
                ${suggestions.map(s => `
                <div style="padding:8px 10px;margin-bottom:6px;border:1px solid var(--border-default);border-radius:var(--radius-sm);display:flex;align-items:center;gap:8px;">
                    <input type="checkbox" checked data-suggestion='${escAttr(JSON.stringify(s))}' class="gap-checkbox">
                    <div style="flex:1;">
                        <div style="font-size:12px;font-weight:500;">${escHtml(s.name)}</div>
                        <div style="font-size:10px;color:var(--text-tertiary);">${escHtml(s.procurement_type)} ${s.trade_match ? '· ' + escHtml(s.trade_match) : ''}</div>
                        <div style="font-size:10px;color:var(--text-secondary);font-style:italic;">${escHtml(s.ai_source || '')}</div>
                    </div>
                </div>`).join('')}
                <div style="display:flex;gap:8px;margin-top:8px;">
                    <button class="btn btn-primary btn-sm" onclick="acceptGapSuggestions(${bidId})">Accept Selected</button>
                    <button class="btn btn-sm" onclick="document.getElementById('gapAnalysisPanel').style.display='none'">Dismiss</button>
                </div>
            </div>`;
    } catch (err) {
        panel.innerHTML = `<div class="card" style="padding:16px;margin-bottom:12px;"><p style="font-size:12px;color:var(--danger-red);">Error: ${escHtml(err.message)}</p></div>`;
    }
}

async function acceptGapSuggestions(bidId) {
    const checkboxes = document.querySelectorAll('.gap-checkbox:checked');
    const suggestions = [];
    checkboxes.forEach(cb => {
        try { suggestions.push(JSON.parse(cb.getAttribute('data-suggestion'))); } catch (e) {}
    });
    if (suggestions.length === 0) { alert('No suggestions selected'); return; }

    try {
        const result = await api(`/bidding/bids/${bidId}/procurement/accept-suggestions`, {
            method: 'POST',
            body: JSON.stringify({ suggestions }),
        });
        document.getElementById('gapAnalysisPanel').style.display = 'none';
        alert(`Created ${result.created} procurement item(s)`);
        renderBidProcurement(window._currentBid);
    } catch (err) { alert('Error: ' + err.message); }
}

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    navigate('jobs');
});
