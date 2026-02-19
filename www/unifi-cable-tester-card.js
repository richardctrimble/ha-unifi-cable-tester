/**
 * UniFi Cable Tester Card
 * Custom Lovelace card for displaying UniFi switch cable test results
 */

const CARD_VERSION = "1.1.0";

// Status colors
const STATUS_COLORS = {
  "OK": "#4CAF50",           // Green
  "Open": "#F44336",         // Red
  "Short": "#FF5722",        // Deep Orange
  "Impedance Mismatch": "#FF9800", // Orange
  "Fiber": "#2196F3",        // Blue
  "Not Tested": "#9E9E9E",   // Gray
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
  }

  static get properties() {
    return {
      _config: {},
      _hass: {},
      _selectedPort: {},
    };
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
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _getEntities() {
    if (!this._hass) return { ports: [], testRunStatus: null, device: null };

    const entities = Object.keys(this._hass.states);
    const ports = [];
    let testRunStatus = null;
    let device = null;

    // Find entities by device_id or switch_name pattern
    const pattern = this._config.device_id || this._config.switch_name || "";

    for (const entityId of entities) {
      const state = this._hass.states[entityId];
      
      // Match cable test sensors (port sensors)
      // Entity names are like: sensor.unifi_switch_port_1_cable_status
      if (entityId.startsWith("sensor.") && 
          entityId.includes("cable_status") &&
          entityId.includes("port_")) {
        
        // Check if this entity belongs to our device
        if (this._matchesDevice(entityId, state)) {
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
      if (entityId.includes("test_run_status") && this._matchesDevice(entityId, state)) {
        testRunStatus = state;
      }

      // Find device info from any matching entity
      if (this._matchesDevice(entityId, state) && state.attributes.device_model) {
        device = {
          name: state.attributes.device_name || "UniFi Switch",
          model: state.attributes.device_model || "Unknown",
          mac: state.attributes.device_mac || "",
          version: state.attributes.device_version || "",
        };
      }
    }

    // Sort ports by port number
    ports.sort((a, b) => a.port - b.port);

    return { ports, testRunStatus, device };
  }

  _matchesDevice(entityId, state) {
    // Match by device_id in attributes or entity naming pattern
    if (this._config.device_id) {
      return state.attributes.device_id === this._config.device_id ||
             entityId.includes(this._config.device_id);
    }
    if (this._config.switch_name) {
      const name = this._config.switch_name.toLowerCase().replace(/[^a-z0-9]/g, "_");
      return entityId.toLowerCase().includes(name);
    }
    return true; // Show all if no filter specified
  }

  _getStatusColor(status) {
    return STATUS_COLORS[status] || STATUS_COLORS["Unknown"];
  }

  _getStatusIcon(status) {
    return STATUS_ICONS[status] || STATUS_ICONS["Unknown"];
  }

  _formatPairDetails(attributes) {
    const pairs = ["pair_a", "pair_b", "pair_c", "pair_d"];
    const details = [];
    
    for (const pair of pairs) {
      const status = attributes[`${pair}_status`];
      const length = attributes[`${pair}_length`];
      
      if (status && status !== "Not Tested") {
        const lengthStr = length ? ` (${length}m)` : "";
        details.push(`${pair.replace("_", " ").toUpperCase()}: ${status}${lengthStr}`);
      }
    }
    
    return details;
  }

  _handlePortClick(port) {
    this._selectedPort = this._selectedPort === port.port ? null : port.port;
    this._render();
  }

  _handleTestAll() {
    if (!this._hass) return;
    
    // Find the test all button entity
    const entities = Object.keys(this._hass.states);
    for (const entityId of entities) {
      if (entityId.startsWith("button.") && 
          entityId.includes("test_all") &&
          this._matchesDevice(entityId, this._hass.states[entityId])) {
        this._hass.callService("button", "press", { entity_id: entityId });
        return;
      }
    }
  }

  _handleTestPort(port) {
    if (!this._hass) return;
    
    // Call the service to test a single port
    this._hass.callService("unifi_cable_tester", "run_cable_test", {
      port: port,
    });
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
          --port-size: ${compact ? "40px" : "50px"};
          --gap: 6px;
        }
        ha-card {
          padding: 16px;
        }
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }
        .card-title {
          font-size: 1.2em;
          font-weight: 500;
        }
        .device-info {
          font-size: 0.85em;
          color: var(--secondary-text-color);
          margin-bottom: 12px;
          padding: 8px 12px;
          background: var(--primary-background-color);
          border-radius: 8px;
        }
        .device-info .model {
          font-weight: 500;
        }
        .test-status {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          border-radius: 8px;
          margin-bottom: 12px;
          font-size: 0.9em;
        }
        .test-status.running {
          background: rgba(255, 193, 7, 0.2);
          color: #FFC107;
        }
        .test-status.completed {
          background: rgba(76, 175, 80, 0.2);
          color: #4CAF50;
        }
        .test-status.failed {
          background: rgba(244, 67, 54, 0.2);
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
          margin-bottom: 16px;
        }
        .port {
          width: 100%;
          aspect-ratio: 1;
          border-radius: 8px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.2s ease;
          position: relative;
          font-size: ${compact ? "0.75em" : "0.85em"};
          box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .port:hover {
          transform: scale(1.05);
          box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }
        .port.selected {
          outline: 3px solid var(--primary-color);
          outline-offset: 2px;
        }
        .port .port-number {
          font-weight: bold;
          font-size: 1.1em;
        }
        .port .port-status {
          font-size: 0.8em;
          opacity: 0.9;
          text-align: center;
          max-width: 100%;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          padding: 0 2px;
        }
        .port.testing {
          animation: pulse 1s infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }
        .port-details {
          background: var(--primary-background-color);
          border-radius: 8px;
          padding: 12px;
          margin-bottom: 12px;
        }
        .port-details h4 {
          margin: 0 0 8px 0;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .port-details .status-badge {
          padding: 2px 8px;
          border-radius: 4px;
          font-size: 0.85em;
          font-weight: 500;
        }
        .port-details .pairs {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 8px;
          margin-top: 8px;
        }
        .port-details .pair {
          padding: 6px 10px;
          background: var(--card-background-color);
          border-radius: 6px;
          font-size: 0.85em;
        }
        .port-details .pair-label {
          font-weight: 500;
          color: var(--secondary-text-color);
        }
        .port-details .connection-info {
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid var(--divider-color);
          font-size: 0.85em;
          color: var(--secondary-text-color);
        }
        .actions {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }
        .action-btn {
          background: var(--primary-color);
          color: var(--text-primary-color);
          border: none;
          padding: 8px 16px;
          border-radius: 8px;
          cursor: pointer;
          font-size: 0.9em;
          display: flex;
          align-items: center;
          gap: 6px;
          transition: background 0.2s;
        }
        .action-btn:hover {
          background: var(--primary-color);
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
          gap: 12px;
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid var(--divider-color);
          font-size: 0.8em;
        }
        .legend-item {
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .legend-color {
          width: 12px;
          height: 12px;
          border-radius: 3px;
        }
        .no-ports {
          text-align: center;
          padding: 32px;
          color: var(--secondary-text-color);
        }
        .loading {
          text-align: center;
          padding: 32px;
          color: var(--secondary-text-color);
        }
      </style>
      <ha-card>
    `;

    // Header
    if (this._config.show_header) {
      html += `
        <div class="card-header">
          <div class="card-title">${this._config.title}</div>
        </div>
      `;
    }

    // Device info
    if (this._config.show_device_info && device) {
      html += `
        <div class="device-info">
          <span class="model">${device.model}</span>
          ${device.name ? ` - ${device.name}` : ""}
          ${device.mac ? `<br><small>${device.mac}</small>` : ""}
        </div>
      `;
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
        const isSelected = this._selectedPort === port.port;
        const isTesting = isRunning && port.state === "Testing";
        
        // Determine text color based on background brightness
        const textColor = this._getContrastColor(color);
        
        html += `
          <div class="port ${isSelected ? 'selected' : ''} ${isTesting ? 'testing' : ''}"
               style="background-color: ${color}; color: ${textColor};"
               data-port="${port.port}">
            <span class="port-number">${port.port}</span>
            <span class="port-status">${this._truncateStatus(port.state)}</span>
          </div>
        `;
      }
      
      html += `</div>`;

      // Selected port details
      if (this._selectedPort !== null) {
        const selectedPortData = ports.find(p => p.port === this._selectedPort);
        if (selectedPortData) {
          const attrs = selectedPortData.attributes;
          const color = this._getStatusColor(selectedPortData.state);
          
          html += `
            <div class="port-details">
              <h4>
                Port ${selectedPortData.port}
                <span class="status-badge" style="background: ${color}; color: ${this._getContrastColor(color)}">
                  ${selectedPortData.state}
                </span>
              </h4>
          `;

          // Pair details
          if (selectedPortData.state !== "Fiber" && selectedPortData.state !== "Not Tested") {
            html += `<div class="pairs">`;
            const pairs = [
              { key: "pair_a", label: "Pair A" },
              { key: "pair_b", label: "Pair B" },
              { key: "pair_c", label: "Pair C" },
              { key: "pair_d", label: "Pair D" },
            ];
            
            for (const pair of pairs) {
              const status = attrs[`${pair.key}_status`] || "N/A";
              const length = attrs[`${pair.key}_length`];
              const lengthStr = length ? ` (${length}m)` : "";
              const pairColor = this._getStatusColor(status);
              
              html += `
                <div class="pair">
                  <span class="pair-label">${pair.label}:</span>
                  <span style="color: ${pairColor}">${status}${lengthStr}</span>
                </div>
              `;
            }
            html += `</div>`;
          }

          // Connection info
          if (attrs.connected !== undefined || attrs.speed) {
            html += `<div class="connection-info">`;
            if (attrs.connected !== undefined) {
              html += `<strong>Connected:</strong> ${attrs.connected ? "Yes" : "No"} `;
            }
            if (attrs.speed) {
              html += `<strong>Speed:</strong> ${attrs.speed} `;
            }
            if (attrs.port_type) {
              html += `<strong>Type:</strong> ${attrs.port_type}`;
            }
            html += `</div>`;
          }

          // Test single port button
          if (this._config.show_test_button) {
            html += `
              <div style="margin-top: 12px;">
                <button class="action-btn secondary" data-action="test-port" data-port="${selectedPortData.port}" ${isRunning ? 'disabled' : ''}>
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
        const port = parseInt(el.dataset.port);
        const portData = ports.find(p => p.port === port);
        if (portData) {
          this._handlePortClick(portData);
        }
      });
    });

    this.shadowRoot.querySelectorAll('[data-action="test-all"]').forEach(el => {
      el.addEventListener('click', () => this._handleTestAll());
    });

    this.shadowRoot.querySelectorAll('[data-action="test-port"]').forEach(el => {
      el.addEventListener('click', () => {
        const port = parseInt(el.dataset.port);
        this._handleTestPort(port);
      });
    });
  }

  _truncateStatus(status) {
    const shortNames = {
      "Impedance Mismatch": "Impedance",
      "Not Tested": "N/T",
    };
    return shortNames[status] || status;
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
      // Match: sensor.XXXX_port_N_cable_status
      const match = entityId.match(/^sensor\.(.+)_port_\d+_cable_status$/);
      if (match) {
        const prefix = match[1];
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
        .config-row {
          margin-bottom: 16px;
        }
        .config-row label {
          display: block;
          margin-bottom: 4px;
          font-weight: 500;
        }
        .config-row input, .config-row select {
          width: 100%;
          padding: 8px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        .config-row input[type="checkbox"] {
          width: auto;
          margin-right: 8px;
        }
        .checkbox-row {
          display: flex;
          align-items: center;
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
