// Summify frontend: submit a job, poll it, then render the reading page.
//
// The stage rail is built from whatever stage_label the API reports, in the
// order the API reports it — the list is never hardcoded here, so adding a
// stage server-side needs no change in this file.

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 20 * 60 * 1000; // give up after 20 minutes
const SPEEDS = [1, 1.25, 1.5, 2];
const WORDS_PER_MINUTE = 220;

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('job-form');
    const urlInput = document.getElementById('video-url');
    const pasteBtn = document.getElementById('paste-btn');
    const languageSelect = document.getElementById('language');
    const runBtn = document.getElementById('run-btn');
    const runLabel = document.getElementById('run-label');
    const formError = document.getElementById('form-error');

    const states = {
        idle: document.getElementById('state-idle'),
        processing: document.getElementById('state-processing'),
        error: document.getElementById('state-error'),
        result: document.getElementById('state-result')
    };

    const progressPercent = document.getElementById('progress-percent');
    const stageList = document.getElementById('stage-list');

    const errorMessage = document.getElementById('error-message');
    const errorReset = document.getElementById('error-reset');

    const readProgress = document.getElementById('read-progress');
    const readProgressFill = document.getElementById('read-progress-fill');

    const resultMedia = document.getElementById('result-media');
    const embed = document.getElementById('result-embed');
    const watchLink = document.getElementById('watch-link');
    const resultKicker = document.getElementById('result-kicker');
    const resultTitle = document.getElementById('result-title');
    const resultMeta = document.getElementById('result-meta');
    const resultProse = document.getElementById('result-prose');
    const resultFooter = document.getElementById('result-footer');

    const keyPointsBlock = document.getElementById('key-points-block');
    const keyPointsList = document.getElementById('key-points-list');
    const sectionList = document.getElementById('section-list');
    const chapterBlock = document.getElementById('chapter-block');
    const chapterList = document.getElementById('chapter-list');

    const listenBlock = document.getElementById('listen-block');
    const audio = document.getElementById('audio-player');
    const dockPlay = document.getElementById('dock-play');
    const dockPlayLabel = document.getElementById('dock-play-label');
    const iconPlay = dockPlay.querySelector('.icon-play');
    const iconPause = dockPlay.querySelector('.icon-pause');
    const dockScrub = document.getElementById('dock-scrub');
    const dockTime = document.getElementById('dock-time');
    const dockSpeed = document.getElementById('dock-speed');

    const copyBtn = document.getElementById('copy-btn');
    const copyLabel = document.getElementById('copy-label');
    const downloadBtn = document.getElementById('download-btn');

    let pollTimer = null;
    let jobRunning = false;
    let stages = [];
    let current = null; // the job request + result currently on screen
    let copyResetTimer = null;

    // ── Small helpers ──────────────────────────────────────────────────

    function selectedMode() {
        const checked = form.querySelector('input[name="mode"]:checked');
        return checked ? checked.value : '';
    }

    function languageName(code) {
        const option = languageSelect.querySelector('option[value="' + code + '"]');
        return option ? option.textContent.replace(/^in\s+/, '') : code;
    }

    function pad(value) {
        return String(value).padStart(2, '0');
    }

    // 0:00, or 1:02:03 once past an hour.
    function formatClock(seconds) {
        if (!isFinite(seconds) || seconds < 0) seconds = 0;
        const total = Math.floor(seconds);
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const secs = total % 60;
        if (hours > 0) return hours + ':' + pad(minutes) + ':' + pad(secs);
        return minutes + ':' + pad(secs);
    }

    function formatDuration(seconds) {
        if (!isFinite(seconds) || seconds <= 0) return '';
        const total = Math.round(seconds);
        const hours = Math.floor(total / 3600);
        const minutes = Math.round((total % 3600) / 60);
        if (hours > 0) return hours + ' hr ' + minutes + ' min';
        return Math.max(1, minutes) + ' min';
    }

    function readingMinutes(text) {
        const words = (text || '').trim().split(/\s+/).filter(Boolean).length;
        return Math.max(1, Math.round(words / WORDS_PER_MINUTE));
    }

    function slugify(text) {
        return (text || 'summify')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .slice(0, 60) || 'summify';
    }

    function clear(node) {
        while (node.firstChild) node.removeChild(node.firstChild);
    }

    function showError(text) {
        formError.textContent = text;
        formError.hidden = false;
    }

    function clearError() {
        formError.textContent = '';
        formError.hidden = true;
    }

    // ── State machine ──────────────────────────────────────────────────

    function setState(name) {
        Object.keys(states).forEach(function (key) {
            states[key].hidden = key !== name;
        });
        readProgress.hidden = name !== 'result';
        if (name !== 'result') readProgressFill.style.transform = 'scaleX(0)';
    }

    // Called whenever a job stops for any reason, so the UI never gets stuck.
    function finishJob() {
        jobRunning = false;
        runBtn.disabled = false;
        if (pollTimer) {
            clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    function failJob(message) {
        finishJob();
        errorMessage.textContent = message;
        setState('error');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── Stage rail ─────────────────────────────────────────────────────

    function checkIcon() {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', '13');
        svg.setAttribute('height', '13');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '3.2');
        svg.setAttribute('stroke-linecap', 'round');
        svg.setAttribute('stroke-linejoin', 'round');
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', 'M20 6 9 17l-5-5');
        svg.appendChild(path);
        return svg;
    }

    function renderStages() {
        clear(stageList);
        stages.forEach(function (stage, index) {
            const active = index === stages.length - 1;

            const item = document.createElement('li');
            item.className = 'stage-item ' + (active ? 'is-active' : 'is-done');

            const icon = document.createElement('span');
            icon.className = 'stage-icon';
            if (active) {
                const spinner = document.createElement('span');
                spinner.className = 'spinner';
                icon.appendChild(spinner);
            } else {
                icon.appendChild(checkIcon());
            }

            const label = document.createElement('span');
            label.className = 'stage-label';
            label.textContent = stage.label;

            item.appendChild(icon);
            item.appendChild(label);
            stageList.appendChild(item);
        });
    }

    function recordStage(job) {
        const key = job.stage || job.stage_label || 'working';
        const label = job.stage_label || 'Working';
        const last = stages[stages.length - 1];
        if (last && last.key === key) {
            if (last.label === label) return;
            last.label = label;
        } else {
            stages.push({ key: key, label: label });
        }
        renderStages();
    }

    function setProgress(value) {
        let pct = Number(value);
        if (!isFinite(pct)) pct = 0;
        pct = Math.max(0, Math.min(100, Math.round(pct)));
        progressPercent.textContent = pct + '%';
    }

    // ── Reading progress ───────────────────────────────────────────────

    let scrollQueued = false;

    function updateReadProgress() {
        scrollQueued = false;
        if (readProgress.hidden) return;
        const scrollable = document.documentElement.scrollHeight - window.innerHeight;
        const fraction = scrollable > 0 ? Math.min(1, window.scrollY / scrollable) : 0;
        readProgressFill.style.transform = 'scaleX(' + fraction + ')';
    }

    window.addEventListener('scroll', function () {
        if (scrollQueued) return;
        scrollQueued = true;
        window.requestAnimationFrame(updateReadProgress);
    }, { passive: true });

    window.addEventListener('resize', updateReadProgress);

    // ── Audio dock ─────────────────────────────────────────────────────

    function syncScrub() {
        const duration = audio.duration;
        const usable = isFinite(duration) && duration > 0;
        const fraction = usable ? audio.currentTime / duration : 0;
        dockScrub.value = String(fraction * 100);
        dockScrub.style.setProperty('--p', (fraction * 100).toFixed(1) + '%');
        dockScrub.setAttribute('aria-valuetext',
            formatClock(audio.currentTime) + ' of ' + formatClock(usable ? duration : 0));
        dockTime.textContent = formatClock(audio.currentTime) + ' / ' +
            formatClock(usable ? duration : 0);
        dockScrub.disabled = !usable;
    }

    function syncPlayButton() {
        const playing = !audio.paused && !audio.ended;
        iconPlay.hidden = playing;
        iconPause.hidden = !playing;
        dockPlayLabel.textContent = playing ? 'Pause' : 'Listen instead';
        dockPlay.setAttribute('aria-label', playing ? 'Pause the audio' : 'Play the audio');
    }

    function resetAudio() {
        audio.pause();
        if (audio.getAttribute('src')) {
            audio.removeAttribute('src');
            audio.load(); // drops the buffered stream; noisy if there was no src
        }
        audio.playbackRate = 1;
        dockSpeed.textContent = '1×';
        listenBlock.hidden = true;
        syncPlayButton();
        syncScrub();
    }

    function renderAudio(audioUrl) {
        if (!audioUrl) {
            // No audio was produced (past TTS_MAX_CHARS); a note explains why.
            resetAudio();
            return;
        }
        audio.src = audioUrl;
        audio.load();
        listenBlock.hidden = false;
        syncPlayButton();
        syncScrub();
    }

    dockPlay.addEventListener('click', function () {
        if (audio.paused) {
            const played = audio.play();
            if (played && played.catch) played.catch(function () { /* user gesture required */ });
        } else {
            audio.pause();
        }
    });

    dockScrub.addEventListener('input', function () {
        const duration = audio.duration;
        if (!isFinite(duration) || duration <= 0) return;
        audio.currentTime = (Number(dockScrub.value) / 100) * duration;
        syncScrub();
    });

    dockSpeed.addEventListener('click', function () {
        const next = SPEEDS[(SPEEDS.indexOf(audio.playbackRate) + 1) % SPEEDS.length];
        audio.playbackRate = next;
        dockSpeed.textContent = next + '×';
    });

    audio.addEventListener('loadedmetadata', syncScrub);
    audio.addEventListener('timeupdate', syncScrub);
    audio.addEventListener('play', syncPlayButton);
    audio.addEventListener('pause', syncPlayButton);
    audio.addEventListener('ended', function () {
        syncPlayButton();
        syncScrub();
    });

    // ── Result rendering ───────────────────────────────────────────────

    // Deep-links into the embedded player. Kept as a real href so a timestamp
    // still goes somewhere with JS off; the click handler seeks in place.
    function timestampUrl(result, seconds) {
        const base = result.embed_url || '';
        if (!base) return '#';
        const start = Math.max(0, Math.floor(Number(seconds) || 0));
        return base + (base.indexOf('?') === -1 ? '?' : '&') + 'start=' + start;
    }

    function seekEmbed(event, result, seconds) {
        if (!result.embed_url) return;
        event.preventDefault();
        embed.src = timestampUrl(result, seconds) + '&autoplay=1';
        embed.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function renderProse(text) {
        clear(resultProse);
        const paragraphs = String(text || '')
            .split(/\n\s*\n/)
            .map(function (p) { return p.trim(); })
            .filter(Boolean);

        if (!paragraphs.length) paragraphs.push('No text was returned for this video.');

        paragraphs.forEach(function (paragraph) {
            const p = document.createElement('p');
            p.textContent = paragraph;
            resultProse.appendChild(p);
        });
    }

    // key_points / sections are not in the API yet. When summarize.py starts
    // emitting them these three renderers light up with no other change.
    function renderKeyPoints(points) {
        clear(keyPointsList);
        if (!Array.isArray(points) || !points.length) {
            keyPointsBlock.hidden = true;
            return;
        }
        points.forEach(function (point) {
            const text = typeof point === 'string' ? point : (point && point.text);
            if (!text) return;
            const div = document.createElement('div');
            div.className = 'key-point';
            div.textContent = text;
            keyPointsList.appendChild(div);
        });
        keyPointsBlock.hidden = !keyPointsList.childNodes.length;
    }

    function renderSections(sections, result) {
        clear(sectionList);
        if (!Array.isArray(sections) || !sections.length) {
            sectionList.hidden = true;
            return;
        }
        sections.forEach(function (section) {
            const wrapper = document.createElement('div');
            wrapper.className = 'section';

            const head = document.createElement('div');
            head.className = 'section-head';

            if (section.start_seconds != null) {
                const time = document.createElement('a');
                time.className = 'section-time';
                time.href = timestampUrl(result, section.start_seconds);
                time.textContent = formatClock(section.start_seconds);
                time.addEventListener('click', function (event) {
                    seekEmbed(event, result, section.start_seconds);
                });
                head.appendChild(time);
            }

            const title = document.createElement('h2');
            title.className = 'section-title';
            title.textContent = section.title || '';
            head.appendChild(title);

            const body = document.createElement('p');
            body.className = 'section-body';
            body.textContent = section.body || '';

            wrapper.appendChild(head);
            wrapper.appendChild(body);
            sectionList.appendChild(wrapper);
        });
        sectionList.hidden = false;
    }

    function renderChapters(sections, result) {
        clear(chapterList);
        const usable = Array.isArray(sections)
            ? sections.filter(function (s) { return s && s.start_seconds != null; })
            : [];
        if (!usable.length) {
            chapterBlock.hidden = true;
            return;
        }
        usable.forEach(function (section) {
            const link = document.createElement('a');
            link.className = 'chapter-link';
            link.href = timestampUrl(result, section.start_seconds);

            const time = document.createElement('span');
            time.className = 'chapter-time';
            time.textContent = formatClock(section.start_seconds);

            const title = document.createElement('span');
            title.textContent = section.title || '';

            link.appendChild(time);
            link.appendChild(title);
            link.addEventListener('click', function (event) {
                seekEmbed(event, result, section.start_seconds);
            });
            chapterList.appendChild(link);
        });
        chapterBlock.hidden = false;
    }

    function sourcePhrase(source) {
        if (source === 'captions') return 'read from captions';
        if (source === 'whisper') return 'from speech recognition';
        return '';
    }

    function sourceSentence(source) {
        if (source === 'captions') {
            return "Read from the video's own caption track, so no speech recognition was needed.";
        }
        if (source === 'whisper') {
            return 'Transcribed from the video’s audio by speech recognition, so occasional errors are expected.';
        }
        return '';
    }

    function renderFooter(result) {
        clear(resultFooter);
        const lines = [];
        const sentence = sourceSentence(result.transcript_source);
        if (sentence) lines.push(sentence);
        if (Array.isArray(result.notes)) {
            result.notes.forEach(function (note) {
                if (note) lines.push(note);
            });
        }
        if (!lines.length) {
            resultFooter.hidden = true;
            return;
        }
        lines.forEach(function (line) {
            const p = document.createElement('p');
            p.textContent = line;
            resultFooter.appendChild(p);
        });
        resultFooter.hidden = false;
    }

    function renderResult(result, request) {
        if (!result) {
            failJob('The job finished but returned no result.');
            return;
        }

        current = { result: result, request: request };

        if (result.embed_url) {
            embed.src = result.embed_url;
            embed.hidden = false;
        } else {
            embed.removeAttribute('src');
            embed.hidden = true;
        }

        if (result.video_id) {
            watchLink.href = 'https://www.youtube.com/watch?v=' + encodeURIComponent(result.video_id);
            watchLink.hidden = false;
        } else {
            watchLink.hidden = true;
        }

        // Nothing to frame if the job returned neither a player nor an id.
        resultMedia.hidden = !result.embed_url && !result.video_id;

        const isSummary = request.mode === 'summarize';
        const kicker = [
            isSummary ? 'Summary' : 'Transcript',
            languageName(result.language || request.language),
            sourcePhrase(result.transcript_source)
        ].filter(Boolean);
        resultKicker.textContent = kicker.join(' · ');

        resultTitle.textContent = result.title || 'Untitled video';

        const meta = [];
        const duration = formatDuration(result.duration_sec);
        if (duration) meta.push(duration + ' of video');
        meta.push('about ' + readingMinutes(result.text) + ' min to read');
        resultMeta.textContent = meta.join(' · ');

        copyLabel.textContent = isSummary ? 'Copy summary' : 'Copy transcript';

        renderKeyPoints(result.key_points);
        renderProse(result.text);
        renderSections(result.sections, result);
        renderChapters(result.sections, result);
        renderFooter(result);
        renderAudio(result.audio_url);

        setState('result');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        window.requestAnimationFrame(updateReadProgress);
    }

    // ── Copy / download ────────────────────────────────────────────────

    function flashCopy(text) {
        copyLabel.textContent = text;
        clearTimeout(copyResetTimer);
        copyResetTimer = setTimeout(function () {
            copyLabel.textContent = current && current.request.mode === 'summarize'
                ? 'Copy summary'
                : 'Copy transcript';
        }, 1600);
    }

    function legacyCopy(text) {
        const area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        let ok = false;
        try {
            ok = document.execCommand('copy');
        } catch (err) {
            ok = false;
        }
        document.body.removeChild(area);
        return ok;
    }

    copyBtn.addEventListener('click', function () {
        if (!current) return;
        const text = current.result.text || '';
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
                flashCopy('Copied');
            }).catch(function () {
                flashCopy(legacyCopy(text) ? 'Copied' : 'Press Ctrl+C');
            });
            return;
        }
        flashCopy(legacyCopy(text) ? 'Copied' : 'Press Ctrl+C');
    });

    downloadBtn.addEventListener('click', function () {
        if (!current) return;
        const result = current.result;
        const body = (result.title ? result.title + '\n\n' : '') + (result.text || '');
        const blob = new Blob([body], { type: 'text/plain;charset=utf-8' });
        const href = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = href;
        link.download = slugify(result.title) + '.txt';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(function () { URL.revokeObjectURL(href); }, 1000);
    });

    // ── Job submission and polling ─────────────────────────────────────

    function pollJob(jobId, startedAt, request) {
        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
            failJob('This is taking longer than 20 minutes, so we stopped waiting. Please try again with a shorter video.');
            return;
        }

        fetch('/api/jobs/' + encodeURIComponent(jobId), {
            headers: { 'Accept': 'application/json' }
        }).then(function (response) {
            if (response.status === 404) {
                failJob('This job is no longer available — it may have expired. Please run it again.');
                return null;
            }
            if (!response.ok) {
                failJob('The server returned an unexpected response (' + response.status + '). Please try again.');
                return null;
            }
            return response.json();
        }).then(function (job) {
            if (!job) return;

            if (job.status === 'done') {
                finishJob();
                renderResult(job.result, request);
                return;
            }

            if (job.status === 'error') {
                failJob(job.error && job.error.message
                    ? job.error.message
                    : 'Something went wrong. Please try again.');
                return;
            }

            recordStage(job);
            setProgress(job.progress);
            pollTimer = setTimeout(function () {
                pollJob(jobId, startedAt, request);
            }, POLL_INTERVAL_MS);
        }).catch(function () {
            failJob('Lost contact with the server. Please check your connection and try again.');
        });
    }

    function submitJob() {
        const videoUrl = urlInput.value.trim();
        const mode = selectedMode();
        const language = languageSelect.value;

        if (!videoUrl) {
            showError('Please paste a YouTube video URL.');
            urlInput.focus();
            return;
        }
        if (!mode) {
            showError('Please choose Transcribe or Summarize.');
            return;
        }
        if (!language) {
            showError('Please pick a language.');
            return;
        }

        const request = { video_url: videoUrl, mode: mode, language: language };

        clearError();
        current = null;
        resetAudio();
        stages = [];
        clear(stageList);
        setProgress(0);
        setState('processing');

        jobRunning = true;
        runBtn.disabled = true;

        fetch('/api/summarize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(request)
        }).then(function (response) {
            return response.json().catch(function () {
                return null;
            }).then(function (body) {
                return { ok: response.ok, status: response.status, body: body };
            });
        }).then(function (res) {
            if (!res.ok || !res.body || !res.body.job_id) {
                finishJob();
                const err = res.body && res.body.error;
                // A rejected URL belongs next to the field it came from.
                setState('idle');
                showError(err && err.message
                    ? err.message
                    : 'Could not start the job. Please check the URL and try again.');
                urlInput.focus();
                return;
            }
            pollJob(res.body.job_id, Date.now(), request);
        }).catch(function () {
            finishJob();
            setState('idle');
            showError('Could not reach the server. Please check your connection and try again.');
        });
    }

    // ── Wiring ─────────────────────────────────────────────────────────

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        if (jobRunning) return;
        submitJob();
    });

    form.addEventListener('change', function (event) {
        if (event.target.name === 'mode') {
            runLabel.textContent = event.target.value === 'transcribe' ? 'Transcribe' : 'Summarize';
        }
    });

    urlInput.addEventListener('input', function () {
        if (!formError.hidden) clearError();
    });

    pasteBtn.addEventListener('click', function () {
        if (!navigator.clipboard || !navigator.clipboard.readText) {
            urlInput.focus();
            return;
        }
        navigator.clipboard.readText().then(function (text) {
            if (text) {
                urlInput.value = text.trim();
                clearError();
            }
            urlInput.focus();
        }).catch(function () {
            // Clipboard permission denied — let the reader paste it themselves.
            urlInput.focus();
        });
    });

    errorReset.addEventListener('click', function () {
        clearError();
        urlInput.value = '';
        current = null;
        resetAudio();
        setState('idle');
        urlInput.focus();
    });

    resetAudio();
    setState('idle');
});
