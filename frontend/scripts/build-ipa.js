/**
 * Prepare iOS release build (web sync + production patches).
 * IPA archive/signing runs on macOS (Codemagic or local Xcode).
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { frontendRoot, logBuildEnv, productionBuildEnv } from './build-env.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const iosRoot = path.join(frontendRoot, 'ios');
const workspace = path.join(iosRoot, 'App.xcworkspace');
const isRelease = process.argv.includes('--release');

function run(command, args, cwd, env = process.env) {
  const result = spawnSync(command, args, {
    cwd,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    env,
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

if (!fs.existsSync(iosRoot)) {
  console.error('iOS project not found. Run: npx cap add ios');
  process.exit(1);
}

const buildEnv = productionBuildEnv();

logBuildEnv('1/3 Building web assets');
run('npm', ['run', 'build'], frontendRoot, buildEnv);

logBuildEnv('2/3 Syncing web assets to iOS');
run('npx', ['cap', 'sync', 'ios'], frontendRoot, buildEnv);

if (isRelease) {
  console.log('3/3 Applying production iOS network config...');
  run('node', ['scripts/patch-ios-production.js'], frontendRoot, buildEnv);
} else {
  console.log('3/3 Skipping production ATS patch (use --release for Railway build).');
}

if (process.platform !== 'darwin') {
  console.log('\niOS project synced. Build the IPA on Codemagic or a Mac:');
  console.log('  open frontend/ios/App.xcworkspace');
  console.log('  Product → Archive → Distribute (Ad Hoc / Development)');
  console.log('\nOr push to GitHub and run the ios-flight-tracker Codemagic workflow.');
  process.exit(0);
}

if (!fs.existsSync(workspace)) {
  console.error(`Workspace not found: ${workspace}`);
  process.exit(1);
}

const exportDir = path.join(iosRoot, 'build', 'export');
const archivePath = path.join(iosRoot, 'build', 'App.xcarchive');
fs.mkdirSync(path.join(iosRoot, 'build'), { recursive: true });

console.log('4/4 Archiving with xcodebuild (macOS only)...');
run('xcodebuild', [
  '-workspace', workspace,
  '-scheme', 'App',
  '-configuration', 'Release',
  '-archivePath', archivePath,
  'archive',
  'CODE_SIGN_STYLE=Automatic',
  'DEVELOPMENT_TEAM=' + (process.env.APPLE_TEAM_ID || ''),
], iosRoot);

const exportPlist = path.join(iosRoot, 'build', 'ExportOptions.plist');
const exportMethod = process.env.IOS_EXPORT_METHOD || 'ad-hoc';
fs.writeFileSync(exportPlist, `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key>
  <string>${exportMethod}</string>
  <key>signingStyle</key>
  <string>automatic</string>
  <key>stripSwiftSymbols</key>
  <true/>
</dict>
</plist>
`);

run('xcodebuild', [
  '-exportArchive',
  '-archivePath', archivePath,
  '-exportPath', exportDir,
  '-exportOptionsPlist', exportPlist,
], iosRoot);

const ipa = fs.readdirSync(exportDir).find((name) => name.endsWith('.ipa'));
if (ipa) {
  console.log('\nIPA ready:');
  console.log(path.join(exportDir, ipa));
} else {
  console.error('\nExport finished but no .ipa found.');
  process.exit(1);
}
