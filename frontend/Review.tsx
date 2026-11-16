import React, {useEffect, useState} from 'react';
import type {Api} from './Workflows';

export type Meal = '早餐'|'午餐'|'晚餐'|'加餐';
export type Food = {food:string; amount:string; acceptance:string};
export type ReviewRecord = {id:string; day:string; meal:Meal; items:Food[]; note:string; version:number; member_name:string; created_at?:string; updated_at?:string};
export type ReviewMenu = {id:string; day:string; meal:Meal; title:string; ingredients:string[]; method:string; note:string; version:number};
type Slot = {meal:Meal; menu:ReviewMenu|null; records:ReviewRecord[]; has_records:boolean};
export type ReviewData = {
  start:string; end:string; days:{day:string; meals:Slot[]}[];
  summary:{planned_meals:number; recorded_meals:number; record_count:number; unrecorded_main_meals:number}; note:string;
};
type OpenRecord = (day:string, meal:Meal, entry?:ReviewRecord, menu?:ReviewMenu)=>void;
const shiftDay=(day:string,n:number)=>{
  const date=new Date(day+'T12:00:00+08:00');date.setUTCDate(date.getUTCDate()+n);
  return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
};
const timeLabel=(value:string)=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));

export function ReviewContent({data,onRecord,onReuse}:{data:ReviewData;onRecord:OpenRecord;onReuse?:(menu:ReviewMenu)=>void}){
  return <>
    <p className="review-note">{data.note}</p>
    <div className="review-stats" aria-label="所选范围记录概况">
      <div><b>{data.summary.planned_meals}</b><span>餐有菜单安排</span></div>
      <div><b>{data.summary.recorded_meals}</b><span>餐有进食记录</span></div>
      <div><b>{data.summary.unrecorded_main_meals}</b><span>餐主餐暂无记录</span></div>
    </div>
    {data.days.map(day=><section className="review-day" key={day.day} aria-label={`${day.day}回看`}>
      <h3>{day.day}</h3>
      {day.meals.filter(slot=>slot.meal!=='加餐'||slot.menu||slot.records.length).map(slot=><article className="review-slot" key={slot.meal}>
        <header><h4>{slot.meal}</h4><span className={'review-status '+(slot.has_records?'has-records':'')}>{slot.has_records?'有记录':'尚未记录'}</span></header>
        <div className="review-columns">
          <div className="review-plan"><h5>菜单安排</h5>{slot.menu?<><b>{slot.menu.title}</b><p>{slot.menu.ingredients.join('、')}</p>{slot.menu.method&&<details><summary>查看做法</summary><p>{slot.menu.method}</p>{slot.menu.note&&<p>{slot.menu.note}</p>}</details>}</>:<p className="muted">未安排菜单</p>}</div>
          <div className="review-actual"><h5>实际记录</h5>{slot.records.length?slot.records.map(entry=><div className="review-entry" key={entry.id}>
            <p className="review-source">{entry.member_name}记录{entry.created_at&&<> · {timeLabel(entry.created_at)}录入</>}{entry.version>1&&' · 已更正'}</p>
            {entry.items.map((item,i)=><div className="review-food" key={i}><b>{item.food}</b><span>{item.amount}</span><span className={item.acceptance==='没吃'?'not-eaten':'accepted'}>{item.acceptance}</span></div>)}
            {entry.note&&<p className="record-note">{entry.note}</p>}
            <button className="text-button" onClick={()=>onRecord(day.day,slot.meal,entry)}>更正这条记录</button>
          </div>):<p className="muted">还没有实际进食记录，可补记。</p>}</div>
        </div>
        <div className="review-actions">{slot.menu&&onReuse&&<button className="secondary" onClick={()=>onReuse(slot.menu!)}>复用这餐菜单</button>}<button className="secondary" onClick={()=>onRecord(day.day,slot.meal)}>{slot.has_records?'补充实际记录':'补记这一餐'}</button>{slot.menu&&<button className="text-button" onClick={()=>onRecord(day.day,slot.meal,undefined,slot.menu!)}>参考菜单填写</button>}</div>
      </article>)}
    </section>)}
  </>;
}

export function Review({api,today,revision,onRecord,onReuse}:{api:Api;today:string;revision:number;onRecord:OpenRecord;onReuse?:(menu:ReviewMenu)=>void}){
  const [end,setEnd]=useState(today),[span,setSpan]=useState(7),[data,setData]=useState<ReviewData|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[retry,setRetry]=useState(0);
  const start=shiftDay(end,1-span);
  useEffect(()=>{
    let active=true, requestId=0;
    setLoading(true);setData(null);setError('');
    async function load(){
      const id=++requestId;
      try{const result=await api(`/review?start=${start}&end=${end}`);if(active&&id===requestId){setData(result);setError('')}}
      catch(e){if(active&&id===requestId)setError((e as Error).message)}
      finally{if(active&&id===requestId)setLoading(false)}
    }
    void load();
    const interval=setInterval(()=>{if(!document.hidden)void load()},20000);
    const visible=()=>{if(!document.hidden)void load()};
    document.addEventListener('visibilitychange',visible);
    return()=>{active=false;clearInterval(interval);document.removeEventListener('visibilitychange',visible)};
  },[api,start,end,revision,retry]);
  return <section className="card review-card">
    <div className="section-title"><div><h2>菜单与实际进食</h2><p>按已记录的事实回看，方便下次安排。</p></div></div>
    <div className="review-controls">
      <label>查看范围<select aria-label="查看范围" value={span} onChange={e=>setSpan(Number(e.target.value))}><option value={1}>一天</option><option value={7}>近七天</option></select></label>
      <label>截至日期<input type="date" max={today} value={end} onChange={e=>{if(e.target.value&&e.target.value<=today)setEnd(e.target.value)}}/></label>
      <button className="secondary" onClick={()=>setEnd(shiftDay(end,-span))}>往前{span===1?'一天':'七天'}</button>
      <button className="secondary" disabled={end>=today} onClick={()=>setEnd(shiftDay(end,span)>today?today:shiftDay(end,span))}>往后{span===1?'一天':'七天'}</button>
      <button className="text-button" onClick={()=>{setEnd(today);setRetry(n=>n+1)}}>回到今天并刷新</button>
    </div>
    <p className="review-range">{start===end?end:`${start} — ${end}`} · 可补记，也可更正已有记录</p>
    {loading&&<p role="status">正在读取回看记录…</p>}
    {error&&<div className="error" role="alert">{error}<button className="text-button" onClick={()=>setRetry(n=>n+1)}>重新读取</button></div>}
    {data&&!loading&&!error&&<ReviewContent data={data} onRecord={onRecord} onReuse={onReuse}/>}
  </section>;
}
