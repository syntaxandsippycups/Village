export type View = 'home'|'directory'|'events'|'needs'|'meals'|'commitments'|'inbox'|'profile'|'settings'|'admin'|'help';
export type Kind = 'events'|'needs'|'meals';
export interface Privacy { directory:boolean; email:boolean; phone:boolean; address:boolean; household:boolean }
export interface Preferences { events:boolean; needs:boolean; meals:boolean; community:boolean; reminders:boolean; in_app:boolean; email:boolean; push:boolean }
export interface Person { id:string; name:string; email:string; phone:string; address:string; household:string; bio:string; skills:string[]; resources:string[]; groups:string[]; available:boolean; privacy:Privacy; preferences:Preferences; verified:boolean; joined?:string }
export interface Church { id:string; name:string; location:string; timezone:string; require_approval:boolean; role:'owner'|'admin'|'member'; status:'pending'|'approved'|'removed'; membership_id:string }
export interface BaseItem { id:string; church_id:string; created_by:string; title:string; description:string; organizer:string; can_manage:boolean }
export interface ChurchEvent extends BaseItem { location:string; starts_at:string; ends_at:string|null; audience:string[]; capacity:number|null; official:boolean; cancelled:boolean; attendee_count:number; my_rsvp:{guest_count:number;note:string}|null; attendees?:{name:string;guest_count:number;note?:string}[] }
export interface Need extends BaseItem { category:string; location:string; volunteers_needed:number; due_date:string|null; status:'open'|'fulfilled'|'closed'; on_behalf:string; consent:boolean; volunteer_count:number; my_volunteer:{note:string}|null; volunteers?:{name:string;note:string}[] }
export interface MealSlot { id:string; date:string; user_id:string|null; name:string; meal:string; note:string; delivered:boolean }
export interface MealTrain extends BaseItem { recipient:string; adults:number; children:number; allergies:string; preferences:string; address:string; instructions:string; delivery_window:string; contact:string; start_date:string; end_date:string; weekdays:number[]; consent:boolean; closed:boolean; slot_count:number; claimed_count:number; my_count:number; slots?:MealSlot[] }
export type Item = ChurchEvent|Need|MealTrain;
export interface Comment { id:string; user_id:string; text:string; name:string; created_at:string; can_delete:boolean }
export interface Notice { id:string; church_id:string; category:string; title:string; body:string; link:string; read:boolean; created_at:string }
export interface Member { id:string; user_id:string; name:string; email:string; role:'member'|'admin'|'owner'; status:'approved'|'pending'|'removed' }
export interface Report { id:string; kind:Kind|'directory'|'comments'; target_id:string; reason:string; resolved:boolean; created_at:string }
export interface Commitments { events:ChurchEvent[]; needs:Need[]; meals:{slot:MealSlot;train:MealTrain}[] }
