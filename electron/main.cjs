const { app, BrowserWindow, dialog } = require('electron');
const { spawn, execFile } = require('child_process');
const http = require('http');
const net = require('net');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

const DEFAULT_BACKEND_PORT = 8000;

// Only one Super Station Studio UI/backend pair may run per Windows user.
// Without this guard, launching the app twice creates two independent
// backends, both with their own audio engine, which can result in double
// playback.
const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
  return;
}

let backendProcess = null;
let backendPort = null;
let frontendServer = null;
let frontendPort = null;
let mainWindow = null;
let schedulerWindow = null;
let quitting = false;
let backendStartError = null;
let backendExitError = null;
let resumeCheckpointTimer = null;
const instanceToken = crypto.randomBytes(24).toString('hex');

function projectRoot() {
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..');
}

function backendDir() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'backend-dist')
    : path.join(projectRoot(), 'backend');
}

function backendCommand() {
  if (app.isPackaged) return path.join(backendDir(), 'SuperStationBackend.exe');
  return process.platform === 'win32' ? 'python' : 'python3';
}

function backendArgs(port) {
  if (app.isPackaged) return [];
  return ['run_backend.py'];
}

function persistentDataDir() {
  const dir = path.join(app.getPath('userData'), 'data');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function backendEnvironment(port) {
  const dbPath = path.join(persistentDataDir(), 'library.db');

  return {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    SSS_BACKEND_PORT: String(port),
    SSS_INSTANCE_TOKEN: instanceToken,
    MUSIC_LIBRARY_DB_PATH: dbPath,
    MUSIC_LIBRARY_DATA_DIR: persistentDataDir(),
  };
}

function findFreePort(host = '127.0.0.1') {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once('error', reject);
    server.listen({ host, port: 0 }, () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : null;
      server.close(err => {
        if (err) return reject(err);
        if (!port) return reject(new Error('Could not allocate a local TCP port.'));
        resolve(port);
      });
    });
  });
}

function startBackend(port) {
  if (backendProcess) return;

  if (app.isPackaged) {
    const exe = backendCommand();
    if (!fs.existsSync(exe)) {
      throw new Error(
        `Backend executable is missing. Expected:\n${exe}\n\n` +
        'Run scripts\\build-backend.bat before creating the desktop installer.'
      );
    }
  }

  backendStartError = null;
  backendExitError = null;
  backendPort = port;

  const child = spawn(backendCommand(), backendArgs(port), {
    cwd: backendDir(),
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: backendEnvironment(port),
  });
  backendProcess = child;

  child.stdout.on('data', d => console.log('[backend]', d.toString().trimEnd()));
  child.stderr.on('data', d => console.error('[backend]', d.toString().trimEnd()));

  child.on('error', err => {
    backendStartError = err;
    console.error('[backend] process error:', err);
  });

  child.on('exit', (code, signal) => {
    console.log(`[backend] exited code=${code} signal=${signal || ''}`);
    if (backendProcess === child) backendProcess = null;

    if (!quitting && mainWindow) {
      backendExitError = new Error(
        `The audio backend stopped unexpectedly (code=${code ?? 'unknown'}, signal=${signal || 'none'}).`
      );
      dialog.showErrorBox(
        'Super Station Studio backend stopped',
        `${backendExitError.message}\n\nPlease restart Super Station Studio.`
      );
    }
  });
}

function getHealth(port) {
  return new Promise((resolve, reject) => {
    const req = http.get(`http://127.0.0.1:${port}/api/health`, res => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`Backend health returned HTTP ${res.statusCode}.`));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch {
          reject(new Error('Backend health response was not valid JSON.'));
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(1500, () => {
      req.destroy(new Error('Health request timed out.'));
    });
  });
}

function waitForBackend(port, timeoutMs = 30000) {
  const started = Date.now();

  return new Promise((resolve, reject) => {
    const check = async () => {
      if (backendStartError) {
        reject(new Error(`Could not start the backend: ${backendStartError.message}`));
        return;
      }
      if (backendExitError) {
        reject(backendExitError);
        return;
      }

      try {
        const health = await getHealth(port);
        if (health?.status === 'ok' && health?.instance_id === instanceToken) {
          resolve(health);
          return;
        }
        // A responding service on this port is not enough. It must be the
        // exact backend process launched by this Electron instance.
      } catch {}

      if (Date.now() - started > timeoutMs) {
        reject(new Error(
          `Backend did not become ready on 127.0.0.1:${port} within 30 seconds.`
        ));
        return;
      }
      setTimeout(check, 250);
    };

    check();
  });
}

function resumeCheckpointPath() {
  return path.join(persistentDataDir(), 'playback-resume.json');
}

function removeResumeCheckpoint() {
  try {
    fs.rmSync(resumeCheckpointPath(), { force: true });
  } catch (err) {
    console.warn('[resume] could not remove checkpoint:', err.message);
  }
}

function saveResumeCheckpointData(status) {
  if (!status || !status.file_path) {
    removeResumeCheckpoint();
    return;
  }

  const state = String(status.state || '').toUpperCase();
  const position = Number(status.position_seconds);
  const duration = Number(status.duration_seconds);

  // Only an actively playing/paused track is resumable. STOP/IDLE/COMPLETED
  // deliberately clears the checkpoint so an intentional stop never comes
  // back after the next application launch.
  if (!['PLAYING', 'PAUSED'].includes(state) || !Number.isFinite(position)) {
    removeResumeCheckpoint();
    return;
  }

  if (Number.isFinite(duration) && duration > 0 && position >= duration - 0.25) {
    removeResumeCheckpoint();
    return;
  }

  const checkpoint = {
    file_path: status.file_path,
    position_seconds: Math.max(0, position),
    duration_seconds: Number.isFinite(duration) ? Math.max(0, duration) : null,
    volume: Number.isFinite(Number(status.volume)) ? Number(status.volume) : null,
    playback_source: status.playback_source || null,
    saved_at: new Date().toISOString(),
  };

  try {
    const target = resumeCheckpointPath();
    const temp = `${target}.tmp`;
    fs.writeFileSync(temp, JSON.stringify(checkpoint, null, 2), 'utf8');
    fs.renameSync(temp, target);
  } catch (err) {
    console.warn('[resume] could not save checkpoint:', err.message);
  }
}

function getJson(port, requestPath, timeoutMs = 1500) {
  return new Promise((resolve, reject) => {
    const req = http.get(`http://127.0.0.1:${port}${requestPath}`, res => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch (err) {
          reject(err);
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('request timed out')));
  });
}

function postJson(port, requestPath, payload, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(payload);
    const req = http.request(`http://127.0.0.1:${port}${requestPath}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    }, res => {
      let response = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { response += chunk; });
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}: ${response.slice(0, 500)}`));
          return;
        }
        try {
          resolve(response ? JSON.parse(response) : null);
        } catch (err) {
          reject(err);
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('request timed out')));
    req.write(body);
    req.end();
  });
}

async function checkpointPlayback() {
  if (quitting || !backendPort) return;
  try {
    const status = await getJson(backendPort, '/api/playback/status', 1200);
    saveResumeCheckpointData(status);
  } catch {
    // Backend may be starting/stopping. The next checkpoint will retry.
  }
}

function startResumeCheckpointing() {
  if (resumeCheckpointTimer) return;
  // Frequent lightweight checkpoints make an accidental close/crash lose at
  // most a couple of seconds of the current song position.
  resumeCheckpointTimer = setInterval(() => {
    checkpointPlayback().catch(() => {});
  }, 2000);
  if (typeof resumeCheckpointTimer.unref === 'function') resumeCheckpointTimer.unref();
}

function stopResumeCheckpointing() {
  if (!resumeCheckpointTimer) return;
  clearInterval(resumeCheckpointTimer);
  resumeCheckpointTimer = null;
}

async function restorePlaybackCheckpoint(port) {
  const target = resumeCheckpointPath();
  if (!fs.existsSync(target)) return false;

  let checkpoint;
  try {
    checkpoint = JSON.parse(fs.readFileSync(target, 'utf8'));
  } catch {
    removeResumeCheckpoint();
    return false;
  }

  const filePath = typeof checkpoint?.file_path === 'string' ? checkpoint.file_path : '';
  const position = Number(checkpoint?.position_seconds);
  if (!filePath || !Number.isFinite(position) || position < 0 || !fs.existsSync(filePath)) {
    removeResumeCheckpoint();
    return false;
  }

  // If the scheduler already started a valid event during backend startup,
  // never override it with an old manual resume checkpoint.
  try {
    const current = await getJson(port, '/api/playback/status', 1500);
    const currentState = String(current?.state || '').toUpperCase();
    if (['PLAYING', 'PAUSED'].includes(currentState)) {
      removeResumeCheckpoint();
      return false;
    }
  } catch {
    return false;
  }

  try {
    await postJson(port, '/api/playback/restore', {
      file_path: filePath,
      position_seconds: position,
      volume: Number.isFinite(Number(checkpoint.volume)) ? Number(checkpoint.volume) : null,
    }, 10000);
    console.log(`[resume] restored ${filePath} at ${position.toFixed(2)}s`);
    removeResumeCheckpoint();
    return true;
  } catch (err) {
    console.warn('[resume] restore failed:', err.message);
    return false;
  }
}

function contentType(file) {
  const ext = path.extname(file).toLowerCase();
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  }[ext] || 'application/octet-stream');
}

function startFrontendServer() {
  const dist = app.isPackaged
    ? path.join(process.resourcesPath, 'frontend-dist')
    : path.join(projectRoot(), 'frontend', 'dist');

  if (!fs.existsSync(path.join(dist, 'index.html'))) {
    throw new Error(`Frontend build is missing. Expected:\n${path.join(dist, 'index.html')}`);
  }

  frontendServer = http.createServer((req, res) => {
    const parsed = new URL(req.url, `http://${req.headers.host}`);

    if (parsed.pathname.startsWith('/api/')) {
      return proxyApi(req, res);
    }

    let rel;
    try {
      rel = decodeURIComponent(parsed.pathname).replace(/^\/+/, '');
    } catch {
      res.writeHead(400);
      return res.end('Bad request');
    }

    const distRoot = path.resolve(dist);
    let file = path.resolve(distRoot, rel || 'index.html');

    if (file !== distRoot && !file.startsWith(distRoot + path.sep)) {
      res.writeHead(403);
      return res.end('Forbidden');
    }

    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      file = path.join(distRoot, 'index.html');
    }

    fs.createReadStream(file)
      .on('error', () => {
        if (!res.headersSent) res.writeHead(404);
        res.end('Not found');
      })
      .once('open', () => {
        res.writeHead(200, {
          'Content-Type': contentType(file),
          'Cache-Control': 'no-cache',
        });
      })
      .pipe(res);
  });

  return new Promise((resolve, reject) => {
    frontendServer.once('error', reject);
    frontendServer.listen({ host: '127.0.0.1', port: 0 }, () => {
      const address = frontendServer.address();
      frontendPort = typeof address === 'object' && address ? address.port : null;
      if (!frontendPort) {
        reject(new Error('Could not allocate the frontend port.'));
        return;
      }
      resolve(frontendPort);
    });
  });
}

function proxyApi(req, res) {
  if (!backendPort) {
    res.writeHead(503, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ detail: 'Backend is not ready.' }));
  }

  const options = {
    hostname: '127.0.0.1',
    port: backendPort,
    path: req.url,
    method: req.method,
    headers: {
      ...req.headers,
      host: `127.0.0.1:${backendPort}`,
    },
  };

  const proxy = http.request(options, upstream => {
    res.writeHead(upstream.statusCode || 502, upstream.headers);
    upstream.pipe(res);
  });

  proxy.on('error', err => {
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json' });
    }
    res.end(JSON.stringify({ detail: `Backend unavailable: ${err.message}` }));
  });

  req.pipe(proxy);
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: '#ffffff',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Any renderer window.open("/?window=scheduler") becomes a real Electron
  // child window attached to the main Super Station Studio window.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const parsed = new URL(url);
      if (parsed.searchParams.get('window') !== 'scheduler') {
        return { action: 'deny' };
      }
    } catch {
      return { action: 'deny' };
    }

    if (schedulerWindow && !schedulerWindow.isDestroyed()) {
      schedulerWindow.show();
      schedulerWindow.focus();
      return { action: 'deny' };
    }

    schedulerWindow = new BrowserWindow({
      parent: mainWindow,
      modal: false,
      width: 900,
      height: 700,
      minWidth: 760,
      minHeight: 560,
      show: false,
      backgroundColor: '#ffffff',
      title: 'Events List',
      autoHideMenuBar: true,
      webPreferences: {
        preload: path.join(__dirname, 'preload.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: false,
      },
    });

    schedulerWindow.once('ready-to-show', () => {
      if (schedulerWindow && !schedulerWindow.isDestroyed()) {
        schedulerWindow.show();
        schedulerWindow.focus();
      }
    });

    schedulerWindow.on('closed', () => {
      schedulerWindow = null;
    });

    schedulerWindow.loadURL(url).catch(err => {
      console.error('[scheduler-window] failed to load:', err);
    });

    return { action: 'deny' };
  });

  await mainWindow.loadURL(`http://127.0.0.1:${frontendPort}/`);
}

async function stopBackend() {
  const child = backendProcess;
  backendProcess = null;

  if (!child || child.killed) return;

  const pid = child.pid;

  // On Windows, killing the direct Python/EXE process alone can leave a
  // spawned child alive. Kill the whole process tree so audio cannot
  // continue after the Electron window closes.
  if (process.platform === 'win32' && pid) {
    await new Promise(resolve => {
      execFile('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true }, () => {
        resolve();
      });
    });
    return;
  }

  try {
    child.kill();
  } catch {}

  await new Promise(resolve => {
    const timeout = setTimeout(resolve, 5000);
    child.once('exit', () => {
      clearTimeout(timeout);
      resolve();
    });
  });
}
async function shutdown() {
  if (quitting) return;

  // Capture the exact playback position before the backend is terminated.
  // This is what makes X/close an actual shutdown while still allowing the
  // next manual launch to continue the interrupted song.
  await checkpointPlayback();
  stopResumeCheckpointing();
  quitting = true;

  if (schedulerWindow && !schedulerWindow.isDestroyed()) {
    try { schedulerWindow.close(); } catch {}
    schedulerWindow = null;
  }

  if (frontendServer) {
    try { frontendServer.close(); } catch {}
    frontendServer = null;
    frontendPort = null;
  }

  await stopBackend();
}

async function boot() {
  try {
    // Dynamic ports prevent one Windows user/instance from accidentally
    // talking to another instance's backend or frontend.
    backendPort = await findFreePort();
    startBackend(backendPort);
    await waitForBackend(backendPort);

    await restorePlaybackCheckpoint(backendPort);
    startResumeCheckpointing();

    frontendPort = await startFrontendServer();
    await createWindow();
  } catch (err) {
    console.error(err);
    await shutdown();
    dialog.showErrorBox('Super Station Studio failed to start', err.message);
    app.quit();
  }
}

app.on('second-instance', () => {
  // Focus the already-running window instead of opening another UI/backend.
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
});

app.whenReady().then(boot);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', event => {
  if (!quitting) {
    event.preventDefault();
    shutdown().finally(() => app.quit());
  }
});

app.on('will-quit', () => {
  if (frontendServer) {
    try { frontendServer.close(); } catch {}
  }
  if (backendProcess && !backendProcess.killed) {
    const pid = backendProcess.pid;
    if (process.platform === 'win32' && pid) {
      try {
        execFile('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true });
      } catch {}
    } else {
      try { backendProcess.kill(); } catch {}
    }
  }
});
