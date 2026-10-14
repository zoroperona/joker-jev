const $ = (id) => document.getElementById(id);
const names = {p0:'你',p1:'东篱',p2:'西窗'};
const kinds = {single:'单张',pair:'对子',triple:'三张',triple_single:'三带一',triple_pair:'三带对',straight:'顺子',pair_straight:'连对',airplane:'飞机',airplane_single:'飞机带单',airplane_pair:'飞机带对',four_two_single:'四带二',four_two_pair:'四带两对',bomb:'炸弹',rocket:'王炸',pass:'不出'};
let state, selected = new Set(), busy = false, toastTimer;
function textCard(rank){return rank === 'BJ' ? '大王' : rank === 'SJ' ? '小王' : rank;}
function card(rank, index=0, small=false, interactive=false){
  const el=document.createElement(interactive?'button':'div');
  const joker=rank==='BJ'||rank==='SJ', red=rank==='BJ'||(!joker&&index%2===1);
  el.className=`card ${small?'small':''} ${red?'red':''} ${joker?'joker':''}`;
  // Suits are decorative: the existing engine represents ranks only.
  const symbol=['♠','♥','♣','♦'][index%4];
  el.innerHTML=joker
    ? `<span class="joker-name">${textCard(rank)}</span><span class="joker-seal" aria-hidden="true">✦</span><span class="joker-caption" aria-hidden="true">JOKER</span>`
    : `<span class="corner"><span class="rank">${rank}</span><span class="suit">${symbol}</span></span><span class="pip" aria-hidden="true">${symbol}</span>`;
  if(interactive){el.setAttribute('aria-label',textCard(rank));el.setAttribute('aria-pressed',selected.has(index));el.classList.toggle('selected',selected.has(index));el.disabled=state.auto||state.thinking||!!state.error||state.public.actor!=='p0'||state.public.phase==='finished';el.onclick=()=>{selected.has(index)?selected.delete(index):selected.add(index);renderHand();renderActions();};}
  return el;
}
function showError(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
async function command(command,extra={}){
  if(busy)return;busy=true;
  try{const response=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command,revision:state?.revision,...extra})});const data=await response.json();if(!response.ok)throw Error(data.error);if(command==='hint'){const action=state.actions.find(a=>a.id===data.action_id);selected.clear();if(action?.payload.cards){const remaining=[...action.payload.cards];state.private.hand.forEach((rank,i)=>{const at=remaining.indexOf(rank);if(at>=0){selected.add(i);remaining.splice(at,1);}});}if(action?.id==='pass')showError('建议：本轮不出');else if(action?.id.startsWith('bid:'))showError(`建议：${action.label}`);renderHand();renderActions();}else{selected.clear();render(data);}}
  catch(error){showError(error.message);}finally{busy=false;}
}
function eventText(e){const d=e.data;if(e.kind==='bid')return `${names[d.player]} · ${d.bid?'叫 '+d.bid+' 分':'不叫'}`;if(e.kind==='redeal')return '三家不叫，重新发牌';if(e.kind==='landlord_selected')return `${names[d.landlord]}成为地主 · 底牌 ${d.bottom_cards.map(textCard).join(' ')}`;if(e.kind==='move')return `${names[d.player]} · ${d.cards.length?d.cards.map(textCard).join(' '):'不出'}`;if(e.kind==='free_lead')return `${names[d.player]}获得自由出牌权`;if(e.kind==='game_finished')return `${d.winner===d.landlord?'地主':'农民'}获胜${d.spring?' · 春天':''}`;return '';}
function renderHand(){const hand=$('hand');hand.style.setProperty('--hand-count',state.private.hand.length);hand.replaceChildren(...state.private.hand.map((r,i)=>card(r,i,false,true)));$('selection').textContent=selected.size?`已选 ${selected.size} 张`:'点击手牌选中，再出牌';}
function selectedAction(){const ranks=[...selected].map(i=>state.private.hand[i]).sort().join(',');return state.actions.find(a=>a.payload.cards?.length&&[...a.payload.cards].sort().join(',')===ranks);}
function addButton(label,handler,style='',disabled=false){const b=document.createElement('button');b.className='action '+style;b.textContent=label;b.disabled=disabled;b.onclick=handler;$('actions').append(b);}
function renderActions(){const p=state.public;$('actions').replaceChildren();if(p.phase==='finished'){addButton('再来一局',()=>command('new'),'primary');return;}if(state.auto){addButton('接管牌局',()=>command('mode',{auto:false}),'primary');return;}const myTurn=p.actor==='p0'&&!state.thinking&&!state.error;if(p.phase==='bidding'){for(let i=0;i<=3;i++)addButton(i?`叫 ${i} 分`:'不叫',()=>command('action',{action_id:`bid:${i}`}),i===3?'primary':'secondary',!myTurn||!state.actions.some(a=>a.id===`bid:${i}`));return;}addButton('不出',()=>command('action',{action_id:'pass'}),'secondary',!myTurn||!state.actions.some(a=>a.id==='pass'));addButton('提示',()=>command('hint'),'secondary',!myTurn);addButton('出牌',()=>{const action=selectedAction();if(action)command('action',{action_id:action.id});},'primary',!myTurn||!selectedAction());}
function render(data){
  const configChanged=!state||state.controller!==data.controller||state.jev_mode!==data.jev_mode;
  if(state?.revision!==data.revision)selected.clear();state=data;const p=state.public;
  names.p0=state.auto&&state.controller==='jev'?'JEV':'你';
  $('p0').querySelector('strong').textContent=names.p0;
  if(configChanged){$('controller').value=state.controller||'human';$('jev-mode').value=state.jev_mode||'minimal';}
  $('opponent-name').textContent=state.opponent||'简单 AI';
  $('controller').querySelector('[value=douzero]').textContent=`${state.opponent||'本地 AI'} 托管`;
  $('controller').querySelector('[value=jev]').disabled=!state.jev_available;
  $('jev-note').textContent=state.jev_available?'JEV 会产生 API 调用。应用配置会重开牌局并清零累计积分。':'JEV 尚未配置：在仓库 .env 设置 TYPESAFE_API_KEY 后重启服务。';
  $('ai-error').hidden=!state.error;
  $('ai-error').querySelector('span').textContent=state.error||'';
  updateModeDescription();
  $('connection').textContent='● 牌桌已连接';$('round').textContent=`第 ${String(state.round).padStart(2,'0')} 局`;
  $('bid-score').textContent=p.bid_score||'—';$('multiplier').textContent='×'+p.multiplier;
  $('bottom').replaceChildren();if(p.bottom_cards.length)p.bottom_cards.forEach((r,i)=>$('bottom').append(card(r,i,true)));else for(let i=0;i<3;i++){const c=document.createElement('div');c.className='card small back';c.textContent='◇';$('bottom').append(c);}
  for(const id of ['p0','p1','p2']){
    const el=$(id), active=p.phase!=='finished'&&p.actor===id;
    el.classList.toggle('active',active);
    el.querySelector('.role').textContent=p.landlord?(p.landlord===id?'地主':'农民'):'待定';
    if(id==='p0')continue;
    el.querySelector('.count').textContent=`手牌 ${p.remaining_counts[id]} 张 · 已出 ${p.play_counts[id]} 手`;
    el.querySelector('.backs').innerHTML='<i></i>'.repeat(p.remaining_counts[id]);
    const currentDeal=state.history.slice(state.history.map(e=>e.kind).lastIndexOf('redeal')+1);
    const last=[...currentDeal].reverse().find(e=>(e.kind==='move'||e.kind==='bid')&&e.data.player===id);
    const label=el.querySelector('.last');
    label.classList.toggle('thinking',active);
    label.textContent=active?(p.phase==='bidding'?'正在考虑叫分…':'正在思考出牌…')
      :last?`上次：${eventText(last).split(' · ').slice(1).join(' · ')}`
      :p.phase==='bidding'?'等待叫分':'等待出牌';
  }
  $('hand-count').textContent=`${state.private.hand.length} 张`;
  $('status').textContent=p.phase==='finished'?'本局已结束':`${p.actor==='p0'?'轮到你':names[p.actor]}${p.phase==='bidding'?'叫分':'出牌'}${state.thinking?' · 思考中':state.auto?' · 自动中':''}`;
  $('trick').replaceChildren();if(p.target)p.target.cards.forEach((r,i)=>$('trick').append(card(r,i,true)));
  $('trick-caption').textContent=p.target?`${names[p.owner]} · ${kinds[p.target.kind]||'出牌'}`:p.phase==='bidding'?'叫一声地主，试试手气。':'新一轮 · 自由出牌';
  document.querySelector('.table-mark').hidden=!!p.target;
  $('result').hidden=p.phase!=='finished';if(p.phase==='finished'){const won=state.rewards.p0>0;$('result').innerHTML=`<h2>${won?'这一局，你赢了。':'好牌，留到下一局。'}</h2><p>${state.winner===Number(p.landlord?.slice(1))?'地主':'农民'}获胜${state.spring?' · 春天':''} · ${p.multiplier} 倍</p><p>本局积分 ${state.rewards.p0>0?'+':''}${state.rewards.p0}${state.auto?' · 即将自动开始下一局':''}</p>`;}
  $('auto').setAttribute('aria-pressed',state.auto);$('auto-description').textContent=state.auto?`${state.controller==='jev'?'JEV':'本地 AI'} 正在对局，结算后自动开始下一局`:'开启托管，按当前配置自动对局';
  if(document.activeElement!==$('speed')){const value=String(state.delay);if([...$('speed').options].some(o=>o.value===value))$('speed').value=value;else{$('speed').value='';}}
  $('scores').textContent=`累计积分  你 ${state.totals.p0} / 东篱 ${state.totals.p1} / 西窗 ${state.totals.p2}`;
  $('history').replaceChildren();[...state.history].reverse().forEach((e,i)=>{const li=document.createElement('li');const time=document.createElement('time');time.textContent=String(state.history.length-i).padStart(2,'0');li.append(time,document.createTextNode(eventText(e)));$('history').append(li);});if(!state.history.length)$('history').textContent='牌已洗好，等一声叫分。';renderHand();renderActions();
}
async function poll(){try{const response=await fetch('/api/state');if(!response.ok)throw Error('无法读取牌局');const data=await response.json();if(!busy&&(!state||state.revision<data.revision))render(data);$('connection').textContent='● 牌桌已连接';}catch{ $('connection').textContent='连接中断 · 正在重试';}finally{setTimeout(poll,400);}}
$('auto').onclick=()=>state&&command('mode',{auto:!state.auto});$('speed').onchange=e=>command('speed',{delay:Number(e.target.value)});$('new').onclick=()=>command('new');$('rules-open').onclick=()=>$('rules').showModal();$('rules-close').onclick=()=>$('rules').close();poll();

function updateModeDescription(){
  $('mode-description').textContent=$('jev-mode').value==='assisted'
    ? '辅助信息：精简信息 + 记牌推断、拆牌组数与动作后果。无模拟排名，不强制让牌。'
    : '精简信息：规则、身份、可见局面、完整历史与合法动作。不添加战术建议。';
}
$('jev-mode').onchange=updateModeDescription;
$('ai-config').onsubmit=e=>{e.preventDefault();command('configure',{controller:$('controller').value,jev_mode:$('jev-mode').value});};
$('retry').onclick=()=>command('retry');
