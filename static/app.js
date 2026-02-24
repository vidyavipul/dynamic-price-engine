/**
 * Dynamic Pricing Engine — Frontend Logic
 *
 * Handles vehicle selection, API calls, and result rendering.
 * Overrides are auto-detected server-side — no manual toggles.
 */

// ── State ──
let selectedVehicle = 'standard_bike';
let vehiclesData = [];

// ── Vehicle emoji mapping ──
const VEHICLE_EMOJIS = {
    scooter: '🛵',
    standard_bike: '🏍️',
    premium_bike: '⚡',
    super_premium: '🔥',
};

// ── Initialize ──
document.addEventListener('DOMContentLoaded', async () => {
    setDefaultDatetime();
    await loadVehicles();
});

function setDefaultDatetime() {
    const input = document.getElementById('rentalDatetime');
    const now = new Date();
    const daysUntilSat = (6 - now.getDay() + 7) % 7 || 7;
    const nextSat = new Date(now);
    nextSat.setDate(now.getDate() + daysUntilSat);
    nextSat.setHours(9, 0, 0, 0);

    const pad = n => String(n).padStart(2, '0');
    input.value = `${nextSat.getFullYear()}-${pad(nextSat.getMonth() + 1)}-${pad(nextSat.getDate())}T${pad(nextSat.getHours())}:${pad(nextSat.getMinutes())}`;
}

async function loadVehicles() {
    try {
        const resp = await fetch('/api/vehicles');
        const data = await resp.json();
        vehiclesData = data.vehicles;
        renderVehicles(vehiclesData);
    } catch (err) {
        vehiclesData = [
            { type: 'scooter', name: 'Scooter (Activa, Jupiter)', base_rate: 60 },
            { type: 'standard_bike', name: 'Standard Bike (Pulsar, FZ)', base_rate: 80 },
            { type: 'premium_bike', name: 'Premium Bike (RE Classic, Dominar)', base_rate: 150 },
            { type: 'super_premium', name: 'Super Premium (Himalayan, KTM 390)', base_rate: 250 },
        ];
        renderVehicles(vehiclesData);
    }
}

// ── Render Functions ──

function renderVehicles(vehicles) {
    const grid = document.getElementById('vehicleGrid');
    grid.innerHTML = vehicles.map(v => `
        <div class="vehicle-card ${v.type === selectedVehicle ? 'selected' : ''}"
             onclick="selectVehicle('${v.type}')" id="vehicle-${v.type}">
            <div class="vehicle-emoji">${VEHICLE_EMOJIS[v.type] || '🏍️'}</div>
            <div class="vehicle-name">${v.name.split('(')[0].trim()}</div>
            <div class="vehicle-rate"><span>₹${v.base_rate}/hr</span> • ${v.name.match(/\((.+)\)/)?.[1] || ''}</div>
        </div>
    `).join('');
}

function selectVehicle(type) {
    selectedVehicle = type;
    document.querySelectorAll('.vehicle-card').forEach(card => {
        card.classList.toggle('selected', card.id === `vehicle-${type}`);
    });
}

// ── Calculate Price ──

async function calculatePrice() {
    const btn = document.getElementById('calculateBtn');
    const datetime = document.getElementById('rentalDatetime').value;
    const duration = parseInt(document.getElementById('durationHours').value);

    if (!datetime) {
        alert('Please select a rental date and time.');
        return;
    }

    btn.classList.add('loading');
    btn.innerHTML = '<span class="btn-icon">⏳</span> Calculating...';

    try {
        const resp = await fetch('/api/price', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rental_datetime: datetime + ':00',
                vehicle_type: selectedVehicle,
                duration_hours: duration,
            }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Failed to calculate price');
        }

        const result = await resp.json();
        renderResults(result);
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        btn.classList.remove('loading');
        btn.innerHTML = '<span class="btn-icon">💰</span> Calculate Dynamic Price';
    }
}

// ── Render Results ──

function renderResults(result) {
    const section = document.getElementById('resultsSection');
    section.style.display = 'block';
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Price hero
    const priceValue = document.getElementById('priceValue');
    priceValue.textContent = `₹${Math.round(result.final_price).toLocaleString('en-IN')}`;
    priceValue.className = 'price-value';
    if (result.final_multiplier > 1.2) {
        priceValue.classList.add('surge');
    } else if (result.final_multiplier < 0.9) {
        priceValue.classList.add('discount');
    }

    // Price meta
    document.getElementById('priceMeta').textContent =
        `${result.vehicle_name} • ${result.duration_hours}hrs • ${result.demand.zone_emoji} ${result.demand.zone} Demand`;

    // Stats
    document.getElementById('surgeValue').textContent = `${result.final_multiplier.toFixed(2)}×`;
    document.getElementById('demandScore').textContent = result.demand.score.toFixed(2);
    document.getElementById('demandZone').innerHTML =
        `${result.demand.zone_emoji} ${result.demand.zone}`;
    document.getElementById('effectiveRate').textContent =
        `₹${result.effective_hourly_rate.toFixed(0)}/hr`;

    // Color the surge value
    const surgeEl = document.getElementById('surgeValue');
    if (result.final_multiplier > 1.2) {
        surgeEl.style.color = '#ef4444';
    } else if (result.final_multiplier < 0.9) {
        surgeEl.style.color = '#22c55e';
    } else {
        surgeEl.style.color = '';
    }

    // Demand gauge
    const fillPercent = result.demand.score * 100;
    const marker = document.getElementById('gaugeMarker');
    marker.style.left = `${fillPercent}%`;
    marker.style.background = result.demand.zone_color || '#fff';

    // Gauge detail
    document.getElementById('gaugeDetail').innerHTML =
        `<strong>${result.demand.zone_emoji} ${result.demand.zone}</strong> — ${result.demand.zone_description}` +
        `<br><span style="color: var(--text-muted);">Day: ${result.demand.day_type.replace(/_/g, ' ')} (${result.demand.day_type_score.toFixed(2)}) • ` +
        `Season: ${result.demand.season_score.toFixed(2)} • Time: ${result.demand.time_slot_score.toFixed(2)}</span>`;

    // Auto-detected overrides
    const overridesCard = document.getElementById('overridesCard');
    if (result.overrides_detected && result.overrides_detected.length > 0) {
        overridesCard.style.display = 'block';
        const overridesList = document.getElementById('overridesList');
        overridesList.innerHTML = result.overrides_detected.map(o => {
            const isDiscount = o.effect === 'discount';
            const arrow = isDiscount ? '↓' : '↑';
            const colorClass = isDiscount ? 'override-discount' : 'override-surge';
            const confDot = { high: '●', medium: '◐', low: '○' }[o.confidence] || '○';

            return `
                <div class="override-item ${colorClass}">
                    <div class="override-item-header">
                        <span class="override-item-name">${arrow} ${o.name}</span>
                        <span class="override-item-factor">×${o.factor.toFixed(2)}</span>
                    </div>
                    <div class="override-item-reason">${confDot} ${o.confidence} confidence — ${o.reason}</div>
                </div>
            `;
        }).join('');
    } else {
        overridesCard.style.display = 'none';
    }

    // Explanation steps
    const stepsContainer = document.getElementById('explanationSteps');
    stepsContainer.innerHTML = result.explanation.map((step, i) => `
        <div class="explanation-step">
            <div class="step-number">${i + 1}</div>
            <div>${step}</div>
        </div>
    `).join('');

    // Warnings
    const warningsCard = document.getElementById('warningsCard');
    if (result.warnings && result.warnings.length > 0) {
        warningsCard.style.display = 'block';
        document.getElementById('warningsList').innerHTML =
            result.warnings.map(w => `<div class="warning-item">${w}</div>`).join('');
    } else {
        warningsCard.style.display = 'none';
    }
}
