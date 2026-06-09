/**
 * Shared production build environment for Capacitor mobile builds.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const frontendRoot = path.join(__dirname, '..');

const androidGoogleServices = path.join(frontendRoot, 'android', 'app', 'google-services.json');
const iosGoogleServices = path.join(frontendRoot, 'ios', 'App', 'GoogleService-Info.plist');

export function isPushEnabled() {
  return fs.existsSync(androidGoogleServices) || fs.existsSync(iosGoogleServices);
}

export function productionBuildEnv(baseEnv = process.env) {
  const productionUrl =
    baseEnv.VITE_API_BASE_URL ||
    'https://flightpricetracker-production.up.railway.app/api';
  return {
    ...baseEnv,
    VITE_API_BASE_URL: productionUrl,
    VITE_PUSH_NOTIFICATIONS_ENABLED: isPushEnabled() ? 'true' : 'false',
  };
}

export function logBuildEnv(label) {
  const push = isPushEnabled();
  console.log(`${label} (push notifications: ${push ? 'enabled' : 'disabled'})`);
}
