'use client';
import {useState} from 'react';
import {api} from '@/lib/api';
import type {Kind,Item,ChurchEvent,Need,MealTrain,Church} from '@/lib/types';
import {dateRange,calendarDate,localInput,todayDate} from '@/lib/dates';
import {Field,Check,Form,val,num} from './ui';
export const categories=['Practical help','Home & yard','Moving','Transportation','Childcare','Tutoring & lessons','Church service','Prayer & company','Borrow a resource'];
export const groups=['Undergrads','Families','Young adults','Older adults','Everyone'];
const split=(v:string)=>v.split(',').map(s=>s.trim()).filter(Boolean);
export function ItemForm({kind,church,item,onSaved}:{kind:Kind;church:Church;item?:Item;onSaved:()=>Promise<void>}){
 const event=item as ChurchEvent|undefined,need=item as Need|undefined,meal=item as MealTrain|undefined;
 const [official,setOfficial]=useState(event?.official||false),[cancelled,setCancelled]=useState(event?.cancelled||false),[consent,setConsent]=useState(meal?.consent||need?.consent||false),[closed,setClosed]=useState(meal?.closed||false);
 const [start,setStart]=useState(meal?.start_date||todayDate()),[end,setEnd]=useState(meal?.end_date||todayDate()),[weekdays,setWeekdays]=useState<number[]>(meal?.weekdays||[0,2,4]);
 const [selected,setSelected]=useState<string[]>(meal?.slots?.map(s=>s.date)||dateRange(start,end,weekdays));
 const [confirmed,setConfirmed]=useState(false);
 const baseDates=dateRange(start,end,weekdays),allDates=dateRange(start,end,[0,1,2,3,4,5,6]);
 function schedule(s:string,e:string,w:number[]){setStart(s);setEnd(e);setWeekdays(w);setSelected(dateRange(s,e,w));setConfirmed(false)}
 return <Form submit={item?'Save changes':kind==='events'?'Share invitation':kind==='needs'?'Ask for help':'Start meal train'} onSubmit={async data=>{
   let payload:unknown;
   const base={title:val(data,'title'),description:val(data,'description')};
   if(kind==='events'){payload={...base,location:val(data,'location'),starts_at:new Date(val(data,'starts_at')).toISOString(),ends_at:val(data,'ends_at')?new Date(val(data,'ends_at')).toISOString():null,audience:split(val(data,'audience')),capacity:val(data,'capacity')?num(data,'capacity'):null,official,cancelled};}
   else if(kind==='needs'){payload={...base,location:val(data,'location'),category:val(data,'category'),volunteers_needed:num(data,'volunteers_needed',1),due_date:val(data,'due_date')||null,status:val(data,'status')||'open',on_behalf:val(data,'on_behalf'),consent};}
   else {
     if(!confirmed)throw new Error('Review the selected dates and check the confirmation before saving.');
     payload={...base,recipient:val(data,'recipient'),adults:num(data,'adults',2),children:num(data,'children'),allergies:val(data,'allergies'),preferences:val(data,'preferences'),address:val(data,'address'),instructions:val(data,'instructions'),contact:val(data,'contact'),delivery_window:val(data,'delivery_window'),start_date:start,end_date:end,weekdays,excluded_dates:baseDates.filter(d=>!selected.includes(d)),extra_dates:selected.filter(d=>!baseDates.includes(d)),consent,closed};
     const preview=await api<{dates:string[]}>(`/churches/${church.id}/meals/preview`,'POST',payload);
     if(JSON.stringify(preview.dates)!==JSON.stringify([...selected].sort()))throw new Error('The dates differ from your selection. Review and try again.');
   }
   await api(`/churches/${church.id}/${kind}${item?'/'+item.id:''}`,item?'PUT':'POST',payload);await onSaved();
 }}>
 <Field label={kind==='events'?'Invitation title':kind==='needs'?'What would help?':'Meal train title'}><input name="title" defaultValue={item?.title||''} required maxLength={180} placeholder={kind==='events'?'Dinner at our house':kind==='needs'?'Help moving a few boxes':'Meals for the Johnson family'}/></Field>
 {kind==='meals'&&<Field label="Who are the meals for?"><input name="recipient" defaultValue={meal?.recipient||''} required maxLength={120}/></Field>}
 <Field label={kind==='meals'?'A little about the family / why meals would help':'Tell your church family a little more'}><textarea name="description" rows={4} defaultValue={item?.description||''} maxLength={8000}/></Field>
 {kind==='events'&&<>
  <p className="subtle">Enter times in your device timezone: {Intl.DateTimeFormat().resolvedOptions().timeZone}. Events display in {church.timezone}.</p>
  <div className="form-grid"><Field label="Starts"><input type="datetime-local" name="starts_at" defaultValue={localInput(event?.starts_at)} required/></Field><Field label="Ends (optional)"><input type="datetime-local" name="ends_at" defaultValue={localInput(event?.ends_at||undefined)}/></Field></div>
  <Field label="Where?"><input name="location" defaultValue={event?.location||''} maxLength={500}/></Field><Field label="Who is this for?" hint="Separate tags with commas. All approved church members can see invitations."><input name="audience" list="audiences" defaultValue={event?.audience?.join(', ')||''} placeholder="Undergrads, Families, Life group…" maxLength={800}/><datalist id="audiences">{groups.map(g=><option key={g}>{g}</option>)}</datalist></Field>
  <Field label="Maximum people (optional)" hint="Includes the member and their guests."><input type="number" min={1} max={10000} name="capacity" defaultValue={event?.capacity||''}/></Field>
  {church.role!=='member'&&<Check label="Official church event" checked={official} onChange={setOfficial}/>}{item&&<Check label="Cancel this event" checked={cancelled} onChange={setCancelled}/>}
 </>}
 {kind==='needs'&&<><div className="form-grid"><Field label="Category"><select name="category" defaultValue={need?.category||categories[0]}>{categories.map(c=><option key={c}>{c}</option>)}</select></Field><Field label="People needed"><input type="number" name="volunteers_needed" min={1} max={1000} defaultValue={need?.volunteers_needed||1}/></Field></div><Field label="Where?"><input name="location" defaultValue={need?.location||''} maxLength={500}/></Field><Field label="Needed by (optional)"><input name="due_date" type="date" defaultValue={need?.due_date||''}/></Field><Field label="Posting for someone else? (optional)"><input name="on_behalf" defaultValue={need?.on_behalf||''} maxLength={120} placeholder="Name of person you’re helping"/></Field><Check label="I have permission to share someone else’s need and details, if applicable." checked={consent} onChange={setConsent}/>{item&&<Field label="Status"><select name="status" defaultValue={need?.status||'open'}><option value="open">Open</option><option value="fulfilled">Fulfilled — thank you!</option><option value="closed">Closed</option></select></Field>}</>}
 {kind==='meals'&&<>
  <h3>What will help them?</h3><div className="form-grid"><Field label="Adults"><input type="number" name="adults" min={1} max={100} defaultValue={meal?.adults||2}/></Field><Field label="Children"><input type="number" name="children" min={0} max={100} defaultValue={meal?.children||0}/></Field></div>
  <Field label="Allergies / dietary restrictions"><textarea name="allergies" defaultValue={meal?.allergies||''} maxLength={1000} placeholder="No peanuts; gluten-free; …"/></Field><Field label="Favorite meals, dislikes, restaurants / gift-card ideas"><textarea name="preferences" defaultValue={meal?.preferences||''} maxLength={1000}/></Field>
  <h3>Delivery details</h3><Field label="Delivery address" hint="Only organizers and members who claim a date can see this."><input name="address" defaultValue={meal?.address||''} maxLength={500}/></Field><Field label="Delivery window"><input name="delivery_window" defaultValue={meal?.delivery_window||'5–6 PM'} maxLength={200}/></Field><Field label="Contact for delivery (optional)"><input name="contact" defaultValue={meal?.contact||''} maxLength={250}/></Field><Field label="Delivery instructions"><textarea name="instructions" defaultValue={meal?.instructions||''} maxLength={1500} placeholder="Leave on the porch; text first; containers don’t need returning…"/></Field>
  <h3>Choose the meal dates</h3><div className="form-grid"><Field label="First date"><input type="date" value={start} onChange={e=>schedule(e.target.value,end,weekdays)} required/></Field><Field label="Last date"><input type="date" value={end} min={start} onChange={e=>schedule(start,e.target.value,weekdays)} required/></Field></div>
  <p className="subtle">Pick weekdays first, then tap individual dates to add or remove them. Changing the date range or weekdays starts a fresh selection.</p>
  <div className="weekdays">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d,i)=><button key={d} type="button" className={weekdays.includes(i)?'selected':''} aria-pressed={weekdays.includes(i)} onClick={()=>schedule(start,end,weekdays.includes(i)?weekdays.filter(w=>w!==i):[...weekdays,i])}>{d}</button>)}</div>
  <div className="date-picker" aria-label="Select meal dates">{allDates.map(d=><button type="button" key={d} className={selected.includes(d)?'selected':''} aria-pressed={selected.includes(d)} onClick={()=>{setSelected(selected.includes(d)?selected.filter(x=>x!==d):[...selected,d]);setConfirmed(false)}}>{calendarDate(d)}</button>)}</div>
  <div className="selection-summary"><strong>{selected.length} meal {selected.length===1?'date':'dates'} selected</strong><p>{[...selected].sort().map(d=>calendarDate(d)).join(' · ')||'Select at least one date.'}</p></div>
  <Check label="These are the exact dates I want available." checked={confirmed} onChange={setConfirmed}/><Check label="I am the recipient or have their permission to share these details." checked={consent} onChange={setConsent}/>
  {item&&<Check label="Close this meal train to new bookings" checked={closed} onChange={setClosed}/>}
 </>}
 </Form>
}
