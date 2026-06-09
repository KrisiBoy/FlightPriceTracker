/**
 * Build a debug APK for Flight Tracker.
 * Requires Android Studio (JDK 17 + Android SDK) installed.
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.join(__dirname, '..');
const androidRoot = path.join(frontendRoot, 'android');
const gradlew = path.join(androidRoot, process.platform === 'win32' ? 'gradlew.bat' : 'gradlew');
const isRelease = process.argv.includes('--release');
const gradleTask = isRelease ? 'assembleRelease' : 'assembleDebug';
const apkDir = path.join(
  androidRoot,
  'app',
  'build',
  'outputs',
  'apk',
  isRelease ? 'release' : 'debug',
);
const apkCandidates = isRelease
  ? ['app-release.apk', 'app-release-unsigned.apk']
  : ['app-debug.apk'];

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: 'inherit', shell: process.platform === 'win32' });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

if (!fs.existsSync(gradlew)) {
  console.error('Android project not found. Run: npx cap add android');
  process.exit(1);
}

console.log('1/3 Syncing web assets to Android...');
run('npm', ['run', 'build'], frontendRoot);
run('npx', ['cap', 'sync', 'android'], frontendRoot);

console.log(`2/3 Applying ${isRelease ? 'production HTTPS' : 'dev HTTP'} network config...`);
if (isRelease) {
  run('node', ['scripts/patch-android-production.js'], frontendRoot);
} else {
  run('node', ['scripts/patch-android-network.js'], frontendRoot);
}

console.log(`3/3 Building ${isRelease ? 'release' : 'debug'} APK...`);
run(gradlew, [gradleTask, '--no-daemon'], androidRoot);

const apkPath = apkCandidates
  .map((name) => path.join(apkDir, name))
  .find((candidate) => fs.existsSync(candidate));

if (apkPath) {
  console.log('\nAPK ready:');
  console.log(apkPath);
} else {
  console.error('\nBuild finished but APK not found at expected path.');
  process.exit(1);
}
