import { spawn } from 'node:child_process';

const DEFAULT_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
const timeoutMs = Number.isFinite(Number.parseInt(process.env.TEST_TIMEOUT_MS ?? '', 10))
  ? Number.parseInt(process.env.TEST_TIMEOUT_MS ?? '', 10)
  : DEFAULT_TIMEOUT_MS;

const vitestArgs = ['exec', 'vitest', '--run', '--reporter', 'default', '--passWithNoTests'];
if (process.env.TEST_MAX_WORKERS) {
  vitestArgs.push('--maxWorkers', process.env.TEST_MAX_WORKERS);
}

const extraArgs = process.argv.slice(2);
if (extraArgs.length > 0) {
  vitestArgs.push(...extraArgs);
}

const pnpmCommand = process.platform === 'win32' ? 'pnpm.cmd' : 'pnpm';

const child = spawn(pnpmCommand, vitestArgs, {
  stdio: 'inherit'
});

const killChild = (signal: NodeJS.Signals = 'SIGTERM') => {
  if (!child.killed) {
    child.kill(signal);
  }
};

const timeoutId = setTimeout(() => {
  console.error(`Test run exceeded ${timeoutMs}ms; terminating vitest.`);
  killChild('SIGTERM');
  setTimeout(() => killChild('SIGKILL'), 5000);
}, timeoutMs);

const exitWith = (code: number) => {
  clearTimeout(timeoutId);
  process.exit(code);
};

child.on('error', (error) => {
  console.error('Failed to start vitest process:', error);
  exitWith(1);
});

child.on('exit', (code, signal) => {
  clearTimeout(timeoutId);
  if (signal) {
    process.exitCode = signal === 'SIGINT' ? 130 : 1;
    return;
  }
  exitWith(code ?? 0);
});

process.on('SIGINT', () => {
  killChild('SIGINT');
});

process.on('SIGTERM', () => {
  killChild('SIGTERM');
});
