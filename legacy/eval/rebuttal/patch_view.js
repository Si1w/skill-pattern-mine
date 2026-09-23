// Render patch text without interpreting it as HTML or hiding context lines.
function parsePatch(text) {
    const files = [];
    let file = null, oldLine = null, newLine = null;
    for (const textLine of text.split('\n')) {
        if (textLine.startsWith('diff --git ') || !file) {
            file = {header: textLine.startsWith('diff --git ') ? textLine : 'Patch', rows: []};
            files.push(file);
            oldLine = newLine = null;
            if (textLine.startsWith('diff --git ')) continue;
        }
        const hunk = textLine.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
        const row = {text: textLine, kind: 'meta', oldLine: '', newLine: ''};
        if (hunk) {
            oldLine = Number(hunk[1]);
            newLine = Number(hunk[2]);
            row.kind = 'hunk';
        } else if (textLine.startsWith('+') && (newLine !== null || !textLine.startsWith('+++'))) {
            row.kind = 'added';
            if (newLine !== null) row.newLine = newLine++;
        } else if (textLine.startsWith('-') && (oldLine !== null || !textLine.startsWith('---'))) {
            row.kind = 'removed';
            if (oldLine !== null) row.oldLine = oldLine++;
        } else if (textLine.startsWith(' ') && oldLine !== null) {
            row.kind = 'context';
            row.oldLine = oldLine++;
            row.newLine = newLine++;
        }
        file.rows.push(row);
    }
    return files;
}

function renderPatch(text) {
    const container = document.getElementById('patch');
    const picker = document.getElementById('patchFile');
    container.replaceChildren();
    picker.replaceChildren();
    const files = parsePatch(text);
    files.forEach((file, index) => {
        const option = document.createElement('option');
        option.value = index;
        option.textContent = `${index + 1}. ${file.header.replace(/^diff --git /, '')}`;
        picker.appendChild(option);
        const details = document.createElement('details');
        details.className = 'diff-file';
        details.open = true;
        const summary = document.createElement('summary');
        summary.textContent = file.header;
        details.appendChild(summary);
        const table = document.createElement('table');
        table.className = 'diff-table';
        table.setAttribute('aria-label', file.header);
        const body = document.createElement('tbody');
        for (const row of file.rows) {
            const tr = document.createElement('tr');
            tr.className = row.kind;
            for (const [name, value] of [['old-number', row.oldLine], ['new-number', row.newLine], ['diff-code', row.text]]) {
                const td = document.createElement('td');
                td.className = name;
                td.textContent = value;
                if (name !== 'diff-code') td.title = name === 'old-number' ? 'Original line' : 'Modified line';
                tr.appendChild(td);
            }
            body.appendChild(tr);
        }
        table.appendChild(body);
        details.appendChild(table);
        container.appendChild(details);
    });
    document.getElementById('rawPatch').textContent = text;
    document.getElementById('patchStats').textContent = `${files.length} files · ${text.split('\n').length.toLocaleString()} patch lines · all context retained`;
    container.scrollTop = 0;
    document.getElementById('rawPatch').scrollTop = 0;
    let changeIndex = -1;
    const changes = [...container.querySelectorAll('.hunk')];
    for (const [id, delta] of [['previousHunk', -1], ['nextHunk', 1]]) {
        document.getElementById(id).onclick = () => {
            if (!changes.length) return;
            changeIndex = changeIndex < 0 ? (delta > 0 ? 0 : changes.length - 1) :
                (changeIndex + delta + changes.length) % changes.length;
            const target = changes[changeIndex];
            target.closest('details').open = true;
            target.scrollIntoView({block: 'center'});
        };
    }
    picker.onchange = () => {
        const target = container.children[Number(picker.value)];
        target.open = true;
        target.scrollIntoView({block: 'start'});
    };
}

function setupPatchControls() {
    const pane = document.getElementById('patchPane');
    document.getElementById('wrapPatch').onchange = event => pane.classList.toggle('no-wrap', !event.target.checked);
    document.getElementById('patchFont').onchange = event => pane.style.setProperty('--patch-font', `${event.target.value}px`);
    document.getElementById('rawToggle').onchange = event => {
        const raw = event.target.checked;
        document.getElementById('patch').hidden = raw;
        document.getElementById('rawPatch').hidden = !raw;
        for (const id of ['patchFile', 'previousHunk', 'nextHunk']) document.getElementById(id).disabled = raw;
    };
    document.getElementById('widerPatch').onclick = event => {
        const wide = document.querySelector('main').classList.toggle('wide-patch');
        event.currentTarget.textContent = wide ? 'Balanced view' : 'Wider patch';
        event.currentTarget.setAttribute('aria-pressed', String(wide));
    };
}
