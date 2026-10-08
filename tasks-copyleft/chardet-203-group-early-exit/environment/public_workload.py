"""PR203 UTF-8 document ingestion: public whole-document encoding detection."""
import hashlib
import json
import os
import sys

TEXTS=(
    'Résumé du rapport: les données révèlent des changements réguliers à Montréal.\n',
    'Документ содержит описание города, культуры и результатов исследования.\n',
    'この文書には都市の歴史と文化についての説明があります。資料を確認してください。\n',
    '本文记录城市发展与文化研究的数据，内容需要完整保存并正确读取。\n',
)


def run(case,size,seed):
    if case not in ('empty', 'ascii', 'utf8-small', 'utf8-documents'):
        raise ValueError('Unsupported public case')
    source=os.environ.get('AQ_SOURCE')
    if source: sys.path.insert(0,source)
    import chardet
    if case != 'utf8-documents':
        raw = {
            'empty': b'',
            'ascii': (f'Report {seed}: standard ASCII text.\n' * max(1,size)).encode('ascii'),
            'utf8-small': 'Résumé 日本語 中文 Кириллица'.encode('utf-8'),
        }[case]
        before=bytes(raw)
        result=chardet.detect(raw)
        return {'result':result,'input_unchanged':raw == before}
    documents=[]
    for n in range(size):
        body=TEXTS[(n+seed)%len(TEXTS)]
        line=f'Document {n}, section {seed%97}. '+body
        documents.append((line*300).encode('utf-8'))
    if os.environ.get('AQ_FLOOR')=='1':return {'floor':True,'count':size,'bytes':sum(map(len,documents))}
    results=[chardet.detect(document) for document in documents]
    return {'count':size,'bytes':sum(map(len,documents)),'results':results,
            'sha256':hashlib.sha256(json.dumps(results,sort_keys=True,separators=(',',':')).encode()).hexdigest()}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--size',type=int,required=True);p.add_argument('--seed',type=int,required=True)
    args=p.parse_args();print(json.dumps(run(args.case,args.size,args.seed),sort_keys=True))
