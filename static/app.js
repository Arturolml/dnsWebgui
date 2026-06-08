// BIND9 DNS WebGUI - Frontend Application Logic

// State management
const state = {
    currentView: 'dashboard',
    activeZone: null,
    activeZoneData: null,
    mode: 'test',
    statusInterval: null
};

// DOM Elements
const views = document.querySelectorAll('.content-view');
const navItems = document.querySelectorAll('.nav-item');
const viewTitle = document.querySelector('.header-info h1');
const alertContainer = document.getElementById('alertContainer');
const serviceIndicator = document.getElementById('serviceIndicator');
const appModeBadge = document.getElementById('appModeBadge');
const configPathText = document.getElementById('configPathText');

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    initRouting();
    initDashboard();
    initZones();
    initRecords();
    initOptions();
    initEditor();
    initDiagnostics();
    
    // Initial status fetch
    fetchSystemStatus();
    // Poll status every 5 seconds
    state.statusInterval = setInterval(fetchSystemStatus, 5000);
});

// --- Alert System ---
function showAlert(message, type = 'success', reminder = false) {
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        <span class="alert-icon" style="align-self: flex-start; margin-top: 2px;">${type === 'success' ? '✓' : type === 'error' ? '✗' : '⚠'}</span>
        <div style="display: flex; flex-direction: column; gap: 2px; text-align: left; width: 100%;">
            <span class="alert-message">${escapeHtml(message)}</span>
            ${reminder && type === 'success' ? `<span class="alert-reminder" style="font-size: 0.8rem; opacity: 0.95; color: #fef3c7; margin-top: 4px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 4px;">💡 Recuerda ir al Panel de Control y <strong>Recargar Config</strong>.</span>` : ''}
        </div>
    `;
    alertContainer.appendChild(alert);
    
    const duration = reminder ? 6000 : 4000;
    // Auto remove
    setTimeout(() => {
        alert.style.opacity = '0';
        alert.style.transform = 'translateX(100%)';
        alert.style.transition = 'all 0.3s ease';
        setTimeout(() => alert.remove(), 300);
    }, duration);
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
}

// --- Routing System ---
function initRouting() {
    const handleRoute = () => {
        const hash = window.location.hash || '#dashboard';
        let viewName = hash.substring(1);
        
        // Handle routes with query parameters like #records?zone=example.com
        let params = {};
        if (viewName.includes('?')) {
            const parts = viewName.split('?');
            viewName = parts[0];
            const queryStr = parts[1];
            const urlParams = new URLSearchParams(queryStr);
            for (const [key, value] of urlParams.entries()) {
                params[key] = value;
            }
        }
        
        switchView(viewName, params);
    };
    
    window.addEventListener('hashchange', handleRoute);
    handleRoute(); // Run once at start
}

function switchView(viewName, params = {}) {
    // Hide all views
    views.forEach(v => v.classList.remove('active'));
    
    // Update active nav item
    navItems.forEach(item => {
        if (item.getAttribute('data-view') === viewName || (viewName === 'records' && item.getAttribute('data-view') === 'zones')) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
    
    // Show target view
    const targetView = document.getElementById(`view-${viewName}`);
    if (targetView) {
        targetView.classList.add('active');
        state.currentView = viewName;
    } else {
        // Fallback to dashboard
        document.getElementById('view-dashboard').classList.add('active');
        state.currentView = 'dashboard';
    }
    
    // View specific loading triggers
    if (state.currentView === 'dashboard') {
        viewTitle.innerText = "Panel de Control";
        fetchSystemStatus();
    } else if (state.currentView === 'zones') {
        viewTitle.innerText = "Zonas DNS";
        loadZonesList();
    } else if (state.currentView === 'records') {
        viewTitle.innerText = "Gestión de Registros";
        if (params.zone) {
            loadZoneRecords(params.zone);
        } else {
            window.location.hash = '#zones';
        }
    } else if (state.currentView === 'options') {
        viewTitle.innerText = "Opciones Globales";
        loadGlobalOptions();
    } else if (state.currentView === 'editor') {
        viewTitle.innerText = "Editor de Configuración";
        loadRawConfigFile();
    } else if (state.currentView === 'diagnostics') {
        viewTitle.innerText = "Diagnósticos y Pruebas";
    }
}

// --- API Helper ---
async function apiCall(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: {}
    };
    
    if (data) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(data);
    }
    
    try {
        const response = await fetch(endpoint, options);
        const result = await response.json();
        return result;
    } catch (error) {
        console.error(`API Call failed to ${endpoint}:`, error);
        return { success: false, message: `Error de red al conectar con el servidor: ${error.message}` };
    }
}

// --- Dashboard Logic ---
function initDashboard() {
    // Bind control buttons
    const bindServiceAction = (action, label) => {
        document.getElementById(`btn${action}Svc`).addEventListener('click', async () => {
            const btn = document.getElementById(`btn${action}Svc`);
            const originalHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner"></span> Procesando...`;
            
            const res = await apiCall('/api/service', 'POST', { action: action.toLowerCase() });
            
            btn.disabled = false;
            btn.innerHTML = originalHtml;
            
            if (res.success) {
                showAlert(res.message, 'success');
            } else {
                showAlert(res.message, 'error');
            }
            fetchSystemStatus();
        });
    };
    
    bindServiceAction('Start', 'Iniciar');
    bindServiceAction('Stop', 'Detener');
    bindServiceAction('Restart', 'Reiniciar');
    bindServiceAction('Reload', 'Recargar');
}

async function fetchSystemStatus() {
    const data = await apiCall('/api/status');
    if (!data) return;
    
    // Update service indicator
    const svc = data.service;
    serviceIndicator.className = 'status-indicator';
    if (svc.status === 'running') {
        serviceIndicator.classList.add('online');
        serviceIndicator.querySelector('.indicator-text').innerText = 'Servidor Activo';
        document.getElementById('dashSvcStatus').innerText = 'ACTIVO';
        document.getElementById('dashSvcStatus').style.color = 'var(--color-green)';
    } else if (svc.status === 'stopped') {
        serviceIndicator.classList.add('offline');
        serviceIndicator.querySelector('.indicator-text').innerText = 'Servidor Detenido';
        document.getElementById('dashSvcStatus').innerText = 'DETENIDO';
        document.getElementById('dashSvcStatus').style.color = 'var(--color-red)';
    } else if (svc.status === 'failed') {
        serviceIndicator.classList.add('offline');
        serviceIndicator.querySelector('.indicator-text').innerText = 'Error (Fallo)';
        document.getElementById('dashSvcStatus').innerText = 'FALLÓ';
        document.getElementById('dashSvcStatus').style.color = 'var(--color-red)';
    } else {
        serviceIndicator.classList.add('warning');
        serviceIndicator.querySelector('.indicator-text').innerText = 'Desconocido';
        document.getElementById('dashSvcStatus').innerText = 'DESCONOCIDO';
        document.getElementById('dashSvcStatus').style.color = 'var(--color-warning)';
    }
    document.getElementById('dashSvcMsg').innerText = svc.message;
    
    // Update Mode Badges & Paths
    state.mode = data.mode;
    appModeBadge.className = `mode-badge ${data.mode}`;
    appModeBadge.innerText = data.mode === 'test' ? 'MODO PRUEBA (LOCAL)' : data.mode === 'production' ? 'PRODUCCIÓN (LIVE)' : 'PERSONALIZADO';
    
    const infoMode = document.getElementById('infoModeBadge');
    infoMode.className = `badge ${data.mode === 'production' ? 'badge-success' : 'badge-warning'}`;
    infoMode.innerText = data.mode === 'production' ? 'PRODUCCIÓN' : 'PRUEBA LOCAL';
    
    configPathText.innerText = `Ruta: ${data.config_dir}`;
    document.getElementById('infoConfigDir').innerText = data.config_dir;
    
    // Update Zones Counters
    document.getElementById('dashZoneCount').innerText = data.zones.total;
    document.getElementById('dashFwdZones').innerText = `${data.zones.forward} Directas`;
    document.getElementById('dashRevZones').innerText = `${data.zones.reverse} Inversas`;
    
    // Update system resources
    const ram = data.system.ram;
    document.getElementById('dashRamPct').innerText = `${ram.percent}%`;
    document.getElementById('dashRamBar').style.width = `${ram.percent}%`;
    document.getElementById('dashRamUsage').innerText = `${ram.used_mb} MB / ${ram.total_mb} MB`;
    
    const cpu = data.system.cpu;
    document.getElementById('dashCpuLoad').innerText = cpu.load_1m.toFixed(2);
    document.getElementById('dashCpuCores').innerText = `Cores: ${cpu.cores} | Load (5m/15m): ${cpu.load_5m.toFixed(2)} / ${cpu.load_15m.toFixed(2)}`;
}

// --- Zones Management ---
function initZones() {
    const modal = document.getElementById('addZoneModal');
    const btnOpen = document.getElementById('btnOpenAddZoneModal');
    const btnClose = document.getElementById('btnCloseAddZoneModal');
    const btnCancel = document.getElementById('btnCancelAddZone');
    const btnSubmit = document.getElementById('btnSubmitAddZone');
    const form = document.getElementById('addZoneForm');
    const searchInput = document.getElementById('zoneSearchInput');
    
    // Modal controls
    btnOpen.addEventListener('click', () => {
        form.reset();
        modal.classList.add('active');
    });
    
    const closeModal = () => modal.classList.remove('active');
    btnClose.addEventListener('click', closeModal);
    btnCancel.addEventListener('click', closeModal);
    
    // Auto toggling checkbox details
    document.getElementById('newZoneIsReverse').addEventListener('change', (e) => {
        const nameInput = document.getElementById('newZoneName');
        if (e.target.checked) {
            nameInput.placeholder = "ejemplo: 1.168.192.in-addr.arpa";
        } else {
            nameInput.placeholder = "ejemplo: miempresa.com";
        }
    });

    // Create Zone Submit
    btnSubmit.addEventListener('click', async (e) => {
        e.preventDefault();
        const name = document.getElementById('newZoneName').value.trim();
        const type = document.getElementById('newZoneType').value;
        const isReverse = document.getElementById('newZoneIsReverse').checked;
        
        if (!name) {
            showAlert("El nombre de la zona es requerido", "error");
            return;
        }
        
        btnSubmit.disabled = true;
        const res = await apiCall('/api/zones', 'POST', { name, type, is_reverse: isReverse });
        btnSubmit.disabled = false;
        
        if (res.success) {
            showAlert(res.message, 'success', true);
            closeModal();
            loadZonesList();
        } else {
            showAlert(res.message, 'error');
        }
    });
    
    // Search Zones Filter
    searchInput.addEventListener('keyup', () => {
        const query = searchInput.value.toLowerCase();
        const rows = document.querySelectorAll('#zonesTableBody tr');
        
        rows.forEach(row => {
            const name = row.cells[0].innerText.toLowerCase();
            const type = row.cells[1].innerText.toLowerCase();
            const dir = row.cells[2].innerText.toLowerCase();
            
            if (name.includes(query) || type.includes(query) || dir.includes(query)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    });
}

async function loadZonesList() {
    const body = document.getElementById('zonesTableBody');
    body.innerHTML = `<tr><td colspan="5" style="text-align: center;"><span class="spinner"></span> Cargando zonas...</td></tr>`;
    
    const res = await apiCall('/api/zones');
    if (!res.success) {
        body.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--color-red);">${res.message}</td></tr>`;
        return;
    }
    
    if (res.zones.length === 0) {
        body.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No hay zonas DNS configuradas. Haz clic en "Nueva Zona" para empezar.</td></tr>`;
        return;
    }
    
    body.innerHTML = '';
    res.zones.forEach(z => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="font-mono" style="font-weight: 600;">${escapeHtml(z.name)}</td>
            <td><span class="badge badge-info">${escapeHtml(z.type)}</span></td>
            <td><span class="badge ${z.is_reverse ? 'badge-warning' : 'badge-success'}">${z.is_reverse ? 'Inversa' : 'Directa'}</span></td>
            <td class="font-mono text-muted" style="font-size: 0.8rem;">${escapeHtml(z.file_path)}</td>
            <td>
                <div style="display: flex; gap: 8px;">
                    <a href="#records?zone=${encodeURIComponent(z.name)}" class="btn btn-secondary btn-sm">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                        Gestionar
                    </a>
                    <button class="btn btn-warning btn-sm btn-rename-zone" data-name="${escapeHtml(z.name)}">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                        Renombrar
                    </button>
                    <button class="btn btn-danger btn-sm btn-delete-zone" data-name="${escapeHtml(z.name)}">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                        Borrar
                    </button>
                </div>
            </td>
        `;
        body.appendChild(row);
    });
    
    // Bind Rename buttons
    document.querySelectorAll('.btn-rename-zone').forEach(btn => {
        btn.addEventListener('click', async () => {
            const oldName = btn.getAttribute('data-name');
            const newName = prompt(`Introduce el nuevo nombre para la zona '${oldName}':`, oldName);
            if (newName && newName.trim() && newName.trim().toLowerCase() !== oldName.toLowerCase()) {
                const res = await apiCall('/api/zones/rename', 'POST', { old_name: oldName, new_name: newName.trim() });
                if (res.success) {
                    showAlert(res.message, 'success', true);
                    loadZonesList();
                } else {
                    showAlert(res.message, 'error');
                }
            }
        });
    });

    // Bind Delete buttons
    document.querySelectorAll('.btn-delete-zone').forEach(btn => {
        btn.addEventListener('click', async () => {
            const name = btn.getAttribute('data-name');
            if (confirm(`¿Estás completamente seguro de borrar la zona '${name}' y todos sus registros asociados?`)) {
                const res = await apiCall(`/api/zones?name=${encodeURIComponent(name)}`, 'DELETE');
                if (res.success) {
                    showAlert(res.message, 'success', true);
                    loadZonesList();
                } else {
                    showAlert(res.message, 'error');
                }
            }
        });
    });
}

// --- Zone Records Management ---
function initRecords() {
    document.getElementById('btnBackToZones').addEventListener('click', () => {
        window.location.hash = '#zones';
    });
    
    document.getElementById('btnAddRecordRow').addEventListener('click', () => {
        appendRecordRow({ name: '', ttl: '', class: 'IN', type: 'A', value: '' });
    });
    
    document.getElementById('btnSaveRecords').addEventListener('click', saveRecordsChanges);
}

async function loadZoneRecords(zoneName) {
    state.activeZone = zoneName;
    document.getElementById('recordsTitle').innerText = `Gestionar Zona: ${zoneName}`;
    
    const body = document.getElementById('recordsTableBody');
    body.innerHTML = `<tr><td colspan="6" style="text-align: center;"><span class="spinner"></span> Cargando registros...</td></tr>`;
    
    const res = await apiCall(`/api/records?zone=${encodeURIComponent(zoneName)}`);
    if (!res.success) {
        body.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--color-red);">${res.message}</td></tr>`;
        return;
    }
    
    state.activeZoneData = res.data;
    
    // Fill SOA fields
    document.getElementById('recordsFilePath').innerText = res.data.file_path;
    document.getElementById('soaDefaultTtl').value = res.data.default_ttl;
    
    const soa = res.data.soa;
    document.getElementById('soaMname').value = soa.mname;
    document.getElementById('soaRname').value = soa.rname;
    document.getElementById('soaSerial').value = soa.serial;
    document.getElementById('soaRefresh').value = soa.refresh;
    document.getElementById('soaRetry').value = soa.retry;
    document.getElementById('soaExpire').value = soa.expire;
    document.getElementById('soaMinimum').value = soa.minimum;
    
    // Fill records table
    body.innerHTML = '';
    if (res.data.records.length === 0) {
        // Automatically add an empty row to help the user
        appendRecordRow({ name: '', ttl: '', class: 'IN', type: 'A', value: '' });
    } else {
        res.data.records.forEach(rec => {
            appendRecordRow(rec);
        });
    }
}

function appendRecordRow(rec) {
    const body = document.getElementById('recordsTableBody');
    const row = document.createElement('tr');
    
    const types = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'PTR', 'SRV'];
    let typeSelectOptions = '';
    types.forEach(t => {
        typeSelectOptions += `<option value="${t}" ${rec.type === t ? 'selected' : ''}>${t}</option>`;
    });
    
    row.innerHTML = `
        <td><input type="text" class="rec-name font-mono" value="${escapeHtml(rec.name)}" placeholder="@ o subdominio"></td>
        <td><input type="text" class="rec-ttl font-mono" value="${escapeHtml(rec.ttl)}" placeholder="Opcional"></td>
        <td><input type="text" class="rec-class font-mono" value="${escapeHtml(rec.class)}" placeholder="IN" style="width: 60px;"></td>
        <td>
            <select class="rec-type font-mono">
                ${typeSelectOptions}
            </select>
        </td>
        <td><input type="text" class="rec-value font-mono" value="${escapeHtml(rec.value)}" placeholder="ej: 192.168.1.10" required></td>
        <td>
            <button class="btn btn-danger btn-sm btn-delete-row">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            </button>
        </td>
    `;
    
    body.appendChild(row);
    
    row.querySelector('.btn-delete-row').addEventListener('click', () => {
        row.remove();
        if (body.children.length === 0) {
            appendRecordRow({ name: '', ttl: '', class: 'IN', type: 'A', value: '' });
        }
    });
}

async function saveRecordsChanges() {
    if (!state.activeZone) return;
    
    const defaultTtl = document.getElementById('soaDefaultTtl').value.trim();
    
    // SOA
    const soa = {
        name: '@',
        mname: document.getElementById('soaMname').value.trim(),
        rname: document.getElementById('soaRname').value.trim(),
        serial: document.getElementById('soaSerial').value,
        refresh: document.getElementById('soaRefresh').value,
        retry: document.getElementById('soaRetry').value,
        expire: document.getElementById('soaExpire').value,
        minimum: document.getElementById('soaMinimum').value
    };
    
    if (!soa.mname || !soa.rname) {
        showAlert("El MName y RName de la sección SOA son requeridos", "error");
        return;
    }
    
    // Records
    const rows = document.querySelectorAll('#recordsTableBody tr');
    const records = [];
    let validationError = false;
    
    rows.forEach((row, idx) => {
        const name = row.querySelector('.rec-name').value.trim();
        const ttl = row.querySelector('.rec-ttl').value.trim();
        const cls = row.querySelector('.rec-class').value.trim() || 'IN';
        const type = row.querySelector('.rec-type').value;
        const value = row.querySelector('.rec-value').value.trim();
        
        if (!name || !value) {
            validationError = true;
            row.style.border = "1px solid var(--color-red)";
        } else {
            row.style.border = "";
            records.push({ name, ttl, class: cls, type, value });
        }
    });
    
    if (validationError) {
        showAlert("Existen registros vacíos o incompletos. Corrige los campos marcados.", "error");
        return;
    }
    
    const btn = document.getElementById('btnSaveRecords');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> Validando y Guardando...`;
    
    const payload = {
        zone: state.activeZone,
        default_ttl: defaultTtl,
        soa,
        records
    };
    
    const res = await apiCall('/api/records', 'POST', payload);
    
    btn.disabled = false;
    btn.innerHTML = originalText;
    
    if (res.success) {
        showAlert(res.message, 'success', true);
        // Reload records to fetch updated serial
        loadZoneRecords(state.activeZone);
    } else {
        showAlert(res.message, 'error');
    }
}

// --- Global Options Logic ---
function initOptions() {
    document.getElementById('btnAddForwarder').addEventListener('click', () => {
        appendForwarderRow('');
    });
    
    document.getElementById('btnSaveOptions').addEventListener('click', saveGlobalOptionsChanges);
}

function appendForwarderRow(ip) {
    const list = document.getElementById('forwardersList');
    const row = document.createElement('div');
    row.className = 'forwarder-row';
    row.innerHTML = `
        <input type="text" class="opt-forwarder font-mono" value="${escapeHtml(ip)}" placeholder="ej: 8.8.8.8">
        <button type="button" class="btn btn-danger btn-sm btn-remove-forwarder">Eliminar</button>
    `;
    list.appendChild(row);
    
    row.querySelector('.btn-remove-forwarder').addEventListener('click', () => {
        row.remove();
    });
}

async function loadGlobalOptions() {
    const list = document.getElementById('forwardersList');
    list.innerHTML = `<div style="padding: 10px 0;"><span class="spinner"></span> Cargando opciones...</div>`;
    
    const res = await apiCall('/api/options');
    if (!res.success) {
        list.innerHTML = `<div style="color: var(--color-red);">${res.message}</div>`;
        return;
    }
    
    document.getElementById('optRecursion').checked = res.options.recursion === 'yes';
    
    list.innerHTML = '';
    if (res.options.forwarders.length === 0) {
        appendForwarderRow('');
    } else {
        res.options.forwarders.forEach(ip => {
            appendForwarderRow(ip);
        });
    }
}

async function saveGlobalOptionsChanges() {
    const recursion = document.getElementById('optRecursion').checked ? 'yes' : 'no';
    
    const forwarderInputs = document.querySelectorAll('.opt-forwarder');
    const forwarders = [];
    forwarderInputs.forEach(input => {
        const val = input.value.trim();
        if (val) forwarders.push(val);
    });
    
    const btn = document.getElementById('btnSaveOptions');
    btn.disabled = true;
    btn.innerText = "Validando y Guardando...";
    
    const res = await apiCall('/api/options', 'POST', {
        options: {
            recursion,
            forwarders
        }
    });
    
    btn.disabled = false;
    btn.innerText = "Guardar Opciones Globales";
    
    if (res.success) {
        showAlert(res.message, 'success', true);
        loadGlobalOptions();
    } else {
        showAlert(res.message, 'error');
    }
}

// --- Editor Logic ---
function initEditor() {
    const selector = document.getElementById('editorFileSelect');
    selector.addEventListener('change', loadRawConfigFile);
    
    document.getElementById('btnSaveRawConfig').addEventListener('click', saveRawConfigFile);
}

async function loadRawConfigFile() {
    const file = document.getElementById('editorFileSelect').value;
    const textarea = document.getElementById('rawConfigTextarea');
    textarea.value = "// Cargando archivo...";
    textarea.disabled = true;
    
    const res = await apiCall(`/api/raw_config?file=${encodeURIComponent(file)}`);
    textarea.disabled = false;
    if (res.success) {
        textarea.value = res.content;
    } else {
        textarea.value = `// Error al cargar el archivo:\n${res.message}`;
    }
}

async function saveRawConfigFile() {
    const file = document.getElementById('editorFileSelect').value;
    const content = document.getElementById('rawConfigTextarea').value;
    
    const btn = document.getElementById('btnSaveRawConfig');
    btn.disabled = true;
    btn.innerText = "Validando y Guardando...";
    
    const res = await apiCall('/api/raw_config', 'POST', { file, content });
    
    btn.disabled = false;
    btn.innerText = "Guardar Archivo de Configuración";
    
    if (res.success) {
        showAlert(res.message, 'success', true);
        loadRawConfigFile();
    } else {
        showAlert(res.message, 'error');
    }
}

// --- Diagnostics Logic ---
function initDiagnostics() {
    document.getElementById('btnRunCheckconf').addEventListener('click', runCheckconf);
}

async function runCheckconf() {
    const consoleDiv = document.getElementById('diagnosticsConsole');
    consoleDiv.innerHTML = `[Ejecutando named-checkconf en segundo plano...]\n`;
    
    const res = await apiCall('/api/validate');
    
    if (res.success) {
        consoleDiv.innerHTML = `<span style="color: var(--color-green); font-weight: bold;">[OK] La validación de sintaxis se completó CORRECTAMENTE.</span>\n`;
        consoleDiv.innerHTML += `named-checkconf retornó código de salida 0.\nNo se detectaron errores de sintaxis en tus archivos de configuración.\n\n${res.output || '(Sin salida de error)'}`;
    } else {
        consoleDiv.innerHTML = `<span style="color: var(--color-red); font-weight: bold;">[ERROR] La validación de sintaxis FALLÓ.</span>\n\n`;
        consoleDiv.innerHTML += `${escapeHtml(res.output)}`;
    }
}
