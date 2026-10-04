import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
const env={...process.env,NEXT_TELEMETRY_DISABLED:'1'};
if(fs.existsSync('.env.native'))for(const line of fs.readFileSync('.env.native','utf8').split('\n')){const m=line.match(/^([A-Z_]+)=(.*)$/);if(m)env[m[1]]=m[2].trim().replace(/^['"]|['"]$/g,'')}
if(!env.NEXT_PUBLIC_API_URL?.startsWith('https://')||!env.NEXT_PUBLIC_WEB_URL?.startsWith('https://')||env.NEXT_PUBLIC_API_URL.includes('YOUR-DOMAIN'))throw new Error('Set real HTTPS NEXT_PUBLIC_API_URL and NEXT_PUBLIC_WEB_URL in .env.native before building the phone apps.');
const policy=fs.readFileSync('public/privacy.html','utf8');
try {
 fs.writeFileSync('public/privacy.html',policy.replace("fetch('/api/health')",'fetch('+JSON.stringify(env.NEXT_PUBLIC_API_URL.replace(/\/$/,'')+'/health')+')'));
 for(const args of [['node_modules/next/dist/bin/next','build','--webpack'],['node_modules/@capacitor/cli/bin/capacitor','sync']]){const r=spawnSync(process.execPath,args,{stdio:'inherit',env});if(r.status!==0)throw new Error('Native build/sync failed.');}
} finally {fs.writeFileSync('public/privacy.html',policy);}

