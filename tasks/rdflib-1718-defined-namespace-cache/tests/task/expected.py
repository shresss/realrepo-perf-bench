import hashlib
RDF='http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDFS='http://www.w3.org/2000/01/rdf-schema#'
OWL='http://www.w3.org/2002/07/owl#'
def expected(case,size,seed):
    if case=='namespaces':
        return {'terms':[RDF+'type',RDFS+'label',OWL+'Class','http://xmlns.com/foaf/0.1/givenName','http://www.w3.org/ns/shacl#Info',RDF+'_1'],'strict_missing':True,'members':[True,True,False]}
    if case!='closure':raise ValueError(case)
    triples=set()
    for i in range(size):
        c='urn:cls:'+str(seed)+':'+str(i);instance='urn:instance:'+str(i);p='urn:property:'+str(i)
        triples.update([(c,RDF+'type',OWL+'Class'),(c,RDFS+'subClassOf',OWL+'Thing'),(c,OWL+'equivalentClass',c),(c,OWL+'sameAs',c),(OWL+'Nothing',RDFS+'subClassOf',c),(instance,RDF+'type',OWL+'Thing'),(instance,OWL+'sameAs',instance),(p,RDF+'type',OWL+'ObjectProperty'),(p,RDFS+'domain',OWL+'Thing'),(p,RDFS+'range',OWL+'Thing'),(p,RDFS+'subPropertyOf',p),(p,OWL+'equivalentProperty',p),(p,OWL+'sameAs',p)])
        ancestor=i
        while True:
            ac='urn:cls:'+str(seed)+':'+str(ancestor)
            triples.update([(c,RDFS+'subClassOf',ac),(instance,RDF+'type',ac),(p,RDFS+'domain',ac),(p,RDFS+'range',ac)])
            if ancestor==0:break
            ancestor=(ancestor-1)//3
    rows=sorted(triples)
    return {'triples':len(rows),'sha256':hashlib.sha256(repr(rows).encode()).hexdigest(),'original_retained':True}
