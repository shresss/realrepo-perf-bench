#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from boundary import prepare,publish
parser=argparse.ArgumentParser()
parser.add_argument('stage')
parser.add_argument('--output',default='/logs/verifier')
parser.add_argument('--rc',type=int,default=0)
parser.add_argument('--prepare',action='store_true')
args=parser.parse_args()
if args.prepare:
    prepare(args.stage,args.output)
else:
    result=publish(args.stage,args.output,args.rc)
    print(json.dumps({key:result.get(key) for key in ['task','reason','validity','model_reward']}))
