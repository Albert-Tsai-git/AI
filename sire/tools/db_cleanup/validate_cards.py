import json,re,sys,glob,os
sys.stdout.reconfigure(encoding='utf-8')
SP=sys.argv[1]
orig={r['record_id']:r for r in json.load(open(SP+'/kr_all.json',encoding='utf-8'))}
TOK=re.compile(r'`([^`\n]{2,80})`|([A-Za-z]:\\[^\s,;，；)）]+)|(\b\d{3,}[\d.]*\b)|([\w./-]+\.(?:py|js|ts|json|md|ps1|sh|yml|yaml|c|h|tsx|vue))')
req=['scene','steps','verify','pitfalls','files','status']
tot=0;bad_all=[];allids=set();errs=[]
for p in sorted(glob.glob(SP+'/cards_*.json')):
    cards=json.load(open(p,encoding='utf-8')); b=os.path.basename(p)
    ids=[c['id'] for c in cards]
    inp=json.load(open(p.replace('cards_','in_'),encoding='utf-8'))
    exp={r['record_id'] for r in inp['records']}
    if set(ids)!=exp or len(ids)!=len(set(ids)): errs.append((b,'ID覆盖不符',len(exp-set(ids)),len(set(ids)-exp)))
    allids|=set(ids)
    keep={c['id']:c for c in cards if c['action']=='keep'}
    srcs={k:[k] for k in keep}
    for c in cards:
        if c['action']=='merge':
            if c.get('target') not in keep: errs.append((b,'merge目标不存在',c['id']))
            else: srcs[c['target']].append(c['id'])
        if c['action'] not in('keep','merge','drop'): errs.append((b,'action非法',c['id']))
        if c['action']=='drop' and not (c.get('reason') or '').strip(): errs.append((b,'drop无原因',c['id']))
    n=0;bad=[]
    for k,c in keep.items():
        card=c.get('card') if 'card' in c else c
        for f in req:
            v=card.get(f)
            if isinstance(v,list): v=' '.join(map(str,v))
            if not (v or '').strip(): errs.append((b,'字段空',k,f))
        text=' '.join(str(card.get(f,'')) if not isinstance(card.get(f),list) else ' '.join(map(str,card[f])) for f in req+['title','keywords'])
        src=' '.join(orig[i]['body']+' '+orig[i]['title']+' '+(orig[i]['keywords'] or '') for i in srcs[k] if i in orig)
        for m in TOK.finditer(text):
            t=next(g for g in m.groups() if g)
            n+=1
            if t not in src: bad.append((k,t))
    tot+=n; bad_all+=[(b,)+x for x in bad]
    print(b,'cards',len(cards),'keep',len(keep),'tokens',n,'未在原文',len(bad),f'{100*len(bad)/max(n,1):.1f}%')
print('ID覆盖全局',len(allids),'/',len(orig),'缺',len(set(orig)-allids))
print('结构错误',len(errs)); [print(e) for e in errs[:20]]
json.dump(bad_all,open(SP+'/bad_tokens.json','w',encoding='utf-8'),ensure_ascii=False)
