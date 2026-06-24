/**
 * Shared utility functions for the PIG piano-roll verifier.
 * Depends on globals: zoom, tooltip, drawPianoRoll.
 */

function midiToNoteName(midi) {
    const notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
    const octave = Math.floor(midi / 12) - 1;
    return notes[midi % 12] + octave;
}

function isBlackKey(midi) {
    const noteInOctave = midi % 12;
    // Black keys: C#(1), D#(3), F#(6), G#(8), A#(10)
    return [1, 3, 6, 8, 10].includes(noteInOctave);
}

function zoomIn()    { zoom *= 1.5; drawPianoRoll(); }
function zoomOut()   { zoom /= 1.5; drawPianoRoll(); }
function resetView() { zoom = 1.0;  drawPianoRoll(); }

function renderStats(overrides, rankNum) {
    const container = document.getElementById('stats-container');
    container.innerHTML = '';

    const allEntries = Object.entries(stats);
    const hasGroups  = allEntries.some(([k]) => k.startsWith('§'));

    if (!hasGroups) {
        allEntries.forEach(([label, value], i) => {
            if (i > 0) {
                const sep = document.createElement('div');
                sep.className = 'stat-group-sep';
                container.appendChild(sep);
            }
            const item = document.createElement('div');
            item.className = 'stat-item';
            item.innerHTML = `<span class="stat-label">${label}:</span><span class="stat-value">${value}</span>`;
            container.appendChild(item);
        });
        return;
    }

    // Grouped stats are kept for compatibility with future verifier extensions.
    function renderEntries(entries, sectionLabel) {
        let firstGroup = true;
        let groupDiv = null;

        function flushGroup() { if (groupDiv) container.appendChild(groupDiv); }

        entries.forEach(([label, value]) => {
            if (label.startsWith('§')) {
                flushGroup();
                if (!firstGroup) {
                    const sep = document.createElement('div');
                    sep.className = 'stat-group-sep';
                    container.appendChild(sep);
                }
                firstGroup = false;
                groupDiv = document.createElement('div');
                groupDiv.className = 'stat-group';
                const hdr = document.createElement('span');
                hdr.className = 'stat-group-label';
                hdr.textContent = sectionLabel || label.slice(1);
                sectionLabel = null;
                groupDiv.appendChild(hdr);
            } else if (groupDiv) {
                const item = document.createElement('div');
                item.className = 'stat-item';
                item.innerHTML = `<span class="stat-label">${label}:</span><span class="stat-value">${value}</span>`;
                groupDiv.appendChild(item);
            }
        });
        flushGroup();
    }

    renderEntries(allEntries, null);

    if (overrides && typeof overrides === 'object' && Object.keys(overrides).length > 0) {
        const sep = document.createElement('div');
        sep.className = 'stat-group-sep';
        container.appendChild(sep);
        const rankLabel = rankNum != null ? `Rank ${rankNum}` : 'Rank';
        renderEntries([['\u00a7rank', null], ...Object.entries(overrides)], rankLabel);
    }
}

function positionTooltip(e) {
    const tooltipWidth  = 300;
    const tooltipHeight = tooltip.offsetHeight || 220;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = e.clientX + 15;
    let top  = e.clientY + 15;
    if (left + tooltipWidth  > vw) left = e.clientX - tooltipWidth  - 15;
    if (top  + tooltipHeight > vh) top  = e.clientY - tooltipHeight - 15;
    if (left < 0) left = 10;
    if (top  < 0) top  = 10;
    tooltip.style.left = left + 'px';
    tooltip.style.top  = top  + 'px';
}
