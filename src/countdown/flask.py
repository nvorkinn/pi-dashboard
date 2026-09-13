from typing import Any
import requests
from flask import Flask, jsonify, redirect, render_template_string, request

from countdown.config_manager import config_manager

app = Flask(__name__)

TFL_API_BASE = "https://api.tfl.gov.uk"


def _get_tfl_params() -> dict[str, str]:
    config = config_manager.load_config()
    return {"app_key": config.tfl.app_key} if config.tfl.app_key else {}


def _resolve_stop_info(stop_id: str, session: requests.Session) -> dict[str, Any] | None:
    """Fetch details for a specific NaPTAN ID and format it for the UI."""
    try:
        r = session.get(f"{TFL_API_BASE}/StopPoint/{stop_id}", params=_get_tfl_params(), timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()

        # Find target in node or its children
        def search_node(node):
            nid = node.get("id") or node.get("naptanId")
            if nid == stop_id:
                return node
            for child in node.get("children", []):
                found = search_node(child)
                if found:
                    return found
            return None

        target = search_node(data) or data
        stop_type = target.get("stopType")
        common_name = target.get("commonName", stop_id)
        modes = target.get("modes", [])
        letter = target.get("stopLetter") or target.get("indicator") or ""
        lines = [l.get("name") for l in target.get("lines", []) if l.get("name")]

        is_tube = "tube" in modes or stop_type == "NaptanMetroStation"
        clean_name = common_name.removesuffix(" Underground Station").strip()

        return {
            "id": stop_id,
            "name": clean_name,
            "mode": "tube" if is_tube else "bus",
            "letter": letter,
            "lines": lines[:8],
            "line_count": len(lines),
        }
    except Exception as e:
        print(f"Error resolving stop {stop_id}: {e}")
        return None


@app.route("/api/search", methods=["GET"])
def search_stops():
    """Searches TfL API for stops and extracts selectable Tube stations and Bus stops."""
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return jsonify([])

    try:
        session = requests.Session()
        params = {"modes": "tube,bus", "maxResults": "15", **_get_tfl_params()}
        res = session.get(f"{TFL_API_BASE}/StopPoint/Search/{query}", params=params, timeout=6)
        res.raise_for_status()
        matches = res.json().get("matches", [])

        results = []
        seen = set()

        for match in matches[:8]:
            mid = match.get("id")
            try:
                sp_res = session.get(f"{TFL_API_BASE}/StopPoint/{mid}", params=_get_tfl_params(), timeout=5)
                if sp_res.status_code != 200:
                    continue
                sp = sp_res.json()

                def extract(node):
                    nid = node.get("id") or node.get("naptanId")
                    if not nid or nid in seen:
                        return
                    st = node.get("stopType")

                    if st == "NaptanMetroStation":
                        seen.add(nid)
                        lines = [l.get("name") for l in node.get("lines", []) if l.get("name")]
                        name = node.get("commonName", "").removesuffix(" Underground Station").strip()
                        results.append({
                            "id": nid,
                            "name": name,
                            "mode": "tube",
                            "letter": "",
                            "lines": lines,
                            "subtitle": f"Underground • {', '.join(lines) if lines else 'All lines'}"
                        })
                    elif st == "NaptanPublicBusCoachTram":
                        seen.add(nid)
                        letter = node.get("stopLetter") or node.get("indicator") or ""
                        lines = [l.get("name") for l in node.get("lines", []) if l.get("name")]
                        subtitle = f"Stop {letter} • {', '.join(lines[:6])}" if letter else f"Bus • {', '.join(lines[:6])}"
                        if len(lines) > 6:
                            subtitle += f" (+{len(lines) - 6} more)"
                        results.append({
                            "id": nid,
                            "name": node.get("commonName", ""),
                            "mode": "bus",
                            "letter": letter,
                            "lines": lines,
                            "subtitle": subtitle
                        })

                    for child in node.get("children", []):
                        extract(child)

                extract(sp)
            except Exception as ex:
                print(f"Error parsing search result {mid}: {ex}")

        return jsonify(results)
    except Exception as e:
        print(f"TfL Search API error: {e}")
        return jsonify([]), 500


@app.route("/", methods=["GET", "POST"])
def index():
    config = config_manager.load_config()

    if request.method == "POST":
        # Form submitted to update stops and settings
        raw_stops = request.form.get("stops_order", "")
        stop_ids = [s.strip() for s in raw_stops.split(",") if s.strip()]
        config.tfl.stop_ids = stop_ids

        interval_val = request.form.get("interval", "10").strip()
        if interval_val.isdigit() and int(interval_val) > 0:
            config.interval = int(interval_val)

        weather_loc = request.form.get("weather_location", "").strip()
        if weather_loc:
            config.weather.location = weather_loc

        spotify_enabled = request.form.get("spotify_enabled") == "on"
        config.spotify.enabled = spotify_enabled

        config_manager.save_config(config)
        return redirect("/")

    # Resolve existing stops to display details
    session = requests.Session()
    existing_stop_ids = config.tfl.stop_ids
    resolved_stops = []
    for sid in existing_stop_ids:
        info = _resolve_stop_info(sid, session)
        if info:
            resolved_stops.append(info)
        else:
            resolved_stops.append({"id": sid, "name": sid, "mode": "unknown", "letter": "", "lines": [], "line_count": 0})

    return render_template_string(HTML_TEMPLATE, config=config, stops=resolved_stops)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transit Countdown Display Settings</title>
    <style>
        :root {
            --tfl-blue: #0019A8;
            --tfl-red: #EE2E24;
            --tfl-dark: #1e293b;
            --bg-page: #f8fafc;
            --bg-card: #ffffff;
            --border: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #64748b;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        body {
            background-color: var(--bg-page);
            color: var(--text-main);
            padding: 30px 20px;
            display: flex;
            justify-content: center;
        }

        .container {
            width: 100%;
            max-width: 820px;
        }

        header {
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-badge {
            background-color: var(--tfl-red);
            color: white;
            font-weight: 800;
            font-size: 13px;
            padding: 4px 10px;
            border-radius: 9999px;
            letter-spacing: 0.5px;
        }

        h1 {
            font-size: 24px;
            font-weight: 700;
        }

        .card {
            background: var(--bg-card);
            border-radius: 12px;
            border: 1px solid var(--border);
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }

        .card-header {
            margin-bottom: 16px;
        }

        .card-title {
            font-size: 17px;
            font-weight: 600;
            margin-bottom: 4px;
        }

        .card-subtitle {
            font-size: 13px;
            color: var(--text-muted);
        }

        /* Search Box */
        .search-container {
            position: relative;
            margin-bottom: 16px;
        }

        .search-input {
            width: 100%;
            padding: 12px 16px;
            font-size: 15px;
            border: 1px solid var(--border);
            border-radius: 8px;
            outline: none;
            transition: border-color 0.2s;
        }

        .search-input:focus {
            border-color: var(--tfl-blue);
            box-shadow: 0 0 0 3px rgba(0,25,168,0.1);
        }

        .search-spinner {
            position: absolute;
            right: 14px;
            top: 14px;
            font-size: 12px;
            color: var(--text-muted);
            display: none;
        }

        .search-results {
            margin-top: 8px;
            border: 1px solid var(--border);
            border-radius: 8px;
            max-height: 280px;
            overflow-y: auto;
            background: #fff;
            display: none;
        }

        .search-item {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            transition: background 0.15s;
        }

        .search-item:last-child {
            border-bottom: none;
        }

        .search-item:hover {
            background-color: #f1f5f9;
        }

        .item-info {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .mode-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 11px;
            border-radius: 6px;
            width: 28px;
            height: 28px;
            color: white;
            flex-shrink: 0;
        }

        .mode-tube {
            background-color: var(--tfl-red);
        }

        .mode-bus {
            background-color: var(--tfl-blue);
        }

        .item-text h4 {
            font-size: 14px;
            font-weight: 600;
        }

        .item-text p {
            font-size: 12px;
            color: var(--text-muted);
        }

        .btn-add {
            background-color: #0f172a;
            color: white;
            border: none;
            padding: 6px 12px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: opacity 0.2s;
        }

        .btn-add:hover {
            opacity: 0.85;
        }

        /* Stops List */
        .stops-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
            min-height: 50px;
        }

        .stop-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 16px;
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 8px;
        }

        .stop-order {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .order-badge {
            font-size: 12px;
            font-weight: 700;
            background: #e2e8f0;
            color: #475569;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 9999px;
        }

        .stop-actions {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .btn-action {
            background: white;
            border: 1px solid var(--border);
            padding: 6px 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            color: #334155;
            transition: background 0.15s;
        }

        .btn-action:hover {
            background: #f1f5f9;
        }

        .btn-delete {
            color: #dc2626;
        }

        .btn-delete:hover {
            background: #fee2e2;
            border-color: #fca5a5;
        }

        .empty-stops {
            text-align: center;
            padding: 24px;
            color: var(--text-muted);
            font-size: 14px;
            border: 1px dashed var(--border);
            border-radius: 8px;
        }

        /* Settings grid */
        .form-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-top: 12px;
        }

        .form-group label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 6px;
        }

        .form-group input[type="text"],
        .form-group input[type="number"] {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid var(--border);
            border-radius: 6px;
            font-size: 14px;
        }

        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 26px;
        }

        .btn-save {
            background-color: var(--tfl-blue);
            color: white;
            border: none;
            padding: 12px 24px;
            font-size: 15px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            width: 100%;
            margin-top: 16px;
            transition: opacity 0.2s;
        }

        .btn-save:hover {
            opacity: 0.9;
        }

        .page-badge {
            font-size: 11px;
            color: var(--text-muted);
            margin-left: 6px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <span class="brand-badge">COUNTDOWN</span>
                <h1>Display Settings</h1>
            </div>
        </header>

        <!-- Search & Add Stops -->
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">Search & Add TfL Stops</h2>
                <p class="card-subtitle">Search for Tube stations, interchange hubs, or Bus stops (e.g. "Kennington", "Kings Cross", "Elephant")</p>
            </div>
            <div class="search-container">
                <input type="text" id="searchInput" class="search-input" placeholder="Type a station, street, or stop name..." autocomplete="off">
                <span id="searchSpinner" class="search-spinner">Searching TfL...</span>
                <div id="searchResults" class="search-results"></div>
            </div>
        </div>

        <form method="POST">
            <!-- Ordered Stops List -->
            <div class="card">
                <div class="card-header">
                    <h2 class="card-title">Configured Arrival Stops</h2>
                    <p class="card-subtitle">The display shows 2 stops at a time and cycles through this list on each refresh cycle.</p>
                </div>

                <input type="hidden" name="stops_order" id="stopsOrderInput" value="{{ stops | map(attribute='id') | join(',') }}">

                <div id="stopsList" class="stops-list">
                    {% if stops %}
                        {% for stop in stops %}
                            <div class="stop-card" data-id="{{ stop.id }}">
                                <div class="stop-order">
                                    <span class="order-badge">{{ loop.index }}</span>
                                    <div class="mode-icon {% if stop.mode == 'tube' %}mode-tube{% else %}mode-bus{% endif %}">
                                        {% if stop.mode == 'tube' %}🚇{% else %}{{ stop.letter or '🚌' }}{% endif %}
                                    </div>
                                    <div class="item-text">
                                        <h4>{{ stop.name }}</h4>
                                        <p>
                                            NaPTAN: <code>{{ stop.id }}</code>
                                            {% if stop.lines %} • {{ stop.lines | join(', ') }}{% endif %}
                                            <span class="page-badge">Page {{ ((loop.index0 // 2) + 1) }}</span>
                                        </p>
                                    </div>
                                </div>
                                <div class="stop-actions">
                                    <button type="button" class="btn-action btn-move-up" title="Move Up">▲</button>
                                    <button type="button" class="btn-action btn-move-down" title="Move Down">▼</button>
                                    <button type="button" class="btn-action btn-delete" title="Remove">✕</button>
                                </div>
                            </div>
                        {% endfor %}
                    {% else %}
                        <div class="empty-stops">No stops configured. Search and add stops above to begin.</div>
                    {% endif %}
                </div>
            </div>

            <!-- General Display Settings -->
            <div class="card">
                <div class="card-header">
                    <h2 class="card-title">General Display Settings</h2>
                    <p class="card-subtitle">Adjust refresh rates and peripheral panels.</p>
                </div>
                <div class="form-grid">
                    <div class="form-group">
                        <label for="interval">Refresh Interval (Seconds)</label>
                        <input type="number" id="interval" name="interval" value="{{ config.interval }}" min="5" max="300" required>
                    </div>

                    <div class="form-group">
                        <label for="weather_location">Weather Location</label>
                        <input type="text" id="weather_location" name="weather_location" value="{{ config.weather.location }}">
                    </div>

                    <div class="form-group checkbox-group">
                        <input type="checkbox" id="spotify_enabled" name="spotify_enabled" {% if config.spotify.enabled %}checked{% endif %}>
                        <label for="spotify_enabled" style="margin: 0; cursor: pointer;">Enable Spotify Now Playing Panel</label>
                    </div>
                </div>

                <button type="submit" class="btn-save">Save & Apply Settings</button>
            </div>
        </form>
    </div>

    <script>
        const searchInput = document.getElementById('searchInput');
        const searchSpinner = document.getElementById('searchSpinner');
        const searchResults = document.getElementById('searchResults');
        const stopsList = document.getElementById('stopsList');
        const stopsOrderInput = document.getElementById('stopsOrderInput');

        let debounceTimeout = null;

        // Auto-search as user types
        searchInput.addEventListener('input', () => {
            clearTimeout(debounceTimeout);
            const query = searchInput.value.trim();
            if (query.length < 2) {
                searchResults.style.display = 'none';
                searchResults.innerHTML = '';
                return;
            }

            searchSpinner.style.display = 'block';
            debounceTimeout = setTimeout(() => {
                fetch(`/api/search?q=${encodeURIComponent(query)}`)
                    .then(r => r.json())
                    .then(data => {
                        searchSpinner.style.display = 'none';
                        renderSearchResults(data);
                    })
                    .catch(err => {
                        searchSpinner.style.display = 'none';
                        console.error('Search error:', err);
                    });
            }, 300);
        });

        function renderSearchResults(items) {
            if (!items || items.length === 0) {
                searchResults.innerHTML = '<div style="padding: 12px 16px; color: #64748b; font-size: 13px;">No matching stops found.</div>';
                searchResults.style.display = 'block';
                return;
            }

            searchResults.innerHTML = items.map(item => `
                <div class="search-item">
                    <div class="item-info">
                        <div class="mode-icon ${item.mode === 'tube' ? 'mode-tube' : 'mode-bus'}">
                            ${item.mode === 'tube' ? '🚇' : (item.letter || '🚌')}
                        </div>
                        <div class="item-text">
                            <h4>${item.name}</h4>
                            <p>${item.subtitle} • <code>${item.id}</code></p>
                        </div>
                    </div>
                    <button type="button" class="btn-add" onclick='addStop(${JSON.stringify(item)})'>+ Add</button>
                </div>
            `).join('');
            searchResults.style.display = 'block';
        }

        function updateOrderBadges() {
            const cards = stopsList.querySelectorAll('.stop-card');
            const ids = [];
            cards.forEach((card, idx) => {
                card.querySelector('.order-badge').textContent = idx + 1;
                const pageNum = Math.floor(idx / 2) + 1;
                const badge = card.querySelector('.page-badge');
                if (badge) badge.textContent = `Page ${pageNum}`;
                ids.push(card.dataset.id);
            });
            stopsOrderInput.value = ids.join(',');

            const emptyNotice = stopsList.querySelector('.empty-stops');
            if (cards.length === 0 && !emptyNotice) {
                stopsList.innerHTML = '<div class="empty-stops">No stops configured. Search and add stops above to begin.</div>';
            } else if (cards.length > 0 && emptyNotice) {
                emptyNotice.remove();
            }
        }

        window.addStop = function(stop) {
            const currentIds = stopsOrderInput.value ? stopsOrderInput.value.split(',') : [];
            if (currentIds.includes(stop.id)) {
                alert('This stop is already in your display list.');
                return;
            }

            const emptyNotice = stopsList.querySelector('.empty-stops');
            if (emptyNotice) emptyNotice.remove();

            const card = document.createElement('div');
            card.className = 'stop-card';
            card.dataset.id = stop.id;
            card.innerHTML = `
                <div class="stop-order">
                    <span class="order-badge">1</span>
                    <div class="mode-icon ${stop.mode === 'tube' ? 'mode-tube' : 'mode-bus'}">
                        ${stop.mode === 'tube' ? '🚇' : (stop.letter || '🚌')}
                    </div>
                    <div class="item-text">
                        <h4>${stop.name}</h4>
                        <p>NaPTAN: <code>${stop.id}</code> • ${stop.lines.join(', ')} <span class="page-badge"></span></p>
                    </div>
                </div>
                <div class="stop-actions">
                    <button type="button" class="btn-action btn-move-up" title="Move Up">▲</button>
                    <button type="button" class="btn-action btn-move-down" title="Move Down">▼</button>
                    <button type="button" class="btn-action btn-delete" title="Remove">✕</button>
                </div>
            `;
            stopsList.appendChild(card);
            attachCardEvents(card);
            updateOrderBadges();

            // Clear search
            searchInput.value = '';
            searchResults.style.display = 'none';
        };

        function attachCardEvents(card) {
            card.querySelector('.btn-move-up').addEventListener('click', () => {
                const prev = card.previousElementSibling;
                if (prev && prev.classList.contains('stop-card')) {
                    stopsList.insertBefore(card, prev);
                    updateOrderBadges();
                }
            });

            card.querySelector('.btn-move-down').addEventListener('click', () => {
                const next = card.nextElementSibling;
                if (next && next.classList.contains('stop-card')) {
                    stopsList.insertBefore(next, card);
                    updateOrderBadges();
                }
            });

            card.querySelector('.btn-delete').addEventListener('click', () => {
                card.remove();
                updateOrderBadges();
            });
        }

        // Attach to existing cards
        stopsList.querySelectorAll('.stop-card').forEach(attachCardEvents);
    </script>
</body>
</html>
"""
