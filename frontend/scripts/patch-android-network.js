/**
 * Patches the generated Android project to allow HTTP (cleartext) to a local FastAPI backend.
 * Run after: npx cap add android
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const androidRoot = path.join(__dirname, '..', 'android');
const manifestPath = path.join(androidRoot, 'app', 'src', 'main', 'AndroidManifest.xml');
const resXmlDir = path.join(androidRoot, 'app', 'src', 'main', 'res', 'xml');
const networkConfigPath = path.join(resXmlDir, 'network_security_config.xml');

if (!fs.existsSync(manifestPath)) {
  console.warn('AndroidManifest.xml not found — run "npx cap add android" first.');
  process.exit(0);
}

fs.mkdirSync(resXmlDir, { recursive: true });

const networkConfig = `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">10.0.2.2</domain>
        <domain includeSubdomains="true">localhost</domain>
    </domain-config>
    <base-config cleartextTrafficPermitted="true" />
</network-security-config>
`;

fs.writeFileSync(networkConfigPath, networkConfig);

let manifest = fs.readFileSync(manifestPath, 'utf8');

if (!manifest.includes('networkSecurityConfig')) {
  manifest = manifest.replace(
    /<application([^>]*)>/,
    '<application$1 android:usesCleartextTraffic="true" android:networkSecurityConfig="@xml/network_security_config">',
  );
  fs.writeFileSync(manifestPath, manifest);
  console.log('Patched AndroidManifest.xml for cleartext HTTP.');
} else {
  console.log('AndroidManifest.xml already patched.');
}
