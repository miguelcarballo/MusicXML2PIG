/**
 * Piano-roll rendering for PIG fingering TXT verification.
 *
 * Note schema from Python:
 *   id, onset, offset, pitch_midi, pitch_name, hand,
 *   finger, finger_label, velocity_on, velocity_off
 */

let zoom = 1.0;
let pixelsPerSecond = 100;
let pixelsPerPitch = 15;

function drawPianoRoll() {
    const width = maxTime * pixelsPerSecond * zoom + 100;
    const pitchRange = maxPitch - minPitch;
    const height = pitchRange * pixelsPerPitch + 100;

    canvas.width = width;
    canvas.height = height;

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);

    ctx.fillStyle = '#ebebeb';
    for (let p = minPitch; p <= maxPitch; p++) {
        if (isBlackKey(p)) {
            const y = height - 50 - (p - minPitch) * pixelsPerPitch;
            ctx.fillRect(0, y, width, pixelsPerPitch);
        }
    }

    ctx.strokeStyle = '#f0f0f0';
    ctx.lineWidth = 1;
    ctx.setLineDash([]);
    for (let t = 0; t <= maxTime; t++) {
        const x = t * pixelsPerSecond * zoom;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
    }
    for (let p = minPitch; p <= maxPitch; p++) {
        const y = height - 50 - (p - minPitch) * pixelsPerPitch;
        ctx.strokeStyle = '#f0f0f0';
        ctx.lineWidth = 1;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
        if (p % 12 === 0) {
            const yBottom = y + pixelsPerPitch;
            ctx.strokeStyle = '#000000';
            ctx.setLineDash([5, 3]);
            ctx.beginPath();
            ctx.moveTo(0, yBottom);
            ctx.lineTo(width, yBottom);
            ctx.stroke();
            ctx.setLineDash([]);
        }
    }

    const showRight = document.getElementById('show-right').checked;
    const showLeft = document.getElementById('show-left').checked;

    notes.forEach(note => {
        if (note.hand === 'right' && !showRight) return;
        if (note.hand === 'left' && !showLeft) return;

        const x = note.onset * pixelsPerSecond * zoom;
        const y = height - 50 - (note.pitch_midi - minPitch) * pixelsPerPitch;
        const w = Math.max((note.offset - note.onset) * pixelsPerSecond * zoom, 4);
        const h = pixelsPerPitch - 2;

        const color = note.finger ? (fingeringColors[note.finger] || '#999') : '#808080';
        ctx.fillStyle = color;
        ctx.fillRect(x, y, w, h);

        ctx.strokeStyle = '#333';
        ctx.lineWidth = 1;
        ctx.strokeRect(x, y, w, h);

        if (note.finger && w > 18 && h > 10) {
            ctx.fillStyle = '#000';
            ctx.font = 'bold 11px Arial';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(note.finger, x + w / 2, y + h / 2 - 1);
        }
    });

    ctx.fillStyle = '#000';
    ctx.font = '12px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (let t = 0; t <= maxTime; t += 2) {
        ctx.fillText(t.toFixed(1) + 's', t * pixelsPerSecond * zoom, height - 45);
    }

    drawLabelsCanvas();
}

canvas.addEventListener('mousemove', event => {
    const rect = canvas.getBoundingClientRect();
    const mx = event.clientX - rect.left;
    const my = event.clientY - rect.top;
    const height = canvas.height;

    let found = null;
    for (const note of notes) {
        const nx = note.onset * pixelsPerSecond * zoom;
        const ny = height - 50 - (note.pitch_midi - minPitch) * pixelsPerPitch;
        const nw = Math.max((note.offset - note.onset) * pixelsPerSecond * zoom, 4);
        const nh = pixelsPerPitch - 2;
        if (mx >= nx && mx <= nx + nw && my >= ny && my <= ny + nh) {
            found = note;
            break;
        }
    }

    if (found) {
        let tooltipHtml = `<div class="tooltip-row"><strong>${found.pitch_name}</strong> (MIDI ${found.pitch_midi})</div>`;
        tooltipHtml += `<div class="tooltip-row">ID: <strong>${found.id}</strong></div>`;
        tooltipHtml += `<div class="tooltip-row">Time: ${found.onset.toFixed(3)}s - ${found.offset.toFixed(3)}s</div>`;
        tooltipHtml += `<div class="tooltip-row">Hand: ${found.hand === 'right' ? 'Right' : 'Left'}</div>`;
        tooltipHtml += '<div class="tooltip-divider">PIG values</div>';
        tooltipHtml += `<div class="tooltip-current">Finger: <strong>${found.finger_label}</strong></div>`;
        tooltipHtml += `<div class="tooltip-current">Velocity: ${found.velocity_on} / ${found.velocity_off}</div>`;

        tooltip.innerHTML = tooltipHtml;
        tooltip.style.display = 'block';
        positionTooltip(event);
    } else {
        tooltip.style.display = 'none';
    }
});

canvas.addEventListener('mouseleave', () => {
    tooltip.style.display = 'none';
});

renderStats();
drawPianoRoll();
