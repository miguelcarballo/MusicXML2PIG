/**
 * keyboard.js
 * Draws the vertical piano keyboard on the labels canvas (left side of piano roll).
 * Depends on globals: labelsCanvas, labelsCtx, minPitch, maxPitch, pixelsPerPitch
 * and the isBlackKey() function from utility.js.
 */

function drawLabelsCanvas() {
    const pitchRange = maxPitch - minPitch;
    const height = pitchRange * pixelsPerPitch + 100;
    const labelsWidth = 31;

    labelsCanvas.width = labelsWidth;
    labelsCanvas.height = height;

    labelsCtx.fillStyle = '#ffffff';
    labelsCtx.fillRect(0, 0, labelsWidth, height);

    // Horizontal grid lines
    labelsCtx.strokeStyle = '#f0f0f0';
    labelsCtx.lineWidth = 1;
    for (let p = minPitch; p <= maxPitch; p++) {
        const y = height - 50 - (p - minPitch) * pixelsPerPitch;
        labelsCtx.beginPath();
        labelsCtx.moveTo(0, y);
        labelsCtx.lineTo(labelsWidth, y);
        labelsCtx.stroke();
    }

    const keyboardX    = 0;
    const whiteKeyWidth  = 31;
    const blackKeyWidth  = 14;
    // 7 white keys per octave
    const whiteKeyHeight = (12 * pixelsPerPitch) / 7;
    // MIDI pitch-class positions of white keys within an octave
    const whiteKeyPattern = [0, 2, 4, 5, 7, 9, 11];

    // Layer 1 — white keys
    for (let p = minPitch; p <= maxPitch; p++) {
        const noteInOctave = p % 12;
        if (whiteKeyPattern.includes(noteInOctave)) {
            const whiteKeyIndex  = whiteKeyPattern.indexOf(noteInOctave);
            const octaveNumber   = Math.floor(p / 12);
            const cOfThisOctave  = octaveNumber * 12;
            const cYTop          = height - 50 - (cOfThisOctave - minPitch) * pixelsPerPitch;
            const cYBottom       = cYTop + pixelsPerPitch;
            const y              = cYBottom - (whiteKeyIndex + 1) * whiteKeyHeight;

            labelsCtx.fillStyle   = '#ffffff';
            labelsCtx.fillRect(keyboardX, y, whiteKeyWidth, whiteKeyHeight);
            labelsCtx.strokeStyle = '#000000';
            labelsCtx.lineWidth   = 1.0;
            labelsCtx.strokeRect(keyboardX, y, whiteKeyWidth, whiteKeyHeight);
        }
    }

    // Layer 2 — black keys (drawn on top)
    for (let p = minPitch; p <= maxPitch; p++) {
        if (isBlackKey(p)) {
            const y            = height - 50 - (p - minPitch) * pixelsPerPitch;
            const blackKeyHeight = pixelsPerPitch * 0.9;

            labelsCtx.fillStyle   = '#000000';
            labelsCtx.fillRect(keyboardX, y - blackKeyHeight / 2 + pixelsPerPitch / 2, blackKeyWidth, blackKeyHeight);
            labelsCtx.strokeStyle = '#555555';
            labelsCtx.lineWidth   = 0.4;
            labelsCtx.strokeRect(keyboardX, y - blackKeyHeight / 2 + pixelsPerPitch / 2, blackKeyWidth, blackKeyHeight);
        }
    }

    // C labels inside white C keys
    labelsCtx.fillStyle    = '#000';
    labelsCtx.font         = 'bold 9px Arial';
    labelsCtx.textAlign    = 'center';
    labelsCtx.textBaseline = 'middle';
    for (let p = minPitch; p <= maxPitch; p++) {
        if (p % 12 === 0) {
            const octaveNumber  = Math.floor(p / 12) - 1;  // MIDI 60 = C4
            const cOfThisOctave = (octaveNumber + 1) * 12;
            const cYTop         = height - 50 - (cOfThisOctave - minPitch) * pixelsPerPitch;
            const cYBottom      = cYTop + pixelsPerPitch;
            const y             = cYBottom - 1 * whiteKeyHeight;
            const labelX        = keyboardX + whiteKeyWidth - 6;
            const labelY        = y + whiteKeyHeight / 2;
            labelsCtx.fillText('C' + octaveNumber, labelX, labelY);
        }
    }
}
