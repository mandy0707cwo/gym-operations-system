"""內嵌CCv2簡表：只有數字／日期，不傳送姓名或私人請假資料。"""
import streamlit as st

JS="""
export default function ({parentElement,data,setTriggerValue}) {
  const root=parentElement.querySelector('#counts-root');
  const scroll=root.scrollLeft; const table=document.createElement('table');
  table.setAttribute('aria-label','核准排班班別人數');
  const head=document.createElement('thead'),top=document.createElement('tr'),bottom=document.createElement('tr');
  const label=document.createElement('th');label.textContent='班別';label.rowSpan=2;label.className='fixed';top.append(label);
  for(const h of data.headers){
    const a=document.createElement('th'),b=document.createElement('th');
    a.textContent=h.day;b.textContent=h.weekday;top.append(a);bottom.append(b);
  }
  head.append(top,bottom);table.append(head);const body=document.createElement('tbody');
  for(const row of data.rows){
    const tr=document.createElement('tr'),title=document.createElement('th');title.textContent=row.label;title.className='fixed';title.scope='row';tr.append(title);
    for(const cell of row.cells){
      const td=document.createElement('td'),button=document.createElement('button');button.type='button';
      button.textContent=cell.text;button.disabled=cell.original===0;
      button.setAttribute('aria-label',`${cell.date} ${row.label} 可用與原排 ${cell.text}`);
      const selected=data.selected?.date===cell.date && data.selected?.group===row.group;
      button.setAttribute('aria-pressed',String(selected));
      if(cell.shortage)button.classList.add('shortage');
      button.onclick=()=>setTriggerValue('clicked',{date:cell.date,group:row.group,context:data.context});
      td.append(button);tr.append(td);
    }
    body.append(tr);
  }
  table.append(body);root.replaceChildren(table);root.scrollLeft=scroll;
}
"""
CSS="""
#counts-root {overflow:auto; max-height:440px; color:var(--st-text-color); font-family:var(--st-font);}
table {border-collapse:separate; border-spacing:0; font-size:inherit; width:max-content;}
th,td {border-right:1px solid var(--st-border-color);border-bottom:1px solid var(--st-border-color);text-align:center;padding:4px;white-space:nowrap;}
thead th {background:var(--st-secondary-background-color); min-width:52px;}
th.fixed {position:sticky;left:0;z-index:1;min-width:72px;background:var(--st-secondary-background-color);}
button {font:inherit;color:inherit;background:transparent;border:1px solid transparent;border-radius:var(--st-button-radius);padding:4px;min-width:48px;cursor:pointer;}
button:hover:not(:disabled),button[aria-pressed=true] {border-color:var(--st-primary-color);}
button:focus-visible {outline:2px solid var(--st-primary-color);}
button:disabled {cursor:default;opacity:.6;}
button.shortage {color:var(--st-red-text-color);}
"""
_COUNTS=st.components.v2.component('schedule_headcount_grid',html='<div id="counts-root" tabindex="0"></div>',js=JS,css=CSS)


def count_grid(result,*,context,selected,key,on_click):
    payload={k:result[k] for k in ('headers','rows')}
    return _COUNTS(data=dict(payload,context=context,selected=selected),key=key,width='stretch',
                   on_clicked_change=on_click).clicked
