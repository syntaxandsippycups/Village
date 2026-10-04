'use client';
import {useState} from 'react';
import {Field} from './ui';
export const defaultGroups=['Families','Parents of young children','New parents','Single adults','Young adults','Undergrads','Married couples','Empty nesters','Older adults','New to church','Church team'];
const key=(value:string)=>value.normalize('NFKC').trim().replace(/\s+/g,' ').toLocaleLowerCase();
export function uniqueGroups(values:string[],options:string[]=defaultGroups){
 const known=new Map(options.map(v=>[key(v),v]));const seen=new Set<string>();
 return values.map(v=>v.normalize('NFKC').trim().replace(/\s+/g,' ')).filter(v=>{if(!v||seen.has(key(v)))return false;seen.add(key(v));return true}).map(v=>known.get(key(v))||v);
}
export function GroupPicker({values,options,onChange}:{values:string[];options:string[];onChange:(values:string[])=>void}){
 const [custom,setCustom]=useState(''),[error,setError]=useState('');
 const choices=uniqueGroups([...defaultGroups,...options,...values],[...defaultGroups,...options]);
 function toggle(value:string){setError('');if(values.some(v=>key(v)===key(value)))onChange(values.filter(v=>key(v)!==key(value)));else if(values.length<20)onChange([...values,value]);else setError('Choose up to 20 groups.');}
 function add(){const value=custom.trim().replace(/\s+/g,' ');if(!value)return;if(value.length>80){setError('Keep group names under 80 characters.');return}const canonical=choices.find(c=>key(c)===key(value))||value;if(!values.some(v=>key(v)===key(canonical))){if(values.length>=20){setError('Choose up to 20 groups.');return}onChange([...values,canonical])}setCustom('');setError('');}
 return <div><h3>My groups / seasons of life</h3><p className="subtle">Choose any that fit, or add a group from your church. These labels help people connect; they do not change who can see your profile.</p><div style={{display:'flex',flexWrap:'wrap',gap:8,marginBottom:16}}>{choices.map(value=>{const selected=values.some(v=>key(v)===key(value));return <button key={key(value)} type="button" aria-pressed={selected} className={selected?'primary':'secondary'} onClick={()=>toggle(value)}>{selected?'✓ ':''}{value}</button>})}</div><Field label="Add another group"><input value={custom} onChange={e=>setCustom(e.target.value)} maxLength={80} placeholder="e.g. Tuesday life group" onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();add()}}}/></Field><button type="button" className="secondary" onClick={add} disabled={!custom.trim()}>Add group</button>{error&&<p className="error" role="alert">{error}</p>}<p className="subtle">{values.length} selected. Select a highlighted group again to remove it.</p></div>;
}
