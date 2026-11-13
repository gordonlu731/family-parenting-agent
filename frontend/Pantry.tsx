import React,{useEffect,useRef,useState} from 'react';
import type {Api} from './Workflows';
import './pantry.css';

export type StockItem={id?:string;version:number;name:string;quantity:string|null;unit:string;amount_note:string;location:string;kind:string;status:string;confirmed_at?:string;member_name?:string;needs_reconfirmation?:boolean};
const newItem=():StockItem=>({version:0,name:'',quantity:null,unit:'适量',amount_note:'',location:'未说明',kind:'raw',status:'available'});
const requestKey=()=>globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random().toString(36).slice(2)}`;
const timeLabel=(value:string)=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));

export function PantryFields({item,onChange}:{item:StockItem;onChange:(value:StockItem)=>void}){
  function field(name:keyof StockItem,value:string){onChange({...item,[name]:value})}
  return <>
    <label>食材名称<input required value={item.name} maxLength={80} onChange={e=>field('name',e.target.value)} placeholder="例如：番茄"/></label>
    <div className="form-grid">
      <label>存放位置<select aria-label="存放位置" value={item.location} onChange={e=>field('location',e.target.value)}>{['未说明','冷藏','冷冻','常温'].map(v=><option key={v}>{v}</option>)}</select></label>
      <label>类型<select aria-label="类型" value={item.kind} onChange={e=>field('kind',e.target.value)}><option value="raw">原料</option><option value="cooked">已经做好的熟食</option></select></label>
    </div>
    <label>现在是否还有<select aria-label="现在是否还有" value={item.status} onChange={e=>onChange({...item,status:e.target.value,...(e.target.value==='used_up'?{quantity:null,unit:'适量',amount_note:''}:{})})}><option value="available">还有，核对当前余量</option><option value="used_up">已用完 / 这条记录无效</option></select></label>
    {item.status==='available'&&<>
      <div className="form-grid">
        <label>当前总量（可留空）<input type="number" min="0.01" max="100000" step="0.01" value={item.quantity??''} onChange={e=>onChange({...item,quantity:e.target.value||null,unit:e.target.value?(item.unit==='适量'?'克':item.unit):'适量'})}/></label>
        <label>单位<select aria-label="单位" disabled={item.quantity===null} value={item.unit} onChange={e=>onChange({...item,unit:e.target.value,...(e.target.value==='适量'?{quantity:null}:{})})}>{['适量','克','毫升','个','份'].map(v=><option key={v}>{v==='适量'?'数量不确定':v}</option>)}</select></label>
      </div>
      <label>粗略余量说明（可选）<input value={item.amount_note} maxLength={200} onChange={e=>field('amount_note',e.target.value)} placeholder="例如：还剩一点，不需要称重"/></label>
    </>}
  </>;
}

export function Pantry({api,ready,onReady}:{api:Api;ready:boolean;onReady:(value:any)=>void}){
  const[data,setData]=useState<{version:number;items:StockItem[];note:string;reconfirm_days:number}|null>(null),[editing,setEditing]=useState<StockItem|null>(null),[baseVersion,setBaseVersion]=useState(0);
  const[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[reviewed,setReviewed]=useState(false),[showUsed,setShowUsed]=useState(false),[text,setText]=useState(''),[questions,setQuestions]=useState<string[]>([]);
  const key=useRef(requestKey()),aiKey=useRef(requestKey());
  async function load(){setLoading(true);try{setData(await api('/pantry'));setError('')}catch(e){setError((e as Error).message)}finally{setLoading(false)}}
  useEffect(()=>{void load()},[api]);
  function begin(item:StockItem){setEditing(item);setBaseVersion(data?.version??0);setReviewed(false);setError('');key.current=requestKey()}
  function change(item:StockItem){setEditing(item);setReviewed(false);key.current=requestKey()}
  async function save(e:React.FormEvent){
    e.preventDefault();if(!editing||!reviewed)return;setBusy(true);setError('');
    try{
      const{ id,version,name,quantity,unit,amount_note,location,kind,status}=editing;
      await api('/pantry','PUT',{version:baseVersion,items:[{id:id||null,version,name,quantity,unit,amount_note,location,kind,status}],review_confirmed:true},key.current);
      setEditing(null);setReviewed(false);await load();
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function extract(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');setQuestions([]);try{const result=await api('/pantry-proposals','POST',{text},aiKey.current);if(result.proposal)onReady(result.proposal);else setQuestions(result.questions||[])}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <div className="pantry-panel">
    <p className="muted">全家共用一份食材清单。填写现在家里实际总量；买完或用完再更新，不需要记采购流水。</p>
    {loading&&<p role="status">正在读取家里食材…</p>}
    {error&&<div className="error" role="alert">{error}<button type="button" className="text-button" disabled={busy} onClick={()=>{setEditing(null);void load()}}>刷新清单后核对</button></div>}
    {editing?<form onSubmit={save}><fieldset disabled={busy}>
      <PantryFields item={editing} onChange={change}/>
      <label className="check-line"><input type="checkbox" required checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/><span>我已核对，这是家里现在实际的食材情况。</span></label>
      <button className="primary full" disabled={!reviewed||busy}>{busy?'正在更新…':'确认更新，全家可见'}</button>
      <button className="text-button" type="button" onClick={()=>{setEditing(null);setError('')}}>取消填写</button>
    </fieldset></form>:<>
      <div className="pantry-toolbar"><button className="primary" disabled={!data||busy||loading} onClick={()=>begin(newItem())}>添加食材</button><button className="secondary" disabled={busy||loading} onClick={()=>void load()}>刷新清单</button><label><input type="checkbox" checked={showUsed} onChange={e=>setShowUsed(e.target.checked)}/>显示已用完</label></div>
      {data?.items.filter(i=>showUsed||i.status==='available').map(item=><article className="pantry-item" key={item.id}>
        <div><b>{item.name}</b><span>{item.location} · {item.kind==='cooked'?'熟食':'原料'}{item.status==='used_up'?' · 已用完':''}</span></div>
        <p>{item.status==='used_up'?'不计入可用食材':item.quantity!==null?`${Number(item.quantity)} ${item.unit}`:item.amount_note||'余量不确定'}</p>
        {item.quantity!==null&&item.amount_note&&<p>{item.amount_note}</p>}
        <small>{item.member_name} · {item.confirmed_at&&timeLabel(item.confirmed_at)}核对</small>
        {item.status==='available'&&item.needs_reconfirmation&&<p className="warning">记录较久未核对，采购时暂不自动抵扣。</p>}
        <button className="text-button" onClick={()=>begin(item)}>更正 / 确认余量</button>
        {item.status==='available'&&<button className="text-button" onClick={()=>begin({...item,status:'used_up',quantity:null,unit:'适量',amount_note:''})}>记为用完</button>}
      </article>)}
      {data&&!data.items.some(i=>showUsed||i.status==='available')&&<p className="muted">还没有登记可用食材。可以先记名称，数量以后再补充。</p>}
      <form onSubmit={extract} className="pantry-ai"><h3>也可以说一句</h3><label>现在家里还有什么？<textarea rows={3} maxLength={2000} required value={text} onChange={e=>{setText(e.target.value);aiKey.current=requestKey();setQuestions([])}} placeholder="例如：冷藏还有2个番茄，牛肉已经用完了。"/></label>
        {questions.map((q,i)=><p className="warning" key={i}>{q}</p>)}
        <button className="secondary full" disabled={!ready||busy||!text.trim()}>{busy?'正在整理…':'整理为待核对食材草稿'}</button>
        {!ready&&<p className="hint">AI尚未接入，仍可用上方表单维护。</p>}
        <>{error&&<button className="text-button" type="button" disabled={busy} onClick={e=>{aiKey.current=requestKey();void extract(e)}}>重新尝试整理</button>}</>
      </form>
    </>}
    <p className="hint">{data?.note} 熟食不按原料推荐或抵扣。{data&&`超过${data.reconfirm_days}天未核对会提示确认；这不是保质期判断。`}</p>
  </div>;
}

export function ShoppingList({shopping,onPantry,onRefresh}:{shopping:any;onPantry:()=>void;onRefresh:()=>void}){
  if(!shopping)return <p role="status">正在读取采购缺口…</p>;
  const groups=[['need_buy','需要买'],['enough','家里已有足够记录'],['check','需要核对余量或用量']];
  return <div className="shopping-gaps">
    <div className="pantry-toolbar"><button className="secondary" onClick={onPantry}>买完了 / 核对家里食材</button><button className="text-button" onClick={onRefresh}>刷新采购清单</button></div>
    {!shopping?.items?.length&&<p className="muted">发布菜单后，这里显示食材缺口。</p>}
    {groups.map(([category,label])=>{
      const items=shopping?.items?.filter((i:any)=>i.category===category)||[];
      return items.length>0&&<section key={category} className="shopping-group"><h4>{label}</h4>{items.map((item:any,i:number)=><article key={i} className="shopping-gap-item"><b>{item.name}</b><p>{item.buy_quantity!==null?category==='enough'?'已登记余量可覆盖所列用量':`预计补买 ${Number(item.buy_quantity)} ${item.unit}`:'数量待核对'}</p><small>菜单估算：{item.quantity?`${Number(item.quantity)} ${item.unit}`:'未说明'}{item.unknown_count>0?'，含未明确用量':''}{item.available_quantity?` · 可核算库存 ${Number(item.available_quantity)} ${item.unit}`:''}</small>{item.notes?.map((note:string,j:number)=><small key={j}>{note}</small>)}</article>)}</section>;
    })}
    <p className="hint">{shopping?.note}</p>
  </div>;
}
