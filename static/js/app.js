// ===== State =====
let videoData = null;
let selectedQuality = null;
let selectedFormatId = null;
let currentPlatform = 'youtube';

// ===== DOM References =====
const urlInput = document.getElementById('urlInput');
const fetchBtn = document.getElementById('fetchBtn');
const errorMsg = document.getElementById('errorMsg');
const videoCard = document.getElementById('videoCard');
const thumbnail = document.getElementById('thumbnail');
const duration = document.getElementById('duration');
const videoTitle = document.getElementById('videoTitle');
const channel = document.getElementById('channel');
const views = document.getElementById('views');
const qualityGrid = document.getElementById('qualityGrid');
const downloadBtn = document.getElementById('downloadBtn');
const downloadBtnText = document.getElementById('downloadBtnText');
const progressSection = document.getElementById('progressSection');
const progressBar = document.getElementById('progressBar');
const progressPhase = document.getElementById('progressPhase');
const progressPercent = document.getElementById('progressPercent');
const progressDetails = document.getElementById('progressDetails');
const platformBadge = document.getElementById('platformBadge');

// ===== Enter key triggers fetch =====
urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') fetchVideoInfo();
});

// ===== Wire up download button =====
let downloadAction = downloadVideo;
downloadBtn.addEventListener('click', () => downloadAction());

// ===== Utility Functions =====
function formatDuration(seconds) {
    if (!seconds) return '0:00';
    seconds = Math.floor(seconds);
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) {
        return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatCount(count) {
    if (!count) return '';
    if (count >= 1_000_000_000) return (count / 1_000_000_000).toFixed(1) + 'B';
    if (count >= 1_000_000) return (count / 1_000_000).toFixed(1) + 'M';
    if (count >= 1_000) return (count / 1_000).toFixed(1) + 'K';
    return count.toLocaleString();
}

function formatViews(count) {
    if (!count) return '0 views';
    return formatCount(count) + ' views';
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '';
    if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(1) + ' GB';
    if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(1) + ' MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return bytes + ' B';
}

function showError(message) {
    errorMsg.textContent = message;
    errorMsg.style.display = 'block';
    setTimeout(() => { errorMsg.style.display = 'none'; }, 6000);
}

function hideError() {
    errorMsg.style.display = 'none';
}

function setFetchLoading(loading) {
    const btnText = fetchBtn.querySelector('.btn-text');
    const btnLoader = fetchBtn.querySelector('.btn-loader');
    fetchBtn.disabled = loading;
    btnText.style.display = loading ? 'none' : 'inline';
    btnLoader.style.display = loading ? 'flex' : 'none';
}

// ===== Fetch Video Info =====
async function fetchVideoInfo() {
    const url = urlInput.value.trim();
    if (!url) {
        showError('Please paste a video link!');
        urlInput.focus();
        return;
    }

    hideError();
    setFetchLoading(true);
    videoCard.style.display = 'none';
    selectedQuality = null;
    selectedFormatId = null;
    currentPlatform = 'youtube';

    try {
        const response = await fetch('/api/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });

        const data = await response.json();

        if (!response.ok) {
            showError(data.error || 'Something went wrong');
            return;
        }

        videoData = data;
        currentPlatform = data.platform || 'youtube';
        renderVideoCard(data);
    } catch (err) {
        showError('Network error — is the server running?');
        console.error(err);
    } finally {
        setFetchLoading(false);
    }
}

// ===== Render Video Card =====
function renderVideoCard(data) {
    thumbnail.src = data.thumbnail;
    thumbnail.alt = data.title;
    duration.textContent = formatDuration(data.duration);
    if (!data.duration) duration.style.display = 'none';
    else duration.style.display = '';
    videoTitle.textContent = data.title;
    channel.textContent = data.channel;

    // Show views or likes (Instagram often has 0 views but has likes)
    const viewsContainer = document.getElementById('views').parentElement;
    const viewCount = data.view_count || 0;
    const likeCount = data.like_count || 0;

    if (viewCount > 0) {
        views.textContent = formatViews(viewCount);
        viewsContainer.style.display = '';
    } else if (likeCount > 0) {
        views.textContent = formatCount(likeCount) + ' likes';
        viewsContainer.style.display = '';
    } else if (data.platform === 'instagram') {
        viewsContainer.style.display = 'none';
    } else {
        views.textContent = '0 views';
        viewsContainer.style.display = '';
    }

    // Platform badge
    if (data.platform === 'instagram') {
        platformBadge.textContent = 'Instagram';
        platformBadge.className = 'platform-badge platform-instagram';
        platformBadge.style.display = '';
    } else {
        platformBadge.textContent = 'YouTube';
        platformBadge.className = 'platform-badge platform-youtube';
        platformBadge.style.display = '';
    }

    qualityGrid.innerHTML = '';
    data.formats.forEach((fmt) => {
        const div = document.createElement('div');
        div.className = 'quality-option';
        div.setAttribute('data-quality', fmt.quality);
        div.setAttribute('data-format-id', fmt.format_id);

        let badgeHTML = '';
        if (fmt.height >= 720) {
            badgeHTML = '<span class="quality-badge badge-hd">HD</span>';
        } else if (fmt.format_id === 'audio') {
            badgeHTML = '<span class="quality-badge badge-audio">MP3</span>';
        }

        const sizeText = formatFileSize(fmt.filesize);

        div.innerHTML = `
            ${badgeHTML}
            <div class="quality-label">${fmt.quality}</div>
            ${sizeText ? `<div class="quality-size">~${sizeText}</div>` : '<div class="quality-size">—</div>'}
        `;

        div.addEventListener('click', () => selectQuality(div, fmt));
        qualityGrid.appendChild(div);
    });

    downloadBtn.disabled = true;
    downloadBtnText.textContent = 'Select a quality to download';
    progressSection.style.display = 'none';

    videoCard.style.display = 'block';
    videoCard.style.animation = 'none';
    videoCard.offsetHeight;
    videoCard.style.animation = 'fadeInUp 0.5s ease-out';
}

// ===== Select Quality =====
function selectQuality(element, fmt) {
    document.querySelectorAll('.quality-option').forEach(el => el.classList.remove('selected'));
    element.classList.add('selected');
    selectedQuality = fmt.quality;
    selectedFormatId = fmt.format_id;
    downloadBtn.disabled = false;
    downloadBtnText.textContent = `Download ${fmt.quality}`;
}

// ===== Download Video =====
async function downloadVideo() {
    if (!videoData || !selectedQuality) return;

    downloadBtn.disabled = true;
    downloadBtnText.textContent = 'Starting...';
    progressSection.style.display = 'block';
    progressBar.style.width = '0%';
    progressBar.style.background = '';
    progressPhase.textContent = 'Starting download...';
    progressPercent.textContent = '0%';
    progressDetails.textContent = '';

    try {
        // Step 1: Start the download task
        const startRes = await fetch('/api/start_download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: videoData.url,
                quality: selectedQuality,
                format_id: selectedFormatId,
                platform: currentPlatform,
            }),
        });

        const startData = await startRes.json();
        if (!startRes.ok) {
            throw new Error(startData.error || 'Failed to start download');
        }

        const taskId = startData.task_id;

        // Step 2: Listen to SSE progress stream
        const done = await listenProgress(taskId);

        if (done.status === 'error') {
            throw new Error(done.error || 'Download failed');
        }

        // Step 3: Download the file from server
        progressBar.style.width = '100%';
        progressPhase.textContent = 'Saving file...';
        progressPercent.textContent = '100%';
        progressDetails.textContent = '';

        const fileRes = await fetch(`/api/file/${taskId}`);
        if (!fileRes.ok) {
            throw new Error('Failed to retrieve file');
        }

        const blob = await fileRes.blob();
        const contentDisposition = fileRes.headers.get('Content-Disposition');
        let filename = 'video.mp4';

        if (contentDisposition) {
            const match = contentDisposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i);
            if (match) filename = decodeURIComponent(match[1]);
        }

        // Trigger browser download
        const downloadUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(downloadUrl);

        // Success!
        progressBar.style.width = '100%';
        progressBar.style.background = 'linear-gradient(90deg, #10b981, #059669)';
        progressPhase.textContent = 'Download complete!';
        progressPercent.textContent = '100%';
        progressDetails.textContent = 'File saved to your downloads folder';
        progressSection.classList.add('success');

        downloadBtn.disabled = false;
        downloadBtn.classList.add('btn-success');
        document.querySelector('.btn-icon-download').style.display = 'none';
        document.querySelector('.btn-icon-success').style.display = '';
        downloadBtnText.textContent = 'Download Another Video';
        downloadAction = resetForNewDownload;

    } catch (err) {
        progressSection.style.display = 'none';
        showError(err.message || 'Download failed \u2014 please try again');
        downloadBtn.disabled = false;
        downloadBtnText.textContent = `Download ${selectedQuality}`;
        downloadAction = downloadVideo;
        console.error(err);
    }
}

// ===== SSE Progress Listener =====
function listenProgress(taskId) {
    return new Promise((resolve, reject) => {
        const evtSource = new EventSource(`/api/progress/${taskId}`);

        evtSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                // Update progress bar
                const pct = data.percent || 0;
                progressBar.style.width = pct + '%';

                // Update phase label
                progressPhase.textContent = data.phase || 'Processing...';

                // Update percentage
                progressPercent.textContent = Math.round(pct) + '%';

                // Update details (speed + ETA)
                let details = '';
                if (data.speed) details += data.speed;
                if (data.eta) details += (details ? '   •   ' : '') + 'ETA ' + data.eta;
                progressDetails.textContent = details;

                // Update button with percentage
                if (pct > 0 && pct < 100) {
                    downloadBtnText.textContent = `${Math.round(pct)}% Downloading...`;
                }

                if (data.status === 'done') {
                    evtSource.close();
                    resolve(data);
                } else if (data.status === 'error') {
                    evtSource.close();
                    resolve(data);
                }
            } catch (e) {
                console.error('SSE parse error:', e);
            }
        };

        evtSource.onerror = () => {
            evtSource.close();
            reject(new Error('Connection to server lost'));
        };

        // Timeout after 10 minutes
        setTimeout(() => {
            evtSource.close();
            reject(new Error('Download timed out'));
        }, 10 * 60 * 1000);
    });
}

// ===== Reset for new download =====
function resetForNewDownload() {
    videoData = null;
    selectedQuality = null;
    selectedFormatId = null;
    currentPlatform = 'youtube';

    videoCard.style.display = 'none';
    progressSection.style.display = 'none';
    progressSection.classList.remove('success');
    progressBar.style.width = '0%';
    progressBar.style.background = '';
    urlInput.value = '';
    urlInput.focus();
    hideError();

    downloadBtn.classList.remove('btn-success');
    document.querySelector('.btn-icon-download').style.display = '';
    document.querySelector('.btn-icon-success').style.display = 'none';
    downloadAction = downloadVideo;
    downloadBtn.disabled = true;
    downloadBtnText.textContent = 'Select a quality to download';
}

// ===== Auto-detect paste =====
function isValidUrl(text) {
    return (
        text.includes('youtube.com') ||
        text.includes('youtu.be') ||
        text.includes('instagram.com') ||
        text.includes('instagr.am')
    );
}

urlInput.addEventListener('paste', () => {
    setTimeout(() => {
        const val = urlInput.value.trim();
        if (val && isValidUrl(val)) {
            fetchVideoInfo();
        }
    }, 100);
});
