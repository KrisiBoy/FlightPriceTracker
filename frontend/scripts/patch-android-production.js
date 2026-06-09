/**
 * Production network config: HTTPS only (no cleartext HTTP).
 * Run after cap sync for release builds.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const androidRoot = path.join(__dirname, '..', 'android');
const manifestPath = path.join(androidRoot, 'app', 'src', 'main', 'AndroidManifest.xml');
const resXmlDir = path.join(androidRoot, 'app', 'src', 'main', 'res', 'xml');
const networkConfigPath = path.join(resXmlDir, 'network_security_config.xml');

const productionDomain = process.env.VITE_API_BASE_URL
  ? new URL(process.env.VITE_API_BASE_URL).hostname
  : null;

if (!fs.existsSync(manifestPath)) {
  console.warn('AndroidManifest.xml not found — run "npx cap add android" first.');
  process.exit(0);
}

fs.mkdirSync(resXmlDir, { recursive: true });

const domainBlock = productionDomain
  ? `    <domain-config cleartextTrafficPermitted="false">
        <domain includeSubdomains="true">${productionDomain}</domain>
    </domain-config>\n`
  : '';

const networkConfig = `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
${domainBlock}    <base-config cleartextTrafficPermitted="false" />
</network-security-config>
`;

fs.writeFileSync(networkConfigPath, networkConfig);

let manifest = fs.readFileSync(manifestPath, 'utf8');
manifest = manifest.replace(/android:usesCleartextTraffic="true"/g, 'android:usesCleartextTraffic="false"');
if (!manifest.includes('networkSecurityConfig')) {
  manifest = manifest.replace(
    /<application([^>]*)>/,
    '<application$1 android:usesCleartextTraffic="false" android:networkSecurityConfig="@xml/network_security_config">',
  );
}
fs.writeFileSync(manifestPath, manifest);
console.log('Applied production HTTPS-only Android network config.');
