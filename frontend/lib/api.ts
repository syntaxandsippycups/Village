import { Capacitor } from '@capacitor/core';
export const native = () => Capacitor.isNativePlatform();
export const apiBase = (process.env.NEXT_PUBLIC_API_URL || '/api').replace(/\/$/,'');
let sessionToken:string|null = null;
let deviceToken:string|null = null;
export class ApiError extends Error { constructor(message:string,public status:number) { super(message) } }
export async function loadSession() {
  if(native()) { const {SecureStorage}=await import('@aparajita/capacitor-secure-storage'); await SecureStorage.setSynchronize(false); sessionToken=(await SecureStorage.get('village-session')) as string|null; }
}
export async function storeSession(token?:string) {
  sessionToken=token||null;
  if(native()) { const {SecureStorage}=await import('@aparajita/capacitor-secure-storage'); if(token) await SecureStorage.set('village-session',token); else await SecureStorage.remove('village-session'); }
}
export function setDevice(token:string|null) {deviceToken=token}
export function headers() { return {'Content-Type':'application/json','X-Village-Client':'v2',...(sessionToken?{'Authorization':`Bearer ${sessionToken}`} : {}),...(deviceToken?{'X-Device-Token':deviceToken}:{})}; }
export async function api<T>(path:string,method='GET',data?:unknown):Promise<T> {
  const response=await fetch(apiBase+path,{method,credentials:'include',headers:headers(),...(data===undefined?{}:{body:JSON.stringify(data)}),cache:'no-store'});
  if(!response.ok) { const body=await response.json().catch(()=>({}));const detail=body.detail;throw new ApiError(typeof detail==='string'?detail:Array.isArray(detail)?detail.map((d:{msg:string})=>d.msg.replace('Value error, ','')).join(' '):'Unable to complete this request. Please try again.',response.status); }
  return response.json();
}
export async function authenticatedBlob(path:string) {
  const r=await fetch(apiBase+path,{credentials:'include',headers:headers()});if(!r.ok)throw new Error('Unable to download.');return r.blob();
}
export async function enablePush(onLink:(link:string)=>void) {
  if(!native())throw new Error('Push notifications are available in the iPhone and Android apps. You can use email or your Village inbox here.');
  const {FirebaseMessaging}=await import('@capacitor-firebase/messaging');
  const result=await FirebaseMessaging.requestPermissions();if(result.receive!=='granted')throw new Error('Notifications were not allowed. You can change this in your device settings.');
  const {token}=await FirebaseMessaging.getToken();setDevice(token);
  await api('/devices','PUT',{token,platform:Capacitor.getPlatform()});
  await FirebaseMessaging.removeAllListeners();
  await FirebaseMessaging.addListener('tokenReceived',async ({token})=>{setDevice(token);await api('/devices','PUT',{token,platform:Capacitor.getPlatform()})});
  await FirebaseMessaging.addListener('notificationActionPerformed',event=>{const data=event.notification.data as {link?:unknown}|undefined;const link=data?.link;if(typeof link==='string')onLink(link)});
}
export async function disablePush() { await api('/devices','DELETE');setDevice(null);if(native()){const {FirebaseMessaging}=await import('@capacitor-firebase/messaging');await FirebaseMessaging.deleteToken();await FirebaseMessaging.removeAllListeners()} }
export async function scanInvitation() {
  const {CapacitorBarcodeScanner}=await import('@capacitor/barcode-scanner');
  const result=await CapacitorBarcodeScanner.scanBarcode({hint:0,scanInstructions:'Scan your church’s Village invitation',scanButton:true,scanText:'Scan QR code',web:{showCameraSelection:true}});
  try {return new URL(result.ScanResult).searchParams.get('join')||result.ScanResult} catch {return result.ScanResult}
}
export async function shareLink(url:string,title:string) {
  if(native()){const {Share}=await import('@capacitor/share');await Share.share({title,text:title,url});}
  else if(navigator.share)await navigator.share({title,url});
  else {await navigator.clipboard.writeText(url);return 'Link copied.'}
  return 'Shared.';
}
