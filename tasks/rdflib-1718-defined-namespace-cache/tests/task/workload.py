import argparse,hashlib,json,sys

def run(case,size,seed):
    from rdflib import Graph,URIRef
    from rdflib.namespace import RDF,RDFS,OWL,FOAF,SH
    if case=='namespaces':
        missing=False
        try:FOAF['term_that_does_not_exist']
        except AttributeError:missing=True
        return {'terms':[str(RDF.type),str(RDFS.label),str(OWL.Class),str(FOAF.givenName),str(SH.Info),str(RDF['_1'])], 'strict_missing':missing,'members':[str(RDF.type) in RDF,'label' in RDFS,'term_that_does_not_exist' in RDFS]}
    if case!='closure':raise ValueError(case)
    from owlrl import DeductiveClosure,OWLRL_Semantics
    graph=Graph();classes=[URIRef('urn:cls:'+str(seed)+':'+str(i)) for i in range(size)]
    for i,c in enumerate(classes):
        graph.add((c,RDF.type,OWL.Class))
        if i:graph.add((c,RDFS.subClassOf,classes[(i-1)//3]))
        graph.add((URIRef('urn:instance:'+str(i)),RDF.type,c))
        p=URIRef('urn:property:'+str(i));graph.add((p,RDF.type,OWL.ObjectProperty));graph.add((p,RDFS.domain,c));graph.add((p,RDFS.range,c))
    initial=set(graph)
    DeductiveClosure(OWLRL_Semantics).expand(graph)
    # Grade the complete application-vocabulary projection of the closure.
    rows=sorted(tuple(str(v) for v in triple) for triple in graph if any(str(v).startswith('urn:') for v in triple))
    return {'triples':len(rows),'sha256':hashlib.sha256(repr(rows).encode()).hexdigest(),'original_retained':initial.issubset(graph)}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--case',default='closure');ap.add_argument('--size',type=int,default=120);ap.add_argument('--seed',type=int,default=71);a=ap.parse_args();sys.path.insert(0,'/app');print(json.dumps(run(a.case,a.size,a.seed),sort_keys=True))
