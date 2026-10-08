import hashlib
import json

TEXTS=(
    'Résumé du rapport: les données révèlent des changements réguliers à Montréal.\n',
    'Документ содержит описание города, культуры и результатов исследования.\n',
    'この文書には都市の歴史と文化についての説明があります。資料を確認してください。\n',
    '本文记录城市发展与文化研究的数据，内容需要完整保存并正确读取。\n',
)

def expected(case,size,seed):
    if case != 'utf8-documents':
        labels={'empty':None,'ascii':'ascii','utf8-small':'utf-8','utf8-bom':'UTF-8-SIG','utf16le':'UTF-16','utf16be':'UTF-16','utf32le':'UTF-32','utf32be':'UTF-32'}
        confidence=0.0 if case=='empty' else (0.99 if case=='utf8-small' else 1.0)
        return {'result':{'encoding':labels[case],'confidence':confidence,'language':None if case=='empty' else ''},'input_unchanged':True}
    results=[{'encoding':'utf-8','confidence':0.99,'language':''} for _ in range(size)]
    total=sum(300*len((f'Document {n}, section {seed%97}. '+TEXTS[(n+seed)%4]).encode('utf-8')) for n in range(size))
    return {'count':size,'bytes':total,'results':results,'sha256':hashlib.sha256(json.dumps(results,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
