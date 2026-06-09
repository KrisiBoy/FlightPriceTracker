/**
 * Production iOS config: HTTPS-only App Transport Security for Railway API.
 * Run after: npx cap sync ios
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const iosRoot = path.join(__dirname, '..', 'ios');
const infoPlistPath = path.join(iosRoot, 'App', 'App', 'info.plist');

const productionDomain = process.env.VITE_API_BASE_URL
  ? new URL(process.env.VITE_API_BASE_URL).hostname
  : 'flightpricetracker-production.up.railway.app';

if (!fs.existsSync(infoPlistPath)) {
  console.warn('iOS Info.plist not found — run "npx cap add ios" first.');
  process.exit(0);
}

let plist = fs.readFileSync(infoPlistPath, 'utf8');

const atsBlock = `	<key>NSAppTransportSecurity</key>
	<dict>
		<key>NSAllowsArbitraryLoads</key>
		<false/>
		<key>NSExceptionDomains</key>
		<dict>
			<key>${productionDomain}</key>
			<dict>
				<key>NSIncludesSubdomains</key>
				<true/>
				<key>NSExceptionAllowsInsecureHTTPLoads</key>
				<false/>
				<key>NSExceptionRequiresForwardSecrecy</key>
				<true/>
			</dict>
		</dict>
	</dict>`;

if (plist.includes('<key>NSAppTransportSecurity</key>')) {
  plist = plist.replace(
    /<key>NSAppTransportSecurity<\/key>[\s\S]*?<\/dict>\s*(?=<key>|<\/dict>)/,
    atsBlock,
  );
} else {
  plist = plist.replace(/<\/dict>\s*$/, `${atsBlock}\n</dict>\n`);
}

fs.writeFileSync(infoPlistPath, plist);
console.log(`Applied production ATS for iOS (${productionDomain}).`);
