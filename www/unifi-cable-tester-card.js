/**
 * UniFi Cable Tester Card
 * Custom Lovelace card for displaying UniFi switch cable test results
 */

const CARD_VERSION = "2.1.0";

// Status colors
const STATUS_COLORS = {
  "OK": "#4CAF50",           // Green
  "Open": "#F44336",         // Red
  "Short": "#FF5722",        // Deep Orange
  "Impedance Mismatch": "#FF9800", // Orange
  "Fiber": "#2196F3",        // Blue
  "Not Tested": "#9E9E9E",   // Gray
  "Test Failed": "#B71C1C",   // Dark Red
  "Unknown": "#757575",      // Dark Gray
  "Testing": "#FFC107",      // Amber (animated)
};

// Status icons
const STATUS_ICONS = {
  "OK": "mdi:check-circle",
  "Open": "mdi:lan-disconnect",
  "Short": "mdi:flash-alert",
  "Impedance Mismatch": "mdi:signal-variant",
  "Fiber": "mdi:fiber-manual-record",
  "Not Tested": "mdi:help-circle-outline",
  "Test Failed": "mdi:alert-circle",
  "Unknown": "mdi:help-circle",
  "Testing": "mdi:loading",
};

class UnifiCableTesterCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._selectedPort = null;
    this._renderScheduled = false;
  }

  setConfig(config) {
    // switch_name is optional - if not specified, shows all switches
    this._config = {
      title: config.title || "UniFi Cable Tester",
      show_header: config.show_header !== false,
      show_test_button: config.show_test_button !== false,
      show_device_info: config.show_device_info !== false,
      compact: config.compact || false,
      columns: config.columns || 12,
      ...config,
    };
    this._scheduleRender();
  }

  set hass(hass) {
    this._hass = hass;
    this._scheduleRender();
  }

  // Debounce rendering to avoid full DOM rebuild on every hass update
  _scheduleRender() {
    if (this._renderScheduled) return;
    this._renderScheduled = true;
    requestAnimationFrame(() => {
      this._renderScheduled = false;
      this._render();
    });
  }

  _getEntities() {
    if (!this._hass) return { ports: [], testRunStatus: null, device: null };

    const entities = Object.keys(this._hass.states);
    const ports = [];
    let testRunStatus = null;
    let device = null;

    for (const entityId of entities) {
      const state = this._hass.states[entityId];
      
      // Match cable test sensors (port sensors)
      // Entity names are like: sensor.unifi_switch_port_1_cable_status
      if (entityId.startsWith("sensor.") && 
          entityId.includes("cable_status") &&
          entityId.includes("port_")) {
        
        // Check if this entity belongs to our device
        if (this._matchesDevice(entityId)) {
          const portMatch = entityId.match(/port_(\d+)/);
          if (portMatch) {
            ports.push({
              entityId,
              port: parseInt(portMatch[1]),
              state: state.state,
              attributes: state.attributes,
            });
          }
        }
      }

      // Find test run status sensor
      if (entityId.includes("test_run_status") && this._matchesDevice(entityId)) {
        testRunStatus = state;
      }
    }

    // Sort ports by port number
    ports.sort((a, b) => a.port - b.port);

    return { ports, testRunStatus, device };
  }

  _matchesDevice(entityId) {
    if (this._config.switch_name) {
      const name = this._config.switch_name.toLowerCase().replace(/[^a-z0-9]/g, "_");
      return entityId.toLowerCase().includes(name);
    }
    return true; // Show all if no filter specified
  }

  // Escape HTML to prevent XSS
  _escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  _getStatusColor(status) {
    return STATUS_COLORS[status] || STATUS_COLORS["Unknown"];
  }

  _getStatusIcon(status) {
    return STATUS_ICONS[status] || STATUS_ICONS["Unknown"];
  }

  _handlePortClick(port) {
    // Store entityId to uniquely identify port across multiple switches
    this._selectedPort = this._selectedPort === port.entityId ? null : port.entityId;
    this._render();
  }

  _handleTestAll() {
    if (!this._hass) return;
    
    // Find the test all button entity
    const entities = Object.keys(this._hass.states);
    for (const entityId of entities) {
      if (entityId.startsWith("button.") && 
          entityId.includes("test_all") &&
          this._matchesDevice(entityId)) {
        this._hass.callService("button", "press", { entity_id: entityId });
        return;
      }
    }
  }

  _handleTestPort(portEntity) {
    if (!this._hass) return;
    
    // Extract the switch prefix from the entity ID
    // Entity format: sensor.{prefix}_port_{N}_cable_status
    const entityMatch = portEntity.entityId.match(/^sensor\.(.+)_port_\d+/);
    if (!entityMatch) {
      console.error("Could not parse entity ID:", portEntity.entityId);
      return;
    }
    const switchPrefix = entityMatch[1];
    
    // Find the Test All button for THIS switch to get the device_id
    const entities = Object.keys(this._hass.states);
    let targetDeviceId = null;
    
    for (const entityId of entities) {
      if (entityId.startsWith("button.") && 
          entityId.includes("test_all") &&
          entityId.includes(switchPrefix)) {
        // Found the button, get its device_id from entities registry
        if (this._hass.entities && this._hass.entities[entityId]) {
          targetDeviceId = this._hass.entities[entityId].device_id;
        }
        break;
      }
    }
    
    // Call the service to test a single port with device targeting
    const serviceData = { port: portEntity.port };
    if (targetDeviceId) {
      serviceData.device_id = targetDeviceId;
    }
    
    this._hass.callService("unifi_cable_tester", "run_cable_test", serviceData);
  }

  _render() {
    if (!this._hass || !this._config) {
      this.shadowRoot.innerHTML = `<ha-card><div class="loading">Loading...</div></ha-card>`;
      return;
    }

    const { ports, testRunStatus, device } = this._getEntities();
    const isRunning = testRunStatus?.state === "Running";
    const columns = this._config.columns;
    const compact = this._config.compact;

    // Build the card HTML
    let html = `
      <style>
        :host {
          --gap: ${compact ? "2px" : "3px"};
        }
        ha-card {
          padding: 12px;
        }
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }
        .card-title {
          font-size: 1em;
          font-weight: 600;
        }
        .device-info {
          font-size: 0.8em;
          color: var(--secondary-text-color);
          margin-bottom: 8px;
          padding: 4px 8px;
          background: var(--primary-background-color);
          border-radius: 6px;
        }
        .device-info .model {
          font-weight: 500;
        }
        .test-status {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 8px;
          border-radius: 6px;
          margin-bottom: 8px;
          font-size: 0.8em;
        }
        .test-status.running {
          background: rgba(255, 193, 7, 0.15);
          color: #FFC107;
        }
        .test-status.completed {
          background: rgba(76, 175, 80, 0.15);
          color: #4CAF50;
        }
        .test-status.failed {
          background: rgba(244, 67, 54, 0.15);
          color: #F44336;
        }
        .test-status.idle {
          background: var(--primary-background-color);
          color: var(--secondary-text-color);
        }
        .ports-grid {
          display: grid;
          grid-template-columns: repeat(${columns}, 1fr);
          gap: var(--gap);
          margin-bottom: 10px;
        }
        .port {
          width: 100%;
          aspect-ratio: 1;
          border-radius: ${compact ? "3px" : "4px"};
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: transform 0.1s, box-shadow 0.1s;
          position: relative;
          font-size: ${compact ? "0.65em" : "0.75em"};
          box-shadow: 0 1px 2px rgba(0,0,0,0.25);
          user-select: none;
          line-height: 1.1;
        }
        .port:hover {
          transform: scale(1.1);
          box-shadow: 0 2px 6px rgba(0,0,0,0.35);
          z-index: 1;
        }
        .port:active {
          transform: scale(0.95);
        }
        .port.selected {
          outline: 2px solid var(--primary-color);
          outline-offset: 1px;
          z-index: 2;
        }
        .port .port-number {
          font-weight: 700;
          font-size: 1.1em;
        }
        .port .port-status {
          font-size: 0.7em;
          opacity: 0.85;
          text-align: center;
          max-width: 100%;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          padding: 0 1px;
          line-height: 1;
        }
        .port.testing {
          animation: pulse 1s infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        .port-details {
          background: var(--primary-background-color);
          border-radius: 6px;
          padding: 10px;
          margin-bottom: 10px;
          font-size: 0.85em;
        }
        .port-details h4 {
          margin: 0 0 8px 0;
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.95em;
        }
        .port-details h5 {
          margin: 8px 0 4px 0;
          font-size: 0.85em;
          color: var(--secondary-text-color);
        }
        .port-details .status-badge {
          padding: 1px 6px;
          border-radius: 3px;
          font-size: 0.85em;
          font-weight: 500;
        }
        .port-details .connection-info {
          font-size: 0.9em;
          line-height: 1.5;
        }
        .port-details .connection-info div {
          margin-bottom: 1px;
        }
        .port-details .pairs-section {
          margin-top: 8px;
          padding-top: 8px;
          border-top: 1px solid var(--divider-color);
        }
        .port-details .pairs {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 4px;
        }
        .port-details .pair {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 6px;
          padding: 4px 8px;
          background: var(--card-background-color);
          border-radius: 4px;
          font-size: 0.85em;
        }
        .port-details .pair-label {
          font-weight: 500;
          color: var(--secondary-text-color);
          font-size: 0.9em;
        }
        .port-details .pair-status {
          font-weight: 500;
        }
        .port-details .pair-length {
          color: var(--secondary-text-color);
          font-size: 0.9em;
        }
        .port-details .fiber-info,
        .port-details .not-tested-info {
          padding: 8px;
          margin-top: 8px;
          border-radius: 4px;
          background: var(--card-background-color);
          font-size: 0.85em;
          color: var(--secondary-text-color);
        }
        .actions {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
        }
        .action-btn {
          background: var(--primary-color);
          color: var(--text-primary-color);
          border: none;
          padding: 5px 12px;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.8em;
          display: inline-flex;
          align-items: center;
          gap: 4px;
          transition: filter 0.15s;
        }
        .action-btn:hover {
          filter: brightness(1.1);
        }
        .action-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .action-btn.secondary {
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
        }
        .legend {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 8px;
          padding-top: 8px;
          border-top: 1px solid var(--divider-color);
          font-size: 0.7em;
        }
        .legend-item {
          display: flex;
          align-items: center;
          gap: 3px;
        }
        .legend-color {
          width: 8px;
          height: 8px;
          border-radius: 2px;
        }
        .no-ports {
          text-align: center;
          padding: 24px;
          color: var(--secondary-text-color);
          font-size: 0.9em;
        }
        .loading {
          text-align: center;
          padding: 24px;
          color: var(--secondary-text-color);
        }
      </style>
      <ha-card>
    `;

    // Header
    if (this._config.show_header) {
      html += `
        <div class="card-header">
          <div class="card-title">${this._escapeHtml(this._config.title)}</div>
        </div>
      `;
    }

    // Device info (from HA device registry)
    if (this._config.show_device_info) {
      const deviceInfo = this._getDeviceInfo(ports);
      if (deviceInfo) {
        html += `
          <div class="device-info">
            <span class="model">${this._escapeHtml(deviceInfo.model)}</span>
            ${deviceInfo.name ? ` &ndash; ${this._escapeHtml(deviceInfo.name)}` : ""}
            ${deviceInfo.mac ? `<br><small>${this._escapeHtml(deviceInfo.mac)}${deviceInfo.version ? ` &bull; FW ${this._escapeHtml(deviceInfo.version)}` : ""}</small>` : ""}
          </div>
        `;
      }
    }

    // Test status
    if (testRunStatus) {
      const statusClass = testRunStatus.state.toLowerCase();
      const attrs = testRunStatus.attributes;
      let statusText = testRunStatus.state;
      
      if (statusClass === "running" && attrs.ports_tested !== undefined) {
        statusText = `Testing... (${attrs.ports_tested}/${attrs.total_ports || "?"} ports)`;
      } else if (statusClass === "completed" && attrs.test_duration_seconds) {
        statusText = `Completed in ${attrs.test_duration_seconds.toFixed(1)}s`;
      } else if (statusClass === "failed" && attrs.error_message) {
        statusText = `Failed: ${attrs.error_message}`;
      }

      html += `
        <div class="test-status ${statusClass}">
          <ha-icon icon="${isRunning ? 'mdi:loading' : 'mdi:information-outline'}"></ha-icon>
          <span>${statusText}</span>
        </div>
      `;
    }

    // Ports grid
    if (ports.length > 0) {
      html += `<div class="ports-grid">`;
      
      for (const port of ports) {
        const color = this._getStatusColor(port.state);
        const isSelected = this._selectedPort === port.entityId;
        const isTesting = isRunning && port.state === "Testing";
        
        // Determine text color based on background brightness
        const textColor = this._getContrastColor(color);
        
        html += `
          <div class="port ${isSelected ? 'selected' : ''} ${isTesting ? 'testing' : ''}"
               style="background-color: ${color}; color: ${textColor};"
               data-entity="${port.entityId}">
            <span class="port-number">${port.port}</span>
            <span class="port-status">${this._truncateStatus(port.state)}</span>
          </div>
        `;
      }
      
      html += `</div>`;

      // Selected port details
      if (this._selectedPort !== null) {
        const selectedPortData = ports.find(p => p.entityId === this._selectedPort);
        if (selectedPortData) {
          const attrs = selectedPortData.attributes;
          const color = this._getStatusColor(selectedPortData.state);
          
          html += `
            <div class="port-details">
              <h4>
                Port ${selectedPortData.port}
                <span class="status-badge" style="background:${color};color:${this._getContrastColor(color)}">
                  ${selectedPortData.state}
                </span>
              </h4>
          `;

          // Connection info - show first
          html += `<div class="connection-info">`;
          if (attrs.port_connected !== undefined && attrs.port_connected !== null) {
            const connIcon = attrs.port_connected ? '🟢' : '🔴';
            html += `<div><strong>Connected:</strong> ${connIcon} ${attrs.port_connected ? "Yes" : "No"}</div>`;
          }
          if (attrs.port_speed) {
            html += `<div><strong>Speed:</strong> ${this._escapeHtml(String(attrs.port_speed))}</div>`;
          }
          if (attrs.port_speed_mbps) {
            html += `<div><strong>Link Speed:</strong> ${attrs.port_speed_mbps} Mbps</div>`;
          }
          if (attrs.port_type) {
            html += `<div><strong>Type:</strong> ${this._escapeHtml(String(attrs.port_type))}</div>`;
          }
          if (attrs.last_tested) {
            const lastTested = new Date(attrs.last_tested);
            html += `<div><strong>Last Tested:</strong> ${lastTested.toLocaleString()}</div>`;
          }
          html += `</div>`;

          // Pair details (2-column grid for compactness)
          if (selectedPortData.state !== "Fiber" && selectedPortData.state !== "Not Tested") {
            html += `<div class="pairs-section"><h5>Cable Pairs</h5><div class="pairs">`;
            // Use pair_1, pair_2, etc. (numbers, not letters)
            const pairs = [
              { key: "pair_1", label: "Pair A (1-2)" },
              { key: "pair_2", label: "Pair B (3-6)" },
              { key: "pair_3", label: "Pair C (4-5)" },
              { key: "pair_4", label: "Pair D (7-8)" },
            ];
            
            for (const pair of pairs) {
              const status = attrs[`${pair.key}_status`] || "N/A";
              const length = attrs[`${pair.key}_length`];
              const lengthStr = length !== null && length !== undefined ? `${length}m` : "-";
              const pairColor = this._getStatusColor(status);
              
              html += `
                <div class="pair">
                  <span class="pair-label">${pair.label}</span>
                  <span class="pair-status" style="color:${pairColor}">${status} ${lengthStr !== "-" ? lengthStr : ""}</span>
                </div>
              `;
            }
            html += `</div></div>`;
          } else if (selectedPortData.state === "Fiber") {
            html += `<div class="fiber-info">🔵 This is a fiber/SFP port - cable testing not applicable</div>`;
          } else {
            html += `<div class="not-tested-info">⚪ No test data - click "Test Port" to run cable diagnostics</div>`;
          }

          // Test single port button
          if (this._config.show_test_button) {
            html += `
              <div style="margin-top: 12px;">
                <button class="action-btn secondary" data-action="test-port" data-entity="${selectedPortData.entityId}" ${isRunning ? 'disabled' : ''}>
                  <ha-icon icon="mdi:ethernet-cable"></ha-icon>
                  Test Port ${selectedPortData.port}
                </button>
              </div>
            `;
          }

          html += `</div>`;
        }
      }
    } else {
      html += `
        <div class="no-ports">
          <ha-icon icon="mdi:ethernet-cable-off"></ha-icon>
          <p>No port sensors found. Make sure the integration is configured.</p>
        </div>
      `;
    }

    // Action buttons
    if (this._config.show_test_button && ports.length > 0) {
      html += `
        <div class="actions">
          <button class="action-btn" data-action="test-all" ${isRunning ? 'disabled' : ''}>
            <ha-icon icon="mdi:play-circle"></ha-icon>
            ${isRunning ? 'Testing...' : 'Test All Cables'}
          </button>
          <button class="action-btn secondary" data-action="refresh">
            <ha-icon icon="mdi:refresh"></ha-icon>
            Refresh Status
          </button>
        </div>
      `;
    }

    // Legend
    html += `
      <div class="legend">
        ${Object.entries(STATUS_COLORS).map(([status, color]) => `
          <div class="legend-item">
            <div class="legend-color" style="background: ${color}"></div>
            <span>${status}</span>
          </div>
        `).join('')}
      </div>
    `;

    html += `</ha-card>`;

    this.shadowRoot.innerHTML = html;

    // Add event listeners
    this.shadowRoot.querySelectorAll('.port').forEach(el => {
      el.addEventListener('click', () => {
        const entityId = el.dataset.entity;
        const portData = ports.find(p => p.entityId === entityId);
        if (portData) {
          this._handlePortClick(portData);
        }
      });
    });

    this.shadowRoot.querySelectorAll('[data-action="test-all"]').forEach(el => {
      el.addEventListener('click', () => this._handleTestAll());
    });

    this.shadowRoot.querySelectorAll('[data-action="refresh"]').forEach(el => {
      el.addEventListener('click', () => this._handleRefresh());
    });

    this.shadowRoot.querySelectorAll('[data-action="test-port"]').forEach(el => {
      el.addEventListener('click', () => {
        const entityId = el.dataset.entity;
        const portData = ports.find(p => p.entityId === entityId);
        if (portData) {
          this._handleTestPort(portData);
        }
      });
    });
  }

  _truncateStatus(status) {
    const shortNames = {
      "Impedance Mismatch": "Impedance",
      "Not Tested": "N/T",
      "Test Failed": "Failed",
    };
    return shortNames[status] || status;
  }

  // Look up device info from the HA device registry
  _getDeviceInfo(ports) {
    if (!this._hass || !this._hass.devices || !this._hass.entities || ports.length === 0) return null;

    // Get the device_id from the first port entity via the entity registry
    const firstEntityId = ports[0].entityId;
    const entityEntry = this._hass.entities[firstEntityId];
    if (!entityEntry || !entityEntry.device_id) return null;

    const device = this._hass.devices[entityEntry.device_id];
    if (!device) return null;

    return {
      name: device.name_by_user || device.name || "",
      model: device.model || "",
      mac: (device.connections || []).find(c => c[0] === "mac")?.[1] || "",
      version: device.sw_version || "",
    };
  }

  // Refresh port status by pressing the refresh button
  _handleRefresh() {
    if (!this._hass) return;
    const entities = Object.keys(this._hass.states);
    for (const entityId of entities) {
      if (entityId.startsWith("button.") &&
          entityId.includes("refresh") &&
          this._matchesDevice(entityId)) {
        this._hass.callService("button", "press", { entity_id: entityId });
        return;
      }
    }
  }

  _getContrastColor(hexColor) {
    // Convert hex to RGB
    const hex = hexColor.replace('#', '');
    const r = parseInt(hex.substr(0, 2), 16);
    const g = parseInt(hex.substr(2, 2), 16);
    const b = parseInt(hex.substr(4, 2), 16);
    
    // Calculate luminance
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    
    return luminance > 0.5 ? '#000000' : '#FFFFFF';
  }

  getCardSize() {
    return 4;
  }

  static getConfigElement() {
    return document.createElement("unifi-cable-tester-card-editor");
  }

  static getStubConfig() {
    return {
      title: "UniFi Cable Tester",
      show_header: true,
      show_test_button: true,
      show_device_info: true,
      columns: 12,
    };
  }
}

// Card Editor
class UnifiCableTesterCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _detectSwitches() {
    // Auto-detect switches by finding cable_status entities and grouping by prefix
    if (!this._hass) return [];
    
    const switches = new Map(); // prefix -> { name, entityCount, sampleEntity }
    const entities = Object.keys(this._hass.states);
    
    for (const entityId of entities) {
      // Match entities with cable_status and port_ in the name
      // More lenient matching than strict regex
      if (entityId.startsWith("sensor.") && 
          entityId.includes("cable_status") &&
          entityId.includes("_port_")) {
        
        // Extract everything before _port_N_cable_status
        const portMatch = entityId.match(/^sensor\.(.+)_port_(\d+)/);
        if (portMatch) {
          const prefix = portMatch[1];
          if (!switches.has(prefix)) {
            // Try to create a friendly name from the prefix
            let friendlyName = prefix
              .replace(/_/g, ' ')
              .replace(/\b\w/g, c => c.toUpperCase());
            
            // Check if it looks like an IP address pattern
            const ipMatch = prefix.match(/(\d+)_(\d+)_(\d+)_(\d+)/);
            if (ipMatch) {
              friendlyName = `Switch ${ipMatch[1]}.${ipMatch[2]}.${ipMatch[3]}.${ipMatch[4]}`;
            }
            
            switches.set(prefix, {
              prefix,
              friendlyName,
              entityCount: 0,
            });
          }
          switches.get(prefix).entityCount++;
        }
      }
    }
    
    return Array.from(switches.values()).sort((a, b) => 
      a.friendlyName.localeCompare(b.friendlyName)
    );
  }

  _render() {
    if (!this._hass) return;

    const detectedSwitches = this._detectSwitches();
    
    // Build switch options for dropdown
    let switchOptions = '<option value="">All Switches</option>';
    for (const sw of detectedSwitches) {
      const selected = this._config.switch_name === sw.prefix ? 'selected' : '';
      switchOptions += `<option value="${sw.prefix}" ${selected}>${sw.friendlyName} (${sw.entityCount} ports)</option>`;
    }
    
    // Show helpful message if no switches found
    const noSwitchesWarning = detectedSwitches.length === 0 
      ? '<div class="warning">No UniFi Cable Tester switches found. Make sure the integration is set up.</div>'
      : '';

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          max-width: 400px;
        }
        .config-row {
          margin-bottom: 16px;
        }
        .config-row label {
          display: block;
          margin-bottom: 4px;
          font-weight: 500;
          font-size: 14px;
        }
        .config-row input[type="text"],
        .config-row select {
          width: 100%;
          max-width: 300px;
          padding: 8px 12px;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 4px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #000);
          font-size: 14px;
          box-sizing: border-box;
        }
        .config-row input:focus, .config-row select:focus {
          outline: none;
          border-color: var(--primary-color, #03a9f4);
        }
        .config-row input[type="checkbox"] {
          width: 18px;
          height: 18px;
          margin-right: 8px;
          padding: 0;
        }
        .config-row input[type="number"] {
          width: 80px;
          max-width: 80px;
          padding: 8px 12px;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 4px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #000);
          font-size: 14px;
          box-sizing: border-box;
        }
        .checkbox-row {
          display: flex;
          align-items: center;
        }
        .checkbox-row label {
          margin-bottom: 0;
        }
        .warning {
          background: rgba(255, 152, 0, 0.2);
          color: #FF9800;
          padding: 12px;
          border-radius: 8px;
          margin-bottom: 16px;
        }
        .detected-info {
          font-size: 0.85em;
          color: var(--secondary-text-color);
          margin-top: 4px;
        }
      </style>
      
      ${noSwitchesWarning}
      
      <div class="config-row">
        <label>Switch</label>
        <select id="switch_name">
          ${switchOptions}
        </select>
        <div class="detected-info">
          ${detectedSwitches.length} switch${detectedSwitches.length !== 1 ? 'es' : ''} detected
        </div>
      </div>
      
      <div class="config-row">
        <label>Card Title</label>
        <input type="text" id="title" value="${this._config.title || 'UniFi Cable Tester'}">
      </div>
      
      <div class="config-row">
        <label>Columns (ports per row)</label>
        <input type="number" id="columns" value="${this._config.columns || 12}" min="4" max="24">
      </div>
      
      <div class="config-row checkbox-row">
        <input type="checkbox" id="show_header" ${this._config.show_header !== false ? 'checked' : ''}>
        <label for="show_header">Show Header</label>
      </div>
      
      <div class="config-row checkbox-row">
        <input type="checkbox" id="show_test_button" ${this._config.show_test_button !== false ? 'checked' : ''}>
        <label for="show_test_button">Show Test Buttons</label>
      </div>
      
      <div class="config-row checkbox-row">
        <input type="checkbox" id="show_device_info" ${this._config.show_device_info !== false ? 'checked' : ''}>
        <label for="show_device_info">Show Device Info</label>
      </div>
      
      <div class="config-row checkbox-row">
        <input type="checkbox" id="compact" ${this._config.compact ? 'checked' : ''}>
        <label for="compact">Compact Mode</label>
      </div>
    `;

    // Bind events
    const inputs = ['switch_name', 'title', 'columns', 'show_header', 'show_test_button', 'show_device_info', 'compact'];
    inputs.forEach(id => {
      const el = this.shadowRoot.getElementById(id);
      if (el) {
        el.addEventListener('change', (e) => this._valueChanged(id, e.target));
      }
    });
  }

  _valueChanged(id, target) {
    let value;
    if (target.type === 'checkbox') {
      value = target.checked;
    } else if (target.type === 'number') {
      value = parseInt(target.value);
    } else {
      value = target.value;
    }

    this._config = { ...this._config, [id]: value };
    
    const event = new CustomEvent('config-changed', {
      detail: { config: this._config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }
}

// Register the card
customElements.define("unifi-cable-tester-card", UnifiCableTesterCard);
customElements.define("unifi-cable-tester-card-editor", UnifiCableTesterCardEditor);

// Register with Home Assistant
window.customCards = window.customCards || [];
window.customCards.push({
  type: "unifi-cable-tester-card",
  name: "UniFi Cable Tester",
  description: "Visual display of UniFi switch cable test results",
  preview: true,
  documentationURL: "https://github.com/richardctrimble/ha-unificablestatus",
});

console.info(
  `%c UNIFI-CABLE-TESTER-CARD %c v${CARD_VERSION} `,
  "color: white; background: #4CAF50; font-weight: bold;",
  "color: #4CAF50; background: white; font-weight: bold;"
);
