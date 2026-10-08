"""Independent PDF-observable oracle, standard library only."""
import hashlib,json

def expected(case,size,seed):
    n_pages=4 if case == 'forms' else 2
    order=list(range(n_pages))
    if case == 'reverse': order.reverse()
    pages=[]
    for p in order:
        widgets=[]
        for f in range(size):
            x=40+(f%6)*90; y=700-(f//6)*14%650
            w={'name':f'Feld äöü 日本 {p}-{f}' if case == 'unicode' else f'field_{p}_{f}', 'value':f'amount {(p*37+f)%9999}.{f%100:02d}', 'rect':[x,y,x+85,y+12], 'flags':(f%3)<<12, 'background':[1,1,f%2], 'rotation':(f%4)*90}
            if case == 'override' and p == 0 and f == 0: w={'name':'OVERRIDDEN','value':'updated','rect':[0,0,1,1],'flags':0,'background':[0,1,0],'rotation':0}
            widgets.append(w)
        pages.append({'box':[0,0,612,792],'contents':f'BT /F1 12 Tf 72 740 Td (Invoice {seed} page {p+1} of {n_pages}) Tj ET','widgets':widgets})
    digest=hashlib.sha256(json.dumps(pages,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    return {'pages':len(pages),'widgets':n_pages*size,'digest':digest,'input_unchanged':True,'sample':pages if size<=3 else None}
