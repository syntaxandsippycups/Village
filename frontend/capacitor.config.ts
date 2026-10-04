import type { CapacitorConfig } from '@capacitor/cli';
const config: CapacitorConfig = {
  appId: 'com.depottowndigital.village', appName: 'Village', webDir: 'out',
  server: { androidScheme: 'https' },
  experimental: { ios: { spm: { packageOptions: { '@capacitor-firebase/messaging': { symlink: true } } } } },
  plugins: { FirebaseMessaging: { presentationOptions: ['badge','sound','alert'] } },
};
export default config;
